"""
Consumes output messages from xfc_scan
Author: Matteo Guarnaccia
Date: 28/07/2025
"""

import calendar
from xfc_control.models import User, CachedDirectoryScan
import sys
import os
import json
import logging
from datetime import datetime, timedelta
from django.core.mail import send_mail
from xfc_control.scripts.RabbitMQConsumer import RabbitMQConsumer
import xfc_control.scripts.config as CFG
from xfc_control.scripts.xfc_scan import format_size

logger = None


def callbackfn(
    channel,
    method,
    properties,
    body,
):
    process_scan_output(json.loads(body))
    channel.basic_ack(delivery_tag=method.delivery_tag)


def main() -> None:
    #
    global logger

    CONSUME_QUEUE_NAME = "xfc_consume_scan"
    consumer = RabbitMQConsumer(queue_name=CONSUME_QUEUE_NAME)
    consumer.setup_logging(__name__)
    consumer.connect()
    # make the logger available globally
    logger = consumer.logger
    consumer.logger.debug(f"Starting process: {__name__}")
    consumer.logger.info(" [*] Waiting for messages. CTRL+C to exit")
    consumer.start_consuming(callbackfn)


def process_scan_output(result: dict) -> None:
    """
    Process the result from the scan, passed in the message body.
    It should be a dictionary containing the following keys:
        dir_name  : name / path of directory that was scanned
        username  : name of the user that owns the directory
        scan_time : datetime of the scan of the directory
        dir_mtime : modified time of the directory
        size      : size in bytes of the directory, obtained by the scan
    """
    #
    global logger

    # get the details from the scan
    dir_name = result["dir_name"]
    username = result["username"]
    scan_time = datetime.fromtimestamp(result["scan_time"])
    dir_mtime = datetime.fromtimestamp(result["dir_mtime"])
    dir_size = result["size"]

    # check that all the details were supplied and correct - username is not needed, as
    # it can be recovered from the dir_name
    if not (dir_name and scan_time and dir_mtime and dir_size >= 0):
        logger.error(f"Invalid scan output: {result}")
        return

    # get the user - if the username does not exist then get the user from the directory
    if username:
        try:
            user = User.objects.get(name=username)
        except User.DoesNotExist:
            logger.error(f": User not found {username}")
            return
    else:
        # all paths contain "user_cache".  Split on this to find the volume and the
        # user directory
        mount_point, cache_dir = dir_name.split("user_cache")
        # add user_cache back to start of cache_dir
        cache_dir = os.path.join("user_cache", cache_dir)
        mount_point = os.path.dirname(mount_point)  # trim any "/"
        user = User.objects.filter(
            cache_disk__mountpoint=mount_point, cache_path__contains=cache_dir
        ).first()

    # Add the CachedDirectoryScan to the database
    completed_scan = CachedDirectoryScan(
        user=user,
        dir_name=dir_name,
        scan_time=scan_time,
        dir_mtime=dir_mtime,
        size_bytes=dir_size,
    )
    completed_scan.save()
    log_scan(completed_scan, "\nCommitting scan:")
    # Now the scan has been added, update the quotas
    update_user_quota(user)


def log_scan(scan: CachedDirectoryScan, log_str="") -> None:
    """Output the scan to the logger"""
    global logger
    log_str += f"\n    Directory     : {scan.dir_name}: "
    log_str += f"\n    User          : {scan.user}"
    log_str += f"\n    Scan time     : {scan.formatted_scan_time()}"
    log_str += f"\n    Scan size     : {scan.formatted_size()}"
    log_str += f"\n    Modified time : {scan.formatted_mtime()}"
    logger.info(log_str)


def update_user_quota(user: User) -> None:
    """Loop through the CachedDirectoryScans for a user and calculate their used quota."""
    # get all the scans
    global logger

    scans = CachedDirectoryScan.objects.filter(user=user).order_by("scan_time")
    if scans.count() == 1:
        total_size = scans[0].size_bytes
        temporal_size = scans[0].size_bytes
        log_scan(scans[0], "\nProcessing scan:")
    else:
        temporal_size = 0.0
        for i in range(1, scans.count()):
            log_scan(scans[i], "\nProcessing scan:")
            size_delta = scans[i].size_bytes - scans[i - 1].size_bytes
            time_delta = scans[i].scan_time - scans[i - 1].scan_time
            # use the time in seconds
            temporal_size += float(size_delta * time_delta.seconds) / (24 * 60 * 60)
        total_size = scans[scans.count() - 1].size_bytes

    # Clamp the size at zero
    if temporal_size < 0.0:
        temporal_size = 0.0
    # round to int
    temporal_size = int(temporal_size)

    log_str = f"\n  Updating quota for user {user.name}: "
    log_str += f"\n  Total size : {total_size} Bytes"
    log_str += f"\n  Temporal size: {temporal_size} Bytes"
    logger.info(log_str)

    user.total_used = total_size
    user.quota_used = temporal_size
    user.save()


def update_all_user_quotas() -> None:
    """Run update_user_quota on all Users"""
    # Need to instantiate a logger
    global logger
    config = CFG.load_config()
    logger = CFG.setup_logging(
        config=config,
        process_name=__name__,
    )
    for user in User.objects.all():
        update_user_quota(user)


def check_user_quota_usage(user: User):
    if user.quota_size < user.quota_used:
        send_notification_email(user)


def send_notification_email(user: User):
    """Send an email to the user to notify that they are over the quota limit"""
    if not user.notify:
        return

    # to address is notify_on_first
    toaddrs = [user.email]
    # from address is just a dummy address
    fromaddr = "support@jasmin.ac.uk"

    date = user.last_scanned or datetime.datetime.now(datetime.timezone.utc)

    # subject
    subject = "[XFC] - Notification of quota exceeded"
    date_string = "% 2i %s %d %02d:%02d" % (
        date.day,
        calendar.month_abbr[date.month],
        date.year,
        date.hour,
        date.minute,
    )

    msg = f"You have exceeded your quota of {user.formatted_size()}. You have used {user.formatted_used()}, as of{date_string}UTC"
    logging.info(f"Sending quota exceeded email to {user.name}")

    try:
        # This has been failing with connection refused errors - not sure why
        send_mail(subject, msg, fromaddr, toaddrs, fail_silently=False)
    except Exception as e:
        logging.error(f"Error sending mail: {e}")


def run(*args):
    """Entry point for the Django script run via ``./manage.py runscript``"""
    try:
        if "update" in args:
            update_all_user_quotas()
        else:
            main()
    except KeyboardInterrupt:
        logging.info("Interrupted")
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
