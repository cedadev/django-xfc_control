# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from xfc_control.models import *
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, Http404
from django.views.generic import View
from django.core.mail import send_mail

import json
import os
import datetime


def HttpError(error_data, status=404):
    """Function that returns a 404 (or other status) HTTP error."""
    return HttpResponse(
        json.dumps(error_data),
        content_type="application/json",
        status=status,
        reason=error_data["error"],
    )


def send_notification_email(user, notify):
    """Send an email to the user to confirm that notifications have been switched on
    :var xfc_control.models.User user: user to send notification email to
    """
    # to address is user.email
    toaddrs = [user.email]
    # from address is just a dummy address
    fromaddr = "support@ceda.ac.uk"

    # subject
    subject = "[XFC] - Notifications"
    if notify:
        subject += " ON"
    else:
        subject += " OFF"

    msg = "This email confirms that JASMIN user: " + str(user.name) + " will "
    if not notify:
        msg += "no longer "
    msg += (
        "be notified when "
        + "files are scheduled for deletion from the JASMIN transfer cache (XFC)."
    )

    send_mail(subject, msg, fromaddr, toaddrs, fail_silently=False)


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
                    return HttpError(error_data)
            except:
                error_data["error"] = "User not found."
                return HttpError(error_data)

            # create the path to the cache area
            cache_path = os.path.join(user.cache_disk.mountpoint, user.cache_path)

            data = {
                "name": user.name,
                "email": user.email,
                "notify": user.notify,
                "quota_size": user.quota_size,
                "quota_used": user.quota_used,
                "hard_limit_size": user.hard_limit_size,
                "total_used": user.total_used,
                "cache_path": cache_path,
            }

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
            error_data["error"] = (
                "No CacheDisk found with enough free space for user's quota."
            )
            return HttpError(error_data, status=403)

        # create cache path
        try:
            user_path = cache_disk.create_user_cache_path(username)
            # create user object
            user = User(
                name=username,
                email=email,
                quota_size=qs,
                quota_used=0,
                hard_limit_size=hl,
                total_used=0,
                cache_path=user_path,
                cache_disk=cache_disk,
            )
            user.save()
        except Exception as e:
            error_data["error"] = str(e)
            return HttpError(error_data, status=500)
        # update the cache_disk allocated quotas
        cache_disk.allocated_bytes += hl
        cache_disk.save()

        # return the details
        data_out = {
            "name": username,
            "email": email,
            "cache_path": os.path.join(user.cache_disk.mountpoint, user_path),
            "quota_size": qs,
            "hard_limit_size": hl,
        }
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
                # create and send a confirmation email to the user
                send_notification_email(user, user.notify)
            else:
                data["notify"] = user.notify
            user.save()
            # return something meaningful
            data_out = {
                "name": username,
                "email": data["email"],
                "notify": data["notify"],
            }
            return HttpResponse(json.dumps(data_out), content_type="application/json")


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
        error_data = {}
        if len(request.GET) == 0:
            for disk in CacheDisk.objects.all():
                disk_data = {
                    "id": disk.pk,
                    "mountpoint": disk.mountpoint,
                    "size": disk.size_bytes,
                    "allocated": disk.allocated_bytes,
                    "used": disk.used_bytes,
                }
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
                    error_data["error"] = (
                        "Could not find CacheDisk with id=" + str(id) + "."
                    )
                    return HttpError(error_data)
            # third case - get disk by mountpoint
            elif mountpoint:
                try:
                    disk = CacheDisk.objects.get(mountpoint=mountpoint)
                except:
                    error_data["error"] = (
                        "Could not find CacheDisk with mountpoint=" + mountpoint + "."
                    )
                    return HttpError(error_data)
            else:
                return HttpError({"error": "Error with supplied parameters"})
            disks = [
                {
                    "id": disk.pk,
                    "mountpoint": disk.mountpoint,
                    "size": disk.size_bytes,
                    "allocated": disk.allocated_bytes,
                    "used": disk.used_bytes,
                }
            ]
        data = {"cache_disks": disks}

        return HttpResponse(json.dumps(data), content_type="application/json")
