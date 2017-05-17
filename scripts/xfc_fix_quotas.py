"""Function to fix the quotas for the Users and the CachedDisks

 This script is designed to be run via the django-extensions runscript command:

  ``python manage.py runscript xfc_scan``
"""

from xfc_control.models import User, CacheDisk, CachedFile
import os

def fix_user_quotas():
    """Fix each user quota in turn by interrogating how much space is used for each
    file owned by the user."""
    # get the users in turn
    for user in User.objects.all():
        user_file_sum = 0
        # get each file the user owns
        files = CachedFile.objects.filter(user=user)
        # calculate the total
        for file in files:
            user_file_sum += file.size
        # reassign and save
        user.quota_used = user_file_sum
        user.save()


def fix_cache_disk_quotas():
    # for each cache disk, get the files
    for cd in CacheDisk.objects.all():
        cache_disk_sum = 0
        # get each file on each disk
        files = CachedFile.objects.filter(cache_disk=cd)
        # calculate the total
        for file in files:
            file_path = os.path.join(cd.mountpoint, file.path)
            cache_disk_sum += file.size
        # reassign and save
        cd.used_bytes = cache_disk_sum
        cd.save()


def run():
    fix_user_quotas()
    fix_cache_disk_quotas()