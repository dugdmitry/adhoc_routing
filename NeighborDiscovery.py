#!/usr/bin/python
"""
Created on Feb 23, 2015

@author: dmitry
"""

import Messages
import threading
import time
import pickle

import logging
import routing_logging

# Set logging level
LOG_LEVEL = logging.INFO
# Set up logging
# neighbor_log_handler = routing_logging.create_routing_handler("routing.neighbor_discovery.log", LOG_LEVEL)
# NEIGHBOR_LOG = logging.getLogger("root.neighbor_discovery")
# NEIGHBOR_LOG.setLevel(LOG_LEVEL)
# NEIGHBOR_LOG.addHandler(neighbor_log_handler)

NEIGHBOR_LOG = routing_logging.create_routing_log("routing.neighbor_discovery.log", "neighbor_discovery", LOG_LEVEL)
# NEIGHBOR_LOG = routing_logging.create_routing_log("routing.neighbor_discovery.log", "root.neighbor_discovery", LOG_LEVEL)


class Neighbor:
    def __init__(self):
        self.l3_addresses = []
        self.mac = ""
        self.last_activity = time.time()


class ProcessNeighbors:
    def __init__(self, node_mac, table_obj):
        self.table = table_obj          # Route table
        self.neighbors_list = {}        # List of current neighbors in a form {ip, neighbor_object}
        # self.own_ip = ip
        
        self.node_mac = node_mac
        
        self.expiry_interval = 5
        self.last_expiry_check = time.time()
        
    def process_neighbor(self, data):
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
            # print "Neighbor's IPs:", self.neighbors_list[mac].l3_addresses

            NEIGHBOR_LOG.debug("Neighbor's IPs: %s", str(self.neighbors_list[mac].l3_addresses))

            for addr in self.neighbors_list[mac].l3_addresses:
                if addr:
                    f.write(addr)
            f.write("\n")
        f.close()

    def check_expired_neighbors(self):
        keys_to_delete = []
        for n in self.neighbors_list:
            if (time.time() - self.neighbors_list[n].last_activity) > self.expiry_interval:
                keys_to_delete.append(n)
        # Deleting from the neighbors' list
        for k in keys_to_delete:
            # print "Neighbor has gone offline. Removing", k

            NEIGHBOR_LOG.info("Neighbor has gone offline. Removing: %s", str(k))

            # Deleting from the Route Table
            self.del_neighbor_entry(self.neighbors_list[k].mac)
            # Deleting this key from the dictionary
            del self.neighbors_list[k]

    def add_neighbor_entry(self, data):
        # Add an entry in the route table in a form (dest_mac, next_hop_mac, n_hops)
        # print "Adding a new neighbor:", data.mac

        NEIGHBOR_LOG.info("Adding a new neighbor: %s", str(data.mac))
        
        # Add an entry in the route table in a form (dst_mac, next_hop_mac, n_hops)
        self.table.add_entry(data.mac, data.mac, 1)
        
        return True
    
    def del_neighbor_entry(self, mac):
        self.table.del_entries(mac)
        return True


class ListenNeighbors(threading.Thread):
    def __init__(self, node_mac, table_obj, hello_msg_queue):
        super(ListenNeighbors, self).__init__()
        # self.port = 5000
        self.running = True
        self.neighbors = ProcessNeighbors(node_mac, table_obj)
        # self.listen_socket = Transport.ReceiveTransport(self.port)
        # self.listen_raw_socket = Transport.RawTransport(dev)
        self.hello_msg_queue = hello_msg_queue
        
    def run(self):
        while self.running:
            data = self.hello_msg_queue.get()
            # data = self.listen_raw_socket.recv_raw_frame()
            # print "Received data:", data.ip, data.mac
            # print "Neighbors list:", self.neighbors.neighbors_list

            self.neighbors.process_neighbor(pickle.loads(data))
            
    def quit(self):
        # self.listen_raw_socket.close_raw_recv_socket()
        # self.listen_socket.close_recv_socket()
        self.running = False


class AdvertiseNeighbor(threading.Thread):
    def __init__(self, node_mac, app_transport_obj, raw_transport_obj):
        super(AdvertiseNeighbor, self).__init__()
        
        self.message = Messages.HelloMessage()
        self.message.mac = node_mac
        self.broadcast_mac = "ff:ff:ff:ff:ff:ff"
        self.dsr_header = Messages.DsrHeader(1)   # Type 1 corresponds to the HELLO message
        self.dsr_header.src_mac = node_mac
        self.dsr_header.tx_mac = node_mac
        
        self.running = True
        self.broadcast_interval = 3
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

        # print "Sending raw HELLO message"

        NEIGHBOR_LOG.info("Sending raw HELLO message")

        self.raw_transport.send_raw_frame(self.broadcast_mac, self.dsr_header, pickle.dumps(self.message))
        self.message.retries += 1
    
    def quit(self):
        self.running = False


class NeighborDiscovery:
    def __init__(self, node_mac, app_transport_obj, raw_transport_obj, table_obj, hello_msg_queue):
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
        
        # print "NeighborDiscovery threads are stopped"

        NEIGHBOR_LOG.info("NeighborDiscovery threads are stopped")

