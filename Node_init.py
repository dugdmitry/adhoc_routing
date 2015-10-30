#!/usr/bin/python
'''
Created on Sep 25, 2014

@author: Dmitrii Dugaev
'''

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
from conf import DEV, UDS_ADDRESS

# Default paths to node settings and topology configuration
#SETTINGS_PATH = "settings.conf"
TOPOLOGY_PATH = "topology.conf"

UDS_PATH = "/tmp/uds_socket"

# Class for logging everything which is printed on the screen
class Logger(object):
    def __init__(self, filename="routing.log"):
        self.terminal = sys.stdout
        self.log = open(filename, "a")

    def write(self, message):
        self.terminal.write(message)            # Output to console
        self.log.write(message)                  # Output to log-file
        # For immediate record to the log file, flush every time
        self.log.flush()
        
    def _print(self, message):
        self.terminal.write(message)
        
# Routing class instance
class Routing():
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
        app_transport = Transport.VirtualTransport()                   # "self." here is needed for setting ip addresses in real time from options
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
        neighbor_routine = NeighborDiscovery.NeighborDiscovery(self.node_mac, raw_transport, table, hello_msg_queue)
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
                print "Packet received from app_transport"
                app_queue.put(output)
                #print "Got data from app:", output
                
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
        addresses = ["", ""]                  # Adddresses' list in a format ["ipv4", "ipv6"]
        try:
            opts = getopt.getopt(sys.argv[1:], "h", ["help", "set_ipv4=", "set_ipv6="])[0]
        except getopt.GetoptError:
            print "Valid options: --set_ipv4 <ipv4_address> --set_ipv6 <ipv6_address>"
        
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
    
    # Get the topology neighbors of a given node from the topology_list. It is needed for correct filtering the broadcast frames sent via raw sockets.
    def get_topology_neighbors(self):
        f = open(TOPOLOGY_PATH, "r")
        data = f.read()[:-1]
        entries = data.split("\n\n")
        for ent in entries:
            arr = ent.split("\n")
            if arr[0] == self.node_mac:
                neighbors = arr[1:]
                return neighbors
            
    def get_mac(self, interface):
        # Return the MAC address of interface
        try:
            string = open('/sys/class/net/%s/address' % interface).readline()
        except:
            string = "00:00:00:00:00:00"
        return string[:17]

# Wraps up everything in daemon
class RoutingDaemon():
    def __init__(self, routing):
        self.routing = routing
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
            print e
            print "pid", self.current_pid
            return False
        
        except ValueError, e:
            print e
            print "PID:", self.current_pid
            # The pid has an invalid format or is empty
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
            # Create or rewrite corresponding pid-file with the new value of pid
            self.create_pid_file(os.getpid())
            
            # Run the whole routing stuff
            self.routing.run()
            
        else:
            os._exit(0)    # Exit parent of the first child.
            
    def start(self):
        # Check whether the daemon is already running or not
        running = self.check_current_pid()
        if running:
            sys.stdout._print("The previous process is still running! Do nothing.\n")
            return 0
        else:
            # Create and run routing daemon
            self.create_daemon()
    
    def stop(self):
        # Check whether the daemon is already running or not
        running = self.check_current_pid()
        if running:
            sys.stdout._print("Sending CTRL-C to the process...\n")
            os.kill(self.current_pid, signal.SIGINT)
        else:
            sys.stdout._print("The process does not exist. Nothing to stop here.\n")
    
    def restart(self):
        # Check whether the daemon is already running or not
        running = self.check_current_pid()
        if running:
            sys.stdout._print("Found the process. Terminating it.\n")
            os.kill(self.current_pid, signal.SIGINT)
            time.sleep(0.2)
            sys.stdout._print("Starting the process.\n")
            self.create_daemon()
        else:
            sys.stdout._print("No process found. Starting a new one.\n")
            self.create_daemon()
            
if __name__ == "__main__":
    # Logging everything to a file
    sys.stdout = Logger()
    ### Creating routing and daemon instances ###
    routing = Routing()
    daemon = RoutingDaemon(routing)
    # Creating unix domain client for sending commands
    uds_client = Transport.UdsClient(UDS_ADDRESS)
    ### Correctly parse input arguments and options ###
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", ["help", "set_ipv4=", "set_ipv6="])
    except getopt.GetoptError:
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
                sys.stdout._print("Unknown command.\n")
        # If an option is set, assign the given ip address to the app_trasport
        else:
            for opt, arg in opts:
                if opt in ("-h", "--help"):
                    print "Usage: %s --set_ipv4 <ipv4_address> --set_ipv6 <ipv6_address> [start|stop|restart]\n" % sys.argv[0]
                    sys.exit()
                elif opt in ("--set_ipv4"):
                    ipv4_address = arg
                    # Check whether the daemon is still running
                    running = daemon.check_current_pid()
                    if running:
                        # Send the ipv4 address to uds_server
                        uds_client.send("ipv4-" + ipv4_address)                     # "-" is a delimeter
                    else:
                        print "The daemon is not running!"
                        
                elif opt in ("--set_ipv6"):
                    ipv6_address = arg
                    # Check whether the daemon is still running
                    running = daemon.check_current_pid()
                    if running:
                        # Send the ipv6 address to uds_server
                        uds_client.send("ipv6-" + ipv6_address)                     # "-" is a delimeter
                    else:
                        print "The daemon is not running!"
                
    else:
        sys.stdout._print("Usage: %s [options] start|stop|restart\n" % sys.argv[0])
    
    
    
    
    
    
        