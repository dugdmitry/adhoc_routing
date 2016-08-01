#!/usr/bin/python
"""
Created on Feb 23, 2015

@author: Dmitrii
"""

import Messages
import threading
import time
import pickle

import routing_logging

lock = threading.Lock()

NEIGHBOR_LOG = routing_logging.create_routing_log("routing.neighbor_discovery.log", "neighbor_discovery")


# Describes a neighbor and its properties
class Neighbor:
    def __init__(self):
        self.l3_addresses = []
        self.mac = ""
        self.last_activity = time.time()


# Main wrapper class, which start two sub-threads for advertising and listening of Hello messages
class NeighborDiscovery:
    def __init__(self, node_mac, app_transport_obj, raw_transport_obj, table_obj, hello_msg_queue):
        # Create initial empty neighbors file
        f = open("neighbors_file", "w")
        f.close()
        # Create listening and advertising threads
        self.listen_thread = ListenNeighbors(node_mac, table_obj, hello_msg_queue)
        self.advertise_thread = AdvertiseNeighbor(node_mac, app_transport_obj, raw_transport_obj)

    def run(self):
        self.listen_thread.start()
        self.advertise_thread.start()

    def stop_threads(self):
        self.listen_thread.quit()
        self.advertise_thread.quit()

        self.listen_thread._Thread__stop()
        self.advertise_thread._Thread__stop()

        NEIGHBOR_LOG.info("NeighborDiscovery threads are stopped")


# A thread which periodically broadcasts Hello messages to the network, so that the neighboring nodes could detect
# the node's activity and register it as their neighbor
class AdvertiseNeighbor(threading.Thread):
    def __init__(self, node_mac, app_transport_obj, raw_transport_obj):
        super(AdvertiseNeighbor, self).__init__()

        self.message = Messages.HelloMessage()
        self.message.mac = node_mac
        self.broadcast_mac = raw_transport_obj.broadcast_mac
        self.dsr_header = Messages.DsrHeader(1)  # Type 1 corresponds to the HELLO message
        self.dsr_header.src_mac = node_mac
        self.dsr_header.tx_mac = node_mac

        self.running = True
        self.broadcast_interval = 2

        self.app_transport = app_transport_obj
        self.raw_transport = raw_transport_obj

    def run(self):
        while self.running:
            self.send_raw_hello()
            time.sleep(self.broadcast_interval)

    def send_raw_hello(self):
        # Try to get L3 ip address (ipv4 or ipv6) assigned to the node, if there is such one
        node_ips = self.app_transport.get_L3_addresses_from_interface()
        self.message.l3_addresses = node_ips

        NEIGHBOR_LOG.debug("Sending raw HELLO message")

        self.raw_transport.send_raw_frame(self.broadcast_mac, self.dsr_header, pickle.dumps(self.message))
        self.message.retries += 1

    def quit(self):
        self.running = False


# A thread for listening to incoming Hello messages and registering the corresponding neighbors
class ListenNeighbors(threading.Thread):
    def __init__(self, node_mac, table_obj, hello_msg_queue):
        super(ListenNeighbors, self).__init__()
        self.running = True
        # self.neighbors = ProcessNeighbors(node_mac, table_obj)
        self.node_mac = node_mac
        self.table = table_obj
        self.hello_msg_queue = hello_msg_queue

        self.neighbors_list = {}  # List of current neighbors in a form {ip, neighbor_object}
        self.expiry_interval = 7
        self.last_expiry_check = time.time()

    def run(self):
        while self.running:
            data = self.hello_msg_queue.get()
            self.process_neighbor(pickle.loads(data))

    def process_neighbor(self, data):
        # Check if the neighbor was not advertising itself for too long
        if (time.time() - self.last_expiry_check) > self.expiry_interval:
            self.check_expired_neighbors()
            self.last_expiry_check = time.time()
        if data.mac == self.node_mac:
            return False
        if data.mac not in self.neighbors_list:
            neighbor = Neighbor()
            neighbor.l3_addresses = data.l3_addresses
            neighbor.mac = data.mac
            self.neighbors_list[data.mac] = neighbor
            # Adding an entry to the Route Table
            self.add_neighbor_entry(data)
        else:
            self.neighbors_list[data.mac].l3_addresses = data.l3_addresses
            self.neighbors_list[data.mac].last_activity = time.time()

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

    def check_expired_neighbors(self):
        keys_to_delete = []
        for n in self.neighbors_list:
            if (time.time() - self.neighbors_list[n].last_activity) > self.expiry_interval:
                keys_to_delete.append(n)
        # Deleting from the neighbors' list
        for k in keys_to_delete:

            NEIGHBOR_LOG.info("Neighbor has gone offline. Removing: %s", str(k))

            # Deleting from the Route Table
            self.del_neighbor_entry(self.neighbors_list[k].mac)
            # Deleting this key from the dictionary
            del self.neighbors_list[k]

    # Add the neighbor entry to the route table
    def add_neighbor_entry(self, data):
        # Add an entry in the route table in a form (dest_mac, next_hop_mac, n_hops)
        NEIGHBOR_LOG.info("Adding a new neighbor: %s", str(data.mac))

        lock.acquire()
        self.table.add_entry(data.mac, data.mac, 1)
        lock.release()

        return True

    # Delete the neighbor entry from the route table
    def del_neighbor_entry(self, mac):
        # Delete an entry from the route table in a form (dest_mac, next_hop_mac, n_hops)
        NEIGHBOR_LOG.info("Deleting the neighbor: %s", str(mac))

        lock.acquire()
        self.table.del_entries(mac)
        lock.release()

        return True

    def quit(self):
        self.running = False
