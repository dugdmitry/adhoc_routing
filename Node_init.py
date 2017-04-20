#!/usr/bin/python
"""
@package Node_init
Created on Sep 25, 2014

@author: Dmitrii Dugaev


This module is a starting point of the program. It performs two main operations - first, provides methods for correctly
daemonizing the application after start, second, provides the main initialization point for all supporting threads and
handlers, used by the the program, as well as the de-construction routine after killing the daemon.
"""

# Import necessary python modules from the standard library
import sys
import os
import time
import atexit
from signal import SIGINT, SIGTERM

# Import the necessary modules of the program
import RoutingManager
import DataHandler
import RouteTable
import Transport
# Get DEV name from the default configuration file
from conf import DEV, SET_TOPOLOGY_FLAG
# Import module for handling the logging
import routing_logging


# Default daemon parameters
## @var REDIRECT_TO
# This constant defines a string with an absolute path to the stdout file of the daemon.
# In case if the program crashes, the last crash output will be written in this file.
REDIRECT_TO = routing_logging.PATH_TO_LOGS + "crash_output.log"
## @var PIDFILE_PATH
# This constant defines a string with an absolute path to the daemon's pid file.
PIDFILE_PATH = "/sdcard/adhoc_routing/run/routing_daemon.pid"
# Path to a topology configuration
## @var ABSOLUTE_PATH
# This constant is a string with an absolute path to the program's main directory.
ABSOLUTE_PATH = routing_logging.ABSOLUTE_PATH
## @var TOPOLOGY_PATH
# This constant is a string with an absolute path to the file with pre-defined network topology.
# This file will be used for incoming frames filtering if the "SET_TOPOLOGY_FLAG" in the conf.py
# configuration file will be set to True.
TOPOLOGY_PATH = ABSOLUTE_PATH + "/topology.conf"

# Set root logger
## @var ROUTING_LOG
# Contains a reference to routing_logging.LogWrapper object of the main root logger for writing
# the log messages of the main module.
ROUTING_LOG = routing_logging.create_routing_log("routing.log", "root")


## A class used for creating and managing the application daemon.
# A generic daemon class for starting the main running function by overriding the run() method.
class Daemon:
    ## Constructor
    # @param self The object pointer.
    # @param pidfile An absolute path to the pid file of the process.
    # @param stdin Path for stdin forwarding
    # @param stdout Path for stdout forwarding
    # @param stderr Path for stderr forwarding
    def __init__(self, pidfile, stdin="/dev/null", stdout=REDIRECT_TO, stderr=REDIRECT_TO):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile
        # Erase all output from previous daemons
        f = open(REDIRECT_TO, "w")
        f.write("\n" + "-" * 100 + "\n")
        f.close()

    ## Daemonize the process and do all the routine related to that
    # @param self The object pointer.
    def daemonize(self):
        # Fork the process
        try:
            pid = os.fork()
            if pid > 0:
                # exit first parent
                sys.exit(0)
        except OSError, e:
            sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        # decouple from parent environment
        os.chdir(ABSOLUTE_PATH)
        os.setsid()
        os.umask(0)

        # do second fork
        try:
            pid = os.fork()
            if pid > 0:
                # exit from second parent
                sys.exit(0)
        except OSError, e:
            sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        # redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        si = file(self.stdin, 'r')
        so = file(self.stdout, 'a+')
        # se = file(self.stderr, 'a+', 0)
        se = file(self.stderr, 'a+')
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())

        # write pidfile
        atexit.register(self.del_pid)
        pid = str(os.getpid())
        file(self.pidfile, 'w+').write("%s\n" % pid)

    ## Delete the pid file.
    # @param self The object pointer.
    def del_pid(self):
        os.remove(self.pidfile)

    ## Start the daemon.
    # @param self The object pointer.
    def start(self):
        # Check for a pidfile to see if the daemon already runs
        try:
            pf = file(self.pidfile, 'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if pid:
            message = "pidfile %s already exist. Daemon already running?\n"
            sys.stderr.write(message % self.pidfile)
            sys.exit(1)

        # Start the daemon
        self.daemonize()
        self.run()

    ## Stop the daemon
    # @param self The object pointer.
    def stop(self):
        # Get the pid from the pidfile
        try:
            pf = file(self.pidfile, 'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if not pid:
            message = "pidfile %s does not exist. Daemon not running?\n"
            sys.stderr.write(message % self.pidfile)
            return  # not an error in a restart

        # Try killing the daemon process
        try:
            # SIGINT needed for correctly quitting the threads (e.g., deleting the uds socket file) before killing
            os.kill(pid, SIGINT)
            time.sleep(0.1)
            while 1:
                os.kill(pid, SIGTERM)
                time.sleep(0.1)
        except OSError, err:
            err = str(err)
            if err.find("No such process") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
            else:
                print str(err)
                sys.exit(1)

    ## Restart the daemon.
    # @param self The object pointer.
    def restart(self):
        self.stop()
        self.start()

    ## Default method for overriding by the child class which inherited the Daemon.
    # It will be called after the process has been daemonized by start() or restart().
    # @param self The object pointer.
    def run(self):
        pass


## Generic routing class.
# This is a generic routing class which initializes all the supporting classes, and runs the process in the main loop.
# It also catches the SIGINT signals from the daemon when the program shuts down.
class RoutingDaemon(Daemon):
    ## Main run method.
    # @param self The object pointer.
    def run(self):
        # Initialize and start the log thread
        routing_logging.init_log_thread()

        ROUTING_LOG.info("Running the routing instance...")

        # Get mac address of the network interface
        node_mac = Transport.get_mac(DEV)
        # Get a list of neighbors MAC addresses to be accepted (if the TOPOLOGY_FLAG is True).
        topology_neighbors = self.get_topology_neighbors(node_mac)
        # Creating a transport for communication with a virtual interface
        app_transport = Transport.VirtualTransport()
        # Creating a transport for communication with network physical interface
        raw_transport = Transport.RawTransport(DEV, node_mac, topology_neighbors)
        # Create a RouteTable object
        table = RouteTable.Table(node_mac)

        # Create data handler thread to process all incoming and outgoing messages
        data_handler = DataHandler.DataHandler(app_transport, raw_transport, table)

        # Creating thread for live configuration / interaction with the running program
        uds_server = RoutingManager.Manager(table)

        try:
            # Start data handler thread
            data_handler.run()

            # Start uds_server thread
            uds_server.start()

            while True:
                packet = app_transport.recv_from_app()
                data_handler.app_handler.process_packet(packet)

        # Catch SIGINT signal, raised by the daemon
        except KeyboardInterrupt:
            # Stop the handlers
            data_handler.stop_threads()

            # Stop UDS server
            uds_server.quit()

            # Stop the log thread
            routing_logging.stop_log_thread()

        return 0

    ## Get the topology neighbors of a given node from the topology_list.
    # It is needed for correct filtering of the incoming frames from the raw socket.
    # @param self The object pointer.
    # @param node_mac The MAC address in a form "xx:xx:xx:xx:xx:xx" of the node's physical network interface used for
    # communication.
    def get_topology_neighbors(self, node_mac):
        # Open a default topology file, if it exists
        try:
            f = open(TOPOLOGY_PATH, "r")
        except IOError:
            # No such file on this path
            ROUTING_LOG.warning("Could not open default topology file!!!")
            if SET_TOPOLOGY_FLAG:
                ROUTING_LOG.warning("All incoming frames will be filtered out!!!")
            return list()

        data = f.read()[:-1]
        entries = data.split("\n\n")
        for ent in entries:
            arr = ent.split("\n")
            if arr[0] == node_mac:
                neighbors = arr[1:]
                return neighbors

        # If nothing was found, return an empty list
        return list()


if __name__ == "__main__":
    ## @var routing
    # Main routing daemon object.
    routing = RoutingDaemon(PIDFILE_PATH)

    if len(sys.argv) == 2:
        if 'start' == sys.argv[1]:
            routing.start()
        elif 'stop' == sys.argv[1]:
            routing.stop()
        elif 'restart' == sys.argv[1]:
            routing.restart()
        else:
            print "Unknown command"
            sys.exit(2)
        sys.exit(0)
    else:
        print "usage: %s start|stop|restart" % sys.argv[0]
        sys.exit(2)
