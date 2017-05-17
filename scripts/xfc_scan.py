"""Function to scan all the files in all user's directories and add them as
entries to CachedFile.

 This script is designed to be run via the django-extensions runscript command:

  ``python manage.py runscript xfc_scan``
"""

from xfc_control.models import User, CachedFile
from xfc_user_lock import lock_user, user_locked, unlock_user
import datetime
import os

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
                filepath = os.path.join(root, file)
                # get the file info and the current time / date
                try:
                    filesize = os.path.getsize(filepath)
                except os.error:
                    raise "Could not find file with path: " + filepath
                # get the current time
                current_time = datetime.datetime.utcnow()
                # create the CachedFile
                try:
                    cf = CachedFile()
                    cf.user = user
                    cf.cache_disk = user.cache_disk
                    # create the short filepath, that does not include the cache disk mountpoint
                    # ensure trailing slash
                    mp = user.cache_disk.mountpoint
                    if mp[-1] != "/":
                        mp += "/"
                    sh_filepath = filepath.replace(mp,"")
                    cf.path = sh_filepath
                    cf.size = filesize
                    cf.first_seen = current_time
                    # check whether this file already exists
                    current_file = CachedFile.objects.filter(user=user, path=sh_filepath)
                    if len(current_file) == 0:
                        cf.save()
                except:
                    raise "Could not create CachedFile with path: " + filepath


def scan_for_deleted_files(user):
    """Find any files that have been deleted but still exist in the database and
       remove them from the database.
       :var xfc_control.models.User user: instance of User to update
    """
    # loop over all the files
    cached_files = CachedFile.objects.filter(user=user)
    for file in cached_files:
        # get the filepath as the concatenation of the mountpoint and path
        filepath = os.path.join(user.cache_disk.mountpoint, file.path)
        # check whether the file exists
        if not os.path.exists(filepath):
            file.delete()


def calc_user_quota(user):
    """Calculate how much of the user's quota has been used up
       :var xfc_control.models.User user: instance of User to update
    """

    # get all the cached files
    cached_files = CachedFile.objects.filter(user=user)
    quota_sum = 0

    # calculate used
    for file in cached_files:
        quota_sum += file.size
    # update the user and save
    user.quota_used = quota_sum
    user.save()


def update_cache_disk_used_quota(user, amount):
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
    # loop over all the users
    for user in User.objects.all():
        # check if user locked
        if user_locked(user):
            continue
        # lock the user
        lock_user(user)
        # get the current user quota
        current_user_quota = user.quota_used
        # scan the directories
        scan_for_added_files(user)
        # check for any files that have been deleted and remove them from the database
        scan_for_deleted_files(user)
        # calculate the user used_quota
        calc_user_quota(user)
        # add on the new used_quota to the cache_disk_quota
        update_cache_disk_used_quota(user, user.quota_used-current_user_quota)
        # unlock the user
        unlock_user(user)