"""Read in the config file for, convert from JSON to a dictionary and return
the config xfc."""

import json
import logging
import os

RABBIT_CONFIG_SECTION = "rabbitMQ"
RABBIT_USER = "user"
RABBIT_PASSWORD = "password"
RABBIT_SERVER = "server"
RABBIT_VHOST = "vhost"
RABBIT_QUEUES = "queues"
RABBIT_QUEUE_NAME = "name"
RABBIT_QUEUE_TYPE = "type"
RABBIT_EXCHANGE_TYPE = "exchange_type"
RABBIT_EXCHANGE_NAME = "exchange"
RABBIT_RK = "routing_key"
RABBIT_HEARTBEAT = "hearbeat"
RABBIT_TIMEOUT = "timeout"

LOG_FILENAME = "log_file"
LOG_LEVEL = "log_level"
LOG_ENABLE = "enable"
LOGGING = "logging"


def config_path():
    """Return the path of the config file"""
    path = "/etc/xfc_control/xfc_config.json"
    return path


def load_config(config_file_path: str = "") -> dict:
    if config_file_path == "":
        config_file_path = config_path()
    try:
        fh = open(os.path.expanduser(f"{config_file_path}"))
    except FileNotFoundError:
        raise FileNotFoundError(
            f"{config_file_path}", "The config file cannot be found."
        )
    # Load the JSON file, ensuring it is correctly formatted
    try:
        json_config = json.load(fh)
        fh.close()
    except json.JSONDecodeError as je:
        raise RuntimeError(
            f"The config file at {config_file_path} has an error at "
            f"character {je.pos}: {je.msg}."
        )
    # Add defaults if not in json_config
    if RABBIT_HEARTBEAT not in json_config[RABBIT_CONFIG_SECTION]:
        json_config[RABBIT_CONFIG_SECTION][RABBIT_HEARTBEAT] = 2
    if RABBIT_TIMEOUT not in json_config[RABBIT_CONFIG_SECTION]:
        json_config[RABBIT_CONFIG_SECTION][RABBIT_TIMEOUT] = 30
    return json_config


def get_queue_config(
    config: dict,
    queue_name: str,
):
    # get the config for a particular queue with the name in queue_name
    all_queues = config[RABBIT_CONFIG_SECTION][RABBIT_QUEUES]
    for q in all_queues:
        if q[RABBIT_QUEUE_NAME] == queue_name:
            return q
    return None


def get_logging_config(config: dict, process_name: str):
    process_config = config[process_name][LOGGING]
    return process_config


def get_process_name(process_name: str):
    """Get the process name either from __file__ (first case) or __name__ (second case)"""
    if ".py" in process_name:
        return process_name.split("/")[-1][:-3]
    else:
        return process_name.split(".")[-1]


def get_logging_level(loglevel):
    """Convert a logging level string into a logging.LOG_LEVEL"""
    if loglevel == "debug":
        return logging.DEBUG
    elif loglevel == "info":
        return logging.INFO
    elif loglevel == "warning":
        return logging.WARNING
    elif loglevel == "error":
        return logging.ERROR
    elif loglevel == "critical":
        return logging.CRITICAL


def get_logging_format():
    """return the format string for the logger"""
    formt = "[%(asctime)s] %(levelname)s:%(message)s"
    return formt


def setup_logging(config: dict, process_name: str):
    """Generic logging setup to output to a file and the stdout."""
    # get the logging config
    log_cfg = get_logging_config(
        config,
        get_process_name(process_name),
    )
    # only continue if the logging is enabled
    if log_cfg[LOG_ENABLE]:
        level_str = log_cfg[LOG_LEVEL]
        filename = log_cfg[LOG_FILENAME]
        # get the logger that matches the calling process name
        logger = logging.getLogger(process_name)
        level = get_logging_level(level_str)
        logger.setLevel(level)
        # create a file handler for this logger and set the level from the config
        fh = logging.FileHandler(filename=filename)
        fh.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        ah = logging.StreamHandler()
        ah.setLevel(level)
        ah.setFormatter(formatter)
        logger.addHandler(ah)
    return logger


def split_args(args):
    # split args that are in the form somekey=somevalue into a dictionary
    arg_dict = {}
    for a in args:
        try:
            split_args = a.split("=")
            arg_dict[split_args[0]] = split_args[1]
        except:
            raise Exception("Error in arguments")
    return arg_dict
