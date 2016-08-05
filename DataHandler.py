#!/usr/bin/python
"""
Created on Oct 6, 2014

@author: Dmitrii Dugaev
"""

import Messages
import PathDiscovery
import ArqHandler

import time
import Queue
import pickle
import threading
from collections import deque

import routing_logging
from conf import MONITORING_MODE_FLAG

lock = threading.Lock()

# Set up logging
DATA_LOG = routing_logging.create_routing_log("routing.data_handler.log", "data_handler")


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

        # Define a structure for handling reward wait threads for given dst_ips.
        # Format: {hash(dst_ip + next_hop_mac): thread_object}.
        # A reward value is being forwarded to the thread via a queue_object.
        reward_wait_list = dict()

        # Creating thread objects
        self.path_discovery_thread = PathDiscovery.PathDiscoveryHandler(app_queue, wait_queue,
                                                                        rrep_queue, arq_handler, table)

        self.app_handler_thread = AppHandler(app_queue, wait_queue, raw_transport,
                                             table, reward_wait_list, broadcast_list)

        self.incoming_traffic_handler_thread = IncomingTrafficHandler(app_queue, service_msg_queue, hello_msg_queue,
                                                                      app_transport, raw_transport, table,
                                                                      reward_wait_list, broadcast_list)

        self.service_messages_handler_thread = ServiceMessagesHandler(table, app_transport, raw_transport, arq_handler,
                                                                      rrep_queue, service_msg_queue, reward_wait_list)

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

        DATA_LOG.info("Traffic handlers are stopped")


class AppHandler(threading.Thread):
    def __init__(self, app_queue, wait_queue, raw_transport, table, reward_wait_list, broadcast_list):
        super(AppHandler, self).__init__()
        self.running = True
        self.app_queue = app_queue
        self.wait_queue = wait_queue
        self.table = table
        self.broadcast_list = broadcast_list
        
        self.transport = raw_transport
        # self.node_mac = table.node_mac
        self.node_mac = raw_transport.node_mac

        self.broadcast_mac = raw_transport.broadcast_mac

        # # Define a structure for handling reward wait threads for given dst_ips.
        # # Format: {hash(dst_ip + next_hop_mac): thread_object}.
        # # A reward value is being forwarded to the thread via a queue_object.
        # self.reward_wait_list = dict()
        self.reward_wait_list = reward_wait_list

    def run(self):
        while self.running:
            src_ip, dst_ip, raw_data = self.app_queue.get()

            # # Lookup for a corresponding dst_mac in the arp table
            # dst_mac = self.table.lookup_mac_address(dst_ip)

            # # Check whether the destination IP exists in the Route Table
            # lock.acquire()
            # entry = self.table.lookup_entry(dst_mac)
            # lock.release()

            # Try to find a mac address of the next hop where a packet should be forwarded to
            next_hop_mac = self.table.get_next_hop_mac(dst_ip)

            # Check if the packet's destination address is IPv6 multicast
            # Always starts from "ff0X::",
            # see https://en.wikipedia.org/wiki/IPv6_address#Multicast_addresses
            if dst_ip[:2] == "ff":

                DATA_LOG.info("Multicast IPv6: %s", dst_ip)

                # Create a broadcast dsr header
                dsr_header = self.create_dsr_broadcast_header()
                # Put the dsr broadcast id to the broadcast_list
                self.broadcast_list.append(dsr_header.broadcast_id)

                DATA_LOG.debug("Trying to send the broadcast...")

                # Broadcast it further to the network
                self.transport.send_raw_frame(self.broadcast_mac, dsr_header, raw_data)

                DATA_LOG.debug("Broadcast sent!!!")

            # Check if the packet's destination address is IPv4 multicast or broadcast.
            # The IPv4 multicasts start with either 224.x.x.x or 239.x.x.x
            # See: https://en.wikipedia.org/wiki/Multicast_address#IPv4
            elif dst_ip[:3] == "224" or dst_ip[:3] == "239":
                DATA_LOG.info("Multicast IPv4: %s", dst_ip)

                # Create a broadcast dsr header
                dsr_header = self.create_dsr_broadcast_header()
                # Put the dsr broadcast id to the broadcast_list
                self.broadcast_list.append(dsr_header.broadcast_id)

                DATA_LOG.debug("Trying to send the broadcast...")

                # Broadcast it further to the network
                self.transport.send_raw_frame(self.broadcast_mac, dsr_header, raw_data)

                DATA_LOG.debug("Broadcast sent!!!")

            # Check if the packet's destination address is IPv4 broadcast.
            # The IPv4 broadcasts ends with .255
            # See: https://en.wikipedia.org/wiki/IP_address#Broadcast_addressing
            elif dst_ip[-3:] == "255":
                DATA_LOG.info("Broadcast IPv4: %s", dst_ip)

                # Create a broadcast dsr header
                dsr_header = self.create_dsr_broadcast_header()
                # Put the dsr broadcast id to the broadcast_list
                self.broadcast_list.append(dsr_header.broadcast_id)

                DATA_LOG.debug("Trying to send the broadcast...")

                # Broadcast it further to the network
                self.transport.send_raw_frame(self.broadcast_mac, dsr_header, raw_data)

                DATA_LOG.debug("Broadcast sent!!!")

            # If next_hop_mac is None, it means that there is no current entry witch dst_ip.
            # In that case, start a PathDiscovery procedure
            elif next_hop_mac is None:

                DATA_LOG.info("No such Entry with given dst_ip in the table. Starting path discovery...")

                # ## Start PathDiscovery procedure ## #
                # Put packet in wait_queue
                self.wait_queue.put([src_ip, dst_ip, raw_data])

            # Else, the packet is unicast, and has the corresponding Entry.
            # Forward packet to the next hop. Start a thread wor waiting an ACK with reward.
            else:

                DATA_LOG.debug("For DST_IP: %s found a next_hop_mac: %s", dst_ip, next_hop_mac)

                # # next_hop_mac = entry.next_hop_mac
                # next_hop_mac = self.table.get_next_hop_mac(src_ip, dst_ip)

                # Create a unicast dsr header with proper values
                dsr_header = self.create_dsr_unicast_header()
                # Send the raw data with dsr_header to the next hop
                self.transport.send_raw_frame(next_hop_mac, dsr_header, raw_data)

                hash_value = hash(dst_ip + next_hop_mac)
                # Start a thread for receiving a reward value on a given dst_ip
                if hash_value not in self.reward_wait_list:
                    reward_wait_thread = RewardWaitThread(dst_ip, next_hop_mac, self.table, self.reward_wait_list)
                    # lock.acquire()
                    self.reward_wait_list.update({hash_value: reward_wait_thread})
                    # lock.release()
                    # Start the thread
                    reward_wait_thread.start()

        DATA_LOG.debug("LOOP FINISHED!!!")

    def create_dsr_unicast_header(self):
        _type = 0                                       # Type 0 corresponds to the data packets
        dsr_header = Messages.DsrHeader(_type)
        dsr_header.src_mac = self.node_mac
        # dsr_header.dst_mac = dst_mac
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


# Thread for waiting for an incoming reward messages on the given dst_ip.
# It receives a reward value via the queue, and updates the RouteTable.
class RewardWaitThread(threading.Thread):
    def __init__(self, dst_ip, mac, table, reward_wait_list):
        super(RewardWaitThread, self).__init__()
        self.dst_ip = dst_ip
        self.mac = mac
        self.table = table
        self.reward_wait_list = reward_wait_list
        self.reward_wait_queue = Queue.Queue()
        # Wait timeout after which initiate negative reward on the dst_ip
        self.wait_timeout = 3

    def run(self):
        try:
            reward = self.reward_wait_queue.get(timeout=self.wait_timeout)
            # Update value by received reward
            self.table.update_entry(self.dst_ip, self.mac, reward)
        # Update with a "bad" reward, if the timeout has been reached
        except Queue.Empty:
            self.table.update_entry(self.dst_ip, self.mac, 0)
        # Finally, delete its own entry from the reward_wait_list
        finally:
            # lock.acquire()
            del self.reward_wait_list[hash(self.dst_ip + self.mac)]
            # lock.release()

    def set_reward(self, reward):
        self.reward_wait_queue.put(reward)


# Thread for generating and sending back a reward message upon receiving a packet with a corresponding dst_ip
# from the network interface.
class RewardSendThread(threading.Thread):
    def __init__(self, dst_ip, mac, table, raw_transport, reward_send_list):
        super(RewardSendThread, self).__init__()
        self.dst_ip = dst_ip
        self.mac = mac
        self.node_mac = raw_transport.node_mac
        self.table = table
        self.raw_transport = raw_transport
        self.reward_send_list = reward_send_list
        # Create a reward message object
        self.reward_message = Messages.RewardMessage()
        # Create a dsr_header object
        self.dsr_header = Messages.DsrHeader(6)         # Type 6 corresponds to Reward Message
        # A time interval the thread waits for, ere generating and sending back the RewardMessage.
        # This timeout is needed to control a number of generated reward messages for some number of
        # the received packets with the same dst_ip.
        self.hold_on_timeout = 2

    def run(self):
        # Sleep for the hold_on_timeout value
        time.sleep(self.hold_on_timeout)
        # Calculate its own average value of the estimated reward towards the given dst_ip
        avg_value = self.table.get_avg_value(self.dst_ip)
        # Assign a reward to the reward message
        self.reward_message.reward_value = avg_value
        self.reward_message.msg_hash = hash(self.dst_ip + self.node_mac)
        # Send it back to the node which has sent the packet
        self.raw_transport.send_raw_frame(self.mac, self.dsr_header, pickle.dumps(self.reward_message))
        # Delete its own entry from the reward_send_list
        # lock.acquire()
        del self.reward_send_list[hash(self.dst_ip + self.mac)]
        # lock.release()


class IncomingTrafficHandler(threading.Thread):
    def __init__(self, app_queue, service_msg_queue, hello_msg_queue,
                 app_transport, raw_transport, table, reward_wait_list, broadcast_list):
        super(IncomingTrafficHandler, self).__init__()
        # Check the MONITORING_MODE_FLAG.
        # If True - override the self.handle_data_packet method for working in the monitoring mode.
        if MONITORING_MODE_FLAG:
            self.handle_data_packet = self.handle_data_packet_monitoring_mode

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

        self.node_mac = raw_transport.node_mac

        # Define a structure for handling reward send threads for given dst_ips.
        # Format: {hash(dst_ip + mac): RewardSendThread}.
        self.reward_send_list = dict()

        self.reward_wait_list = reward_wait_list

    def run(self):
        while self.running:

            dsr_header, raw_data = self.raw_transport.recv_data()

            dsr_type = dsr_header.type

            # If it's a data packet, handle it accordingly
            if dsr_type == 0:
                self.handle_data_packet(dsr_header, raw_data)

            # If the dsr packet contains HELLO message from the neighbour
            elif dsr_type == 1:
                # Handle HELLO message
                self.hello_msg_queue.put(raw_data)

            # If dsr packet contains some service message: RREQ, RREP, ACK or Reward (types 2, 3, 5 or 6)
            elif dsr_type == 2 or dsr_type == 3 or dsr_type == 5 or dsr_type == 6:
                # Handle RREQ / RREP / ACK / Reward
                DATA_LOG.debug("Got service message. TYPE: %s", dsr_type)

                self.service_msg_queue.put([dsr_header, raw_data])

            # If the packet is the broadcast one, either broadcast it further or drop it
            elif dsr_type == 4:

                DATA_LOG.debug("Received broadcast TTL: %s", dsr_header.broadcast_ttl)

                self.handle_broadcast_packet(dsr_header, raw_data)

    # Check the dst_mac from dsr_header. If it matches the node's own mac -> send it up to the virtual interface
    # If the packet carries the data, either send it to the next hop, or,
    # if there is no such one, put it to the AppQueue, or,
    # if the dst_mac equals to the node's mac, send the packet up to the application
    def handle_data_packet(self, dsr_header, raw_data):
        # dst_mac = dsr_header.dst_mac
        # Generate and send back a reward message to the node which has sent this packet
        mac = dsr_header.tx_mac

        # Get src_ip, dst_ip from the incoming packet
        src_ip, dst_ip = self.app_transport.get_L3_addresses_from_packet(raw_data)

        # Start send thread
        hash_value = hash(dst_ip + mac)
        if hash_value not in self.reward_send_list:
            reward_send_thread = RewardSendThread(dst_ip, mac, self.table, self.raw_transport, self.reward_send_list)
            self.reward_send_list.update({hash_value: reward_send_thread})
            reward_send_thread.start()

        # If the dst_ip matches the node's ip, send data to the App
        if dst_ip in self.table.current_node_ips:

            DATA_LOG.debug("Sending packet with to the App... SRC_IP: %s, DST_IP: %s", src_ip, dst_ip)

            self.send_up(raw_data)

        # Else, try to find the next hop in the route table
        else:
            # lock.acquire()
            # entry = self.table.lookup_entry(dst_mac)
            # lock.release()

            next_hop_mac = self.table.get_next_hop_mac(dst_ip)
            DATA_LOG.debug("IncomingTraffic: For DST_IP: %s found a next_hop_mac: %s", dst_ip, next_hop_mac)
            DATA_LOG.debug("Current entry: %s", self.table.get_entry(dst_ip))

            # If no entry is found, put the packet to the initial AppQueue
            if next_hop_mac is None:
                # Get src_ip and dst_ip from the raw_data
                # ips = self.app_transport.get_L3_addresses_from_packet(raw_data)
                # self.app_queue.put([ips[0], ips[1], raw_data])
                # ips = self.app_transport.get_L3_addresses_from_packet(raw_data)
                self.app_queue.put([src_ip, dst_ip, raw_data])

            # Else, forward the packet to the next_hop. Start a reward wait thread, if necessary.
            else:
                # next_hop_mac = entry.next_hop_mac
                dsr_header.tx_mac = self.node_mac
                # Send the raw data with dsr_header to the next hop
                self.raw_transport.send_raw_frame(next_hop_mac, dsr_header, raw_data)

                hash_value = hash(dst_ip + next_hop_mac)
                # Start a thread for receiving a reward value on a given dst_ip
                if hash_value not in self.reward_wait_list:
                    reward_wait_thread = RewardWaitThread(dst_ip, next_hop_mac, self.table, self.reward_wait_list)
                    # lock.acquire()
                    self.reward_wait_list.update({hash_value: reward_wait_thread})
                    # lock.release()
                    # Start the thread
                    reward_wait_thread.start()

    # Handle data packet, if in monitoring mode. If the dst_mac is the mac of the receiving node,
    # send the packet up to the application, otherwise, discard the packet
    def handle_data_packet_monitoring_mode(self, dsr_header, raw_data):
        # dst_mac = dsr_header.dst_mac
        # Generate and send back a reward message to the node which has sent this packet
        mac = dsr_header.tx_mac

        # Get src_ip, dst_ip from the incoming packet
        src_ip, dst_ip = self.app_transport.get_L3_addresses_from_packet(raw_data)

        # Start send thread
        hash_value = hash(dst_ip + mac)
        if hash_value not in self.reward_send_list:
            reward_send_thread = RewardSendThread(dst_ip, mac, self.table, self.raw_transport, self.reward_send_list)
            self.reward_send_list.update({hash_value: reward_send_thread})
            reward_send_thread.start()

        # If the dst_ip matches the node's ip, send data to the App
        if dst_ip in self.table.current_node_ips:

            DATA_LOG.debug("Sending packet with to the App... SRC_IP: %s, DST_IP: %s", src_ip, dst_ip)

            self.send_up(raw_data)

        # In all other cases, discard the packet
        else:
            DATA_LOG.debug("This data packet is not for me. Discarding the data packet, since in Monitoring Mode.")

    # Check the broadcast_ttl with the defined max value, and either drop or forward it, accordingly
    def handle_broadcast_packet(self, dsr_header, raw_data):
        # Check whether the packet with this particular broadcast_id has been previously received
        if dsr_header.broadcast_id in self.broadcast_list:

            # Just ignore it
            DATA_LOG.debug("Dropped broadcast id: %s", dsr_header.broadcast_id)

        # Check whether the broadcast packet has reached the maximum established broadcast ttl
        elif dsr_header.broadcast_ttl > self.max_broadcast_ttl:

            # Just ignore it
            DATA_LOG.debug("Dropped broadcast id due to max_ttl: %s", dsr_header.broadcast_id)

        else:
            # Accept and forward the broadcast further
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
    def __init__(self, route_table, app_transport, raw_transport,
                 arq_handler, rrep_queue, service_msg_queue, reward_wait_list):
        super(ServiceMessagesHandler, self).__init__()
        # Check the MONITORING_MODE_FLAG.
        # If True - override the self.rreq_handler and self.rrep_handler methods for working in the monitoring mode.
        if MONITORING_MODE_FLAG:
            self.handle_rreq = self.handle_rreq_monitoring_mode
            self.handle_rrep = self.handle_rrep_monitoring_mode

        self.table = route_table
        self.raw_transport = raw_transport
        self.app_transport = app_transport
        self.arq_handler = arq_handler

        self.broadcast_mac = raw_transport.broadcast_mac
        self.node_mac = raw_transport.node_mac
        self.service_msg_queue = service_msg_queue
        self.rrep_queue = rrep_queue  # Store the received RREP in queue for further handling by Path_Discovery thread
        
        self.rreq_ids = deque(maxlen=10000)  # Limit the max length of the list
        self.rrep_ids = deque(maxlen=10000)  # Limit the max length of the list

        self.running = True

        self.reward_wait_list = reward_wait_list

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
                
                self.handle_rreq(dsr_header, data)

            if isinstance(data, Messages.RouteReply):
                # Do something with incoming RREP             
                DATA_LOG.info("Got RREP: %s" % str(data))

                self.handle_rrep(dsr_header, data)

            if isinstance(data, Messages.AckMessage):
                # Do something with ACK
                DATA_LOG.info("Got ACK: %s" % str(data))

                self.handle_ack(data)

            if isinstance(data, Messages.RewardMessage):
                # Do something with Reward message
                DATA_LOG.info("Got Reward message: %s" % data)

                # self.handle_ack(data)
                self.handle_reward(data)

    def gen_dsr_header(self, dsr_header, _type):
        dsr = Messages.DsrHeader(_type)
        dsr.src_mac = self.node_mac
        dsr.dst_mac = dsr_header.src_mac
        dsr.tx_mac = self.node_mac
        
        return dsr

    def handle_rreq(self, dsr_header, rreq):
        # Send back the ACK on the received RREQ in ALL cases
        self.arq_handler.send_ack(rreq, dsr_header.tx_mac)

        if rreq.id in self.rreq_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The RREQ with this ID has been already processed. Sending the ACK back.")

            return 0

        DATA_LOG.info("Processing RREQ")

        self.rreq_ids.append(rreq.id)

        # # Adding entries in route table:
        # # Add an entry in the route table in a form (dst_mac, next_hop_mac, n_hops)
        # lock.acquire()
        # self.table.add_entry(dsr_header.src_mac, dsr_header.tx_mac, rreq.hop_count)
        # lock.release()
        # # Update arp_table
        # lock.acquire()
        # self.table.update_arp_table(rreq.src_ip, dsr_header.src_mac)
        # lock.release()

        # Update corresponding estimation values in RouteTable for the given src_ip and mac address of the RREQ
        self.table.update_entry(rreq.src_ip, dsr_header.tx_mac, round(100.0 / rreq.hop_count, 2))

        if rreq.dst_ip in self.table.current_node_ips:

            DATA_LOG.info("Processing the RREQ, generating and sending back the RREP broadcast")

            # Generate and send RREP back to the source
            rrep = Messages.RouteReply()
            rrep.src_ip = rreq.dst_ip
            rrep.dst_ip = rreq.src_ip
            rrep.hop_count = 1
            rrep.id = rreq.id
            
            # Prepare a dsr_header
            new_dsr_header = self.gen_dsr_header(dsr_header, 3)         # Type 3 corresponds to RREP service message

            # Send the RREP reliably using arq_handler
            # self.arq_handler.arq_send(rrep, new_dsr_header, [dsr_header.tx_mac])
            self.arq_handler.arq_send(rrep, new_dsr_header, self.table.get_neighbors())

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

    # Handle RREQs if in Monitoring Mode. Process only the RREQs, which have been sent for them (dst_ip in node_ips)
    # Do not forward any other RREQs further.
    def handle_rreq_monitoring_mode(self, dsr_header, rreq):
        # Send back the ACK on the received RREQ in ALL cases
        self.arq_handler.send_ack(rreq, dsr_header.tx_mac)

        if rreq.id in self.rreq_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The RREQ with this ID has been already processed. Sending the ACK back.")

            return 0

        DATA_LOG.info("Processing RREQ")

        self.rreq_ids.append(rreq.id)

        # # Adding entries in route table:
        # # Add an entry in the route table in a form (dst_mac, next_hop_mac, n_hops)
        # lock.acquire()
        # self.table.add_entry(dsr_header.src_mac, dsr_header.tx_mac, rreq.hop_count)
        # lock.release()
        # # Update arp_table
        # lock.acquire()
        # self.table.update_arp_table(rreq.src_ip, dsr_header.src_mac)
        # lock.release()

        # Update corresponding estimation values in RouteTable for the given src_ip and mac address of the RREQ
        self.table.update_entry(rreq.src_ip, dsr_header.tx_mac, round(100.0 / rreq.hop_count, 2))

        if rreq.dst_ip in self.table.current_node_ips:

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
            # self.arq_handler.arq_send(rrep, new_dsr_header, [dsr_header.tx_mac])
            self.arq_handler.arq_send(rrep, new_dsr_header, self.table.get_neighbors())

            DATA_LOG.debug("Generated RREP: %s", str(rrep))
            DATA_LOG.debug("RREQ.dst_ip: %s", str(rreq.dst_ip))

        # If the dst_ip is not for this node, discard the RREQ
        else:

            DATA_LOG.info("This RREQ is not for me. Discarding RREQ, since in Monitoring Mode.")

    def handle_rrep(self, dsr_header, rrep):
        # Send back the ACK on the received RREP in ALL cases
        self.arq_handler.send_ack(rrep, dsr_header.tx_mac)

        if rrep.id in self.rrep_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The RREP with this ID has been already processed. Sending the ACK back.")

            return 0

        DATA_LOG.info("Processing RREP...")

        self.rrep_ids.append(rrep.id)

        # # Adding entries in route table:
        # # Add an entry in the route table in a form (dst_mac, next_hop_mac, n_hops)
        # # entry = self.table.add_entry(dsr_header.src_mac, dsr_header.tx_mac, RREP.hop_count)
        # lock.acquire()
        # self.table.add_entry(dsr_header.src_mac, dsr_header.tx_mac, rrep.hop_count)
        # lock.release()
        # # Update arp_table
        # lock.acquire()
        # self.table.update_arp_table(rrep.src_ip, dsr_header.src_mac)
        # self.table.update_arp_table(rrep.dst_ip, dsr_header.dst_mac)
        # lock.release()

        # Update corresponding estimation values in RouteTable for the given src_ip and mac address of the RREQ
        self.table.update_entry(rrep.src_ip, dsr_header.tx_mac, round(100.0 / rrep.hop_count, 2))

        if rrep.dst_ip in self.table.current_node_ips:

            DATA_LOG.info("This RREP is for me. Stop the discovery procedure, send the data.")

            # Put RREP in rrep_queue
            self.rrep_queue.put(rrep.src_ip)

        else:

            DATA_LOG.info("Broadcasting RREP further")

            # Change next_hop value to NODE_IP and broadcast the message further
            rrep.hop_count += 1

            # Send the RREP reliably using arq_handler to the list of current neighbors except the one who sent it
            dst_mac_list = self.table.get_neighbors()
            if dsr_header.tx_mac in dst_mac_list:
                dst_mac_list.remove(dsr_header.tx_mac)

            # Prepare a dsr_header
            dsr_header.tx_mac = self.node_mac

            self.arq_handler.arq_send(rrep, dsr_header, dst_mac_list)

        # if dsr_header.dst_mac != self.node_mac:
        #     # Forward RREP further
        #     DATA_LOG.info("Forwarding RREP further. RREP_ID: %s", str(rrep.id))
        #
        #     # Find the entry in route table, corresponding to a given RREQ(RREP) id
        #     lock.acquire()
        #     entry = self.table.lookup_entry(dsr_header.dst_mac)
        #     lock.release()
        #
        #     # If no entry is found. Just do nothing.
        #     if entry is None:
        #
        #         DATA_LOG.info("No further route for this RREP. Removing. RREP_ID: %s", str(rrep.id))
        #
        #     else:
        #         # Forward the RREP to the next hop derived from the route table
        #         rrep.hop_count += 1
        #
        #         # Prepare a dsr_header
        #         dsr_header.tx_mac = self.node_mac
        #
        #         # Forward the RREP reliably using arq_handler
        #         self.arq_handler.arq_send(rrep, dsr_header, [entry.next_hop_mac])
        #
        # else:
        #
        #     DATA_LOG.info("This RREP is for me. Stop the discovery procedure, send the data.")
        #
        #     # Put RREP in rrep_queue
        #     self.rrep_queue.put(rrep.src_ip)

    # Handle incoming RREPs while in Monitoring Mode.
    # Receive the RREPs, which have been sent to this node, discard all other RREPs.
    def handle_rrep_monitoring_mode(self, dsr_header, rrep):
        # Send back the ACK on the received RREP in ALL cases
        self.arq_handler.send_ack(rrep, dsr_header.tx_mac)

        if rrep.id in self.rrep_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The RREP with this ID has been already processed. Sending the ACK back.")

            return 0

        DATA_LOG.info("Processing RREP...")

        self.rrep_ids.append(rrep.id)

        # # Adding entries in route table:
        # # Add an entry in the route table in a form (dst_mac, next_hop_mac, n_hops)
        # # entry = self.table.add_entry(dsr_header.src_mac, dsr_header.tx_mac, RREP.hop_count)
        # lock.acquire()
        # self.table.add_entry(dsr_header.src_mac, dsr_header.tx_mac, rrep.hop_count)
        # lock.release()
        # # Update arp_table
        # lock.acquire()
        # self.table.update_arp_table(rrep.src_ip, dsr_header.src_mac)
        # self.table.update_arp_table(rrep.dst_ip, dsr_header.dst_mac)
        # lock.release()

        # Update corresponding estimation values in RouteTable for the given src_ip and mac address of the RREQ
        self.table.update_entry(rrep.src_ip, dsr_header.tx_mac, round(100.0 / rrep.hop_count, 2))

        if rrep.dst_ip in self.table.current_node_ips:

            DATA_LOG.info("This RREP is for me. Stop the discovery procedure, send the data.")

            # Put RREP in rrep_queue
            self.rrep_queue.put(rrep.src_ip)

        # Otherwise, discard the RREP
        else:
            DATA_LOG.info("This RREP is not for me. Discarding RREP, since in Monitoring Mode.")

        # if dsr_header.dst_mac == self.node_mac:
        #
        #     DATA_LOG.info("This RREP is for me. Stop the discovery procedure, send the data.")
        #
        #     # Put RREP in rrep_queue
        #     self.rrep_queue.put(rrep.src_ip)
        #
        # # Otherwise, discard the RREP
        # else:
        #     DATA_LOG.info("This RREP is not for me. Discarding RREP, since in Monitoring Mode.")

    # Handling incoming ack messages
    def handle_ack(self, ack):
        # Process the ACK by arq_handler
        self.arq_handler.process_ack(ack)

    # Handling incoming reward messages
    def handle_reward(self, reward_message):
        if reward_message.msg_hash in self.reward_wait_list:
            DATA_LOG.debug("GOT REWARD MESSAGE: %s , reward value: %s, updating the entry...",
                           reward_message.msg_hash, reward_message.reward_value)
            self.reward_wait_list[reward_message.msg_hash].set_reward(reward_message.reward_value)
        else:
            DATA_LOG.debug("NO SUCH REWARD HASH! Dropping the reward message: %s, reward value: %s",
                           reward_message.msg_hash, reward_message.reward_value)
