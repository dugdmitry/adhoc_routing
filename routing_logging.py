#!/usr/bin/python
"""
This module creates logging instances for corresponding routing modules.
It also performs all log writing operations in a single thread, while receiving the messages via queue.
"""

import os
import sys
import threading
import Queue
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


# A thread which will perform all writing operations to the given logging instance
class LoggingHandler(threading.Thread):
    def __init__(self, logging_instance):
        super(LoggingHandler, self).__init__()
        self.running = True
        self.logging_queue = Queue.Queue()
        self.logging_instance = logging_instance

    # Get the log message and its arguments from the queue, write them to the log instance
    def run(self):
        while self.running:
            try:
                loglevel, msg, args, kwargs = self.logging_queue.get()

                print loglevel, msg, args, kwargs

                if loglevel == logging.INFO:
                    self.logging_instance.info(msg, *args, **kwargs)

                elif loglevel == logging.DEBUG:
                    self.logging_instance.debug(msg, *args, **kwargs)

                elif loglevel == logging.ERROR:
                    self.logging_instance.error(msg, *args, **kwargs)

                elif loglevel == logging.WARNING:
                    self.logging_instance.warning(msg, *args, **kwargs)

                elif loglevel == logging.CRITICAL:
                    self.logging_instance.critical(msg, *args, **kwargs)

                else:
                    self.logging_instance.info(msg, *args, **kwargs)

            except:
                e = sys.exc_info()[0]
                print "Caught some exception!!! %s" % e

            print "END OF ITERATION"

    # Define callbacks which will be used by other modules to send their logging messages to
    def info(self, msg, *args, **kwargs):
        loglevel = logging.INFO

        # print loglevel, msg, args, kwargs

        self.logging_queue.put((loglevel, msg, args, kwargs))

    def debug(self, msg, *args, **kwargs):
        loglevel = logging.DEBUG

        # print loglevel, msg, args, kwargs

        self.logging_queue.put((loglevel, msg, args, kwargs))

    def error(self, msg, *args, **kwargs):
        loglevel = logging.ERROR
        self.logging_queue.put((loglevel, msg, args, kwargs))

    def warning(self, msg, *args, **kwargs):
        loglevel = logging.WARNING
        self.logging_queue.put((loglevel, msg, args, kwargs))

    def critical(self, msg, *args, **kwargs):
        loglevel = logging.CRITICAL
        self.logging_queue.put((loglevel, msg, args, kwargs))

    def quit(self):
        self.running = False
        self._Thread__stop()

    def __del__(self):
        print "Thread is deleted!"


# Create a single logging instance and output a thread object which will receiving incoming logging messages
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
        # Create and start the log handling thread object
        logging_handler_thread = LoggingHandler(routing_log)
        print "Starting logging thread...", log_hierarchy
        logging_handler_thread.start()
        print "logging thread started!!!", log_hierarchy

        return logging_handler_thread

    routing_log.setLevel(LOG_LEVEL)
    routing_log.addHandler(log_handler)

    # Create and start the log handling thread object
    logging_handler_thread = LoggingHandler(routing_log)
    print "Starting logging thread...", log_hierarchy
    logging_handler_thread.start()
    print "logging thread started!!!", log_hierarchy

    return logging_handler_thread
