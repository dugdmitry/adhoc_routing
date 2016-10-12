#!/usr/bin/python
"""
This module creates logging instances for corresponding routing modules.
It also performs all log writing operations in a single thread, while receiving the messages via queue.
"""

import os
import threading
import Queue
import logging
from logging.handlers import RotatingFileHandler
from conf import LOG_LEVEL

# Define an absolute path to the program's directory
ABSOLUTE_PATH = os.path.dirname(os.path.abspath(__file__))
# Define a default path to log directory
PATH_TO_LOGS = "/var/log/adhoc_routing/"
# Define a global queue for receiving the methods from the Logger objects and its arguments
LOG_QUEUE = Queue.Queue()

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
    def __init__(self):
        super(LoggingHandler, self).__init__()
        self.running = True
        self.root_logger = logging.getLogger()

    # Get the log message and its arguments from the queue, write them to the log instance
    def run(self):
        self.root_logger.info("STARTING THE LOG THREAD...")
        while self.running:
            # loglevel, msg, args, kwargs = self.logging_queue.get()
            log_object_method, msg, args, kwargs = LOG_QUEUE.get()
            # Execute the method
            log_object_method(msg, *args, **kwargs)

    def quit(self):
        self.running = False
        self.root_logger.info("STOPPING THE LOG THREAD...")


# Handles the log methods (info, debug, error, etc.) called from the modules, and forwards
# them into the global queue so the LoggingHandler thread will perform the actual writing operation
class LogWrapper:
    def __init__(self, logger_object):
        self.logger_object = logger_object
        self.info("THE LOG INSTANCE IS CREATED: %s", self.logger_object.name)

    # Define callbacks which will be used by other modules to send their logging messages to
    def info(self, msg, *args, **kwargs):
        LOG_QUEUE.put((self.logger_object.info, msg, args, kwargs))

    def debug(self, msg, *args, **kwargs):
        LOG_QUEUE.put((self.logger_object.debug, msg, args, kwargs))

    def error(self, msg, *args, **kwargs):
        LOG_QUEUE.put((self.logger_object.error, msg, args, kwargs))

    def warning(self, msg, *args, **kwargs):
        LOG_QUEUE.put((self.logger_object.warning, msg, args, kwargs))

    def critical(self, msg, *args, **kwargs):
        LOG_QUEUE.put((self.logger_object.critical, msg, args, kwargs))


# Create and output a logger wrap object which will be sending the logging messages to a single log thread
def create_routing_log(log_name, log_hierarchy):
    # Create log directory, if it's not been created already
    if not os.path.exists(PATH_TO_LOGS):
        os.makedirs(PATH_TO_LOGS)

    log_formatter = logging.Formatter('%(asctime)s %(levelname)s %(funcName)s(%(lineno)d) %(message)s')
    log_file = PATH_TO_LOGS + log_name
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
        # Create and return the log wrapper object
        log_wrapper_object = LogWrapper(routing_log)

        return log_wrapper_object

    routing_log.setLevel(LOG_LEVEL)
    routing_log.addHandler(log_handler)

    # Create and return the log wrapper object
    log_wrapper_object = LogWrapper(routing_log)

    return log_wrapper_object


# Initialize the log thread
def init_log_thread():
    global LOG_THREAD
    LOG_THREAD = LoggingHandler()
    LOG_THREAD.start()


# Stop the log thread
def stop_log_thread():
    LOG_THREAD.quit()
