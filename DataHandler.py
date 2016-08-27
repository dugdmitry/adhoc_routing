#!/usr/bin/python
"""
Created on Oct 6, 2014

@author: Dmitrii Dugaev
"""

import Messages
import Transport
import PathDiscovery
import NeighborDiscovery
import ArqHandler
import RewardHandler

import threading
from collections import deque

import routing_logging
from conf import MONITORING_MODE_FLAG

lock = threading.Lock()

# Set up logging
DATA_LOG = routing_logging.create_routing_log("routing.data_handler.log", "data_handler")


# Wrapping class for starting all auxiliary handlers and threads
class DataHandler:
    def __init__(self, app_transport, raw_transport, table):
        # Creating handlers instances
        self.app_handler = AppHandler(app_transport, raw_transport, table)
        # Creating handler threads
        self.neighbor_routine = NeighborDiscovery.NeighborDiscovery(raw_transport, table)
        self.incoming_traffic_handler_thread = IncomingTrafficHandler(self.app_handler, self.neighbor_routine)

    # Starting the threads
    def run(self):
        self.neighbor_routine.run()
        self.incoming_traffic_handler_thread.start()

    # Stopping the threads
    def stop_threads(self):
        self.neighbor_routine.stop_threads()
        self.incoming_traffic_handler_thread.quit()

        DATA_LOG.info("Traffic handlers are stopped")


# A starting point of message transmission.
# It initialises all handler objects, which then will be used by IncomingTraffic thread upon receiving messages
# from the network.
class AppHandler:
    def __init__(self, app_transport, raw_transport, table):
        # Creating a deque list for keeping the received broadcast IDs
        self.broadcast_list = deque(maxlen=100)  # Limit the max length of the list

        self.app_transport = app_transport
        self.raw_transport = raw_transport
        self.table = table

        self.broadcast_mac = raw_transport.broadcast_mac

        # Create an arq handler instance
        self.arq_handler = ArqHandler.ArqHandler(raw_transport, table)

        # Create a handler for waiting for an incoming reward for previously sent packets
        self.reward_wait_handler = RewardHandler.RewardWaitHandler(table)

        # Create and start path_discovery_handler for dealing with the packets with no next hop node
        self.path_discovery_handler = PathDiscovery.PathDiscoveryHandler(app_transport, self.arq_handler)

    def process_packet(self, packet):
        # Get the src_ip and dst_ip from the packet
        src_ip, dst_ip, packet = Transport.get_l3_addresses_from_packet(packet)

        # Try to find a mac address of the next hop where a packet should be forwarded to
        next_hop_mac = self.table.get_next_hop_mac(dst_ip)

        # Check if the packet's destination address is IPv6 multicast
        # Always starts from "ff0X::",
        # see https://en.wikipedia.org/wiki/IPv6_address#Multicast_addresses
        if dst_ip[:2] == "ff":

            DATA_LOG.info("Multicast IPv6: %s", dst_ip)

            # Create a broadcast dsr message
            dsr_message = Messages.BroadcastPacket()
            dsr_message.broadcast_ttl = 1
            # Put the dsr broadcast id to the broadcast_list
            self.broadcast_list.append(dsr_message.id)

            # Broadcast it further to the network
            self.raw_transport.send_raw_frame(self.broadcast_mac, dsr_message, packet)

        # Check if the packet's destination address is IPv4 multicast or broadcast.
        # The IPv4 multicasts start with either 224.x.x.x or 239.x.x.x
        # See: https://en.wikipedia.org/wiki/Multicast_address#IPv4
        elif dst_ip[:3] == "224" or dst_ip[:3] == "239":
            DATA_LOG.info("Multicast IPv4: %s", dst_ip)

            # Create a broadcast dsr message
            dsr_message = Messages.BroadcastPacket()
            dsr_message.broadcast_ttl = 1
            # Put the dsr broadcast id to the broadcast_list
            self.broadcast_list.append(dsr_message.id)

            # Broadcast it further to the network
            self.raw_transport.send_raw_frame(self.broadcast_mac, dsr_message, packet)

        # Check if the packet's destination address is IPv4 broadcast.
        # The IPv4 broadcasts ends with .255
        # See: https://en.wikipedia.org/wiki/IP_address#Broadcast_addressing
        elif dst_ip[-3:] == "255":
            DATA_LOG.info("Broadcast IPv4: %s", dst_ip)

            # Create a broadcast dsr message
            dsr_message = Messages.BroadcastPacket()
            dsr_message.broadcast_ttl = 1
            # Put the dsr broadcast id to the broadcast_list
            self.broadcast_list.append(dsr_message.id)

            # Broadcast it further to the network
            self.raw_transport.send_raw_frame(self.broadcast_mac, dsr_message, packet)

        # If next_hop_mac is None, it means that there is no current entry with dst_ip.
        # In that case, start a PathDiscovery procedure
        elif next_hop_mac is None:

            DATA_LOG.info("No such Entry with given dst_ip in the table. Starting path discovery...")

            # ## Initiate PathDiscovery procedure for the given packet ## #
            self.path_discovery_handler.run_path_discovery(src_ip, dst_ip, packet)

        # Else, the packet is unicast, and has the corresponding Entry.
        # Forward packet to the next hop. Start a thread wor waiting an ACK with reward.
        else:

            DATA_LOG.debug("For DST_IP: %s found a next_hop_mac: %s", dst_ip, next_hop_mac)

            # Create a unicast dsr message with proper values
            dsr_message = Messages.UnicastPacket()
            dsr_message.hop_count = 1

            # Send the raw data with dsr_header to the next hop
            self.raw_transport.send_raw_frame(next_hop_mac, dsr_message, packet)
            # Process the packet through the reward_wait_handler
            self.reward_wait_handler.wait_for_reward(dst_ip, next_hop_mac)

    # Send the packet back to the virtual network interface
    def send_back(self, packet):
        self.app_transport.send_to_interface(packet)

    # Send the data packet up to the application
    def send_up(self, packet):
        self.app_transport.send_to_app(packet)


# A thread for receiving the incoming data from a real network interface.
class IncomingTrafficHandler(threading.Thread):
    def __init__(self, app_handler_thread, neighbor_routine):
        super(IncomingTrafficHandler, self).__init__()
        # Check the MONITORING_MODE_FLAG.
        # If True - override the self.handle_data_packet method for working in the monitoring mode.
        # If True - override the self.rreq_handler and self.rrep_handler methods for working in the monitoring mode.
        if MONITORING_MODE_FLAG:
            self.handle_data_packet = self.handle_data_packet_monitoring_mode
            self.handle_rreq = self.handle_rreq_monitoring_mode
            self.handle_rrep = self.handle_rrep_monitoring_mode

        self.running = True
        self.app_handler_thread = app_handler_thread
        self.raw_transport = self.app_handler_thread.raw_transport
        self.arq_handler = app_handler_thread.arq_handler

        self.path_discovery_handler = app_handler_thread.path_discovery_handler

        self.listen_neighbors_handler = neighbor_routine.listen_neighbors_handler
        self.table = self.app_handler_thread.table
        self.broadcast_list = app_handler_thread.broadcast_list
        self.broadcast_mac = self.app_handler_thread.broadcast_mac
        # Set a maximum number of hops a broadcast frame can be forwarded over
        self.max_broadcast_ttl = 1

        # Create a handler for generating and sending back a reward to the sender node
        self.reward_send_handler = RewardHandler.RewardSendHandler(self.table, self.raw_transport)
        self.reward_wait_handler = app_handler_thread.reward_wait_handler

        self.rreq_ids = deque(maxlen=100)  # Limit the max length of the list
        self.rrep_ids = deque(maxlen=100)  # Limit the max length of the list

    def run(self):
        while self.running:

            src_mac, dsr_message, packet = self.raw_transport.recv_data()

            dsr_type = dsr_message.type

            # If it's a data packet, handle it accordingly
            if dsr_type == 0:
                DATA_LOG.debug("Got unicast data packet: %s", str(dsr_message))
                self.handle_data_packet(src_mac, dsr_message, packet)

            elif dsr_type == 1:
                DATA_LOG.debug("Got broadcast data packet: %s", str(dsr_message))
                self.handle_broadcast_packet(dsr_message, packet)

            elif dsr_type == 2 or dsr_type == 3:
                DATA_LOG.debug("Got RREQ service message: %s", str(dsr_message))
                self.handle_rreq(src_mac, dsr_message)

            elif dsr_type == 4 or dsr_type == 5:
                DATA_LOG.debug("Got RREP service message: %s", str(dsr_message))
                self.handle_rrep(src_mac, dsr_message)

            elif dsr_type == 6:
                DATA_LOG.debug("Got HELLO service message: %s", str(dsr_message))
                # Handle HELLO message
                self.listen_neighbors_handler.process_neighbor(src_mac, dsr_message)

            elif dsr_type == 7:
                DATA_LOG.debug("Got ACK service message: %s", str(dsr_message))
                self.handle_ack(dsr_message)

            elif dsr_type == 8:
                DATA_LOG.debug("Got REWARD service message: %s", str(dsr_message))
                self.handle_reward(dsr_message)

    # Check the dst_mac from dsr_header. If it matches the node's own mac -> send it up to the virtual interface
    # If the packet carries the data, either send it to the next hop, or,
    # if there is no such one, put it to the AppQueue, or,
    # if the dst_mac equals to the node's mac, send the packet up to the application
    def handle_data_packet(self, src_mac, dsr_message, packet):
        # Get src_ip, dst_ip from the incoming packet
        src_ip, dst_ip, packet = Transport.get_l3_addresses_from_packet(packet)

        # Generate and send back a reward message
        self.reward_send_handler.send_reward(dst_ip, src_mac)

        # If the dst_ip matches the node's ip, send data to the App
        if dst_ip in self.table.current_node_ips:

            DATA_LOG.debug("Sending packet with to the App... SRC_IP: %s, DST_IP: %s", src_ip, dst_ip)

            self.app_handler_thread.send_up(packet)

        # Else, try to find the next hop in the route table
        else:
            next_hop_mac = self.table.get_next_hop_mac(dst_ip)
            DATA_LOG.debug("IncomingTraffic: For DST_IP: %s found a next_hop_mac: %s", dst_ip, next_hop_mac)
            DATA_LOG.debug("Current entry: %s", self.table.get_entry(dst_ip))

            # If no entry is found, put the packet to the initial AppQueue
            if next_hop_mac is None:
                self.app_handler_thread.send_back(packet)

            # Else, forward the packet to the next_hop. Start a reward wait thread, if necessary.
            else:
                dsr_message.hop_count += 1
                # Send the raw data with dsr_header to the next hop
                self.raw_transport.send_raw_frame(next_hop_mac, dsr_message, packet)

                # Process the packet through the reward_wait_handler
                self.reward_wait_handler.wait_for_reward(dst_ip, next_hop_mac)

    # Handle data packet, if in monitoring mode. If the dst_mac is the mac of the receiving node,
    # send the packet up to the application, otherwise, discard the packet
    def handle_data_packet_monitoring_mode(self, src_mac, dsr_message, packet):
        # Get src_ip, dst_ip from the incoming packet
        src_ip, dst_ip, packet = Transport.get_l3_addresses_from_packet(packet)

        # Generate and send back a reward message
        self.reward_send_handler.send_reward(dst_ip, src_mac)

        # If the dst_ip matches the node's ip, send data to the App
        if dst_ip in self.table.current_node_ips:

            DATA_LOG.debug("Sending packet with to the App... SRC_IP: %s, DST_IP: %s", src_ip, dst_ip)

            self.app_handler_thread.send_up(packet)

        # In all other cases, discard the packet
        else:
            DATA_LOG.debug("This data packet is not for me. Discarding the data packet, "
                           "since in Monitoring Mode. Dsr header: %s", dsr_message)

    # Check the broadcast_ttl with the defined max value, and either drop or forward it, accordingly
    def handle_broadcast_packet(self, dsr_message, packet):
        # Check whether the packet with this particular broadcast_id has been previously received
        if dsr_message.id in self.broadcast_list:

            # Just ignore it
            DATA_LOG.debug("Dropped broadcast id: %s", dsr_message.id)

        # Check whether the broadcast packet has reached the maximum established broadcast ttl
        elif dsr_message.broadcast_ttl > self.max_broadcast_ttl:

            # Just ignore it
            DATA_LOG.debug("Dropped broadcast id due to max_ttl: %s", dsr_message.id)

        else:
            # Accept and forward the broadcast further
            DATA_LOG.debug("Accepting the broadcast: %s", dsr_message.id)

            # Send this ipv4 broadcast/multicast or ipv6 multicast packet up to the application
            self.app_handler_thread.send_up(packet)
            # Put it to the broadcast list
            self.broadcast_list.append(dsr_message.id)
            # Increment broadcast ttl and send the broadcast the packet further
            dsr_message.broadcast_ttl += 1
            self.raw_transport.send_raw_frame(self.broadcast_mac, dsr_message, packet)

    def handle_rreq(self, src_mac, rreq):
        # Send back the ACK on the received RREQ in ALL cases
        self.arq_handler.send_ack(rreq, src_mac)

        if rreq.id in self.rreq_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The RREQ with this ID has been already processed. Sending the ACK back.")

            return 0

        DATA_LOG.info("Processing RREQ")

        self.rreq_ids.append(rreq.id)

        # Update corresponding estimation values in RouteTable for the given src_ip and mac address of the RREQ
        self.table.update_entry(rreq.src_ip, src_mac, round(50.0 / rreq.hop_count, 2))

        if rreq.dst_ip in self.table.current_node_ips:

            DATA_LOG.info("Processing the RREQ, generating and sending back the RREP broadcast")

            # Generate and send RREP back to the source
            rrep = Messages.RrepMessage()
            rrep.src_ip = rreq.dst_ip
            rrep.dst_ip = rreq.src_ip
            rrep.hop_count = 1
            rrep.id = rreq.id

            # Send the RREP reliably using arq_handler
            self.arq_handler.arq_broadcast_send(rrep)

            DATA_LOG.debug("Generated RREP: %s", str(rrep))

        else:

            DATA_LOG.info("Broadcasting RREQ further")

            # Change next_hop value to NODE_IP and broadcast the message further
            rreq.hop_count += 1

            # Send the RREQ reliably using arq_handler to the list of current neighbors except the one who sent it
            dst_mac_list = self.table.get_neighbors()
            if src_mac in dst_mac_list:
                dst_mac_list.remove(src_mac)

            self.arq_handler.arq_send(rreq, dst_mac_list)

    # Handle RREQs if in Monitoring Mode. Process only the RREQs, which have been sent for them (dst_ip in node_ips)
    # Do not forward any other RREQs further.
    def handle_rreq_monitoring_mode(self, src_mac, rreq):
        # Send back the ACK on the received RREQ in ALL cases
        self.arq_handler.send_ack(rreq, src_mac)

        if rreq.id in self.rreq_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The RREQ with this ID has been already processed. Sending the ACK back.")

            return 0

        DATA_LOG.info("Processing RREQ")

        self.rreq_ids.append(rreq.id)

        # Update corresponding estimation values in RouteTable for the given src_ip and mac address of the RREQ
        self.table.update_entry(rreq.src_ip, src_mac, round(50.0 / rreq.hop_count, 2))

        if rreq.dst_ip in self.table.current_node_ips:

            DATA_LOG.info("Processing the RREQ, generating and sending back the RREP")

            # Generate and send RREP back to the source
            rrep = Messages.RrepMessage()
            rrep.src_ip = rreq.dst_ip
            rrep.dst_ip = rreq.src_ip
            rrep.hop_count = 1
            rrep.id = rreq.id

            # Send the RREP reliably using arq_handler
            self.arq_handler.arq_broadcast_send(rrep)

            DATA_LOG.debug("Generated RREP: %s", str(rrep))

        # If the dst_ip is not for this node, discard the RREQ
        else:

            DATA_LOG.info("This RREQ is not for me. Discarding RREQ, since in Monitoring Mode.")

    def handle_rrep(self, src_mac, rrep):
        # Send back the ACK on the received RREP in ALL cases
        self.arq_handler.send_ack(rrep, src_mac)

        if rrep.id in self.rrep_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The RREP with this ID has been already processed. Sending the ACK back.")

            return 0

        DATA_LOG.info("Processing RREP...")

        self.rrep_ids.append(rrep.id)

        # Update corresponding estimation values in RouteTable for the given src_ip and mac address of the RREQ
        self.table.update_entry(rrep.src_ip, src_mac, round(50.0 / rrep.hop_count, 2))

        if rrep.dst_ip in self.table.current_node_ips:

            DATA_LOG.info("This RREP is for me. Stop the discovery procedure, send the data.")

            # Put RREP in the processing by path_discovery_handler
            self.path_discovery_handler.process_rrep(rrep)

        else:

            DATA_LOG.info("Broadcasting RREP further")

            # Change next_hop value to NODE_IP and broadcast the message further
            rrep.hop_count += 1

            # Send the RREP reliably using arq_handler to the list of current neighbors except the one who sent it
            dst_mac_list = self.table.get_neighbors()
            if src_mac in dst_mac_list:
                dst_mac_list.remove(src_mac)

            self.arq_handler.arq_send(rrep, dst_mac_list)

    # Handle incoming RREPs while in Monitoring Mode.
    # Receive the RREPs, which have been sent to this node, discard all other RREPs.
    def handle_rrep_monitoring_mode(self, src_mac, rrep):
        # Send back the ACK on the received RREP in ALL cases
        self.arq_handler.send_ack(rrep, src_mac)

        if rrep.id in self.rrep_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The RREP with this ID has been already processed. Sending the ACK back.")

            return 0

        DATA_LOG.info("Processing RREP...")

        self.rrep_ids.append(rrep.id)

        # Update corresponding estimation values in RouteTable for the given src_ip and mac address of the RREQ
        self.table.update_entry(rrep.src_ip, src_mac, round(50.0 / rrep.hop_count, 2))

        if rrep.dst_ip in self.table.current_node_ips:

            DATA_LOG.info("This RREP is for me. Stop the discovery procedure, send the data.")

            # Put RREP in the processing by path_discovery_handler
            self.path_discovery_handler.process_rrep(rrep)

        # Otherwise, discard the RREP
        else:
            DATA_LOG.info("This RREP is not for me. Discarding RREP, since in Monitoring Mode.")

    # Handling incoming ack messages
    def handle_ack(self, ack_message):
        # Process the ACK by arq_handler
        self.arq_handler.process_ack(ack_message)

    # Handling incoming reward messages
    def handle_reward(self, reward_message):
        self.reward_wait_handler.set_reward(reward_message)

    def quit(self):
        self.running = False
