#!/usr/bin/python
"""
@package routing_logging
Created on Aug 1, 2016

@author: Dmitrii Dugaev


This module creates logging instances for corresponding routing modules.
It also performs all log writing operations in a single thread, while receiving the messages via queue.
"""

# Import necessary python modules from the standard library
import os
import threading
import Queue
import logging
from logging.handlers import RotatingFileHandler

# Import the necessary modules of the program
from conf import LOG_LEVEL

## @var ABSOLUTE_PATH
# Define an absolute path to the program's directory.
ABSOLUTE_PATH = os.path.dirname(os.path.abspath(__file__))
## @var PATH_TO_LOGS
# Define a default path to log directory.
PATH_TO_LOGS = "/sdcard/adhoc_routing/log/"
## @var LOG_QUEUE
# Define a global queue for receiving the methods from the Logger objects and its arguments.
LOG_QUEUE = Queue.Queue()

## @var LOG_LEVEL
# Set a global variable LOG_LEVEL according to the string variable in conf file.
# Log levels correspond to standard levels defined in the "logging" module.
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


## A thread class which performs all writing operations to the given logging instance.
class LoggingHandler(threading.Thread):
    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        super(LoggingHandler, self).__init__()
        ## @var running
        # Thread running state bool() flag.
        self.running = False
        ## @var root_logger
        # Create a logger instance from the default Python logging module.
        self.root_logger = logging.getLogger()

    ## Main thread routine.
    # Get the log message and its arguments from the queue, write them to the log instance.
    # @param self The object pointer.
    # @return None
    def run(self):
        self.running = True
        self.root_logger.info("STARTING THE LOG THREAD...")
        while self.running:
            # loglevel, msg, args, kwargs = self.logging_queue.get()
            log_object_method, msg, args, kwargs = LOG_QUEUE.get()
            # Execute the method
            log_object_method(msg, *args, **kwargs)

    ## Stop and quit the thread operation.
    # @param self The object pointer.
    # @return None
    def quit(self):
        self.running = False
        self.root_logger.info("STOPPING THE LOG THREAD...")


## Class for overriding default logging methods.
# Handles the log methods (info, debug, error, etc.) called from the modules, and forwards them into the global queue
# so the LoggingHandler thread will perform the actual writing operation.
class LogWrapper:
    ## Constructor.
    # @param self The object pointer.
    # @param logger_object Reference to the Python logger object.
    # @return None
    def __init__(self, logger_object):
        ## @var logger_object
        # Reference to the Python logger object.
        self.logger_object = logger_object
        self.info("THE LOG INSTANCE IS CREATED: %s", self.logger_object.name)

    # Define callbacks which will be used by other modules to send their logging messages to.
    ## Info log method.
    # @param self The object pointer.
    # @param msg Message to be logged.
    # @param *args Arguments to the message, if any.
    # @param **kwargs Key arguments to the message, if any.
    # @return None
    def info(self, msg, *args, **kwargs):
        LOG_QUEUE.put((self.logger_object.info, msg, args, kwargs))

    ## Debug log method.
    # @param self The object pointer.
    # @param msg Message to be logged.
    # @param *args Arguments to the message, if any.
    # @param **kwargs Key arguments to the message, if any.
    # @return None
    def debug(self, msg, *args, **kwargs):
        LOG_QUEUE.put((self.logger_object.debug, msg, args, kwargs))

    ## Error log method.
    # @param self The object pointer.
    # @param msg Message to be logged.
    # @param *args Arguments to the message, if any.
    # @param **kwargs Key arguments to the message, if any.
    # @return None
    def error(self, msg, *args, **kwargs):
        LOG_QUEUE.put((self.logger_object.error, msg, args, kwargs))

    ## Warning log method.
    # @param self The object pointer.
    # @param msg Message to be logged.
    # @param *args Arguments to the message, if any.
    # @param **kwargs Key arguments to the message, if any.
    # @return None
    def warning(self, msg, *args, **kwargs):
        LOG_QUEUE.put((self.logger_object.warning, msg, args, kwargs))

    ## Critical log method.
    # @param self The object pointer.
    # @param msg Message to be logged.
    # @param *args Arguments to the message, if any.
    # @param **kwargs Key arguments to the message, if any.
    # @return None
    def critical(self, msg, *args, **kwargs):
        LOG_QUEUE.put((self.logger_object.critical, msg, args, kwargs))


## Create and output a logger wrap object which will be sending the logging messages to a single log thread.
# @param log_name Name of the log file.
# @param log_hierarchy Hierarchy of the log.
# @return LogWrapper object.
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


## Initialize the log thread.
def init_log_thread():
    global LOG_THREAD
    LOG_THREAD = LoggingHandler()
    LOG_THREAD.start()


## Stop the log thread.
def stop_log_thread():
    LOG_THREAD.quit()
