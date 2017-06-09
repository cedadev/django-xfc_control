"""Function to scan all the files in all user's directories and add them as
entries to CachedFile.

 This script is designed to be run via the django-extensions runscript command:

  ``python manage.py runscript xfc_scan``
"""

from xfc_control.models import User, CachedFile
from xfc_user_lock import lock_user, user_locked, unlock_user
import datetime
import calendar
import os
import logging
import xfc_control.settings as settings


def setup_logging(module_name):
    # setup the logging
    try:
        log_path = settings.LOG_PATH
    except:
        log_path = "./"

    date = datetime.datetime.utcnow()
    date_string = "%d%02i%02i" % (date.year, date.month, date.day)
    log_fname = log_path + "/" + module_name+ "_" + date_string

    logging.basicConfig(filename=log_fname, level=logging.DEBUG)


def get_log_time_string():
    current_time = datetime.datetime.utcnow()
    current_time_string = "%02i %s %d %02d:%02d.%02d" % (
        current_time.day, calendar.month_abbr[current_time.month], current_time.year, current_time.hour,
        current_time.minute, current_time.second)
    return current_time_string


def scan_for_added_files(user):
    """Scan the user directory and add the files as CachedFile objects.
       :var xfc_control.models.User user: instance of User to scan
    """

    # get the user directory
    user_dir = os.path.join(user.cache_disk.mountpoint, user.cache_path)
    # walk the directory
    user_file_list = os.walk(user_dir, followlinks=True)
    for root, dirs, files in user_file_list:
        # if the files is not an empty list then add the files to the user's files
        if len(files) != 0:
            for file in files:
                # get the current time
                current_time_string = get_log_time_string()
                filepath = os.path.join(root, file)
                # get the file info and the current time / date
                try:
                    filesize = os.path.getsize(filepath)
                except os.error:
                    logging.error("[" + current_time_string + "] Could not find file with path: " + filepath)
                    continue
                try:
                    # create the short filepath, that does not include the cache disk mountpoint
                    # ensure trailing slash
                    mp = user.cache_disk.mountpoint
                    if mp[-1] != "/":
                        mp += "/"
                    sh_filepath = filepath.replace(mp,"")
                    # check whether this file already exists
                    current_file = CachedFile.objects.filter(user=user, path=sh_filepath)
                    if len(current_file) == 0:
                        logging.info("[" + current_time_string + "] Adding file: " + filepath)
                        # create the CachedFile
                        cf = CachedFile()
                        cf.user = user
                        cf.cache_disk = user.cache_disk
                        cf.path = sh_filepath
                        cf.size = filesize
                        cf.first_seen = datetime.datetime.utcnow()
                        cf.save()
                    elif current_file[0].size != filesize:
                        # check whether this file's size has changed
                        logging.info("[" + current_time_string + "] File size changed: " + filepath)
                        current_file[0].size = filesize
                        current_file[0].save()
                except:
                    logging.error("[" + current_time_string + "] Could not create CachedFile with path: " + filepath)


def scan_for_deleted_files(user):
    """Find any files that have been deleted but still exist in the database and
       remove them from the database.
       :var xfc_control.models.User user: instance of User to update
    """
    # loop over all the files
    cached_files = CachedFile.objects.filter(user=user)
    for file in cached_files:

        current_time = datetime.datetime.utcnow()
        current_time_string = "%02i %s %d %02d:%02d.%02d" % (
            current_time.day, calendar.month_abbr[current_time.month], current_time.year, current_time.hour,
            current_time.minute, current_time.second)

        # get the filepath as the concatenation of the mountpoint and path
        filepath = os.path.join(user.cache_disk.mountpoint, file.path)
        # check whether the file exists
        if not os.path.exists(filepath):
            logging.info("[" + current_time_string + "] Deleting file: " + filepath)
            file.delete()


def calc_user_quota(user):
    """Calculate how much of the user's quota has been used up.
       The quota is in bytes day - so the algorithm is::

          nfiles
          sum(current_date - file(n).date_first_seen)*file(n).size
          n=0

       :var xfc_control.models.User user: instance of User to update
    """

    # get all the cached files
    cached_files = CachedFile.objects.filter(user=user)
    quota_sum = 0

    # calculate used
    for file in cached_files:
        # get the time delta in days - add one so that the quota is used on the first day the file was seen
        quota_sum += file.quota_use()
    # update the user and save
    user.quota_used = quota_sum
    user.save()


def calc_user_used_space(user):
    """Calculate how much space on the cache disk the user has used.
       This is different to the quota as there is no temporal element to this number
       :var xfc_control.models.User user: instance of User to calculate
    """
    # get all the cached files
    cached_files = CachedFile.objects.filter(user=user)
    sum = 0

    # calculate used
    for file in cached_files:
        sum += file.size
    user.total_used = sum
    user.save()


def update_cache_disk_used_space(user, amount):
    """Update the CacheDisk used quota for the current user
       :var User user: user whose CacheDisk we are modifying
       :var amount int: number of bytes (positive or negative) to update b
    """
    # get the cache disk
    cd = user.cache_disk
    # update the amount and save
    cd.used_bytes += amount
    cd.save()


def run():
    """Entry point for the Django script run via ``./manage.py runscript``
    """
    setup_logging(__name__)

    # loop over all the users
    for user in User.objects.all():
        # check if user locked
        if user_locked(user):
            logging.info("[" + get_log_time_string() + "] User already locked: " + user.name)
            continue
        # lock the user
        lock_user(user)
        # get the current user quota
        old_user_used_space = user.total_used
        # scan the directories
        scan_for_added_files(user)
        # check for any files that have been deleted and remove them from the database
        scan_for_deleted_files(user)
        # calculate the user used_quota
        calc_user_quota(user)
        # calculate the total space used
        calc_user_used_space(user)
        # adjust the used space in the cache_disk
        update_cache_disk_used_space(user, user.total_used-old_user_used_space)
        # unlock the user
        unlock_user(user)