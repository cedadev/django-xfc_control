"""Function to fix the quotas for the Users and the CachedDisks

 This script is designed to be run via the django-extensions runscript command:

  ``python manage.py runscript xfc_scan``

Author: Neil Massey
"""

from xfc_control.models import User, CacheDisk
from xfc_process_scan import update_user_quota, update_cache_disk_quota
import os


def fix_user_quotas():
    """Fix each user quota in turn by interrogating how much space is used for each
    file owned by the user."""
    # get the users in turn
    for user in User.objects.all():
        update_user_quota(user)


def fix_cache_disk_quotas():
    # for each cache disk, get the files
    for cd in CacheDisk.objects.all():
        update_cache_disk_quota(cd)


def run():
    fix_user_quotas()
    fix_cache_disk_quotas()
