"""Function to sweep the users database and find the user with the oldest `last_scanned`.

The selected user's data will then be published to a RabbitMQ, where `xfc_scan` will
pick up the message, and begin scanning their directory.

Note - this script currently is run manually, this should be looped using cron job.

Date: 17/06/2026
Authors: Matteo Guarnaccia and Neil Massey

"""

from xfc_control.models import User, CacheDisk
import os
from xfc_control.scripts.RabbitMQPublisher import RabbitMQPublisher


def queue_next_user(publisher: RabbitMQPublisher):
    user = User.objects.order_by("last_scanned").first()

    if user:
        publish_user_scan_message(publisher, user)
    else:
        publisher.log("error", "No user selected for scan")


def queue_all_users(publisher: RabbitMQPublisher):
    users = User.objects.order_by("last_scanned").all()
    if len(users) == 0:
        publisher.log("error", "No users selected for scan")

    for user in users:
        publish_user_scan_message(publisher, user)


def queue_all_volumes(publisher: RabbitMQPublisher):
    volumes = CacheDisk.objects.all()
    if len(volumes) == 0:
        publisher.log("error", "No volumes selected for scan")

    for volume in volumes:
        publish_volume_scan_message(publisher, volume)


def publish_user_scan_message(
    publisher: RabbitMQPublisher,
    user: User,
):
    user_dir = os.path.join(user.cache_disk.mountpoint, user.cache_path)
    publisher.log(
        "info",
        f"Sending scan message for user: {user.name}, with directory: " f"{user_dir}",
    )
    scan_message = {
        "type": "user_scan",
        "username": user.name,
        "work_dir": user_dir,
    }
    publisher.publish_message(message=scan_message)


def publish_volume_scan_message(
    publisher: RabbitMQPublisher,
    volume: CacheDisk,
):
    volume_dir = os.path.join(volume.mountpoint, "user_cache")
    publisher.log("info", f"Sending scan message for volume: {volume_dir}")
    scan_message = {
        "type": "volume_scan",
        "work_dir": volume_dir,
    }
    publisher.publish_message(message=scan_message)


def run(*args):
    """Entry point for the Django script run via ``./manage.py runscript``"""
    # Create the publisher for the rabbit Q
    QUEUE_NAME = "xfc_publish_scan"
    publisher = RabbitMQPublisher(queue_name=QUEUE_NAME)
    publisher.setup_logging(__name__)
    publisher.log("debug", f"Starting process: {__name__}")
    publisher.connect()
    if "one_user" in args:
        queue_next_user(publisher=publisher)
    elif "all_users" in args:
        queue_all_users(publisher=publisher)
    elif "all_vols" in args:
        queue_all_volumes(publisher=publisher)
    else:
        print(
            "No args supplied: use `--script-args all_users` or `--script-args "
            "one_user` or `--script-args all_vols`"
        )
    publisher.close()
