#!/usr/bin/python
'''
Created on Oct 6, 2014

@author: Dmitrii Dugaev
'''

import Messages
import PathDiscovery

import Queue
import pickle
import threading
from collections import deque

import logging
import routing_logging

lock = threading.Lock()

# Set logging level
LOG_LEVEL = logging.DEBUG
# Set up logging
DATA_LOG = routing_logging.create_routing_log("routing.data_handler.log", "data_handler", LOG_LEVEL)
# DATA_LOG = routing_logging.create_routing_log("routing.data_handler.log", "root.data_handler", LOG_LEVEL)


class AppHandler(threading.Thread):
    def __init__(self, app_queue, wait_queue, raw_transport, table, broadcast_list):
        super(AppHandler, self).__init__()
        self.running = True
        self.app_queue = app_queue
        self.wait_queue = wait_queue
        self.table = table
        self.broadcast_list = broadcast_list
        
        self.transport = raw_transport
        self.node_mac = table.node_mac
        
        self.broadcast_mac = "ff:ff:ff:ff:ff:ff"
        
    def run(self):
        while self.running:
            src_ip, dst_ip, raw_data = self.app_queue.get()

            # Lookup for a corresponding dst_mac in the arp table
            dst_mac = self.table.lookup_mac_address(dst_ip)
            
            # Check whether the destination IP exists in the Route Table
            entry = self.table.lookup_entry(dst_mac)

            # print "DEST_IP:", dst_ip
            
            if dst_ip[:2] == "ff" or dst_ip == "10.0.0.255":
                # print "Multicast IPv6", dst_ip                          # ## IPv4 PACKETS GO UNCHECKED FOR NOW ## #

                DATA_LOG.info("Multicast IPv6: %s", dst_ip)

                # Create a broadcast dsr header
                dsr_header = self.create_dsr_broadcast_header()
                # Put the dsr broadcast id to the broadcast_list
                self.broadcast_list.append(dsr_header.broadcast_id)

                # print "Trying to send the broadcast..."

                DATA_LOG.debug("Trying to send the broadcast...")

                # Broadcast it further to the network
                self.transport.send_raw_frame(self.broadcast_mac, dsr_header, raw_data)

                # print "Broadcast sent!!!"

                DATA_LOG.debug("Broadcast sent!!!")

            elif entry is None:
                # print "No such route in the table. Starting route discovery..."

                DATA_LOG.info("No such route in the table. Starting route discovery...")

                # ## Start PathDiscovery procedure ## #
                # Put packet in wait_queue
                self.wait_queue.put([src_ip, dst_ip, raw_data])
                
            else:
                # print "Found an entry:"
                # self.table.print_entry(entry)

                DATA_LOG.debug("Found an entry: %s", str(entry))

                next_hop_mac = entry.next_hop_mac
                # Create a unicast dsr header with proper values
                dsr_header = self.create_dsr_unicast_header(dst_mac)
                # Send the raw data with dsr_header to the next hop
                self.transport.send_raw_frame(next_hop_mac, dsr_header, raw_data)

        # print "LOOP FINISHED!!!"
        DATA_LOG.debug("LOOP FINISHED!!!")

    def create_dsr_unicast_header(self, dst_mac):
        _type = 0                                       # Type 0 corresponds to the data packets
        dsr_header = Messages.DsrHeader(_type)
        dsr_header.src_mac = self.node_mac
        dsr_header.dst_mac = dst_mac
        dsr_header.tx_mac = self.node_mac
        return dsr_header

    def create_dsr_broadcast_header(self):
        _type = 4                                       # Type 4 corresponds to the broadcast packets
        dsr_header = Messages.DsrHeader(_type)
        dsr_header.src_mac = self.node_mac
        dsr_header.tx_mac = self.node_mac
        dsr_header.broadcast_ttl = 1
        return dsr_header

    def quit(self):
        self.running = False


# Wrapping class for starting app_handler and incoming_data_handler threads
class DataHandler:
    def __init__(self, app_transport, app_queue, hello_msg_queue, raw_transport, table):
        # ## Creating a socket object for exchanging service messages
        # service_transport = Transport.ServiceTransport(table.node_ip, 3001)
        # Creating a queue for receiving RREPs
        rrep_queue = Queue.Queue()
        # Creating a queue for the delayed packets waiting for rrep message
        wait_queue = Queue.Queue()
        # Creating a queue for handling incoming RREQ and RREP packets from the raw_socket
        service_msg_queue = Queue.Queue()
        # Creating a deque list for keeping the received broadcast IDs
        broadcast_list = deque(maxlen=1000000)  # Limit the max length of the list

        # Creating thread objects
        self.path_discovery_thread = PathDiscovery.PathDiscoveryHandler(app_queue, wait_queue, rrep_queue, raw_transport)
        
        self.app_handler_thread = AppHandler(app_queue, wait_queue, raw_transport, table, broadcast_list)
        
        self.service_messages_handler_thread = ServiceMessagesHandler(table, app_transport, raw_transport, rrep_queue, service_msg_queue)
        
        self.incoming_traffic_handler_thread = IncomingTrafficHandler(app_queue, service_msg_queue,
                                                                      hello_msg_queue, app_transport,
                                                                      raw_transport, table, broadcast_list)

    # Starting the threads
    def run(self):
        self.app_handler_thread.start()
        self.incoming_traffic_handler_thread.start()
        self.path_discovery_thread.start()
        self.service_messages_handler_thread.start()
        
    def stop_threads(self):
        self.app_handler_thread.quit()
        self.incoming_traffic_handler_thread.quit()
        self.path_discovery_thread.quit()
        self.service_messages_handler_thread.quit()
        
        self.app_handler_thread._Thread__stop()
        self.incoming_traffic_handler_thread._Thread__stop()
        self.path_discovery_thread._Thread__stop()
        self.service_messages_handler_thread._Thread__stop()
        
        # print "Traffic handlers are stopped"

        DATA_LOG.info("Traffic handlers are stopped")


class IncomingTrafficHandler(threading.Thread):
    def __init__(self, app_queue, service_msg_queue, hello_msg_queue,
                 app_transport, raw_transport, table, broadcast_list):
        super(IncomingTrafficHandler, self).__init__()
        self.running = True
        self.app_transport = app_transport
        self.raw_transport = raw_transport
        self.app_queue = app_queue
        self.service_msg_queue = service_msg_queue
        self.hello_msg_queue = hello_msg_queue
        self.table = table
        self.broadcast_list = broadcast_list
        self.broadcast_mac = "ff:ff:ff:ff:ff:ff"
        self.max_broadcast_ttl = 1              # Set a maximum number of hops a broadcast frame can be forwarded over
        
    def run(self):
        while self.running:

            dsr_header, raw_data = self.raw_transport.recv_data()

            dsr_type = dsr_header.type

            # Check the dst_ip from dsr_header. If it matches the node's own ip -> send it up to the virtual interface
            # If the packet carries the data, either send it to the next hop, or,
            # if there is no such one, put it to the AppQueue, or,
            # if the dst_mac equals to the node's mac, send the packet up to the application
            if dsr_type == 0:
                dst_mac = dsr_header.dst_mac
                # If the dst_ip matches the node's ip, send data to the App
                if dst_mac == self.table.node_mac:
                    # print "Sending data to the App..."

                    DATA_LOG.debug("Sending data to the App...")

                    self.send_up(raw_data)
                # elif dst_mac == self.broadcast_mac:
                #     # Send the ipv4 broadcast/multicast or ipv6 multicast packet up to the application
                #     self.send_up(raw_data)

                # Else, try to find the next hop in the route table
                else:
                    entry = self.table.lookup_entry(dst_mac)
                    # If no entry is found, put the packet to the initial AppQueue
                    if entry is None:
                        # Get src_ip and dst_ip from the raw_data
                        ips = self.app_transport.get_L3_addresses_from_packet(raw_data)
                        self.app_queue.put([ips[0], ips[1], raw_data])

                    # Else, forward the packet to the next_hop
                    else:
                        next_hop_mac = entry.next_hop_mac
                        # Send the raw data with dsr_header to the next hop
                        self.raw_transport.send_raw_frame(next_hop_mac, dsr_header, raw_data)

            # If the dsr packet contains HELLO message from the neighbour
            elif dsr_type == 1:
                # Handle HELLO message
                self.hello_msg_queue.put(raw_data)

            # If the dsr packet contains RREQ or RREQ service messages
            elif dsr_type == 2 or dsr_type == 3:
                # Handle RREQ / RREP
                self.service_msg_queue.put([dsr_header, raw_data])

            # If the packet is the broadcast one, either broadcast it further or drop it
            elif dsr_type == 4:
                # print "Received broadcast TTL:", dsr_header.broadcast_ttl

                DATA_LOG.debug("Received broadcast TTL: %s", dsr_header.broadcast_ttl)

                # Check whether the packet with this particular broadcast_id has been previously received
                if dsr_header.broadcast_id in self.broadcast_list:
                    # print "Dropped broadcast id:", dsr_header.broadcast_id

                    DATA_LOG.debug("Dropped broadcast id: %s", dsr_header.broadcast_id)

                    # Just ignore it
                    # print "Ignoring the broadcast"
                    pass
                # Check whether the broadcast packet has reached the maximum established broadcast ttl
                elif dsr_header.broadcast_ttl > self.max_broadcast_ttl:
                    # Just ignore it
                    # print "Ignoring the broadcast"

                    DATA_LOG.debug("Dropped broadcast id due to max_ttl: %s", dsr_header.broadcast_id)

                    pass
                else:
                    # print "Accepting the broadcast"

                    DATA_LOG.debug("Accepting the broadcast: %s", dsr_header.broadcast_id)

                    # Send this ipv4 broadcast/multicast or ipv6 multicast packet up to the application
                    self.send_up(raw_data)
                    # Put it to the broadcast list
                    self.broadcast_list.append(dsr_header.broadcast_id)
                    # Increment broadcast ttl and send the broadcast the packet further
                    dsr_header.broadcast_ttl += 1
                    self.raw_transport.send_raw_frame(self.broadcast_mac, dsr_header, raw_data)

    # Send the raw data up to virtual interface
    def send_up(self, raw_data):
        self.app_transport.send_to_app(raw_data)
        
    def quit(self):
        self.running = False


class ServiceMessagesHandler(threading.Thread):
    def __init__(self, route_table, app_transport, raw_transport, rrep_queue, service_msg_queue):
        super(ServiceMessagesHandler, self).__init__()
        self.table = route_table
        self.raw_transport = raw_transport
        self.app_transport = app_transport
        self.broadcast_mac = "ff:ff:ff:ff:ff:ff"
        self.node_mac = route_table.node_mac
        self.service_msg_queue = service_msg_queue
        self.rrep_queue = rrep_queue  # Store the received RREP in queue for further handling by Path_Discovery thread
        
        self.rreq_ids = []
        self.running = True

    def quit(self):
        self.raw_transport.close_raw_recv_socket()
        self.running = False
    
    def run(self):
        while self.running:
            dsr_header, raw_data = self.service_msg_queue.get()
            data = pickle.loads(raw_data)
            
            if isinstance(data, Messages.RouteRequest):
                # Do something with incoming RREQ

                DATA_LOG.info("Got RREQ: %s" % str(data))
                
                self.RREQ_handler(dsr_header, data)
            if isinstance(data, Messages.RouteReply):
                # Do something with incoming RREP             

                DATA_LOG.info("Got RREP: %s" % str(data))

                self.RREP_handler(dsr_header, data)
                
    def gen_dsr_header(self, dsr_header, _type):
        dsr = Messages.DsrHeader(_type)
        dsr.src_mac = self.node_mac
        dsr.dst_mac = dsr_header.src_mac
        dsr.tx_mac = self.node_mac
        
        return dsr

    def RREQ_handler(self, dsr_header, RREQ):
        if RREQ.id in self.rreq_ids:
            # print "The RREQ with this ID has been already processed\n"

            DATA_LOG.info("The RREQ with this ID has been already processed")

            return 0
        
        # print "Processing RREQ \n"

        DATA_LOG.info("Processing RREQ")

        self.rreq_ids.append(RREQ.id)
        
        # Adding entries in route table:
        # Add an entry in the route table in a form (dst_mac, next_hop_mac, n_hops)
        self.table.add_entry(dsr_header.src_mac, dsr_header.tx_mac, RREQ.hop_count)
        # Update arp_table
        self.table.update_arp_table(RREQ.src_ip, dsr_header.src_mac)
        
        # Get a list of currently assigned ip addresses to the node
        node_ips = self.app_transport.get_L3_addresses_from_interface()
        
        if RREQ.dst_ip in node_ips:        
            # print "Processing the RREQ, generating and sending back the RREP\n"

            DATA_LOG.info("Processing the RREQ, generating and sending back the RREP")

            # Generate and send RREP back to the source
            RREP = Messages.RouteReply()
            RREP.src_ip = RREQ.dst_ip
            RREP.dst_ip = RREQ.src_ip
            RREP.hop_count = 1
            RREP.id = RREQ.id
            
            # Prepare a dsr_header
            new_dsr_header = self.gen_dsr_header(dsr_header, 3)         # Type 3 corresponds to RREP service message
            self.raw_transport.send_raw_frame(dsr_header.tx_mac, new_dsr_header, pickle.dumps(RREP))
            
            # print RREP, RREQ.dst_ip

            DATA_LOG.debug("Generated RREP: %s", str(RREP))
            DATA_LOG.debug("RREQ.dst_ip: %s", str(RREQ.dst_ip))

        else:
            # print "Broadcasting RREQ further\n"

            DATA_LOG.info("Broadcasting RREQ further")

            # Change next_hop value to NODE_IP and broadcast the message further
            RREQ.hop_count += 1
            
            # Prepare a dsr_header
            dsr_header.tx_mac = self.node_mac
                        
            # Send the broadcast frame with RREQ object
            self.raw_transport.send_raw_frame(self.broadcast_mac, dsr_header, pickle.dumps(RREQ))
            
    def RREP_handler(self, dsr_header, RREP):
        # Adding entries in route table:
        # Add an entry in the route table in a form (dst_mac, next_hop_mac, n_hops)
        # entry = self.table.add_entry(dsr_header.src_mac, dsr_header.tx_mac, RREP.hop_count)
        self.table.add_entry(dsr_header.src_mac, dsr_header.tx_mac, RREP.hop_count)
        # Update arp_table
        self.table.update_arp_table(RREP.src_ip, dsr_header.src_mac)
        self.table.update_arp_table(RREP.dst_ip, dsr_header.dst_mac)
        
        if dsr_header.dst_mac != self.node_mac:
            # Forward RREP further
            # print "Forwarding RREP further\n"

            DATA_LOG.info("Forwarding RREP further. RREP_ID: %s", str(RREP.id))

            # Find the entry in route table, corresponding to a given RREQ(RREP) id
            
            entry = self.table.lookup_entry(dsr_header.dst_mac)
            
            # If no entry is found. Just do nothing.
            if entry is None:
                # print "No further route for this RREP. Removing"
                DATA_LOG.info("No further route for this RREP. Removing. RREP_ID: %s", str(RREP.id))
            else:
                # Forward the RREP to the next hop derived from the route table
                RREP.hop_count += 1

                # Prepare a dsr_header
                dsr_header.tx_mac = self.node_mac

                self.raw_transport.send_raw_frame(entry.next_hop_mac, dsr_header, pickle.dumps(RREP))

        else:
            # print "This RREP is for me. Stop the discovery procedure, send the data.\n"

            DATA_LOG.info("This RREP is for me. Stop the discovery procedure, send the data.")

            # Put RREP in rrep_queue
            self.rrep_queue.put(RREP.src_ip)

