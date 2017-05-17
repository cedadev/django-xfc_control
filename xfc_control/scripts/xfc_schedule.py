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

from django.core.mail import send_mail

from xfc_control.models import User, ScheduledDeletion, CachedFile
from xfc_user_lock import lock_user, user_locked, unlock_user

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
    fromaddr = "xfc@ceda.ac.uk"

    # subject
    subject = "[CEDA XFC] - Notification of file deletion"
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
    over_bytes = user.quota_used - user.quota_size

    # get a list of user cached files sorted descending
    cached_files = CachedFile.objects.filter(user=user).order_by('first_seen')
    # sum of files to delete
    sum_delete = 0
    # list of files to delete
    files_to_delete = []

    # get enough files to bring the quota back to its allocated amount
    for cf in cached_files:
        if sum_delete > over_bytes:
            break
        # keep a running total
        sum_delete += cf.size
        # add the files
        files_to_delete.append(cf.path)

    # create the ScheduledDeletion
    sd = ScheduledDeletion()
    sd.user = user
    sd.time_entered = datetime.datetime.utcnow()
    # users have 24 hours to save their files!
    sd.time_delete =  datetime.datetime.utcnow() + datetime.timedelta(hours=ScheduledDeletion.schedule_hours)
    sd.save()
    # deletion files
    sd.delete_files = CachedFile.objects.filter(user=user, path__in=files_to_delete)
    sd.save()

    # send the notification email
    if user.notify:
        send_notification_email(user, files_to_delete, sd.time_delete)


def run():
    """Entry point for the Django script run via ``./manage.py runscript``
    """
    # loop over all the users
    for user in User.objects.all():
        # check if user locked
        if user_locked(user):
            print user.name + " already locked"
            continue
        # lock the user
        lock_user(user)
        # schedule the deletions if the quota used is greater than the quota allocated
        if user.quota_used > user.quota_size:
            schedule_deletions(user)
        # unlock the user
        unlock_user(user)
