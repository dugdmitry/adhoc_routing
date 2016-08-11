#!/usr/bin/python
"""
Created on Feb 23, 2015

@author: Dmitrii Dugaev
"""

import Messages
import Transport
import threading
import time
from socket import inet_aton
from socket import error as sock_error

import routing_logging

NEIGHBOR_LOG = routing_logging.create_routing_log("routing.neighbor_discovery.log", "neighbor_discovery")


# Describes a neighbor and its properties
class Neighbor:
    def __init__(self):
        self.l3_addresses = list()
        self.mac = str()
        self.last_activity = time.time()


# Main wrapper class, which start two sub-threads for advertising and listening of Hello messages
class NeighborDiscovery:
    def __init__(self, raw_transport_obj, table_obj):
        # Create initial empty neighbors file
        f = open("neighbors_file", "w")
        f.close()
        # Create listening and advertising threads
        self.listen_neighbors_handler = ListenNeighbors(raw_transport_obj.node_mac, table_obj)
        self.advertise_thread = AdvertiseNeighbor(raw_transport_obj, table_obj)

    def run(self):
        self.advertise_thread.start()

    def stop_threads(self):
        self.advertise_thread.quit()

        NEIGHBOR_LOG.info("NeighborDiscovery threads are stopped")


# A thread which periodically broadcasts Hello messages to the network, so that the neighboring nodes could detect
# the node's activity and register it as their neighbor.
# Also, this thread is used for periodically printing out the entries of the route table.
class AdvertiseNeighbor(threading.Thread):
    def __init__(self, raw_transport_obj, table_obj):
        super(AdvertiseNeighbor, self).__init__()
        self.running = True
        # Store current IP addresses of this node
        self.current_node_ips = [None]

        self.message = Messages.HelloMessage()
        self.broadcast_mac = raw_transport_obj.broadcast_mac

        self.broadcast_interval = 2

        self.raw_transport = raw_transport_obj
        self.table_obj = table_obj
        self.node_mac = raw_transport_obj.node_mac

    def run(self):
        while self.running:
            # Sending the Hello message
            self.send_raw_hello()
            # Printing out the route table entries
            self.table_obj.print_table()
            time.sleep(self.broadcast_interval)

    # Update node's own ips in the route table
    def update_ips_in_route_table(self, node_ips):
        for ip in node_ips:
            if ip not in self.table_obj.current_node_ips:
                self.table_obj.update_entry(ip, self.node_mac, 100)
        self.table_obj.current_node_ips = node_ips

    def send_raw_hello(self):
        # Try to get L3 ip address (ipv4 or ipv6) assigned to the node, if there are such ones
        node_ips = Transport.get_l3_addresses_from_interface()

        if self.current_node_ips != node_ips:

            # Update entries in RouteTable
            self.update_ips_in_route_table(node_ips)

            if node_ips:
                # Check if the node has IPv4 address assigned
                try:
                    inet_aton(node_ips[0])
                    self.message.ipv4_count = 1
                    self.message.ipv4_address = node_ips[0]

                    # If there are some IPv6 addresses in the list -> write them as well
                    self.message.ipv6_count = len(node_ips)
                    self.message.ipv6_addresses = node_ips[1:]

                except sock_error:
                    # Otherwise, assign IPv6 addresses
                    self.message.ipv4_count = 0
                    self.message.ipv6_count = len(node_ips)
                    self.message.ipv6_addresses = node_ips

            else:
                self.message.ipv4_count = 0
                self.message.ipv6_count = 0

        NEIGHBOR_LOG.debug("Sending HELLO message:\n %s", self.message)

        self.raw_transport.send_raw_frame(self.broadcast_mac, self.message, "")
        self.message.tx_count += 1
        # Update the current list of ips
        self.current_node_ips = node_ips

    def quit(self):
        self.running = False


# A class for handling incoming Hello messages and registering the corresponding neighbors.
# It handles the cases when the neighbors are disappeared, or some new nodes have appeared.
class ListenNeighbors:
    def __init__(self, node_mac, table_obj):
        self.node_mac = node_mac
        self.table = table_obj

        # Internal list of current neighbors in a form {mac: neighbor_object}
        self.neighbors_list = table_obj.neighbors_list
        self.expiry_interval = 7
        self.last_expiry_check = time.time()

    def process_neighbor(self, src_mac, dsr_hello_message):
        l3_addresses_from_message = []
        if dsr_hello_message.ipv4_count:
            l3_addresses_from_message.append(dsr_hello_message.ipv4_address)

        if dsr_hello_message.ipv6_count:
            for ipv6 in dsr_hello_message.ipv6_addresses:
                l3_addresses_from_message.append(ipv6)

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

    # Create and update the file with current neighbors, derived from self.neighbors_list
    def update_neighbors_file(self):
        f = open("neighbors_file", "w")
        for mac in self.neighbors_list:

            NEIGHBOR_LOG.debug("Neighbor's IPs: %s", str(self.neighbors_list[mac].l3_addresses))

            for addr in self.neighbors_list[mac].l3_addresses:
                if addr:
                    f.write(addr)
                    f.write("\n")
            f.write("\n")
        f.close()

    # Check all the neighbors for the expired timeout. Delete all the expired neighbors.
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

    # Add the neighbor entry to the shared dictionary
    def add_neighbor_entry(self, neighbor):
        NEIGHBOR_LOG.info("Adding a new neighbor: %s", str(neighbor.mac))

        self.neighbors_list.update({neighbor.mac: neighbor})

    # Delete the neighbor entry from the shared dictionary
    def del_neighbor_entry(self, mac):
        NEIGHBOR_LOG.debug("Deleting the neighbor: %s", str(mac))
        if mac in self.neighbors_list:
            del self.neighbors_list[mac]
