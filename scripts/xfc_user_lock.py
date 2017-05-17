"""Functions to check whether a user directory is locked or available.
User directories are locked when one of the 3 scripts / daemons runs:
  1. xfc_scan - scans the user directories and updates cached files
  2. xfc_schedule - looks at user quotas and produces a list of files that are scheduled for deletion
  3. xfc_delete - looks at the list of scheduled deletions and deletes files
"""

from xfc_control.models import UserLock, User


def user_locked(user):
    """Check whether the user is already locked.
    :var xfc_control.models.User user: instance of User to check"""
    existing_lock = UserLock.objects.filter(user_lock=user)
    return len(existing_lock) != 0


def lock_user(user):
    """Lock the user by getting the User instance by querying on the user
    and adding an entry to UserLock.
    :var xfc_control.models.User user: instance of User to lock"""
    # check whether the user is already locked
    existing_lock = UserLock.objects.filter(user_lock=user)
    if len(existing_lock) == 0:
        # does not exist so create a lock
        lock = UserLock(user_lock=user)
        lock.save()


def unlock_user(user):
    """Unlock the user.
    :var xfc_control.models.User user: instance of User to unlock"""
    # check whether the user is already locked
    try:
        existing_lock = UserLock.objects.get(user_lock=user)
        # lock found so delete
        existing_lock.delete()
    except UserLock.DoesNotExist:
        pass
