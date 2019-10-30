"""Read in the config file for, convert from JSON to a dictionary and return
the config xfc."""

import json
import logging

def config_path():
    """Return the path of the config file"""
    path = "/etc/xfc_control/xfc_config.json"
    return path

def read_process_config(process):
    """Read in the config file and return the dictionary for the process."""
    cfg_path = config_path()
    fh = open(cfg_path)
    cfg = json.load(fh)
    fh.close()
    try:
        return cfg["processes"][process]
    except Exception as e:
        raise Exception("Process {} not found in config file {}".format(
            process,
            cfg_path)
        )

def get_logging_level(loglevel):
    """Convert a logging level string into a logging.LOG_LEVEL"""
    if loglevel == "DEBUG":
        return logging.DEBUG
    elif loglevel == "INFO":
        return logging.INFO
    elif loglevel == "WARNING":
        return logging.WARNING
    elif loglevel == "ERROR":
        return logging.ERROR
    elif loglevel == "CRITICAL":
        return logging.CRITICAL

def get_logging_format():
    """return the format string for the logger"""
    formt = "[%(asctime)s] %(levelname)s:%(message)s"
    return formt

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
