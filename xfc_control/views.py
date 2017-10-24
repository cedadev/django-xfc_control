# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from xfc_control.models import *
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, Http404
from django.views.generic import View
import json
import os
import datetime


def HttpError(error_data, status=404):
    """Function that returns a 404 (or other status) HTTP error."""
    return HttpResponse(json.dumps(error_data),
                        content_type="application/json", status=status, reason=error_data["error"])

class UserView(View):
    """:rest-api

    Requests to resources which return information about the users in the Transfer Cache.
    """

    def get(self, request, *args, **kwargs):
        """:rest-api

           .. http:get:: /xfc_control/api/v1/user

               Get the details of a user identified by their username

               :queryparam string name: (*optional*) The username (same as JASMIN username).

               ..

               :>jsonarr string name: username - should be same as JASMIN username
               :>jsonarr string cache_path: path to the user's cache area
               :>jsonarr int quota_size: quota size allocated to user (in bytes)
               :>jsonarr int quota_used: amount of quota used by user so far (in bytes)
               :>jsonarr int hard_limit_size: maximum size of all the files owned by the user
               :>jsonarr int total_used: total size of all files owned by the user
               :>jsonarr string email: email address of the user

               :statuscode 200: request completed successfully.

               **Example request**

               .. sourcecode:: http

                   GET /xfc_control/api/v1/user?name=fred HTTP/1.1
                   Host: xfc.ceda.ac.uk
                   Accept: application/json

               **Example response**

               .. sourcecode:: http

                   HTTP/1.1 200 OK
                   Vary: Accept
                   Content-Type: application/json

                   [
                     {
                       "quota_used": 0,
                       "cache_path": "/cache/disk1/users/fred",
                       "name": "fred",
                       "quota_size": 5368709120,
                       "email": "fred@fredco.com"
                     }
                   ]

        """
        # first case - error as you can only retrieve single users
        if len(request.GET) == 0:
            return HttpError({"error": "No name supplied"})
        else:
            # get the username
            username = request.GET.get("name", "")
            # get the user or 404
            error_data = {}
            try:
                if username:
                    user = User.objects.get(name=username)
                else:
                    error_data["error"] = "Error with name parameter."
                    return HttpError(data)
            except:
                error_data["error"] = "User not found."
                return HttpError(data)

            # create the path to the cache area
            cache_path = os.path.join(user.cache_disk.mountpoint, user.cache_path)

            data = {"name" : user.name,
                    "email" : user.email,
                    "notify" : user.notify,
                    "quota_size" : user.quota_size,
                    "quota_used" : user.quota_used,
                    "hard_limit_size" : user.hard_limit_size,
                    "total_used" : user.total_used,
                    "cache_path" : cache_path}

        return HttpResponse(json.dumps(data), content_type="application/json")


    def post(self, request, *args, **kwargs):
        """:rest-api

           .. http:post:: /xfc_control/api/v1/user

                Create a user identified by their username and (*optional*) email address

                ..

                :<jsonarr string name: the username (same as JASMIN username)
                :<jsonarr string email: (*optional*) email address of the user for deletion notifications

                :>jsonarr string name: the username
                :>jsonarr string email: the user's email address
                :>jsonarr string cache_path: path to the user's cache area
                :>jsonarr int quota_size: quota size allocated to user (in bytes)

                :statuscode 200: request completed successfully
                :statuscode 403: error with user quota: no CacheDisk could be found with enough space on it to hold the user's quota
                :statuscode 403: Transfer cache already initialized for this user
                :statuscode 404: name not supplied in POST request

                **Example request**

                .. sourcecode:: http

                    POST /xfc_control/api/v1/user HTTP/1.1
                    Host: xfc.ceda.ac.uk
                    Accept: application/json
                    Content-Type: application/json

                    [
                      {
                        "name": "fred",
                        "email": "fred@fredco.com",
                      }
                    ]


                **Example response**

                .. sourcecode:: http

                    HTTP/1.1 200 OK
                    Vary: Accept
                    Content-Type: application/json

                    [
                      {
                        "name": "fred",
                        "email": "fred@fredco.com",
                        "cache_path": "/cache/disk1/users/fred",
                        "quota_size": 5368709120,
                      }
                    ]

                .. sourcecode:: http

                    HTTP/1.1 403 Forbidden
                    Vary: Accept
                    Content-Type: application/json

                    [
                      {
                        "error": "No CacheDisk found with enough free space for user's quota"
                      }

                      {
                        "error": "Transfer cache already initialized for this user"
                      }
                    ]

                .. sourcecode:: http

                    HTTP/1.1 404 Not found
                    Vary: Accept
                    Content-Type: application/json

                    [
                      "No username supplied to POST request"
                    ]
        """
        # get the json formatted data
        data = request.read()
        data = json.loads(data)
        # copy input data into error_data
        error_data = data

        # get the user name and email out of the json
        if "name" in data:
            username = data["name"]
        else:
            error_data["error"] = "No name supplied."
            return HttpError(error_data)

        if "email" in data:
            email = data["email"]
        else:
            email = ""

        # check if user already exists
        user_query = User.objects.filter(name=username)
        if len(user_query) != 0:
            error_data["error"] = "Transfer cache already initialized for this user."
            return HttpError(error_data, status=403)

        # get the (initial) quota size
        qs = User.get_quota_size()
        # get the hard limit size
        hl = User.get_hard_limit_size()

        # find a CacheDisk with enough free space (unallocated space)
        cache_disk = CacheDisk.find_free_cache_disk(hl)
        # check that a CacheDisk was found, if not return an error
        if not cache_disk:
            error_data["error"] = "No CacheDisk found with enough free space for user's quota."
            return HttpError(error_data, status=403)

        # create cache path
        try:
            user_path = cache_disk.create_user_cache_path(username)
            # create user object
            user = User(name = username, email=email, quota_size=qs, quota_used=0, hard_limit_size=hl, total_used=0,
                        cache_path=user_path, cache_disk=cache_disk)
            user.save()
        except Exception as e:
            error_data["error"] = str(e)
            return HttpError(error_data, status=500)
        # update the cache_disk allocated quotas
        cache_disk.allocated_bytes += hl
        cache_disk.save()

        # return the details
        data_out = {"name" : username, "email" : email,
                    "cache_path" : os.path.join(user.cache_disk.mountpoint, user_path),
                    "quota_size" : qs, "hard_limit_size" : hl}
        return HttpResponse(json.dumps(data_out), content_type="application/json")


    def put(self, request, *args, **kwargs):
        """:rest-api

        .. http:put:: /xfc_control/api/v1/user

            Update a user info - just allows update of email address and notifications at the moment

            ..

            :queryparam string name: The username (same as JASMIN username).

            :<jsonarr string email: (*optional*) email address of the user for deletion notifications
            :<jsonarr boolean notify: (*optional*) whether to email the user about scheduled deletions

            :>jsonarr string name: the username
            :>jsonarr string email: the user's email address
            :>jsonarr bool notify: notifications on / off

            :statuscode 200: request completed successfully
            :statuscode 404: name not supplied in PUT request
            :statuscode 404: name not found as supplied in PUT request

            **Example request**

            .. sourcecode:: http

                PUT /xfc_control/api/v1/user HTTP/1.1
                Host: xfc.ceda.ac.uk
                Accept: application/json
                Content-Type: application/json

                [
                  {
                    "name": "fred",
                    "email": "fred@fredco.com",
                    "notify": true,
                  }
                ]


            **Example response**

            .. sourcecode:: http

                HTTP/1.1 200 OK
                Vary: Accept
                Content-Type: application/json

                [
                  {
                    "name": "fred",
                    "email": "fred@fredco.com",
                    "notify": true,
                  }
                ]

            .. sourcecode:: http

                HTTP/1.1 404 Not found
                Vary: Accept
                Content-Type: application/json

                [
                  "No username supplied to PUT request"
                ]

                [
                  "User not found as supplied in PUT request"
                ]
        """
        # find the user first
        if len(request.GET) == 0:
            return HttpError({"error": "No name supplied."})
        else:
            # get the username
            username = request.GET.get("name", "")
            # update the user using the json
            data = request.read()
            data = json.loads(data)
            # copy the data into error_data
            error_data = data
            try:
                if username:
                    user = User.objects.get(name=username)
                else:
                    error_data["error"] = "Error with name parameter."
                    return HttpError(error_data)
            except:
                error_data["error"] = "User not found."
                return HttpError(error_data)

            if "email" in data:
                user.email = data["email"]
            else:
                data["email"] = user.email
            if "notify" in data:
                user.notify = data["notify"]
            else:
                data["notify"] = user.notify
            user.save()
            # return something meaningful
            data_out = {"name": username, "email": data["email"], "notify": data["notify"]}
            return HttpResponse(json.dumps(data_out), content_type="application/json")


class CachedFileView(View):
    """:rest-api

    Requests to resources which return information about the files in the Transfer Cache.

    """


    def get(self, request, *args, **kwargs):
        """:rest-api

         .. http:get:: /xfc_control/api/v1/file

             Get the details of a user identified by their username

             :queryparam string name: The username (same as JASMIN username).

             :queryparam string match: (*optional*) Substring to match against in the name of the CachedFile.

             :queryparam bool full_path: (*optional*) whether to output full paths of the files or paths relative to the mountpoint of the CacheDisk.

             ..

             :>jsonarr List[Dictionary] files: Details of the files returned, each dictionary contains:

             ..

                 - **path** (`string`): path to the file
                 - **size** (`integer`): size of the file (in bytes)
                 - **quota_used** (`integer`): amount of temporal quota used
                 - **first_seen** (`string`): date the file was first seen in the system, in isoformat

             :statuscode 200: request completed successfully.

             **Example request**

             .. sourcecode:: http

                 GET /xfc_control/api/v1/file?user=fred?match=.nc?full_path HTTP/1.1
                 Host: xfc.ceda.ac.uk
                 Accept: application/json

             **Example response**

             .. sourcecode:: http

                 HTTP/1.1 200 OK
                 Vary: Accept
                 Content-Type: application/json

                 [
                   {
                     "path": 0,
                     "size": "/cache/disk1/users/fred",
                   },
                   {
                     "path": 0,
                     "size": "/cache/disk1/users/fred",
                   }
                 ]

        """
        if len(request.GET) == 0:
            return HttpError({"error" : "No name supplied."})
        else:
            # get the username
            username = request.GET.get("name", "")
            try:
                if username:
                    user = User.objects.get(name=username)
                else:
                    error_data["error"] = "Error with name parameter."
                    return HttpError(error_data)
            except:
                error_data["error"] = "User not found."
                return HttpError(error_data)
            # get the match if present
            match = request.GET.get("match", "")
            # get whether a full path is required
            full_path = (request.GET.get("full_path", "") == "1")
            # filter the files on user and matching key
            cfiles = CachedFile.objects.filter(user=user, path__contains=match)
            data = []
            # get the current date for calculating quota used
            current_date = datetime.datetime.utcnow()
            # loop over the files and build the output
            for f in cfiles:
                # calculate the quota used
                quota_used = ((current_date - f.first_seen).days + 1) * f.size
                # output the size, date and quota used
                file_entry = {"size": f.size, "first_seen": f.first_seen.isoformat(), "quota_used": quota_used}
                # output the full path or not
                if full_path:
                    file_entry["path"] = os.path.join(user.cache_disk.mountpoint, f.path)
                else:
                    file_entry["path"] = f.path
                data.append(file_entry)
            return HttpResponse(json.dumps(data), content_type = "application/json")


class CacheDiskView(View):
    """:rest-api

    Requests to resources which return information about the disks / cache areas in the Transfer Cache.
    """

    def get(self, request, *args, **kwargs):
        """:rest-api

           .. http:get:: /xfc_control/api/v1/disk

               Get a list of available CacheDisks or a single CacheDisk optionally identified by the uid or the mountpoint.

               :queryparam int id: (*optional*) Unique id (the Django DB pik) of the CacheDisk.

               :queryparam string mountpoint: (*optional*) String containing the mountpoint of the disk.

               ..

               :>jsonarr List[Dictionary] cache_disks: Details of the disks returned, each dictionary contains:

               ..

                   - **mountpoint** (`string`): path of the mountpoint of the disk.
                   - **allocated** (`int`): the amount of space that has been allocated to users via their quotas (in bytes).
                   - **used** (`int`): the amount of space that has been used by the users via their quotas (in bytes).
                   - **size** (`int`): the total size of the disk (in bytes).
                   - **id** (`int`): the unique identifier of the disk.

               :statuscode 200: request completed successfully.

               **Example request**

               .. sourcecode:: http

                   GET /xfc_control/api/v1/disk?id=1 HTTP/1.1
                   Host: xfc.ceda.ac.uk
                   Accept: application/json

               **Example response**

               .. sourcecode:: http

                   HTTP/1.1 200 OK
                   Vary: Accept
                   Content-Type: application/json

                   [
                     {
                       "cache_disks": [
                                        {
                                          "mountpoint": "/cache/disk1",
                                          "allocated": 0,
                                          "used": 0,
                                          "id": 1,
                                          "size": 5242880
                                        }
                                      ]
                     }
                   ]

        """
        # first case - get all disks
        disks = []
        if len(request.GET) == 0:
            for disk in CacheDisk.objects.all():
                disk_data = {"id": disk.pk,
                             "mountpoint": disk.mountpoint,
                             "size": disk.size_bytes,
                             "allocated": disk.allocated_bytes,
                             "used": disk.used_bytes}
                disks.append(disk_data)
        else:
            # check if search by mountpoint or id
            id = request.GET.get("id", "")
            mountpoint = request.GET.get("mountpoint", "")
            # second case - get disk by uid
            if id:
                try:
                    disk = CacheDisk.objects.get(pk=id)
                except:
                    error_data["error"] = "Could not find CacheDisk with id=" + str(id) + "."
                    return HttpError(error_data)
            # third case - get disk by mountpoint
            elif mountpoint:
                try:
                    disk = CacheDisk.objects.get(mountpoint=mountpoint)
                except:
                    error_data["error"] = "Could not find CacheDisk with mountpoint=" + mountpoint + "."
                    return HttpError(error_data)
            else:
                return HttpError({"error": "Error with supplied parameters"})
            disks = [{"id": disk.pk,
                      "mountpoint": disk.mountpoint,
                      "size": disk.size_bytes,
                      "allocated": disk.allocated_bytes,
                      "used": disk.used_bytes}]
        data = {"cache_disks": disks}

        return HttpResponse(json.dumps(data), content_type="application/json")


class ScheduledDeletionView(View):
    """:rest-api

    Requests to resources which return information about the scheduled deletions in the Transfer Cache.
    """

    def get(self, request, *args, **kwargs):
        """:rest-api

           .. http:get:: /xfc_control/api/v1/scheduled_deletions

               Get the details of the files that are scheduled for deletion for a user, identified by their username

               :queryparam string name: (*optional*) The username (same as JASMIN username).

               ..

              :>jsonarr Dictionary scheduled_deletions: Details of the scheduled deletions returned, the dictionary contains:

               ..

                   - **name** (`string`): the name of the user who owns this scheduled deletion
                   - **time_entered** (`string`): the date which the deletion was inserted into the system, in isoformat
                   - **time_delete** (`string`): the date / time on which the deletion will take place, in isoformat
                   - **cache_disk** (`string`): mountpoint of the cache disk where the files are kept
                   - **files** (`List[string]`): list of files scheduled to be deleted

               :statuscode 200: request completed successfully

               :statuscode 404: name not found - i.e. user does not exist

               **Example request**

               .. sourcecode:: http

                   GET /xfc_control/api/v1/scheduled_deletions?name=fred HTTP/1.1
                   Host: xfc.ceda.ac.uk
                   Accept: application/json

               **Example response**

               .. sourcecode:: http

                   HTTP/1.1 200 OK
                   Vary: Accept
                   Content-Type: application/json

                   [
                     {
                       "files": [
                                  "/cache/disk1/user_cache/dhk63261/cru/data/cru_ts/cru_ts_3.24.01/data/tmp/cru_ts3.24.01.1941.1950.tmp.dat.nc"
                                ],
                       "time_entered": "2017-05-17T09:55:02.789476",
                       "time_delete": "2017-05-18T09:55:02.789479",
                       "name": "fred"
                     }
                   ]

        """
        # First get the user details
        if len(request.GET) == 0:
            return HttpError({"error" : "No name supplied."})
        else:
            # get the username
            username = request.GET.get("name", "")
            try:
                if username:
                    user = User.objects.get(name=username)
                else:
                    error_data["error"] = "Error with name parameter."
                    return HttpError(error_data)
            except:
                error_data["error"] = "User not found."
                return HttpError(error_data)
        # Now get the scheduled deletions
        scheduled_deletions = ScheduledDeletion.objects.filter(user=user)
        if len(scheduled_deletions) == 0:  # no scheduled deletions for this user
            # return JSON with null strings for the times and an empty list for the files
            data = [{"name": username, "time_entered": "", "time_delete": "", "cache_disk":"", "files": []}]
        else:
            data = []
            # there should only be one scheduled deletion, but there may be more in the future
            # so return as a list for flexibility
            for sd in scheduled_deletions:
                # output this scheduled deletion data
                data.append({"name": sd.user.name,
                             "time_entered": sd.time_entered.isoformat(),
                             "time_delete": sd.time_delete.isoformat(),
                             "cache_disk": sd.user.cache_disk.mountpoint,
                             "files": [os.path.join(f.path) for f in sd.delete_files.all()]})
        return HttpResponse(json.dumps(data), content_type = "application/json")


def predict(request):
    """:rest-api

       .. http:get:: /xfc_control/api/v1/scheduled_deletions

            Predict when the next deletions will occur and which files will be in the deletions, for a user

            :queryparam string name: (*optional*) The username (same as JASMIN username).

            ..

           :>jsonarr Dictionary scheduled_deletions: Details of the scheduled deletions returned, the dictionary contains:

            ..

                - **name** (`string`): the name of the user who owns this scheduled deletion
                - **time_predict** (`string`): the date when deletions will start, in isoformat
                - **over_quota** (`int`): the amount that the user will exceed the quota by
                - **cache_disk** (`string`): mountpoint of the cache disk where the files are kept
                - **files** (`List[string]`): list of files which will be deleted

            :statuscode 200: request completed successfully

            :statuscode 404: name not fourd - i.e. user does not exist

            **Example request**

            .. sourcecode:: http

                GET /xfc_control/api/v1/scheduled_deletions?name=fred HTTP/1.1
                Host: xfc.ceda.ac.uk
                Accept: application/json

            **Example response**

            .. sourcecode:: http

                HTTP/1.1 200 OK
                Vary: Accept
                Content-Type: application/json

                [
                  {
                    "cache_disk": "/cache/disk1",
                    "files": [
                               "user_cache/dhk63261/cru/data/cru_ts/cru_ts_3.24.01/data/tmp/cru_ts3.24.01.1901.1910.tmp.dat.nc",
                               "user_cache/dhk63261/cru/data/cru_ts/cru_ts_3.24.01/data/tmp/cru_ts3.24.01.2001.2010.tmp.dat.nc",
                               "user_cache/dhk63261/cru/data/cru_ts/cru_ts_3.24.01/data/tmp/cru_ts3.24.01.1951.1960.tmp.dat.nc",
                               "user_cache/dhk63261/cru/data/cru_ts/cru_ts_3.24.01/data/tmp/cru_ts3.24.01.1971.1980.tmp.dat.nc",
                               "user_cache/dhk63261/cru/data/cru_ts/cru_ts_3.24.01/data/tmp/cru_ts3.24.01.1961.1970.tmp.dat.nc"
                             ],
                    "over_quota": 1207043264,
                    "name": "dhk63261",
                    "time_predict": "2017-05-23T15:43:47.437739"
                  }
                ]

    """
    # First get the user details
    if len(request.GET) == 0:
        return HttpError({"error": "No name supplied."})
    else:
        # get the username
        username = request.GET.get("name", "")
        try:
            if username:
                user = User.objects.get(name=username)
            else:
                error_data["error"] = "Error with name parameter."
                return HttpError(error_data)
        except:
            error_data["error"] = "User not found."
            return HttpError(error_data)


    # now calculate the number of days until the quota will run out
    # first check that the user has files
    if user.total_used == 0:
        data = {"name": username,
                "files": []}
        return HttpResponse(json.dumps(data), content_type="application/json")

    n_days = int((user.quota_size - user.quota_used) / user.total_used) + 1
    # create the date
    current_date = datetime.datetime.utcnow()
    deletion_date = current_date + datetime.timedelta(hours=ScheduledDeletion.schedule_hours * n_days)
    # calculate how much over
    over_quota = n_days * user.total_used + user.quota_used - user.quota_size

    # get a list of (predicted) files that will be deleted
    # get a list of user cached files sorted descending
    cached_files = CachedFile.objects.filter(user=user).order_by('first_seen')
    # sum of files to delete
    quota_delete = 0
    # list of files to delete
    files_to_delete = []

    # get enough files to bring the quota back to its allocated amount
    for cf in cached_files:
        if quota_delete > over_quota:
            break
        # keep a running total
        quota_delete += cf.quota_use()
        # add the files
        files_to_delete.append(cf.path)

    data = {"name": username,
            "time_predict": deletion_date.isoformat(),
            "cache_disk": user.cache_disk.mountpoint,
            "over_quota": over_quota,
            "files": files_to_delete}
    return HttpResponse(json.dumps(data), content_type="application/json")
