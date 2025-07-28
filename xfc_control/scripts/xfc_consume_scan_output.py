'''Consumes output messages from xfc_scan'''

import calendar
import pika
from xfc_control.models import User
import sys
import os
import json
import logging
import datetime
from django.core.mail import send_mail


def main():
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
    channel = connection.channel()

    channel.queue_declare(queue='scanner_output', durable=True)

    def callback(ch, method, properties, body):
        logging.info(f" [x] Recieved {body.decode()}")

        try:
            process_scan_output(json.loads(body))
        except Exception as e:
            logging.error(f"Error: {e}")
            # TODO let scan producer know there was error?

        ch.basic_ack(delivery_tag=method.delivery_tag)
         
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(
        queue='scanner_output',
        on_message_callback=callback
    )

    logging.info(' [*] Waiting for messages. CTRL+C to exit')
    channel.start_consuming()


def process_scan_output(output):
    username = output['username']
    hard_q = output['hard_q']
    temp_q = output['temp_q']

    if not (username or hard_q or temp_q):
        logging.error('Error: Invalid scan output')

    user = User.objects.get(name=username)

    if user:
        user.quota_used = temp_q
        user.total_used = hard_q
        user.last_scanned = datetime.datetime.now(datetime.timezone.utc)
        user.save()
        check_user_quota_usage(user)
    else:
        logging.error('User not found')


def check_user_quota_usage(user: User):
    if user.quota_size < user.quota_used:
        send_notification_email(user)


def send_notification_email(user: User):
    """Send an email to the user to notify that they are over the quota limit
    """
    if not user.notify:
        return

    # to address is notify_on_first
    toaddrs = [user.email]
    # from address is just a dummy address
    fromaddr = "support@ceda.ac.uk"

    date = user.last_scanned or datetime.datetime.now(datetime.timezone.utc)

    # subject
    subject = "[XFC] - Notification of quota exceeded"
    date_string = "% 2i %s %d %02d:%02d" % (date.day, calendar.month_abbr[date.month], date.year, date.hour, date.minute)

    msg = f"You have exceeded your quota of {user.formatted_size()}. You have used {user.formatted_used()}, as of{date_string}UTC"
    logging.info(f'Sending quota exceeded email to {user.name}')
    
    try:
        # This has been failing with connection refused errors - not sure why
        send_mail(subject, msg, fromaddr, toaddrs, fail_silently=False)
    except Exception as e:
        logging.error(f'Error sending mail: {e}')

def run(*args):
    """Entry point for the Django script run via ``./manage.py runscript``
    """
    try:
        main()
    except KeyboardInterrupt:
        logging.info('Interrupted')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)