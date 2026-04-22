"""Function to scan all the files in all user's directories to calculate quota usage.

 This script is designed to be run from the command line

  ``python xfc_control/scripts/xfc_scan.py --path /userdir --email example@example.com -h``
"""

# this needs to pick up a message - and then produce one. so it is a producerconsumer

# sends it to an external consumer. - which will notif user or something ??

import datetime
import time
import os
import click
import pika
import json
import logging
import sys


import django
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "xfc_site.settings")
django.setup()

from concurrent.futures import ThreadPoolExecutor
from xfc_control.models import CachedDirectoryScan
from django.contrib.auth import get_user_model
User = get_user_model()

output_channel = None

def get_output_channel():
    global output_channel
    if output_channel is None:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters('rabbitmq')
        )
        output_channel = connection.channel()
        output_channel.queue_declare(queue='scanner_output', durable=True)
    return output_channel


def publish_quotas(username, hard_quota, temporal_quota):
    try:
        channel = get_output_channel()
    except Exception:
        print("No RabbitMQ — printing instead:")
        print(username, hard_quota, temporal_quota)
        return

    message = {
        'hard_q': hard_quota,
        'temp_q': temporal_quota,
        'username': username
    }

    channel.basic_publish(
        exchange='',
        routing_key='scanner_output',
        body=json.dumps(message)
    )

    # output_connection.close()

def receive_scan_request():
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
            scan_dirs(work_dir, username)
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
@click.option('--email', required=True, help="User email")
@click.option('--human', '-h', is_flag=True, help="Human readable output")
def scan_directory(path, email, human):
    scan_directory_logic(path, email, human)
    
def scan_directory_logic(path, email, human=False):
    start = time.time()
    results, human_res = scan_dirs(path, max_workers=8, human=human)
    end = time.time()
    user = User.objects.get(email=email)

    print(f"Took {end - start:.2f}s")
    print(f"Scanned {len(results)} directories")
    print("Results:")
    if human_res:
        for r in human_res:
            print(r)
    else:
        for r in results:
            print(r)
    print("")
    print("Adding to database")
    records = [
        CachedDirectoryScan(
            user=user,
            dir_name=row["dir_name"],
            scan_time=row["scan_time"],
            dir_mtime=row["dir_mtime"],
            size_bytes=row["size"]
        )
            for row in results
    ]

    CachedDirectoryScan.objects.bulk_create(records)


def format_size(num_bytes):
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num_bytes)

    for unit in units:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024

    return f"{size:.2f} EB"


def format_time(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def get_dir_size(path):
    total = 0
    stack = [path]

    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            total += entry.stat().st_size
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                    except Exception:
                        continue
        except Exception:
            continue

    return total


def process_dir(entry, now):
    try:
        stat = entry.stat()
        size = get_dir_size(entry.path)

        return {
            "dir_name": entry.path,
            "scan_time": now,
            "dir_mtime": datetime.datetime.fromtimestamp(stat.st_mtime),
            "size": size
        }

    except Exception:
        return None


def scan_dirs(base_path, max_workers=8, human=False):
    now = datetime.datetime.now()

    # only top-level dirs
    dirs = []

    with os.scandir(base_path) as entries:
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                dirs.append(entry)

    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []

        for d in dirs:
            future = executor.submit(process_dir, d, now)
            futures.append(future)

        for f in futures:
            res = f.result()
            if res:
                results.append(res)
    
    human_res = []
    if human:
        for r in results:
            human_res.append({
                "dir_name": r["dir_name"],
                "scan_time": format_time(r["scan_time"]),
                "dir_mtime": format_time(r["dir_mtime"]),
                "size": format_size(r["size"])
            })

    return results, human_res


# TODO: integrate with rabbits




    
def run(*args):
    """Entry point for the Django script run via ``./manage.py runscript``
    """
    try:
        #receive_scan_request()
        if len(args) < 2:
            raise ValueError("Usage: <path> <email> [human]")

        path = args[0]
        email = args[1]
        human = False

        if len(args) > 2:
            human = args[2].lower() in ("true", "1", "yes", "y")

        scan_directory_logic(path, email, human)
    except KeyboardInterrupt:
        logging.info('Interrupted')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)

if __name__ == "__main__":
    scan_directory()