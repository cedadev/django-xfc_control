'''Function to sweep the users database and find the user with the oldest `last_scanned`.

    The selected user's data will then be published to a RabbitMQ, where `xfc_scan` will
    pick up the message, and begin scanning their directory.

    Note - this script currently is run manually, this should be looped using cron job.

'''

from xfc_control.models import User
import pika
import logging
import json
import time
import os

connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
channel = connection.channel()

channel.queue_declare(queue='scanner_request', durable=True)

def enqueue_next_user():
    user = User.objects.order_by('last_scanned').first()

    if user:
        publish_to_scanner_request_queue(user)
    else:
        logging.error('No user selected for scan')


def publish_to_scanner_request_queue(user: User):
    message = {
        'username': user.name,
        'work_dir': os.path.join(user.cache_disk.mountpoint, user.cache_path)
    }

    channel.basic_publish(
        exchange='',
        routing_key='scanner_request',
        body=json.dumps(message)
    )

    # connection.close()

def run(*args):
    """Entry point for the Django script run via ``./manage.py runscript``
    """
    while True:
        enqueue_next_user()
        time.sleep(60)
