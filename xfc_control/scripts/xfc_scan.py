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
import subprocess


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
#logging.basicConfig(level=logging.DEBUG)

RABBIT_NAME = 'localhost'
QUEUE_NAME = "scanner_request"

output_channel = None

def handle_message(ch, delivery, body):
    try:
        msg = json.loads(body)
        email = msg['email']
        work_dir = msg['work_dir']
        scan_method = msg['method']

        if not email or not work_dir:
            raise ValueError("Invalid message: email/work_dir required")

        logging.info(f"[X] Scan requested: {email} -> {work_dir}")
        
        scan_directory_logic(work_dir, email, scan_method)
        
        ch.basic_ack(delivery_tag=delivery.delivery_tag)

    except Exception as e:
        logging.exception("Worker Error")
        ch.basic_nack(delivery_tag=delivery.delivery_tag, requeue=False)

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
def send_scan_request(email, work_dir, method):
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(RABBIT_NAME)
    )
    channel = connection.channel()

    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    message = {
        "email": email,
        "work_dir": work_dir,
        "method": method,
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
@click.option('--du', 'method', flag_value='du')
@click.option('--pdu', 'method', flag_value='pdu')
@click.option('--default', 'method', flag_value='default', default=True)
def scan_directory(path, email, human, rabbit, method):
    path = os.path.abspath(path)

    if rabbit:
        send_scan_request(email, path, method)
        logging.info("Scan job sent to queue")
    else:
        scan_directory_logic(path, email, method, human)


# Scan formatting logic and database
def scan_directory_logic(path, email, method, human=False):
    start = time.time()
    results, human_res = scan_dirs(path, method, max_workers=8, human=human)
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


def determine_best_method(path, method):
    if method != "default":
        checks = []

        if method == "pdu":
            checks.extend([
                ("pdu", "-sb"),
                ("pdu", "-sk"),
            ])

        checks.extend([
            ("du", "-sb"),
            ("du", "-sk"),
        ])

        for command, flag in checks:
            try:
                subprocess.run(
                    [command, flag, path],
                    capture_output=True,
                    text=True,
                    check=True
                )
                return command, flag
            except Exception:
                pass
        logging.error(f"{method} failed, falling back to default")

    return "default", ""
        

def shell_method_scan_all(dirs, now, method, params):
    paths = [d.path for d in dirs]

    if not paths:
        return []

    logging.info(
        f"running {method} with parameters {params} for {len(paths)} directories"
    )

    cmd = [method, params] + paths

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True
    )

    results = []

    size_map = {}

    for line in result.stdout.splitlines():
        parts = line.split(maxsplit=1)

        if len(parts) != 2:
            continue

        raw_size, path = parts

        size = int(raw_size)

        # convert -sk to bytes
        if params == "-sk":
            size *= 1024

        size_map[path] = size

    for entry in dirs:
        if entry.path not in size_map:
            logging.warning(f"No size found for {entry.path} in {method} output")
        try:
            stat = entry.stat()

            results.append({
                "dir_name": entry.path,
                "scan_time": now,
                "dir_mtime": datetime.datetime.fromtimestamp(
                    stat.st_mtime
                ),
                "size": size_map.get(entry.path, 0)
            })

        except Exception as e:
            logging.error(f"Error processing {entry.path}: {e}")

    return results

def process_dir(entry, now):
    try:
        stat = entry.stat()
        path = entry.path
        size = get_dir_size(path)

        return {
            "dir_name": path,
            "scan_time": now,
            "dir_mtime": datetime.datetime.fromtimestamp(stat.st_mtime),
            "size": size
        }
    except Exception as e:
        logging.error(f"Error processing {entry.path}: {e}")
        return None


def scan_dirs(base_path, method, max_workers=8, human=False):
    now = timezone.now()

    # only top-level dirs
    dirs = []

    with os.scandir(base_path) as entries:
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                dirs.append(entry)

    results = []
    method, params = determine_best_method(base_path, method)

    if method != "default":
        results = shell_method_scan_all(
            dirs,
            now,
            method,
            params
        )
    else:
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