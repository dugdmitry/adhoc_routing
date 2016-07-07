#!/usr/bin/python
"""
This module creates logging instances for corresponding routing modules
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from conf import ABSOLUTE_PATH, LOG_LEVEL

# Set a global variable LOG_LEVEL according to the string variable in conf file
# Log levels correspond to standard levels defined in the "logging" module
if LOG_LEVEL == "CRITICAL":
    LOG_LEVEL = logging.CRITICAL
elif LOG_LEVEL == "ERROR":
    LOG_LEVEL = logging.ERROR
elif LOG_LEVEL == "WARNING":
    LOG_LEVEL = logging.WARNING
elif LOG_LEVEL == "INFO":
    LOG_LEVEL = logging.INFO
elif LOG_LEVEL == "DEBUG":
    LOG_LEVEL = logging.DEBUG
else:
    # Else, set the log level to the default INFO value
    LOG_LEVEL = logging.INFO


def create_routing_log(log_name, log_hierarchy):
    # Create log directory, if it's not been created already
    if not os.path.exists(ABSOLUTE_PATH + "logs/"):
        os.makedirs(ABSOLUTE_PATH + "logs/")

    log_formatter = logging.Formatter('%(asctime)s %(levelname)s %(funcName)s(%(lineno)d) %(message)s')
    log_file = ABSOLUTE_PATH + "logs/" + log_name
    log_handler = RotatingFileHandler(log_file, mode='a', maxBytes=5*1024*1024,
                                      backupCount=10, encoding=None, delay=0)

    log_handler.setFormatter(log_formatter)
    log_handler.setLevel(LOG_LEVEL)

    if log_hierarchy == "root":
        routing_log = logging.getLogger()
    else:
        routing_log = logging.getLogger(log_hierarchy)

    # Avoid duplicate handlers
    if routing_log.handlers:
        return routing_log

    routing_log.setLevel(LOG_LEVEL)
    routing_log.addHandler(log_handler)

    return routing_log
