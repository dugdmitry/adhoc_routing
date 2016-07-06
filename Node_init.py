#!/usr/bin/python
"""
Created on Sep 25, 2014

@author: Dmitrii Dugaev
"""

import DataHandler
import RouteTable
import Transport
import NeighborDiscovery

import Queue
import sys
import os
import time
import atexit
from signal import SIGINT, SIGTERM

# Get DEV name from the default configuration file
from conf import DEV, UDS_ADDRESS, ABSOLUTE_PATH, SET_TOPOLOGY_FLAG
# Import module for handling the logging
import routing_logging


# Default daemon parameters.
REDIRECT_TO = "/tmp/routing_output.log"
PIDFILE_PATH = "/tmp/routing_daemon.pid"
# Path to a topology configuration
TOPOLOGY_PATH = ABSOLUTE_PATH + "topology.conf"

# Set root logger
ROUTING_LOG = routing_logging.create_routing_log("routing.log", "root")


class Daemon:
    """
    A generic daemon class.

    Usage: subclass the Daemon class and override the run() method
    """
    def __init__(self, pidfile, stdin="/dev/null", stdout=REDIRECT_TO, stderr=REDIRECT_TO):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile
        # Erase all output from previous daemons
        f = open(REDIRECT_TO, "w")
        f.write("\n" + "-" * 100 + "\n")
        f.close()

    def daemonize(self):
        """
        do the UNIX double-fork magic, see Stevens' "Advanced
        Programming in the UNIX Environment" for details (ISBN 0201563177)
        http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
        """
        try:
            pid = os.fork()
            if pid > 0:
                # exit first parent
                sys.exit(0)
        except OSError, e:
            sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        # decouple from parent environment
        # os.chdir("/")
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
        atexit.register(self.delpid)
        pid = str(os.getpid())
        file(self.pidfile, 'w+').write("%s\n" % pid)

    def delpid(self):
        os.remove(self.pidfile)

    def start(self):
        """
        Start the daemon
        """
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

    def stop(self):
        """
        Stop the daemon
        """
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

    def restart(self):
        """
        Restart the daemon
        """
        self.stop()
        self.start()

    def run(self):
        """
        You should override this method when you subclass Daemon. It will be called after the process has been
        daemonized by start() or restart().
        """


# Routing class instance
class RoutingDaemon(Daemon):

    def run(self):
        # Start all logging threads
        routing_logging.start_all_log_threads()

        ROUTING_LOG.info("Running the routing instance...")

        # Get mac address of the network interface
        node_mac = self.get_mac(DEV)
        # Creating a transport for communication with a virtual interface
        app_transport = Transport.VirtualTransport()
        # Creating a raw_transport object for sending DSR-like packets over the given interface
        topology_neighbors = self.get_topology_neighbors(node_mac)
        raw_transport = Transport.RawTransport(DEV, node_mac, topology_neighbors)
        # Create a RouteTable object
        table = RouteTable.Table(node_mac)
        # Create a queue for in coming app data
        app_queue = Queue.Queue()
        # Creating a queue for handling HELLO messages from the NeighborDiscovery
        hello_msg_queue = Queue.Queue()
        # Create a Neighbor routine thread
        neighbor_routine = NeighborDiscovery.NeighborDiscovery(node_mac, app_transport, raw_transport, table, hello_msg_queue)
        # Create app_data handler thread
        data_handler = DataHandler.DataHandler(app_transport, app_queue, hello_msg_queue, raw_transport, table)
        # Creating thread for live configuration / interaction with the running program
        uds_server = Transport.UdsServer(UDS_ADDRESS)

        try:
            # Start app_data thread
            data_handler.run()
            # Start Neighbor Discovery procedure
            neighbor_routine.run()
            # Start uds_server thread
            uds_server.start()

            while True:
                output = app_transport.recv_from_app()
                app_queue.put(output)

        # Catch SIGINT signal, raised by the daemon
        except KeyboardInterrupt:
            # Stop the handlers
            data_handler.stop_threads()
            neighbor_routine.stop_threads()
            # Stop UDS server
            uds_server.quit()
            # Stop all logging threads
            routing_logging.stop_all_log_threads()

        return 0

    # Get the topology neighbors of a given node from the topology_list.
    # It is needed for correct filtering the broadcast frames sent via raw sockets
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
            
    def get_mac(self, interface):
        # Return the MAC address of interface
        try:
            string = open('/sys/class/net/%s/address' % interface).readline()
        except:
            string = "00:00:00:00:00:00"
        return string[:17]


if __name__ == "__main__":
    # Create the routing daemon instance
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
