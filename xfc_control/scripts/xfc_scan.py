#! /usr/bin/env python
"""Function to scan all the files in all user's directories to calculate quota usage.

This script can be run from the command line, where it will scan multiple directories
in parallel and then submit the result of each scan to the RabbitMQ queue.

 ``python xfc_control/scripts/xfc_scan.py --path /userdir -h``

It can also be invoked from the Django ``./manage.py runscript`` environment, where it
will wait for a message on the RabbitMQ queue, scan the directory indicated in the
message, and then put a message on the return queue, to be picked up by
xfc_process_scan.py

Author: Neil Massey and Will Cross
"""

from datetime import datetime, timezone
import time
import os
import click
import logging
import sys
import subprocess
import json

from concurrent.futures import ThreadPoolExecutor
from posix import DirEntry

import xfc_control.scripts.config as CFG
from xfc_control.scripts.RabbitMQPublisher import RabbitMQPublisher
from xfc_control.scripts.RabbitMQConsumer import RabbitMQConsumer

# need a global config
config = CFG.load_config()
logger = CFG.setup_logging(config, __file__)


# Rabbit producer
def publish_results(username, results):
    global logger
    logger.info("Starting publishing results of scan")

    # publish TO the consume scan queue
    PUBLISH_QUEUE_NAME = "xfc_consume_scan"
    publisher = RabbitMQPublisher(queue_name=PUBLISH_QUEUE_NAME)
    publisher.attach_logger(logger)
    publisher.connect()

    # publish a message for each result
    for r in results:
        # need to convert the datetimes into floating point numbers
        msg = {
            "username": username,
            "dir_name": r["dir_name"],
            "scan_time": r["scan_time"].timestamp(),
            "dir_mtime": r["dir_mtime"].timestamp(),
            "size": r["size"],
        }
        try:
            publisher.publish_message(msg)
        except Exception as e:
            # if it has failed then reconnect
            publisher.connect()
            publisher.publish_message(msg)


# scan logic
def format_size(num_bytes: int):
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num_bytes)

    for unit in units:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024

    return f"{size:.2f} EB"


def format_time(dt: datetime):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def default_python_du(path: str) -> int:
    """
    This is the pure Python implementation to find the total size of a directory.
    It scans the files and directories below the path and returns the result in bytes.
    """
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


def determine_best_method(path: str, method: str) -> tuple[str, str]:
    """
    Find the best method to use to scan the directories.
    This is platform dependent - some tools are only available on HPC systems, or with
    specific filesystems.
    These methods are:
        1. default: the fallback method.  This uses Python libraries to scan.
        2. du: the operating system method of du
        3. pdu: parallel du, usually the fastest, where supported
    In addition the reporting method is determined by checking to see if each command
    supports reporting in bytes (most accurate) vs reporting in kilobytes
        1. -sb: report in bytes
        2. -sk: report in kilobytes
    """
    global logger
    if method != "default":
        checks = []
        # check for parallel du - this is the preferred option as it's the fastest
        if method == "pdu":
            checks.extend(
                [
                    ("pdu", "-sb"),
                    ("pdu", "-sk"),
                ]
            )
        # also check for du - the OS option, this is 2nd preference
        checks.extend(
            [
                ("du", "-sb"),
                ("du", "-sk"),
            ]
        )
        # fall through will be default - python only method
        for command, flag in checks:
            try:
                subprocess.run(
                    [command, flag, path], capture_output=True, text=True, check=True
                )
                if method != command:
                    logger.error(f"{method} failed, using {command} instead")
                return command, flag
            except Exception:
                pass
        logger.error(f"{method} failed, falling back to default")

    return "default", ""


def shell_method_scan_all(
    paths: list[str], now: datetime, method: str, params: str
) -> list[dict]:
    """This is the method to scan the directories using a command in the shell,
    i.e. du or pdu commands"""
    global logger

    # if no paths
    if not paths:
        return []

    logger.info(
        f"Running {method} with parameters {params} for {len(paths)} directories"
    )

    cmd = [method, params] + paths
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
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

    for path in paths:
        if path not in size_map:
            logger.warning(f"No size found for {path} in {method} output")
        try:
            stat = os.stat(path)
            results.append(
                {
                    "dir_name": path,
                    "scan_time": now,
                    "dir_mtime": datetime.fromtimestamp(stat.st_mtime),
                    "size": size_map.get(path, 0),
                }
            )

        except Exception as e:
            logger.error(f"Error processing {path}: {e}")

    return results


def python_scan_dir(path: str, now: datetime) -> dict:
    """Scan a single directory using the default python method"""
    global logger
    try:
        stat = os.stat(path)
        logger.info(f"Calculating size for directory: {path}")
        size = default_python_du(path)

        return {
            "dir_name": path,
            "scan_time": now,
            "dir_mtime": datetime.fromtimestamp(stat.st_mtime),
            "size": size,
        }
    except Exception as e:
        logger.error(f"Error processing {path}: {e}")
        return None


def python_method_scan_all(dirs: list[str], now: datetime) -> list[dict]:
    """Use pure python method to scan all directories in dirs list.
    Uses futures to perform multithreading."""
    results = []
    max_workers = 8  # NRM - get this from config
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []

        for d in dirs:
            future = executor.submit(python_scan_dir, d, now)
            futures.append(future)

        for f in futures:
            res = f.result()
            if res:
                results.append(res)
    return results


def scan_all_dirs_from_base(
    base_path: str, scan_type: str, method: str, human: bool = False
) -> tuple[list[dict], list[dict]]:
    """Scan all the directories below the base_path.
    The best method to use for scanning will be determined and then used."""

    global logger
    logger.info(f"Scanning from base directory: {base_path}")

    # Get the best method, i.e. fastest supported
    method, params = determine_best_method(base_path, method)

    # get the current time for scanning
    time_now = datetime.now()

    # only top-level dirs
    dirs = []

    # Build a list of directories to scan from the base path.
    # These are the user's top-level directories in the XFC database.
    # We only need to do this for volume scans
    if scan_type == "volume_scan":
        with os.scandir(base_path) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    dirs.append(entry.path)

    elif scan_type == "user_scan":
        dirs = [base_path]
    else:
        logger.error(f"Unknown scan_type: {scan_type}")
        return

    # if the method is default then use pure Python scan method
    if method == "default":
        results = python_method_scan_all(dirs, time_now)
    else:
        results = shell_method_scan_all(dirs, time_now, method, params)

    # if "human readable" results were selected then return them so they can be output
    # on the console
    human_res = []
    if human:
        for r in results:
            human_res.append(
                {
                    "dir_name": r["dir_name"],
                    "scan_time": format_time(r["scan_time"]),
                    "dir_mtime": format_time(r["dir_mtime"]),
                    "size": format_size(r["size"]),
                }
            )

    return results, human_res


def rabbit_callbackfn(
    channel,
    method,
    properties,
    body,
):
    global config
    # get the dictionary from the body
    body_json = json.loads(body)
    if "username" in body_json:
        username = body_json["username"]
    else:
        username = ""
    # scan types are: "user_scan" OR "volume_scan"
    scan_type = body_json["type"]
    base_dir = body_json["work_dir"]
    process_name = CFG.get_process_name(__name__)
    scan_method = config[process_name]["scan_method"]  # put this in config
    results, _ = scan_all_dirs_from_base(base_dir, scan_type, scan_method, human=False)
    # publish the results to the processing queue
    publish_results(username, results)

    channel.basic_ack(delivery_tag=method.delivery_tag)


def run(*args):
    """
    Entry point for the Django script run via ``./manage.py runscript``
    This will use the RabbitMQ queues to receive and send message
    """
    global logger
    logger.info("Starting scan from Django runscript")

    try:
        # For the rabbit implementation we have to create a consumer for the
        # xfc_consume_queue
        CONSUME_QUEUE_NAME = "xfc_publish_scan"
        consumer = RabbitMQConsumer(queue_name=CONSUME_QUEUE_NAME)
        consumer.attach_logger(logger)
        consumer.connect()
        consumer.start_consuming(rabbit_callbackfn)

    except KeyboardInterrupt:
        logger.info("Interrupted")
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)


# CLI
@click.command()
@click.option(
    "-u",
    "--username",
    type=str,
    help=(
        "\b\n"
        "The username to perform the scan for.  This is used in the reporting, so must match a username in the XFC database."
    ),
    required=False,
    default="",
)
@click.option(
    "-p",
    "--path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help=(
        "\b\n"
        "The base path to start the scan at. This is usually the volume under \n"
        "which the user's cache directories appear."
    ),
    required=True,
)
@click.option(
    "--method",
    "-m",
    type=click.Choice(["du", "pdu", "default"]),
    default="default",
    help=(
        "\b\n"
        "The method to use for scanning directories. The choices are:\n"
        "1. default - a pure Python implementation, that uses multithreading to\n"
        "   speed up the scan.\n"
        "2. pdu - parallel du, if available on the OS, is a faster version of du.\n"
        "3. du - standard du, provided by every Linux and BSD distribution."
    ),
)
@click.option("--human", "-h", is_flag=True, help="Human readable output")
@click.option(
    "--rabbit",
    "-r",
    is_flag=True,
    default=False,
    help="Send results to RabbitMQ queue for processing",
)
#
def scan_directory(
    username: str, path: str, human: bool, method: str, rabbit: bool
) -> None:
    """Command line to scan directory, being able to choose the method"""
    # set up the logging
    global logger

    logger.info("Starting scan from command line")
    # start the scan and time it
    path = os.path.abspath(path)
    start = time.time()
    if username:
        scan_type = "user_scan"
    else:
        scan_type = "volume_scan"
    results, human_res = scan_all_dirs_from_base(path, scan_type, method, human=human)
    end = time.time()

    # output the results
    logger.info(f"Took {end - start:.2f}s")
    logger.info(f"Scanned {len(results)} directories")
    n = len(human_res)
    if human_res:
        for i, r in enumerate(human_res):
            log_str = f"Result {i+1}/{n}: \nDirectory name : {r['dir_name']}"
            if username:
                log_str += f"\n  User         : {username}"
            log_str += f"\n  Scan time    : {r['scan_time']}"
            log_str += f"\n  Modified time: {r['dir_mtime']}"
            log_str += f"\n  Total size   : {r['size']}"
            logger.info(log_str)
    else:
        for r in results:
            logger.info(r)

    # publish the results to the processing queue
    if rabbit:
        publish_results(username, results)


if __name__ == "__main__":
    """
    Entry point if the Python program is run on the command line.
    This will use click to run the scanner, it will not pull a message from the RabbitMQ
    queue but it will submit (potentially multiple) messages to the return RabbitMQ
    queue.
    """
    scan_directory()
