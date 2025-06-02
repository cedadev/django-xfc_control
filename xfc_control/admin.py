# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin
from xfc_control.models import *

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
                    'formatted_hard_limit', 'formatted_total_used','cache_disk', 'cache_path')
    fields = ('name', 'email', 'notify', 'quota_size', 'formatted_used',
              'hard_limit_size', 'formatted_total_used', 'cache_disk', 'cache_path')
    search_fields = ('name', 'email')
    readonly_fields = ('email', 'formatted_used', 'formatted_total_used')
admin.site.register(User, UserAdmin)

class UserLockAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ('id', 'user_lock',)
    readonly_fields = ('user_lock',)
admin.site.register(UserLock, UserLockAdmin)

# Register CachedFile model with admin

class CachedFileAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ('full_path', 'formatted_size', 'first_seen', 'user')
    fields = ('path', 'formatted_size', 'first_seen', 'user')
    search_fields = ('path', )
    readonly_fields = ('path', 'formatted_size', 'first_seen', 'user')
admin.site.register(CachedFile, CachedFileAdmin)

class ScheduledDeletionAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ('user', 'time_entered', 'time_delete')
    search_fields = ('user',)
    fields = ('user', 'time_entered', 'time_delete')
    readonly_fields = ('user', 'time_entered')
admin.site.register(ScheduledDeletion, ScheduledDeletionAdmin)
