"""Function to schedule deletion of some user files after a notification period has been served.

   If the  modification date on the files is updated (ahead of deletion entry), then the deletion
   will not take place.  This allows users to touch files to keep them.

   However, the scheduling algorithm is relentless - it will simply schedule some other files to
   be deleted.

   This script is designed to be run via the django-extensions runscript command:

      ``python manage.py runscript xfc_scan``
"""

import datetime, calendar
import os
import logging

from django.core.mail import send_mail

from xfc_control.models import User, ScheduledDeletion, CachedFile
from xfc_control.scripts.xfc_user_lock import lock_user, user_locked, unlock_user
from xfc_control.scripts.xfc_scan import setup_logging, get_log_time_string
import xfc_site.settings as settings


def send_notification_email(user, file_list, date):
    """Send an email to the user to notify which files will be deleted and when
    :var xfc_control.models.User user: user to send notification email to
    """
    if not user.notify:
        return

    if len(file_list) == 0:
        return

    # to address is notify_on_first
    toaddrs = [user.email]
    # from address is just a dummy address
    fromaddr = "support@ceda.ac.uk"

    # subject
    subject = "[XFC] - Notification of file deletion"
    date_string = "% 2i %s %d %02d:%02d" % (date.day, calendar.month_abbr[date.month], date.year, date.hour, date.minute)

    msg = "The following files will be deleted from the transfer cache (XFC) on" + date_string + " UTC\n\n"
    for f in file_list:
        msg += os.path.join(user.cache_disk.mountpoint, f) + "\n"

    send_mail(subject, msg, fromaddr, toaddrs, fail_silently=False)


def schedule_deletions(user):
    """Make entries of ScheduledDeletion(s) into the database
    :var xfc_control.models.User user: user to schedule deletions for
    """

    # Check whether the user has a deletion pending
    user_sd = ScheduledDeletion.objects.filter(user=user)
    if len(user_sd) != 0:
        return

    # determine how many bytes we have to recover
    over_quota = user.quota_used - user.quota_size
    over_limit = user.total_used - user.hard_limit_size

    # get a list of user cached files sorted descending
    cached_files = CachedFile.objects.filter(user=user).order_by('first_seen')
    # sum of files to delete
    quota_delete = 0
    hard_delete  = 0
    # list of files to delete
    files_to_delete = []

    # we need the current time / date for various things
    current_date = datetime.datetime.utcnow()

    # get enough files to bring the quota back to its allocated amount
    # need to use the quota formula described in xfc_scan.calc_user_quota
    # get the current date
    for cf in cached_files:
        # determine how old this file is in days
        file_age = (current_date - cf.first_seen).days
        # the over_quota and over_limit could be negative, if the user is not
        # over their quota limit or hard limit
        # also check the file age, to check it's not over the MAX_PERSISTENCE
        if quota_delete > over_quota and hard_delete > over_limit and file_age < settings.XFC_DEFAULT_MAX_PERSISTENCE:
            continue
        # keep a running total
        quota_delete += cf.quota_use()
        hard_delete += cf.size
        # add the files
        files_to_delete.append(cf.path)

    # don't do anything if no files found
    if len(files_to_delete) == 0:
        return

    # create the ScheduledDeletion
    sd = ScheduledDeletion()
    sd.user = user
    sd.time_entered = current_date
    # users have 24 hours to save their files!
    sd.time_delete = current_date + datetime.timedelta(hours=ScheduledDeletion.schedule_hours)
    sd.save()
    # deletion files
    sd.delete_files = CachedFile.objects.filter(user=user, path__in=files_to_delete)
    sd.save()

    # send the notification email
    if user.notify:
        send_notification_email(user, files_to_delete, sd.time_delete)

    # send to the logger
    current_time_string = get_log_time_string()
    schedule_time_string =  "%02i %s %d %02d:%02d" % \
        (sd.time_delete.day, calendar.month_abbr[sd.time_delete.month], sd.time_delete.year,
         sd.time_delete.hour, sd.time_delete.minute)

    logging.info("[" + current_time_string + "] Scheduling files for deletion on: " + schedule_time_string)
    for f in files_to_delete:
        logging.info("    " + os.path.join(user.cache_disk.mountpoint, f))


def run():
    """Entry point for the Django script run via ``./manage.py runscript``
    """
    setup_logging(__name__)
    # loop over all the users
    for user in User.objects.all():
        # check if user locked
        if user_locked(user):
            continue
        # lock the user
        lock_user(user)
        # schedule the deletions, there are three possibilities for files to be deleted:
        # 1. the user's quota has been exceeded
        # 2. the user's hard limit has been exceeded
        # 3. some user's files are greater than the maximum persistence
        schedule_deletions(user)
        # unlock the user
        unlock_user(user)
