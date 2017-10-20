"""Function to fix the quotas for the Users and the CachedDisks

 This script is designed to be run via the django-extensions runscript command:

  ``python manage.py runscript xfc_scan``
"""

from xfc_control.models import User, CacheDisk, CachedFile
from xfc_control.scripts.xfc_scan import calc_user_quota
import os

def fix_user_quotas():
    """Fix each user quota in turn by interrogating how much space is used for each
    file owned by the user."""
    # get the users in turn
    for user in User.objects.all():
        calc_user_quota(user)


def fix_cache_disk_quotas():
    # for each cache disk, get the files
    for cd in CacheDisk.objects.all():
        cache_disk_sum = 0
        # get the users using this cache disk
        users = User.objects.filter(cache_disk=cd)
        # for each user get their files
        for user in users:
            files = CachedFile.objects.filter(user=user)
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
