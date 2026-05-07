"""Function to scan all the files in all user's directories to calculate quota usage.

 This script is designed to be run from the command line

  ``python xfc_control/scripts/xfc_scan.py --path /userdir --email example@example.com -h``
"""

# this needs to pick up a message - and then produce one. so it is a producerconsumer

# sends it to an external consumer. - which will notif user or something ??

import datetime
from django.utils import timezone
import time
import os
import click
import pika
import json
import logging
import sys
import logging


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

RABBIT_NAME = 'localhost'
QUEUE_NAME = "scanner_request"

output_channel = None

def handle_message(ch, method, body):
    try:
        msg = json.loads(body)
        email = msg['email']
        work_dir = msg['work_dir']

        if not email or not work_dir:
            raise ValueError("Invalid message: email/work_dir required")

        logging.info(f"[X] Scan requested: {email} -> {work_dir}")
        
        scan_directory_logic(work_dir, email)
        
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logging.exception("Worker Error")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

# Rabbit consumer worker
def receive_scan_request():
    request_connection = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_NAME))
    requests_channel = request_connection.channel()

    requests_channel.queue_declare(queue=QUEUE_NAME, durable=True)

    def callback(ch, method, properties, body):
        handle_message(ch, method, body)
    
    requests_channel.basic_qos(prefetch_count=1)
    requests_channel.basic_consume(
        queue=QUEUE_NAME,
        on_message_callback=callback
    )

    logging.info(' [*] Waiting for scan jobs. CTRL+C to exit')
    requests_channel.start_consuming()


# Rabbit producer
def send_scan_request(email, work_dir):
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(RABBIT_NAME)
    )
    channel = connection.channel()

    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    message = {
        "email": email,
        "work_dir": work_dir,
    }

    channel.basic_publish(
        exchange="",
        routing_key=QUEUE_NAME,
        body=json.dumps(message),
        properties=pika.BasicProperties(delivery_mode=2),
    )

    connection.close()



# CLI
@click.command()
@click.option('--path', type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True))
@click.option('--email', required=True, help="User email")
@click.option('--human', '-h', is_flag=True, help="Human readable output")
@click.option('--rabbit', is_flag=True, help="Send to RabbitMQ instead of running locally")
def scan_directory(path, email, human, rabbit):
    path = os.path.abspath(path)

    if rabbit:
        send_scan_request(email, path)
        logging.info("Scan job sent to queue")
    else:
        scan_directory_logic(path, email, human)


# Scan formatting logic and database
def scan_directory_logic(path, email, human=False):
    start = time.time()
    results, human_res = scan_dirs(path, max_workers=8, human=human)
    end = time.time()
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        raise ValueError(f"User not found: {email}")

    logging.info(f"Took {end - start:.2f}s")
    logging.info(f"Scanned {len(results)} directories")
    logging.info("Results:")
    if human_res:
        for r in human_res:
            logging.info(r)
    else:
        for r in results:
            logging.info(r)
    logging.info("")
    logging.info("Adding to database")
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
    logging.info("Success!")


# scan logic
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
    now = timezone.now()

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

    
def run(*args):
    """Entry point for the Django script run via ``./manage.py runscript``
    """
    try:
        receive_scan_request()
    except KeyboardInterrupt:
        logging.info('Interrupted')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)

if __name__ == "__main__":
    scan_directory()