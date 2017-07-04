# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models

from sizefield.models import FileSizeField
from sizefield.utils import filesizeformat
import os, sys
import subprocess
import datetime
import calendar
import settings


class CacheDisk(models.Model):
    """Allocated area(s) of disk(s) to hold cached files.  Users will be allocated space
    on a disk, depending on their quota and which disk has free space.

    :var models.CharField mountpoint: the path to the cache area
    :var FileSizeField size_bytes: amount of space on the disk allocated to users
    :var FileSizeField allocated_bytes: number of bytes allocated to users via their quotas
    :var FileSizeField used_bytes: amount of space that has been used in the cache area
    """

    mountpoint = models.CharField(blank=True, max_length=1024, help_text="Root directory of cache area", unique=True)
    size_bytes = FileSizeField(default=0,
                               help_text="Maximum size on the disk that can be allocated to the cache area")
    allocated_bytes = FileSizeField(default=0,
                                    help_text="Amount of space allocated to users")
    used_bytes = FileSizeField(default=0,
                               help_text="Used value calculated by update daemon")
    def __unicode__(self):
        return "%s" % self.mountpoint

    def formatted_used(self):
        return filesizeformat(self.used_bytes)
    formatted_used.short_description = "used"

    def formatted_allocated(self):
        return filesizeformat(self.allocated_bytes)
    formatted_allocated.short_description = "allocated"

    def formatted_size(self):
        return filesizeformat(self.size_bytes)
    formatted_size.short_description = "total size"

    @staticmethod
    def find_free_cache_disk(requested_bytes):
        """Find a CacheDisk with enough free (unallocated) space to store the user's quota.
        If the mountpoint of the CacheDisk does not exist then it will be created.

        :var int requested_bytes: amount of space requested for the user's allocated quota
        """
        free_cd = None
        for cd in CacheDisk.objects.all():
            if (cd.size_bytes - cd.used_bytes) > requested_bytes:
                free_cd = cd
                break
        # if the free_cd root path does not exist then create it
        if free_cd:
            if not os.path.exists(cd.mountpoint):
                os.makedirs(cd.mountpoint)
        return free_cd

    def create_user_cache_path(self, username):
        """Create the path to the user's cache.
        :var string username: name of the user to create.
        """
        # concatenate the mountpoint and the user_cache area
        cache_path = os.path.join(self.mountpoint, "user_cache")
        user_path = os.path.join("user_cache", username)
        # concatenate the user_cache and the relative userpath
        total_path = os.path.join(self.mountpoint, user_path)

        # create the cache area for all users
        if not os.path.exists(cache_path):
            os.makedirs(cache_path, mode=0o755)

        # create the cache area for the user
        if not os.path.exists(total_path):
            os.makedirs(total_path, mode=0o700)

            # transfer ownership to the user
            groupname = "users"
            # have to use subprocess to do as sudo
            subprocess.call(["/usr/bin/sudo", "/bin/chown", username+":"+groupname, total_path])

        # return just the user path - will facilitate moving entire user directories to a new cache disk
        return user_path


class User(models.Model):
    """User of the transfer cache disk(s).  Users will be allocated space on a CacheDisk
    depending on which CacheDisk has free space.
    :var models.CharField name: the user name / id of the user
    :var models.EmailField email: email address of the user
    :var FileSizeField quota_size: total quota amount
    :var FileSizeField quota_used: total quota amount used
    :var models.CharField cache_path: path to the user's cache area AFTER the CacheDisk mountpoint
    :var models.ForeignKey cache_disk: the CacheDisk the user is allocated
    """

    name = models.CharField(max_length=254, help_text="Name of user - should be same as JASMIN user name")
    email = models.EmailField(max_length=254, help_text="Email of user")
    notify = models.BooleanField(default=False, help_text="Switch notifications on / off")
    quota_size = FileSizeField(default=0, help_text="Size of quota allocated to user, in (bytes day)")
    quota_used = FileSizeField(default=0, help_text="Size of quota allocated to user, in (bytes day)")
    hard_limit_size = FileSizeField(default=0,
                                    help_text="Upper limit allocated to user, in bytes. This limit cannot be exceeded.")
    total_used = FileSizeField(default=0, help_text="Total size of all files owned by the user.")

    cache_path = models.CharField(max_length=2024, help_text="Relative path to cache area")
    cache_disk = models.ForeignKey(CacheDisk, help_text="Cache disk allocated to the user")

    def __unicode__(self):
        return "%s (%s / %s)" % (self.name, filesizeformat(self.quota_used), filesizeformat(self.quota_size))

    def formatted_used(self):
        return filesizeformat(self.quota_used)
    formatted_used.short_description = "quota_used"

    def formatted_size(self):
        return filesizeformat(self.quota_size)
    formatted_size.short_description = "allocated"

    def formatted_hard_limit(self):
        return filesizeformat(self.hard_limit_size)
    formatted_hard_limit.short_description = "hard_limit"

    def formatted_total_used(self):
        return filesizeformat(self.total_used)
    formatted_total_used.short_description = "total_used"

    @staticmethod
    def get_quota_size():
        """Get the initial size of the quota for the user.  This could be algorithmically
           determined, but at the moment is just fixed at 2GB."""
        qs = settings.DEFAULT_QUOTA_SIZE
        return qs

    @staticmethod
    def get_hard_limit_size():
        """Get the initial size of the hard limit for the user.  This could be algorithmically
           determined, but at the moment is just fixed at 2GB."""
        qs = settings.DEFAULT_HARD_LIMIT
        return qs


class UserLock(models.Model):
    """Entry to lock a user's cache directory.  This allows multiple instances of the management
    scripts to run without any errors due to the scripts acting on the same directory when (for
    example) listing the directory and deleting files.
    :var models.ForeignKey user_lock: the user id that is currently locked
    """

    user_lock = models.ForeignKey(User, blank=True, help_text="User that is locked")


class CachedFile(models.Model):
    """Description of a cached file.  These files are added by the xfc_scan.py Daemon.

    :var models.CharField path: path to the file AFTER the User mountpoint
    :var FileSizeField size: size of the file
    :var models.DateTimeField first_seen: time the file was first scanned by the cache_manager Daemon
    :var models.ForeignKey user: the user that the file belongs to
    """

    path = models.CharField(max_length=2024, help_text="Relative path to the file")
    size = FileSizeField(default=0, help_text="Size of the file")
    first_seen = models.DateTimeField(blank=True, null=True,
                                      help_text="Date the file was first scanned by the cache_manager")
    user = models.ForeignKey(User, help_text="User that owns the file", null=True)

    def formatted_size(self):
        return filesizeformat(self.size)

    def full_path(self):
        return os.path.join(self.user.cache_disk.mountpoint, self.path)

    def __unicode__(self):
        d = self.first_seen
        return "%s (%s) (%02d %s %04d %02d:%02d)" % (
          os.path.join(self.user.cache_disk.mountpoint, self.path), filesizeformat(self.size),
                       d.day, calendar.month_abbr[d.month], d.year, d.hour, d.minute)

    def quota_use(self):
        """Get the amount of quota the file will use up"""
        current_date = datetime.datetime.utcnow()
        days_persistent = (current_date - self.first_seen).days + 1
        use = self.size * days_persistent
        return use


class ScheduledDeletion(models.Model):
    """Description of the deletion of a file which will take place in the future.
    The date the deletion was entered into the schedule is kept so that the user can touch the files, whereupon
    they will be newer than this date.  This indicates to xfc_delete not to delete the file, as the user wishes
    to keep them.  However, xfc_schedule will then just schedule another file to be deleted.

    :var models.DateTimeField time_entered: time the ScheduledDeletion was entered into the db
    :var models.DateTimeField time_delete:  time the ScheduledDeletion will take place
    :var models.ForeignKey user: user that the ScheduledDeletion will target
    """

    schedule_hours = 24  # number of hours before file is deleted

    time_entered = models.DateTimeField(blank=True, null=True,
                                        help_text="Date the deletion was entered into the scheduler")
    time_delete  = models.DateTimeField(blank=True, null=True, help_text="Time the deletion will take place")
    user = models.ForeignKey(User, help_text="User that the ScheduledDeletion belongs to")
    delete_files = models.ManyToManyField(CachedFile, default=None,
                                          help_text="The list of files to be deleted in this schedule")

    def __unicode__(self):
        return "%s" % self.user.name
