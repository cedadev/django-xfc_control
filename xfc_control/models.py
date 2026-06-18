# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from django.conf import settings as django_settings

from sizefield.models import FileSizeField
from sizefield.utils import filesizeformat

from jasmin_ldap.core import *
from jasmin_ldap.query import *

import os, sys
import subprocess
import datetime
import calendar
import xfc_site.settings as settings


class CacheDisk(models.Model):
    """Allocated area(s) of disk(s) to hold cached files.  Users will be allocated space
    on a disk, depending on their quota and which disk has free space.

    :var models.CharField mountpoint: the path to the cache area
    :var FileSizeField size_bytes: amount of space on the disk allocated to users
    :var FileSizeField allocated_bytes: number of bytes allocated to users via their quotas
    :var FileSizeField used_bytes: amount of space that has been used in the cache area
    """

    mountpoint = models.CharField(
        blank=True,
        max_length=1024,
        help_text="Root directory of cache area",
        unique=True,
    )
    size_bytes = FileSizeField(
        default=0,
        help_text="Maximum size on the disk that can be allocated to the cache area",
    )
    allocated_bytes = FileSizeField(
        default=0, help_text="Amount of space allocated to users"
    )
    used_bytes = FileSizeField(
        default=0, help_text="Used value calculated by update daemon"
    )

    def __str__(self):
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
        """Find a CacheDisk with the most free (unallocated) space to store the user's quota.
        If the mountpoint of the CacheDisk does not exist then it will be created.

        :var int requested_bytes: amount of space requested for the user's allocated quota
        """
        free_cd = None
        free_bytes = 0
        for cd in CacheDisk.objects.all():
            if (cd.size_bytes - cd.used_bytes) > free_bytes:
                free_cd = cd
                free_bytes = cd.size_bytes - cd.used_bytes

        # if the free_cd root path does not exist then create it
        if free_cd:
            if not os.path.exists(cd.mountpoint):
                # have to use subprocess to do as sudo
                subprocess.call(["/usr/bin/sudo", "/bin/mkdir", "-p", cd.mountpoint])
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
            # have to use subprocess to do as sudo
            subprocess.call(
                ["/usr/bin/sudo", "/bin/mkdir", "-p", cache_path, "-m", "755"]
            )

        # create the cache area for the user
        if not os.path.exists(total_path):
            # transfer ownership to the user - first we have to get the numeric uid and gid from the ldap server
            servers = ServerPool(settings.XFC_LDAP_PRIMARY, settings.XFC_LDAP_REPLICAS)
            with Connection.create(servers) as conn:
                # form the query
                query = Query(conn, base_dn=settings.XFC_LDAP_BASE_USER).filter(
                    uid=username
                )
                # check for a valid return
                if len(query) == 0:
                    raise Exception(
                        "Username: {} not found from LDAP in create_user_cache_path".format(
                            username
                        )
                    )

                # use just the first returned result
                q = query[0]
                # # check that the keys exist in q
                if not ("uidNumber" in q and "gidNumber" in q):
                    raise Exception(
                        "uidNumber and / or gidNumber not in returned LDAP query for user {}".format(
                            username
                        )
                    )

                # Only create the directory if the user exists in LDAP.  Have to use subprocess to do as sudo
                subprocess.call(
                    ["/usr/bin/sudo", "/bin/mkdir", "-p", total_path, "-m", "700"]
                )

                # form the user:group string
                uidgid = str(q["uidNumber"][0]) + ":" + str(q["gidNumber"][0])
                # have to use subprocess to do as sudo
                subprocess.call(
                    ["/usr/bin/sudo", "/bin/chown", "-R", uidgid, total_path]
                )

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

    name = models.CharField(
        max_length=254, help_text="Name of user - should be same as JASMIN user name"
    )
    email = models.EmailField(max_length=254, help_text="Email of user")
    notify = models.BooleanField(
        default=False, help_text="Switch notifications on / off"
    )
    quota_size = FileSizeField(
        default=0, help_text="Size of quota allocated to user, in (bytes day)"
    )
    quota_used = FileSizeField(
        default=0, help_text="Size of quota allocated to user, in (bytes day)"
    )
    hard_limit_size = FileSizeField(
        default=0,
        help_text="Upper limit allocated to user, in bytes. This limit cannot be exceeded.",
    )
    total_used = FileSizeField(
        default=0, help_text="Total size of all files owned by the user."
    )

    cache_path = models.CharField(
        max_length=2024, help_text="Relative path to cache area"
    )
    cache_disk = models.ForeignKey(
        CacheDisk,
        help_text="Cache disk allocated to the user",
        on_delete=models.CASCADE,
    )
    last_scanned = models.DateTimeField(
        default=datetime.datetime(1900, 1, 1),
        help_text="The last time the user's work directory was scanned",
    )

    def __str__(self):
        return "%s (%s / %s)" % (
            self.name,
            filesizeformat(self.quota_used),
            filesizeformat(self.quota_size),
        )

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
        qs = settings.XFC_DEFAULT_QUOTA_SIZE
        return qs

    @staticmethod
    def get_hard_limit_size():
        """Get the initial size of the hard limit for the user.  This could be algorithmically
        determined, but at the moment is just fixed at 2GB."""
        qs = settings.XFC_DEFAULT_HARD_LIMIT
        return qs


class CachedDirectoryScan(models.Model):
    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="directory_scans",
    )

    dir_name = models.TextField()
    scan_time = models.DateTimeField()
    dir_mtime = models.DateTimeField()
    size_bytes = models.BigIntegerField()

    scan_id = models.CharField(max_length=64, db_index=True)

    def __str__(self):
        return f"{self.user} - {self.dir_name} ({self.size_bytes} bytes)"
