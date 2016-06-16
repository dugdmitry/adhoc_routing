#!/usr/bin/python
"""
Created on Oct 6, 2014

@author: Dmitrii Dugaev
"""

import Messages
import PathDiscovery
import ArqHandler

import Queue
import pickle
import threading
from collections import deque

import routing_logging

lock = threading.Lock()

# Set up logging
DATA_LOG = routing_logging.create_routing_log("routing.data_handler.log", "data_handler")
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
        
        self.broadcast_mac = raw_transport.broadcast_mac
        
    def run(self):
        while self.running:
            src_ip, dst_ip, raw_data = self.app_queue.get()

            # Lookup for a corresponding dst_mac in the arp table
            dst_mac = self.table.lookup_mac_address(dst_ip)
            
            # Check whether the destination IP exists in the Route Table
            lock.acquire()
            entry = self.table.lookup_entry(dst_mac)
            lock.release()

            if dst_ip[:2] == "ff" or dst_ip == "10.0.0.255":
                # print "Multicast IPv6", dst_ip                          # ## IPv4 PACKETS GO UNCHECKED FOR NOW ## #

                DATA_LOG.info("Multicast IPv6: %s", dst_ip)

                # Create a broadcast dsr header
                dsr_header = self.create_dsr_broadcast_header()
                # Put the dsr broadcast id to the broadcast_list
                self.broadcast_list.append(dsr_header.broadcast_id)

                DATA_LOG.debug("Trying to send the broadcast...")

                # Broadcast it further to the network
                self.transport.send_raw_frame(self.broadcast_mac, dsr_header, raw_data)

                DATA_LOG.debug("Broadcast sent!!!")

            elif entry is None:

                DATA_LOG.info("No such route in the table. Starting route discovery...")

                # ## Start PathDiscovery procedure ## #
                # Put packet in wait_queue
                self.wait_queue.put([src_ip, dst_ip, raw_data])
                
            else:

                DATA_LOG.debug("Found an entry: %s", str(entry))

                next_hop_mac = entry.next_hop_mac
                # Create a unicast dsr header with proper values
                dsr_header = self.create_dsr_unicast_header(dst_mac)
                # Send the raw data with dsr_header to the next hop
                self.transport.send_raw_frame(next_hop_mac, dsr_header, raw_data)

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
        # Create an arq handler object
        arq_handler = ArqHandler.ArqHandler(raw_transport)

        # Creating a queue for receiving RREPs
        rrep_queue = Queue.Queue()
        # Creating a queue for the delayed packets waiting for rrep message
        wait_queue = Queue.Queue()
        # Creating a queue for handling incoming RREQ and RREP packets from the raw_socket
        service_msg_queue = Queue.Queue()
        # Creating a deque list for keeping the received broadcast IDs
        broadcast_list = deque(maxlen=10000)  # Limit the max length of the list

        # Creating thread objects
        self.path_discovery_thread = PathDiscovery.PathDiscoveryHandler(app_queue, wait_queue,
                                                                        rrep_queue, arq_handler, table)
        
        self.app_handler_thread = AppHandler(app_queue, wait_queue, raw_transport, table, broadcast_list)

        self.incoming_traffic_handler_thread = IncomingTrafficHandler(app_queue, service_msg_queue,
                                                                      hello_msg_queue, app_transport,
                                                                      raw_transport, table, broadcast_list)

        self.service_messages_handler_thread = ServiceMessagesHandler(table, app_transport, raw_transport,
                                                                      arq_handler, rrep_queue, service_msg_queue)

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
        self.broadcast_mac = raw_transport.broadcast_mac
        self.max_broadcast_ttl = 1          # Set a maximum number of hops a broadcast frame can be forwarded over
        
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
                    lock.acquire()
                    entry = self.table.lookup_entry(dst_mac)
                    lock.release()
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

            # If the dsr packet contains RREQ or RREQ, or the ACK service messages (types 2, 3 and 5)
            elif dsr_type == 2 or dsr_type == 3 or dsr_type == 5:
                # Handle RREQ / RREP / ACK

                DATA_LOG.debug("Got service message. TYPE: %s", dsr_type)

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
    def __init__(self, route_table, app_transport, raw_transport, arq_handler, rrep_queue, service_msg_queue):
        super(ServiceMessagesHandler, self).__init__()
        self.table = route_table
        self.raw_transport = raw_transport
        self.app_transport = app_transport
        self.arq_handler = arq_handler

        self.broadcast_mac = raw_transport.broadcast_mac
        self.node_mac = route_table.node_mac
        self.service_msg_queue = service_msg_queue
        self.rrep_queue = rrep_queue  # Store the received RREP in queue for further handling by Path_Discovery thread
        
        self.rreq_ids = deque(maxlen=10000)  # Limit the max length of the list
        self.rrep_ids = deque(maxlen=10000)  # Limit the max length of the list

        self.running = True

    def quit(self):
        self.raw_transport.close_raw_recv_socket()
        self.running = False
    
    def run(self):
        while self.running:
            dsr_header, raw_data = self.service_msg_queue.get()
            data = pickle.loads(raw_data)

            DATA_LOG.debug("Message from service queue: %s", str(data))

            if isinstance(data, Messages.RouteRequest):
                # Do something with incoming RREQ
                DATA_LOG.info("Got RREQ: %s" % str(data))
                
                self.rreq_handler(dsr_header, data)

            if isinstance(data, Messages.RouteReply):
                # Do something with incoming RREP             
                DATA_LOG.info("Got RREP: %s" % str(data))

                self.rrep_handler(dsr_header, data)

            if isinstance(data, Messages.AckMessage):
                # Do something with ACK
                DATA_LOG.info("Got ACK: %s" % str(data))

                self.ack_handler(data)
                
    def gen_dsr_header(self, dsr_header, _type):
        dsr = Messages.DsrHeader(_type)
        dsr.src_mac = self.node_mac
        dsr.dst_mac = dsr_header.src_mac
        dsr.tx_mac = self.node_mac
        
        return dsr

    def rreq_handler(self, dsr_header, rreq):
        # Send back the ACK on the received RREQ in ALL cases
        self.arq_handler.send_ack(rreq, dsr_header.tx_mac)

        if rreq.id in self.rreq_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The RREQ with this ID has been already processed. Sending the ACK back.")

            return 0

        DATA_LOG.info("Processing RREQ")

        self.rreq_ids.append(rreq.id)

        # Adding entries in route table:
        # Add an entry in the route table in a form (dst_mac, next_hop_mac, n_hops)
        lock.acquire()
        self.table.add_entry(dsr_header.src_mac, dsr_header.tx_mac, rreq.hop_count)
        lock.release()
        # Update arp_table
        lock.acquire()
        self.table.update_arp_table(rreq.src_ip, dsr_header.src_mac)
        lock.release()
        
        # Get a list of currently assigned ip addresses to the node
        node_ips = self.app_transport.get_L3_addresses_from_interface()
        
        if rreq.dst_ip in node_ips:

            DATA_LOG.info("Processing the RREQ, generating and sending back the RREP")

            # Generate and send RREP back to the source
            rrep = Messages.RouteReply()
            rrep.src_ip = rreq.dst_ip
            rrep.dst_ip = rreq.src_ip
            rrep.hop_count = 1
            rrep.id = rreq.id
            
            # Prepare a dsr_header
            new_dsr_header = self.gen_dsr_header(dsr_header, 3)         # Type 3 corresponds to RREP service message

            # Send the RREP reliably using arq_handler
            self.arq_handler.arq_send(rrep, new_dsr_header, [dsr_header.tx_mac])

            # self.raw_transport.send_raw_frame(dsr_header.tx_mac, new_dsr_header, pickle.dumps(rrep))

            DATA_LOG.debug("Generated RREP: %s", str(rrep))
            DATA_LOG.debug("RREQ.dst_ip: %s", str(rreq.dst_ip))

        else:

            DATA_LOG.info("Broadcasting RREQ further")

            # Change next_hop value to NODE_IP and broadcast the message further
            rreq.hop_count += 1

            # Send the RREQ reliably using arq_handler to the list of current neighbors except the one who sent it
            dst_mac_list = self.table.get_neighbors()
            if dsr_header.tx_mac in dst_mac_list:
                dst_mac_list.remove(dsr_header.tx_mac)

            # Prepare a dsr_header
            dsr_header.tx_mac = self.node_mac

            self.arq_handler.arq_send(rreq, dsr_header, dst_mac_list)

            # # Send the broadcast frame with RREQ object
            # self.raw_transport.send_raw_frame(self.broadcast_mac, dsr_header, pickle.dumps(rreq))

    def rrep_handler(self, dsr_header, rrep):
        # Send back the ACK on the received RREP in ALL cases
        self.arq_handler.send_ack(rrep, dsr_header.tx_mac)

        if rrep.id in self.rrep_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The RREP with this ID has been already processed. Sending the ACK back.")

            return 0

        DATA_LOG.info("Processing RREP...")

        self.rrep_ids.append(rrep.id)

        # Adding entries in route table:
        # Add an entry in the route table in a form (dst_mac, next_hop_mac, n_hops)
        # entry = self.table.add_entry(dsr_header.src_mac, dsr_header.tx_mac, RREP.hop_count)
        lock.acquire()
        self.table.add_entry(dsr_header.src_mac, dsr_header.tx_mac, rrep.hop_count)
        lock.release()
        # Update arp_table
        lock.acquire()
        self.table.update_arp_table(rrep.src_ip, dsr_header.src_mac)
        self.table.update_arp_table(rrep.dst_ip, dsr_header.dst_mac)
        lock.release()
        
        if dsr_header.dst_mac != self.node_mac:
            # Forward RREP further
            DATA_LOG.info("Forwarding RREP further. RREP_ID: %s", str(rrep.id))

            # Find the entry in route table, corresponding to a given RREQ(RREP) id
            lock.acquire()
            entry = self.table.lookup_entry(dsr_header.dst_mac)
            lock.release()
            
            # If no entry is found. Just do nothing.
            if entry is None:

                DATA_LOG.info("No further route for this RREP. Removing. RREP_ID: %s", str(rrep.id))

            else:
                # Forward the RREP to the next hop derived from the route table
                rrep.hop_count += 1

                # Prepare a dsr_header
                dsr_header.tx_mac = self.node_mac

                # Forward the RREP reliably using arq_handler
                self.arq_handler.arq_send(rrep, dsr_header, [entry.next_hop_mac])

                # self.raw_transport.send_raw_frame(entry.next_hop_mac, dsr_header, pickle.dumps(rrep))

        else:

            DATA_LOG.info("This RREP is for me. Stop the discovery procedure, send the data.")

            # Put RREP in rrep_queue
            self.rrep_queue.put(rrep.src_ip)

    # Handling incoming ack messages
    def ack_handler(self, ack):
        # Process the ACK by arq_handler
        self.arq_handler.process_ack(ack)
