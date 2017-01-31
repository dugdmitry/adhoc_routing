#!/usr/bin/python
"""
@package RoutingManager
Created on Jan 26, 2017

@author: Dmitrii Dugaev


This module implements an external interface for interaction with the running routing daemon. The communication is done
via command-exchange procedure through the Unix Domain Socket (UDS) interface.
In the future, it can be also implemented via file I/O access, and so on.

Currently, the following command IDs are supported:
2 - get_table - returns a dictionary with current routing table;
3 - get_neighbors - returns a list L3 addresses of current neighbors of the node.
"""


# Import necessary python modules from the standard library
import threading
import subprocess
import socket
import pickle
import os

import routing_logging

MANAGER_LOG = routing_logging.create_routing_log("routing.manager.log", "manager")


## A manager thread which listens for the incoming requests from the established UDS socket.
class Manager(threading.Thread):
    def __init__(self, table):
        super(Manager, self).__init__()
        ## @var running
        # Thread running state bool() flag.
        self.running = False
        ## @var table
        # Reference to RouteTable.Table object.
        self.table = table
        ## @var server_address
        # UDS file location.
        self.server_address = "/tmp/uds_socket"
        ## @var FNULL
        # Create file descriptor for forwarding all the output to /dev/null from subprocess calls.
        self.FNULL = open(os.devnull, "w")
        # Delete the previous uds_socket if it still exists on this address.
        subprocess.call("rm %s" % self.server_address, shell=True, stdout=self.FNULL, stderr=subprocess.STDOUT)
        ## @var sock
        # Create a UDS socket.
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.server_address)
        # Listen for incoming connections
        self.sock.listen(1)
        self.connection = None

    ## Main thread routine. Receives and processes messages from the UDS.
    # @param self The object pointer.
    # @return None
    def run(self):
        self.running = True
        while self.running:
            self.connection = self.sock.accept()[0]
            request = self.connection.recv(4096)

            MANAGER_LOG.debug("Got request from UDS socket: %s", request)

            request = request.split(":")
            if request[0] == "0":
                self.flush_table()

            elif request[0] == "1":
                self.flush_neighbors()

            elif request[0] == "2":
                self.get_table()

            elif request[0] == "3":
                self.get_neighbors()

            else:
                print "Unknown command!", request[0], type(request[0])

    ## Flush all the entries of the current routing table.
    # @param self
    # @return 0 - Success, 1 - Error
    def flush_table(self):
        pass

    ## Flush all the current neighbors of the node.
    # @param self
    # @return 0 - Success, 1 - Error
    def flush_neighbors(self):
        pass

    ## Get and return all the entries of the current routing table.
    # @param self
    # @return Pickled dict() of the routing table, 1 - Error
    def get_table(self):
        table_data = self.table.get_list_of_entries()
        # Send the pickled data back to the client
        self.connection.sendall(pickle.dumps(table_data))

    ## Get and return all the current neighbors of the node.
    # @param self
    # @return 0 - Pickled list() of the L3 addresses of the neighbors, 1 - Error
    def get_neighbors(self):
        neighbors = self.table.get_neighbors_l3_addresses()
        # Send the pickled data back to the client
        self.connection.sendall(pickle.dumps(neighbors))

    ## Stop and quit the thread operation.
    # @param self The object pointer.
    # @return None
    def quit(self):
        self.running = False
        self.sock.close()
