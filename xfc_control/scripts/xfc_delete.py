"""Function to delete files in the ScheduledDeletions after the notification period has been served.

   If the  modification date on the files is updated (ahead of deletion entry), then the deletion
   will not take place.  This allows users to touch files to keep them.

   However, the scheduling algorithm is relentless - it will simply schedule some other files to
   be deleted.

   This script is designed to be run via the django-extensions runscript command:

      ``python manage.py runscript xfc_delete``
"""
import datetime, calendar
import os
import logging

from django.core.mail import send_mail

from xfc_control.models import User, CachedFile, ScheduledDeletion
from xfc_control.scripts.xfc_user_lock import lock_user, user_locked, unlock_user
from xfc_control.scripts.xfc_scan import update_cache_disk_used_space, calc_user_quota, calc_user_used_space
from xfc_control.scripts.xfc_scan import setup_logging, get_log_time_string


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
    subject = "[XFC] - Files deleted"
    date_string = "% 2i %s %d %02d:%02d" % (date.day, calendar.month_abbr[date.month], date.year, date.hour, date.minute)

    msg = "The following files have been deleted on " + date_string + " UTC\n\n"
    for f in file_list:
        msg += os.path.join(user.cache_disk.mountpoint, f.path) + "\n"

    send_mail(subject, msg, fromaddr, toaddrs, fail_silently=False)


def do_deletions(user):
    """Delete files from the ScheduledDeletions
    :var User user: user to perform deletions for
    """
    # get the scheduled deletion(s) that have a schedule time less than the current time
    # there should only be one (due to the user locking but we'll assume there may be more
    scheduled_deletions = ScheduledDeletion.objects.filter(user=user, time_delete__lt=datetime.datetime.utcnow())

    # keep a list of files to delete, as those with newer date will not be deleted
    files_to_delete = []

    # loop over them all
    for sd in scheduled_deletions:
        # loop over all the files
        for file in sd.delete_files.all():
            # get the filepath
            filepath = os.path.join(user.cache_disk.mountpoint, file.path)
            log_time = get_log_time_string()
            try:
                # get the time from the file
                file_date = datetime.datetime.fromtimestamp(os.stat(filepath).st_mtime)
                # check file_date against time_entered - anything newer will not be deleted
                if file_date < sd.time_entered:
                    files_to_delete.append(file)
            except:
                logging.error("[" + log_time + "] Could not get information about file: " + filepath)

    # There are five things to do when deleting the file:
    # 1. Update the user's quota, subtracting the amount used
    # 2. Update the CacheDisk that the user's files reside on
    # 3. Remove the CachedFile from the database
    # 4. Unlink the CachedFile on the disk
    # 5. Remove the scheduled deletions

    # get the number of bytes used on the cache disk by the user
    old_user_used_space = user.total_used
    # Delete the files and remove from the database
    for file in files_to_delete:
        try:
            # get the filepath
            filepath = os.path.join(user.cache_disk.mountpoint, file.path)
            os.unlink(filepath)
        except:
            logging.error("[" + log_time + "] Could not delete the file: " + filepath)
        else:
            # remove the file from the database
            logging.info("[" + log_time + "] Deleted file: " + filepath)
            file.delete()

    # Update the user quota
    calc_user_quota(user)
    # Update the disk quota
    calc_user_used_space(user)
    update_cache_disk_used_space(user, user.total_used-old_user_used_space)

    # remove the scheduled deletions
    for sd in scheduled_deletions:
        sd.delete()

    # send email if notifications on
    if user.notify:
        send_notification_email(user, files_to_delete, datetime.datetime.utcnow())

def run():
    setup_logging(__name__)

    for user in User.objects.all():
        # check if user locked
        if user_locked(user):
            continue
        # lock the user
        lock_user(user)
        # schedule the deletions if the quota used is greater than the quota allocated
        if user.quota_used > user.quota_size or user.total_used > user.hard_limit_size:
            do_deletions(user)
        # unlock the user
        unlock_user(user)
