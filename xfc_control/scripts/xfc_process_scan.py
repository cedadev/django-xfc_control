"""
Consumes output messages from xfc_scan
Author: Matteo Guarnaccia
Date: 28/07/2025
"""

import calendar
from xfc_control.models import User, CachedDirectoryScan, CacheDisk
import sys
import os
import json
import logging
from datetime import datetime
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
    # Now the scan has been added, update the user quota
    update_user_quota(user)
    # Update the disk quota as well
    cache_disk = user.cache_disk
    update_cache_disk_quota(cache_disk)


def log_scan(scan: CachedDirectoryScan, log_str="") -> None:
    """Output the scan to the logger"""
    global logger
    log_str += f"\n    Directory     : {scan.dir_name}: "
    log_str += f"\n    User          : {scan.user}"
    log_str += f"\n    Scan time     : {scan.formatted_scan_time()}"
    log_str += f"\n    Scan size     : {scan.formatted_size()}"
    log_str += f"\n    Modified time : {scan.formatted_mtime()}"
    logger.info(log_str)


def calculate_temporal_usage_3(scans: list[CachedDirectoryScan]):
    """
    Calculate the temporal usage.
    This is as simple as the length of time between scans multiplied by the scan size.
    The complication comes when the scan size is less than the previous scan size.
    To counteract this the algorithm is:
        1. Calculate the temporal usage backwards, i.e. start with the latest scan
        1. The maximum size is the size of the current scan = max_size
        2. For each scan, the contribution to the temporal usage is the minimum of the
           scan and the maximum size * time between scans:
           C = min(scan_size, max_size) * time_delta
        3. Update the maximum size at each iteration.  This

    This can be thought of via the following scenario:
        1. The user adds data to the volume, it keeps increasing.  The temporal usage
           goes up in line with this.
        2. The user removes data from the volume. It drops to X bytes.
        3. The temporal usage still needs to reflect that this amount of data has been
           present since the scan size was above or equal to X.
        4. Hence taking the min between the latest scan size and the sizes for
           each of the scans.
        5. The usage could drop to Y bytes where Y < X, before the user adds more data
           to take the latest scan to X bytes.
        6. This is why the scan is performed backwards, and the max_size is constantly
           updated.
    """
    global logger

    n_scans = scans.count()
    lsi = n_scans - 1  # last scan index

    max_size = scans[lsi].size_bytes  # maximum size of scan
    n_secs_day = 24 * 60 * 60  # number of seconds per day
    temporal_size = scans[lsi].size_bytes  # start with latest scan size

    log_str = "\nUpdating user quota from scans:"
    log_str += f"\n    Directory     : {scans[lsi].dir_name}"
    log_str += f"\n    User          : {scans[lsi].user}"

    # loop backwards
    x = 1
    for i in range(n_scans - 1, 0, -1):
        log_str += (
            f"\n    Scan ({x}/{n_scans})    : "
            f"{scans[i].formatted_scan_time()} : {scans[i].formatted_size()}"
        )
        # get the minimum scan size
        c_scan_size = min(scans[i - 1].size_bytes, max_size)
        # get the time delta
        td = (scans[i].scan_time - scans[i - 1].scan_time).total_seconds()
        temporal_size += c_scan_size * td / n_secs_day
        # update max size
        max_size = min(max_size, scans[i - 1].size_bytes)
        x += 1
    logger.info(log_str)
    return temporal_size


def update_user_quota(user: User) -> None:
    """Loop through the CachedDirectoryScans for a user and calculate their used quota."""
    # get all the scans
    global logger

    scans = CachedDirectoryScan.objects.filter(user=user).order_by("scan_time")
    total_size = scans[scans.count() - 1].size_bytes
    temporal_size = calculate_temporal_usage_3(scans=scans)

    # round to int
    temporal_size = int(temporal_size)

    log_str = f"\n  Updating quota for user {user.name}: "
    log_str += f"\n  Total size      : {format_size(total_size)}"
    log_str += f"\n  Temporal size   : {format_size(temporal_size)}"
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


def update_cache_disk_quota(cache_disk: CacheDisk) -> None:
    """Update the amount of space used on the cache_disk"""
    # get the users who have used this CacheDisk
    global logger
    users = User.objects.filter(cache_disk=cache_disk)
    sum = 0.0

    log_str = f"\nUpdating CacheDisk: {cache_disk.mountpoint}"
    for user in users:
        # get the last CachedDirectoryScan for the user
        scan = (
            CachedDirectoryScan.objects.filter(user=user).order_by("scan_time").last()
        )
        log_str += f"\n  Adding used_bytes by: {user.name}, total_used: {scan.formatted_size()}"
        sum += scan.size_bytes
    # set to the sum
    cache_disk.used_bytes = sum
    log_str += (
        f"\n  Total used: {cache_disk.formatted_used()} / {cache_disk.formatted_size()}"
    )
    logger.info(log_str)


def update_all_cache_disk_quota() -> None:
    """Update all the cache disks"""
    for cache_disk in CacheDisk.objects.all():
        update_cache_disk_quota(cache_disk)


def check_user_quota_usage(user: User):
    if user.quota_size < user.quota_used or user.hard_limit_size < user.total_used:
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
            update_all_cache_disk_quota()
        else:
            main()
    except KeyboardInterrupt:
        logging.info("Interrupted")
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
