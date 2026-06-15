# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin
from xfc_control.models import CachedDirectoryScan, CacheDisk, User

# Register CacheDisk model with admin

class CacheDiskAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ('mountpoint', 'formatted_size', 'formatted_allocated', 'formatted_used')
    search_fields = ('mountpoint',)
    fields = ('mountpoint', 'size_bytes', 'formatted_allocated', 'formatted_used')
    readonly_fields = ('formatted_allocated', 'formatted_used',)
admin.site.register(CacheDisk, CacheDiskAdmin)

# Register User model with admin

class UserAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ('name', 'email', 'notify', 'formatted_size', 'formatted_used',
                    'formatted_hard_limit', 'formatted_total_used','cache_disk', 'cache_path', 'last_scanned')
    fields = ('name', 'email', 'notify', 'quota_size', 'formatted_used',
              'hard_limit_size', 'formatted_total_used', 'cache_disk', 'cache_path', 'last_scanned')
    search_fields = ('name', 'email')
    readonly_fields = ('email', 'formatted_used', 'formatted_total_used', 'last_scanned')
admin.site.register(User, UserAdmin)

class CachedDirectoryScanAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = (
        'user', 'dir_name', 'scan_time', 'dir_mtime', 'size_bytes', 'scan_id'
    )
    search_fields = ('user',)
    fields = ('user', 'dir_name', 'scan_time', 'dir_mtime', 'size_bytes', 'scan_id')
    readonly_fields= (
        'user', 'dir_name', 'scan_time', 'dir_mtime', 'size_bytes', 'scan_id'
    )
admin.site.register(CachedDirectoryScan, CachedDirectoryScanAdmin)
