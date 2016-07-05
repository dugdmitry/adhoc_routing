#!/usr/bin/python
"""
Created on Sep 25, 2014

@author: Dmitrii Dugaev
"""

import DataHandler
import RouteTable
import Transport

import NeighborDiscovery

import sys
import os
import signal
import time

import Queue

import getopt

# Get DEV name from the default configuration file
from conf import DEV, UDS_ADDRESS, ABSOLUTE_PATH, SET_TOPOLOGY_FLAG
# Import module for handling the logging
import routing_logging


# Default daemon parameters.
# File mode creation mask of the daemon.
UMASK = 0
REDIRECT_TO = "/tmp/routing_output.log"

# Default maximum for the number of available file descriptors.
MAXFD = 1024

TOPOLOGY_PATH = ABSOLUTE_PATH + "topology.conf"


def create_root_logger():
    global ROUTING_LOG
    ROUTING_LOG = routing_logging.create_routing_log("routing.log", "root")


# Routing class instance
class Routing:
    def __init__(self):
        self.node_mac = ""
        self.dev = ""
        
    def get_parameters(self):
        self.dev = DEV
        self.node_mac = self.get_mac(self.dev)
        return 0
    
    def run(self):
        # Get initial parameters from settings files
        self.get_parameters()
        # Creating a transport for communication with a virtual interface
        app_transport = Transport.VirtualTransport()
        # Creating a raw_transport object for sending DSR-like packets over the given interface
        topology_neighbors = self.get_topology_neighbors()
        raw_transport = Transport.RawTransport(self.dev, self.node_mac, topology_neighbors)
        # Create a RouteTable object
        table = RouteTable.Table(self.node_mac)
        # Create a queue for in coming app data
        app_queue = Queue.Queue()
        # Creating a queue for handling HELLO messages from the NeighborDiscovery
        hello_msg_queue = Queue.Queue()
        # Create a Neighbor routine thread
        neighbor_routine = NeighborDiscovery.NeighborDiscovery(self.node_mac, app_transport, raw_transport, table, hello_msg_queue)
        # Create app_data handler thread
        data_handler = DataHandler.DataHandler(app_transport, app_queue, hello_msg_queue, raw_transport, table)
        # Creating thread for configuring the virtual interface
        uds_server = Transport.UdsServer(UDS_ADDRESS)
        try:
            # Start app_data thread
            data_handler.run()
            # Start Neighbor Discovery procedure
            neighbor_routine.run()
            # Start uds_server thread
            uds_server.start()

            # Creating uds client which sends the commands
            uds_client = Transport.UdsClient(UDS_ADDRESS)
            # Check the options, and set the ip addresses, if needed
            addresses = self.check_options()
            self.assign_addresses(uds_client, addresses)
            
            while True:
                output = app_transport.recv_from_app()
                app_queue.put(output)

        except KeyboardInterrupt:
            data_handler.stop_threads()
            neighbor_routine.stop_threads()
 
            uds_server.quit()
            uds_server._Thread__stop()

        return 0
    
    def assign_addresses(self, uds_client, addresses):
        ipv4, ipv6 = addresses
        if ipv4 != "":
            self.set_ipv4_address(uds_client, ipv4)
        elif ipv6 != "":
            self.set_ipv6_address(uds_client, ipv6)
    
    def check_options(self):
        addresses = ["", ""]                  # Addresses' list in a format ["ipv4", "ipv6"]
        opts = list()
        try:
            opts = getopt.getopt(sys.argv[1:], "h", ["help", "set_ipv4=", "set_ipv6="])[0]
        except getopt.GetoptError:
            ROUTING_LOG.warning("Valid options: --set_ipv4 <ipv4_address> --set_ipv6 <ipv6_address>")
        
        for opt, arg in opts:
            if opt in ("--set_ipv4"):
                addresses[0] = arg
            elif opt in ("--set_ipv6"):
                addresses[1] = arg
                
        return addresses
    
    def set_ipv4_address(self, uds_client, ipv4):
        uds_client.send("ipv4-" + ipv4)                                 # "-" is a delimeter
        
    def set_ipv6_address(self, uds_client, ipv6):
        uds_client.send("ipv6-" + ipv6)                                 # "-" is a delimeter
    
    # Get the topology neighbors of a given node from the topology_list.
    # It is needed for correct filtering the broadcast frames sent via raw sockets
    def get_topology_neighbors(self):
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
            if arr[0] == self.node_mac:
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


# Wraps up everything in daemon
class RoutingDaemon:
    def __init__(self):
        self.current_pid = 0

    def create_pid_file(self, pid):
        with open("/tmp/routing_daemon.pid", "w") as f:
            f.write(str(pid))

    # Check whether the daemon is already running or not
    def check_current_pid(self):
        try:
            with open("/tmp/routing_daemon.pid", "r") as f:
                self.current_pid = int(f.read())
        except IOError, e:
            ROUTING_LOG.warning(str(e))
            ROUTING_LOG.warning("Routing instance is not running: %s", self.current_pid)

            return False
        
        except ValueError, e:
            # The pid has an invalid format or is empty
            ROUTING_LOG.warning("Given PID has an invalid format or is empty: %s", self.current_pid)

            return False
        # Check for the existence of a unix pid
        try:
            os.kill(self.current_pid, 0)
        except OSError:
            # The pid is invalid or there is no such process with the given pid.
            return False
        else:
            return True
        
    def create_daemon(self):
        try:
            # Fork a child process so the parent can exit.  This returns control to
            # the command-line or shell.  It also guarantees that the child will not
            # be a process group leader, since the child receives a new process ID
            # and inherits the parent's process group ID.  This step is required
            # to insure that the next call to os.setsid is successful.
            pid = os.fork()
        except OSError, e:
            raise Exception, "%s [%d]" % (e.strerror, e.errno)
        
        if pid == 0:
            # To become the session leader of this new session and the process group
            # leader of the new process group, we call os.setsid().  The process is
            # also guaranteed not to have a controlling terminal.
            os.setsid()

            # # Create or rewrite corresponding pid-file with the new value of pid
            # self.create_pid_file(os.getpid())
            # # Run the whole routing stuff
            # self.routing.run()

            try:
                # Fork a second child and exit immediately to prevent zombies.  This
                # causes the second child process to be orphaned, making the init
                # process responsible for its cleanup.  And, since the first child is
                # a session leader without a controlling terminal, it's possible for
                # it to acquire one by opening a terminal in the future (System V-
                # based systems).  This second fork guarantees that the child is no
                # longer a session leader, preventing the daemon from ever acquiring
                # a controlling terminal.
                pid = os.fork()	# Fork a second child.
            except OSError, e:
                raise Exception, "%s [%d]" % (e.strerror, e.errno)

            if (pid == 0):  # The second child.
                # Since the current working directory may be a mounted filesystem, we
                # avoid the issue of not being able to unmount the filesystem at
                # shutdown time by changing it to the root directory.
                os.chdir(ABSOLUTE_PATH)
                # We probably don't want the file mode creation mask inherited from
                # the parent, so we give the child complete control over permissions.
                os.umask(UMASK)

            else:
                # exit() or _exit()?  See below.
                os._exit(0)     # Exit parent (the first child) of the second child.

        else:
            os._exit(0)    # Exit parent of the first child.

        # Iterate through and close all file descriptors.
        for fd in range(0, 2):
            try:
                os.close(fd)
            except OSError:     # ERROR, fd wasn't open to begin with (ignored)
                pass

        # Redirect the standard I/O file descriptors to the specified file.  Since
        # the daemon has no controlling terminal, most daemons redirect stdin,
        # stdout, and stderr to /dev/null.  This is done to prevent side-effects
        # from reads and writes to the standard I/O file descriptors.

        # This call to open is guaranteed to return the lowest file descriptor,
        # which will be 0 (stdin), since it was closed above.
        # ## Make an error redirection of a single program execution to the output file ## #
        f = open(REDIRECT_TO, "w")
        f.write("\n" + "-" * 100 + "\n")
        f.close()
        self.fout = os.open(REDIRECT_TO, os.O_RDWR)	# standard input (0)

        # Duplicate standard input to standard output and standard error.
        os.dup2(0, 1)			# standard output (1)
        os.dup2(0, 2)			# standard error (2)

        # Create or rewrite corresponding pid-file with the new value of pid
        self.create_pid_file(os.getpid())

        # Run the whole routing stuff
        routing = Routing()
        routing.run()

    def start(self):
        # Check whether the daemon is already running or not
        running = self.check_current_pid()
        if running:
            ROUTING_LOG.info("The previous process is still running! Do nothing.")

            return 0
        else:
            # Create and run routing daemon
            self.create_daemon()
    
    def stop(self):
        # Check whether the daemon is already running or not
        running = self.check_current_pid()
        if running:
            ROUTING_LOG.info("Sending CTRL-C to the process...")

            os.kill(self.current_pid, signal.SIGINT)
        else:
            ROUTING_LOG.info("The process does not exist. Nothing to stop here.")
    
    def restart(self):
        # Check whether the daemon is already running or not
        running = self.check_current_pid()
        if running:
            ROUTING_LOG.info("Found the process. Terminating it.")

            os.kill(self.current_pid, signal.SIGINT)
            time.sleep(0.2)
            ROUTING_LOG.info("Starting the process...")

            self.create_daemon()
        else:
            ROUTING_LOG.info("No process found. Starting a new one...")

            self.create_daemon()

if __name__ == "__main__":
    # Create root logger
    create_root_logger()
    # ## Creating routing and daemon instances ## #
    daemon = RoutingDaemon()
    # Creating unix domain client for sending commands
    uds_client = Transport.UdsClient(UDS_ADDRESS)
    # ## Correctly parse input arguments and options ## #
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", ["help", "set_ipv4=", "set_ipv6="])
    except getopt.GetoptError:
        ROUTING_LOG.info("Valid options: --set_ipv4 <ipv4_address> --set_ipv6 <ipv6_address>")
        print "Valid options: --set_ipv4 <ipv4_address> --set_ipv6 <ipv6_address>"

        sys.exit(2)
    if len(args) <= 1:
        # Check last input argument
        if len(args) == 1:
            if "start" == args[0]:
                daemon.start()
            elif "stop" == args[0]:
                daemon.stop()
            elif "restart" == args[0]:
                daemon.restart()
            else:
                ROUTING_LOG.info("Unknown command.")
                print "Unknown command."

        # If an option is set, assign the given ip address to the app_trasport
        else:
            for opt, arg in opts:
                if opt in ("-h", "--help"):
                    ROUTING_LOG.info("Usage: %s --set_ipv4 <ipv4_address> --set_ipv6 <ipv6_address> [start|stop|restart]", sys.argv[0])
                    print "Usage: %s --set_ipv4 <ipv4_address> --set_ipv6 <ipv6_address> [start|stop|restart]" % sys.argv[0]

                    sys.exit()
                elif opt in ("--set_ipv4"):
                    ipv4_address = arg
                    # Check whether the daemon is still running
                    running = daemon.check_current_pid()
                    if running:
                        # Send the ipv4 address to uds_server
                        uds_client.send("ipv4-" + ipv4_address)                     # "-" is a delimeter
                    else:
                        ROUTING_LOG.info("The daemon is not running!")
                        print "The daemon is not running!"

                elif opt in ("--set_ipv6"):
                    ipv6_address = arg
                    # Check whether the daemon is still running
                    running = daemon.check_current_pid()
                    if running:
                        # Send the ipv6 address to uds_server
                        uds_client.send("ipv6-" + ipv6_address)                     # "-" is a delimeter
                    else:
                        ROUTING_LOG.info("The daemon is not running!")
                        print "The daemon is not running!"

    else:
        ROUTING_LOG.info("Usage: %s [options] start|stop|restart", sys.argv[0])
        print "Usage: %s [options] start|stop|restart" % sys.argv[0]
