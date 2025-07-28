"""Function to scan all the files in all user's directories to calculate quota usage.

 This script is designed to be run from the command line

  ``python xfc_scan.py --path /userdir``
"""

# this needs to pick up a message - and then produce one. so it is a producerconsumer

# sends it to an external consumer. - which will notif user or something ??

import datetime
import os
import click
import pika
import json
import logging
import sys

output_connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
output_channel = output_connection.channel()


output_channel.queue_declare(queue='scanner_output', durable=True)


def publish_quotas(username, hard_quota, temporal_quota):

    message = {
        'hard_q': hard_quota,
        'temp_q': temporal_quota,
        'username': username
    }

    output_channel.basic_publish(
        exchange='',
        routing_key='scanner_output',
        body=json.dumps(message)
    )

    # output_connection.close()

def recieve_scan_request():
    request_connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
    requests_channel = request_connection.channel()

    requests_channel.queue_declare(queue='scanner_request', durable=True)

    def callback(ch, method, properties, body):
        msg = json.loads(body)
        username = msg['username']
        work_dir = msg['work_dir']

        error = ''
        if not username:
            error = 'Username not supplied'
        elif not work_dir:
            error = 'Work directory not supplied'

        if error:
            logging.error(f"Error: {error}")
            # TODO let request producer know message was invalid?
            return

        logging.info(f"[X] Scanning work directory for {username}")
        
        try:
            perform_scan(work_dir, username)
        except Exception as e:
            logging.error(f"Error: {e}")
            # TODO let request producer know there was an error?
            return
        ch.basic_ack(delivery_tag = method.delivery_tag)
    
    requests_channel.basic_qos(prefetch_count=1)
    requests_channel.basic_consume(
        queue='scanner_request',
        on_message_callback=callback
    )

    logging.info(' [*] Waiting for messages. CTRL+C to exit')
    requests_channel.start_consuming()


@click.command()
@click.option('--path', type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True))
@click.option('--username', type=click.STRING)
def scan_directory(path, username):
    perform_scan(path, username)
    

def perform_scan(work_dir, username):
    """
    Scans all the files under a specific directoy and calculates:
        - Hard Quota - total size of all files.
        - Temporal Quota - sum of (file size * time present)

    params:
        work_dir: The directory path specified by the user in the command line.
    """

    # works in this local context. I assume the path needs to change for actual deployment
    dir = os.path.join('/app/xfc_control/test_xfc/', work_dir)
    user_file_list = os.walk(dir, followlinks=True)

    now = datetime.datetime.now()
    hard_quota = 0
    temporal_quota = 0

    for root, dirs, files in user_file_list:
        for file in files:
            try:
                filepath = os.path.join(root, file)
                stat = os.stat(filepath)
                size = stat.st_size
                created_time = datetime.datetime.fromtimestamp(stat.st_mtime) # use mtime as ctime returns diff values on different os
                days_present = (now - created_time).days + 1

                hard_quota += size
                temporal_quota += (size * days_present)
            except Exception as e:
                click.echo(f"Error processing {filepath}: {e}", err=True)
        
    
    logging.info(f"Hard Quota (bytes): {hard_quota}")
    logging.info(f"Temporal Quota (bytes): {temporal_quota}")
    publish_quotas(username=username, hard_quota=hard_quota, temporal_quota=temporal_quota)

    
def run(*args):
    """Entry point for the Django script run via ``./manage.py runscript``
    """
    try:
        recieve_scan_request()
    except KeyboardInterrupt:
        logging.info('Interrupted')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)