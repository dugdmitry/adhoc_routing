#!/usr/bin/python
"""
@package NeighborDiscovery
Created on Feb 23, 2015

@author: Dmitrii Dugaev


This module provides functionality for a procedure of a node's neighbors discovery by periodically broadcasting and
receiving HELLO service message into/from the network.
The module is responsible for both broadcasting the HELLO messages, as well as for correctly processing the incoming
HELLO messages from the neighbors, updating the corresponding entries in the routing table, and maintaining the list of
currently available neighbors, which includes deleting the expired/non-answering neighbors, and adding the new ones.
"""

# Import necessary python modules from the standard library
import Messages
import Transport
import threading
import time
from socket import inet_aton
from socket import error as sock_error

# Import the necessary modules of the program
import routing_logging

## @var ABSOLUTE_PATH
# This constant stores a string with an absolute path to the program's main directory.
ABSOLUTE_PATH = routing_logging.ABSOLUTE_PATH
## @var NEIGHBOR_LOG
# Global routing_logging.LogWrapper object for logging NeighborDiscovery activity.
NEIGHBOR_LOG = routing_logging.create_routing_log("routing.neighbor_discovery.log", "neighbor_discovery")


## Class describing a neighbor and its properties.
class Neighbor:
    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        ## @var l3_addresses
        # List of a neighbor's L3 (both IPv4 and IPv6) addresses in a string representation.
        self.l3_addresses = list()
        ## @var mac
        # MAC address of a neighbor, in a string "xx:xx:xx:xx:xx:xx" format.
        self.mac = str()
        ## @var last_activity
        # Timestamp of the last registered activity of a neighbor, i.e. the last time the node has received the HELLO
        # message from this neighbor. float().
        self.last_activity = time.time()


## Main wrapper class, which starts the classes for advertising and listening of Hello messages.
class NeighborDiscovery:
    ## Constructor.
    # @param self The object pointer.
    # @param raw_transport_obj Reference to Transport.RawTransport object.
    # @param table_obj Reference to RouteTable.Table object.
    # @return None
    def __init__(self, raw_transport_obj, table_obj):
        # Create initial empty neighbors file
        f = open(ABSOLUTE_PATH + "/neighbors_file", "w")
        f.close()
        # Create listening and advertising threads
        ## @var listen_neighbors_handler
        # Create and store an object of ListenNeighbors class.
        self.listen_neighbors_handler = ListenNeighbors(raw_transport_obj.node_mac, table_obj)
        ## @var advertise_thread
        # Create and store an object of AdvertiseNeighbor class.
        self.advertise_thread = AdvertiseNeighbor(raw_transport_obj, table_obj)

    ## Start the advertising thread.
    # @param self The object pointer.
    # @return None
    def run(self):
        self.advertise_thread.start()

    ## Stop the advertising thread.
    # @param self The object pointer.
    # @return None
    def stop_threads(self):
        self.advertise_thread.quit()
        NEIGHBOR_LOG.info("NeighborDiscovery threads are stopped")


## Class for periodically broadcasting HELLO message from the node.
# A thread which periodically broadcasts Hello messages to the network, so that the neighboring nodes could detect
# the node's activity and register it as their neighbor.
# Also, this thread is used for periodically printing out the entries of the route table.
class AdvertiseNeighbor(threading.Thread):
    ## Constructor.
    # @param self The object pointer.
    # @param raw_transport_obj Reference to Transport.RawTransport object.
    # @param table_obj Reference to RouteTable.Table object.
    # @return None
    def __init__(self, raw_transport_obj, table_obj):
        super(AdvertiseNeighbor, self).__init__()
        ## @var running
        # Thread running state bool() flag.
        self.running = False
        ## @var current_node_ips
        # Store current IP addresses of this node. list().
        self.current_node_ips = [None]
        ## @var message
        # Create and store the default Messages.HelloMessage object used for broadcasting.
        self.message = Messages.HelloMessage()
        ## @var broadcast_mac
        # Reference to Transport.RawTransport.broadcast_mac default value.
        self.broadcast_mac = raw_transport_obj.broadcast_mac
        ## @var broadcast_interval
        # Default value of a broadcast time interval between the Hello messages.
        self.broadcast_interval = 2
        ## @var raw_transport
        # Reference to Transport.RawTransport object.
        self.raw_transport = raw_transport_obj
        ## @var table_obj
        # Reference to RouteTable.Table object.
        self.table_obj = table_obj
        ## @var node_mac
        # Reference to the node's own MAC address, stored in Transport.RawTransport.node_mac.
        self.node_mac = raw_transport_obj.node_mac

    ## Main thread routine.
    # @param self The object pointer.
    # @return None
    def run(self):
        self.running = True
        while self.running:
            # Sending the Hello message
            self.send_raw_hello()
            # Printing out the route table entries
            self.table_obj.print_table()
            time.sleep(self.broadcast_interval)

    ## Update node's own ips in the route table.
    # @param self The object pointer.
    # @param node_ips List of node's IP addresses.
    # @return None
    def update_ips_in_route_table(self, node_ips):
        for ip in node_ips:
            if ip not in self.table_obj.current_node_ips:
                self.table_obj.update_entry(ip, self.node_mac, 100)
        self.table_obj.current_node_ips = node_ips

    ## Broadcast the HELLO message frame to the network.
    # @param self The object pointer.
    # @return None
    def send_raw_hello(self):
        # Try to get L3 ip address (ipv4 or ipv6) assigned to the node, if there are such ones
        node_ips = Transport.get_l3_addresses_from_interface()

        if self.current_node_ips != node_ips:
            # Update entries in RouteTable
            self.update_ips_in_route_table(node_ips)

            # Copy the current list of ips and check for the default routes address in order to properly set
            # the gw_mode value
            if Messages.DEFAULT_ROUTE in node_ips:
                self.message.gw_mode = 1
                ips = node_ips[:-1]

            else:
                self.message.gw_mode = 0
                ips = node_ips

            if ips:
                # Check if the node has IPv4 address assigned
                try:
                    inet_aton(ips[0])
                    self.message.ipv4_count = 1
                    self.message.ipv4_address = ips[0]

                    # If there are some IPv6 addresses in the list -> write them as well
                    self.message.ipv6_count = len(ips[1:])
                    self.message.ipv6_addresses = ips[1:]

                except sock_error:
                    # Otherwise, assign IPv6 addresses
                    self.message.ipv4_count = 0
                    self.message.ipv6_count = len(ips)
                    self.message.ipv6_addresses = ips

            else:
                self.message.ipv4_count = 0
                self.message.ipv6_count = 0

        NEIGHBOR_LOG.debug("Sending HELLO message:\n %s", self.message)

        self.raw_transport.send_raw_frame(self.broadcast_mac, self.message, "")
        self.message.tx_count += 1
        # Update the current list of ips
        self.current_node_ips = node_ips

    ## Stop and quit the thread operation.
    # @param self The object pointer.
    # @return None
    def quit(self):
        self.running = False


## A class for handling incoming Hello messages and registering the corresponding neighbors.
# This class handles the cases when the neighbors disappeared, or some new nodes appeared.
class ListenNeighbors:
    ## Constructor.
    # @param self The object pointer.
    # @param node_mac Reference to the node's own MAC address, stored in Transport.RawTransport.node_mac.
    # @param table_obj Reference to RouteTable.Table object.
    # @return None
    def __init__(self, node_mac, table_obj):
        ## @var node_mac
        # Reference to the node's own MAC address, stored in Transport.RawTransport.node_mac.
        self.node_mac = node_mac
        ## @var table
        # Reference to RouteTable.Table object.
        self.table = table_obj
        ## @var neighbors_list
        # Internal list of current neighbors in a form {mac: neighbor_object}, referenced from
        # RouteTable.Table.neighbors_list.
        self.neighbors_list = table_obj.neighbors_list
        ## @var expiry_interval
        # Expiry timeout interval, after which the neighbor entry is deleted from the neighbors_list if the HELLO
        # message hasn't been received.
        self.expiry_interval = 7
        ## @var last_expiry_check
        # Store a timestamp of the last expiry check event.
        self.last_expiry_check = time.time()

    ## Process the received HELLO message from a neighbor.
    # @param self The object pointer.
    # @param src_mac MAC address of the neighbor that has sent this HELLO message.
    # @param dsr_hello_message Messages.HelloMessage object.
    # @return None
    def process_neighbor(self, src_mac, dsr_hello_message):
        l3_addresses_from_message = []
        if dsr_hello_message.ipv4_count:
            l3_addresses_from_message.append(dsr_hello_message.ipv4_address)

        if dsr_hello_message.ipv6_count:
            for ipv6 in dsr_hello_message.ipv6_addresses:
                l3_addresses_from_message.append(ipv6)

        # Check for the gateway flag
        if dsr_hello_message.gw_mode == 1:
            l3_addresses_from_message.append(Messages.DEFAULT_ROUTE)

        # Check if the neighbor was not advertising itself for too long
        if (time.time() - self.last_expiry_check) > self.expiry_interval:
            self.check_expired_neighbors()
            self.last_expiry_check = time.time()

        if src_mac == self.node_mac:
            NEIGHBOR_LOG.warning("Neighbor has the same mac address as mine! %s", self.node_mac)
            return False

        if src_mac not in self.neighbors_list:
            neighbor = Neighbor()

            neighbor.l3_addresses = l3_addresses_from_message
            neighbor.mac = src_mac

            self.neighbors_list[src_mac] = neighbor
            # Adding an entry to the neighbors list
            self.add_neighbor_entry(neighbor)
            # Add the entries for the received L3 ip addresses to the RouteTable
            for ip in neighbor.l3_addresses:
                self.table.update_entry(ip, src_mac, 50)

        else:
            if self.neighbors_list[src_mac].l3_addresses != l3_addresses_from_message:
                self.neighbors_list[src_mac].l3_addresses = l3_addresses_from_message
                # Add the entries for the received L3 ip addresses to the RouteTable
                for ip in l3_addresses_from_message:
                    self.table.update_entry(ip, src_mac, 50)

            self.neighbors_list[src_mac].last_activity = time.time()

        # Update the file with current list of neighbors' ip addresses
        self.update_neighbors_file()

    ## Create or update the file with current neighbors, derived from ListenNeighbors.neighbors_list.
    # @param self The object pointer.
    # @return None
    def update_neighbors_file(self):
        f = open(ABSOLUTE_PATH + "/neighbors_file", "w")
        for mac in self.neighbors_list:

            NEIGHBOR_LOG.debug("Neighbor's IPs: %s", str(self.neighbors_list[mac].l3_addresses))

            for addr in self.neighbors_list[mac].l3_addresses:
                if addr:
                    f.write(addr)
                    f.write("\n")
            f.write("\n")
        f.close()

    ## Check all the neighbors for the expired timeout. Delete all the expired neighbors.
    # @param self The object pointer.
    # @return None
    def check_expired_neighbors(self):
        macs_to_delete = []
        for n in self.neighbors_list:
            if (time.time() - self.neighbors_list[n].last_activity) > self.expiry_interval:
                macs_to_delete.append(n)
        # Deleting from the neighbors' list
        for mac in macs_to_delete:

            NEIGHBOR_LOG.info("Neighbor has gone offline. Removing: %s", str(mac))

            # Deleting this key from the dictionary
            self.del_neighbor_entry(mac)

    ## Add the neighbor entry to the shared ListenNeighbors.neighbors_list dictionary.
    # @param self The object pointer.
    # @param neighbor A Neighbor object.
    # @return None
    def add_neighbor_entry(self, neighbor):
        NEIGHBOR_LOG.info("Adding a new neighbor: %s", str(neighbor.mac))
        self.neighbors_list.update({neighbor.mac: neighbor})

    # Delete the neighbor entry from the shared dictionary
    def del_neighbor_entry(self, mac):
        NEIGHBOR_LOG.debug("Deleting the neighbor: %s", str(mac))
        if mac in self.neighbors_list:
            del self.neighbors_list[mac]
