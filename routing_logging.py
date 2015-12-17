#!/usr/bin/python
"""
This module creates logging instances for corresponding routing modules
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from conf import ABSOLUTE_PATH


def create_routing_log(log_name, log_hierarchy, log_level=logging.DEBUG):
    # Create log directory, if it's not been created already
    if not os.path.exists(ABSOLUTE_PATH + "logs/"):
        os.makedirs(ABSOLUTE_PATH + "logs/")

    log_formatter = logging.Formatter('%(asctime)s %(levelname)s %(funcName)s(%(lineno)d) %(message)s')
    log_file = ABSOLUTE_PATH + "logs/" + log_name
    log_handler = RotatingFileHandler(log_file, mode='a', maxBytes=5*1024*1024,
                                      backupCount=10, encoding=None, delay=0)

    log_handler.setFormatter(log_formatter)
    log_handler.setLevel(log_level)

    if log_hierarchy == "root":
        routing_log = logging.getLogger()
    else:
        routing_log = logging.getLogger(log_hierarchy)

    # Avoid duplicate handlers
    if routing_log.handlers:
        return routing_log

    routing_log.setLevel(log_level)
    routing_log.addHandler(log_handler)

    return routing_log
