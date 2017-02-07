#!/usr/bin/python
"""
@package DataHandler
Created on Oct 6, 2014

@author: Dmitrii Dugaev


This module is responsible for processing all incoming/outgoing data transmission from the user application performed
by AppHandler thread, and from the network interface performed by IncomingTrafficHandler thread.
This processing includes all unicast/broadcast data packets, and all RLRP service messages.
"""

# Import necessary python modules from the standard library
import Messages
import Transport
import PathDiscovery
import NeighborDiscovery
import ArqHandler
import RewardHandler
import threading
from collections import deque

# Import the necessary modules of the program
import routing_logging
from conf import MONITORING_MODE_FLAG, ENABLE_ARQ, ARQ_LIST, GW_TYPE

## @var lock
# Store the global threading.Lock object.
lock = threading.Lock()

# Set up logging
## @var DATA_LOG
# Global routing_logging.LogWrapper object for logging DataHandler activity.
DATA_LOG = routing_logging.create_routing_log("routing.data_handler.log", "data_handler")


## Wrapping class for starting all auxiliary handlers and threads.
class DataHandler:
    ## Constructor.
    # @param self The object pointer.
    # @param app_transport Reference to Transport.VirtualTransport object.
    # @param raw_transport Reference to Transport.RawTransport object.
    # @param table Reference to RouteTable.Table object.
    # @return None
    def __init__(self, app_transport, raw_transport, table):
        # Creating handlers instances
        ## @var app_handler
        # Create and store the object of DataHandler.AppHandler class.
        self.app_handler = AppHandler(app_transport, raw_transport, table)
        # Creating handler threads
        ## @var neighbor_routine
        # Create and store the object of NeighborDiscovery.NeighborDiscovery class.
        self.neighbor_routine = NeighborDiscovery.NeighborDiscovery(raw_transport, table)
        ## @var incoming_traffic_handler_thread
        # Create and store the object of DataHandler.IncomingTrafficHandler class.
        self.incoming_traffic_handler_thread = IncomingTrafficHandler(self.app_handler, self.neighbor_routine)

    ## Start the main threads.
    # @param self The object pointer.
    # @return None
    def run(self):
        self.neighbor_routine.run()
        self.incoming_traffic_handler_thread.start()

    ## Stop the main threads.
    # @param self The object pointer.
    # @return None
    def stop_threads(self):
        self.neighbor_routine.stop_threads()
        self.incoming_traffic_handler_thread.quit()
        DATA_LOG.info("Traffic handlers are stopped")


## Class for parsing the destination L3 address of an incoming packet.
# If the GW_MODE is on, the corresponding method of this class will transform the destination address to the default
# gateway address ("0.0.0.0"), if the given packet is destined to the outside network.
# The different "address transformation" logic is applied here, depending on the defined GW_TYPE value.
# See more info in the documentation.
class GatewayHandler:
    ## Constructor.
    # @param self The object pointer.
    # @param path_discovery_handler Reference to PathDiscovery.PathDiscoveryHandler object.
    # @return None
    def __init__(self, path_discovery_handler):
        ## @var default_address
        # Default IP representation of the address, located outside the given network.
        self.default_address = "0.0.0.0"
        ## @var path_discovery_handler
        # Reference to PathDiscovery.PathDiscoveryHandler object.
        self.path_discovery_handler = path_discovery_handler
        ## @var check_destination_address
        # Create a reference to the default self.check_destination_address method, depending on the GW_TYPE value.
        if GW_TYPE == "local":
            self.check_destination_address = self.check_destination_address_local

        elif GW_TYPE == "public":
            self.check_destination_address = self.check_destination_address_public

        elif GW_TYPE == "disabled":
            pass

        else:
            # Else, set the "local" mode as the default one
            self.check_destination_address = self.check_destination_address_local

    ## Default method for checking the destination address.
    # It is being overridden in the constructor, depending on the GW_MODE and GW_TYPE values, defined in the
    # configuration file.
    # Input: dst_ip - destination L3 address.
    # Output: parsed (transformed) destination L3 address.
    # @param self The object pointer.
    def check_destination_address(self, dst_ip):
        return dst_ip

    ## Check the destination address in the local mode.
    # In the local mode, the destination IP address is being checked whether it belongs to public or private domain of
    # IPv4/IPv6 addresses.
    # @param self The object pointer.
    # @param dst_address Destination IP address in string format.
    # @return Destination address
    def check_destination_address_local(self, dst_address):
        # Check if dst_address is IPv4 or IPv6
        if dst_address[0] == "f":
            # Check IPv6 address
            # Check private IPv6 addresses formats (fc00::, fd00). See RFC 4193.
            if (dst_address[:4] == "fc00") or (dst_address[:4] == "fd00"):
                return dst_address
            # Check link-local IPv6 formats (fe80::). See RFC 4862.
            elif dst_address[:4] == "fe80":
                return dst_address
            # Else, assume that the given IPv6 address is a public one, return default address.
            else:
                return self.default_address

        else:
            # Check IPv4 address
            parsed_address = map(int, dst_address.split("."))
            # Check for the IPv4 private domain. See RFC 1918.
            if parsed_address[0] == 10:
                return dst_address

            elif (parsed_address[0] == 192) and (parsed_address[1] == 168):
                return dst_address

            elif (parsed_address[0] == 172) and (16 <= parsed_address[1] <= 31):
                return dst_address

            # Check for link-local IPv4 addresses. See RFC 6890.
            elif (parsed_address[0] == 169) and (parsed_address[1] == 254):
                return dst_address

            # Else, return the default address.
            else:
                return self.default_address

    ## Check the destination address in the public mode.
    # In the public mode, the destination IP address is considered to be from outside network, if the path discovery
    # procedure has failed to find the route towards inner node. In other words, if the protocol cannot find the route
    # for the given destination address, then it will be sent to the nearest gateway node.
    # @param self The object pointer.
    # @param dst_address Destination IP address in string format.
    # @return Destination address
    def check_destination_address_public(self, dst_address):
        # Check whether the destination address is in the list if failed path discovery queries or not
        if dst_address in self.path_discovery_handler.failed_ips:
            # If yes, then return the default address
            return self.default_address
        else:
            return dst_address


## Class for handling all incoming user application data, received from the virtual network interface.
# A starting point of message transmission.
# It initialises all handler objects, which then will be used by IncomingTraffic thread upon receiving messages
# from the network.
class AppHandler:
    ## Constructor.
    # @param self The object pointer.
    # @param app_transport Reference to Transport.VirtualTransport object.
    # @param raw_transport Reference to Transport.RawTransport object.
    # @param table Reference to RouteTable.Table object.
    # @return None
    def __init__(self, app_transport, raw_transport, table):
        ## @var broadcast_list
        # List of IDs of all previously processed broadcast messages.
        # Creating a deque list for keeping the received broadcast IDs.
        self.broadcast_list = deque(maxlen=100)  # Limit the max length of the list
        ## @var app_transport
        # Reference to Transport.VirtualTransport object.
        self.app_transport = app_transport
        ## @var raw_transport
        # Reference to Transport.RawTransport object.
        self.raw_transport = raw_transport
        ## @var table
        # Reference to RouteTable.Table object.
        self.table = table
        ## @var broadcast_mac
        # Store the default MAC broadcast value, referenced from Transport.RawTransport.broadcast_mac.
        self.broadcast_mac = raw_transport.broadcast_mac
        ## @var arq_handler
        # Create and store an ArqHandler.ArqHandler instance.
        self.arq_handler = ArqHandler.ArqHandler(raw_transport, table)
        ## @var reward_wait_handler
        # Create and store a RewardHandler.RewardWaitHandler object for waiting for an incoming reward of previously
        # sent packets.
        self.reward_wait_handler = RewardHandler.RewardWaitHandler(table)
        ## @var path_discovery_handler
        # Create and store a PathDiscovery.PathDiscoveryHandler object for dealing with the packets with no next hop
        # node.
        self.path_discovery_handler = PathDiscovery.PathDiscoveryHandler(app_transport, self.arq_handler)
        ## @var gateway_handler
        # Create and store a DataHandler.GatewayHandler object for checking the location of the destination IP address.
        self.gateway_handler = GatewayHandler(self.path_discovery_handler)
        ## @var send_unicast_packet
        # Create a reference to the default self.send_unicast_packet method, depending on the ENABLE_ARQ value.
        if ENABLE_ARQ:
            self.send_unicast_packet = self.send_packet_with_arq
        else:
            self.send_unicast_packet = self.send_packet

    ## Process an incoming data packet from the upper application layer.
    # @param self The object pointer.
    # @param packet Received raw packet from the virtual network interface.
    # @return None
    def process_packet(self, packet):
        # Get the src_ip and dst_ip from the packet
        try:
            src_ip, dst_ip, packet = Transport.get_l3_addresses_from_packet(packet)
        except TypeError:
            DATA_LOG.error("The packet has UNSUPPORTED L3 protocol! Dropping the packet...")
            return 1

        # ## Handle multicast traffic ## #
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
            return None

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
            return None

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
            return None

        # ## Handle Unicast Traffic ## #
        # Check the destination address if it's inside or outside the network
        dst_ip = self.gateway_handler.check_destination_address(dst_ip)
        # Try to find a mac address of the next hop where the packet should be forwarded to
        next_hop_mac = self.table.get_next_hop_mac(dst_ip)

        # If next_hop_mac is None, it means that there is no current entry with dst_ip.
        # In that case, start a PathDiscovery procedure
        if next_hop_mac is None:
            DATA_LOG.info("No such Entry with given dst_ip in the table. Starting path discovery...")
            # ## Initiate PathDiscovery procedure for the given packet ## #
            self.path_discovery_handler.run_path_discovery(src_ip, dst_ip, packet)

        # Else, the packet is unicast, and has the corresponding Entry.
        # Check if the packet should be transmitted using ARQ.
        # Forward packet to the next hop. Start a thread for waiting an ACK with reward.
        else:
            DATA_LOG.debug("For DST_IP: %s found a next_hop_mac: %s", dst_ip, next_hop_mac)
            self.send_unicast_packet(packet, dst_ip, next_hop_mac)

    ## Send a packet to a next_hop_mac.
    # @param self The object pointer.
    # @param packet Received raw packet from the virtual network interface.
    # @param dst_ip Destination IP of the packet.
    # @param next_hop_mac MAC address of a next hop node.
    # @return None
    def send_packet(self, packet, dst_ip, next_hop_mac):
        # Create a unicast dsr message with proper values
        dsr_message = Messages.UnicastPacket()
        dsr_message.hop_count = 1
        # Send the raw data with dsr_header to the next hop
        self.raw_transport.send_raw_frame(next_hop_mac, dsr_message, packet)
        # Process the packet through the reward_wait_handler
        self.reward_wait_handler.wait_for_reward(dst_ip, next_hop_mac)

    ## Send a packet to a next_hop_mac, if ARQ retransmission is enabled.
    # @param self The object pointer.
    # @param packet Received raw packet from the virtual network interface.
    # @param dst_ip Destination IP of the packet.
    # @param next_hop_mac MAC address of a next hop node.
    # @return None
    def send_packet_with_arq(self, packet, dst_ip, next_hop_mac):
        # Check if the packet should be transmitted reliably
        upper_proto, port_number = Transport.get_upper_proto_info(packet)
        if (upper_proto in ARQ_LIST) and (port_number in ARQ_LIST[upper_proto]):
            # Transmit the packet reliably
            DATA_LOG.debug("This packet should be transmitted reliably: %s, %s", upper_proto, port_number)
            # Create reliable dsr data message with proper values
            dsr_message = Messages.ReliableDataPacket()
            dsr_message.hop_count = 1
            # Send the message using ARQ
            self.arq_handler.arq_send(dsr_message, [next_hop_mac], payload=packet)
            # Process the packet through the reward_wait_handler
            self.reward_wait_handler.wait_for_reward(dst_ip, next_hop_mac)
        # Else, transmit the data packet normally
        else:
            self.send_packet(packet, dst_ip, next_hop_mac)

    ## Send the packet back to the virtual network interface.
    # @param self The object pointer.
    # @param packet Received raw packet from the virtual network interface.
    # @return None
    def send_back(self, packet):
        self.app_transport.send_to_interface(packet)

    ## Send the data packet up to the application
    # @param self The object pointer.
    # @param packet Received raw packet from the virtual network interface.
    # @return None
    def send_up(self, packet):
        self.app_transport.send_to_app(packet)


## A thread class for receiving incoming data from the real physical network interface.
class IncomingTrafficHandler(threading.Thread):
    ## Constructor.
    # @param self The object pointer.
    # @param app_handler_thread Reference to DataHandler.AppHandler object.
    # @param neighbor_routine Reference to NeighborDiscovery.NeighborDiscovery object.
    # @return None
    def __init__(self, app_handler_thread, neighbor_routine):
        super(IncomingTrafficHandler, self).__init__()
        ## @var handle_data_packet
        # Create a reference to default self.handle_data_packet method.
        # Check the MONITORING_MODE_FLAG.
        # If True - override the self.handle_data_packet variable for working in the monitoring mode.
        ## @var handle_reliable_data_packet
        # Create a reference to default self.handle_reliable_data_packet method.
        # Check the MONITORING_MODE_FLAG.
        # If True - override the self.handle_reliable_data_packet method for working in the monitoring mode.
        ## @var handle_rreq
        # Create a reference to default self.handle_rreq method.
        # Check the MONITORING_MODE_FLAG.
        # If True - override the self.rreq_handler method for working in the monitoring mode.
        ## @var handle_rrep
        # Create a reference to default self.handle_rrep method.
        # Check the MONITORING_MODE_FLAG.
        # If True - override the self.rrep_handler method for working in the monitoring mode.
        if MONITORING_MODE_FLAG:
            self.handle_data_packet = self.handle_data_packet_monitoring_mode
            self.handle_reliable_data_packet = self.handle_reliable_data_packet_monitoring_mode
            self.handle_rreq = self.handle_rreq_monitoring_mode
            self.handle_rrep = self.handle_rrep_monitoring_mode

        ## @var running
        # Thread running state bool() flag.
        self.running = False
        ## @var app_handler_thread
        # Reference to DataHandler.AppHandler object.
        self.app_handler_thread = app_handler_thread
        ## @var raw_transport
        # Reference to Transport.RawTransport object.
        self.raw_transport = self.app_handler_thread.raw_transport
        ## @var arq_handler
        # Reference to DataHandler.AppHandler.arq_handler object.
        self.arq_handler = app_handler_thread.arq_handler
        ## @var path_discovery_handler
        # Reference to DataHandler.AppHandler.path_discovery_handler object.
        self.path_discovery_handler = app_handler_thread.path_discovery_handler
        ## @var gateway_handler
        # Reference to DataHandler.GatewayHandler object.
        self.gateway_handler = app_handler_thread.gateway_handler
        ## @var listen_neighbors_handler
        # Reference to NeighborDiscovery.NeighborDiscovery.listen_neighbors_handler object.
        self.listen_neighbors_handler = neighbor_routine.listen_neighbors_handler
        ## @var table
        # Reference to RouteTable.Table object.
        self.table = self.app_handler_thread.table
        ## @var broadcast_list
        # Reference to DataHandler.AppHandler.broadcast_list attribute.
        self.broadcast_list = app_handler_thread.broadcast_list
        ## @var broadcast_mac
        # Store the default MAC broadcast value, referenced from Transport.RawTransport.broadcast_mac.
        self.broadcast_mac = self.app_handler_thread.broadcast_mac
        ## @var max_broadcast_ttl
        # Set a maximum number of hops a broadcast frame can be forwarded over. Default value is 1.
        self.max_broadcast_ttl = 1
        ## @var reward_send_handler
        # Create a handler for generating and sending back a reward to the sender node.
        self.reward_send_handler = RewardHandler.RewardSendHandler(self.table, self.raw_transport)
        ## @var reward_wait_handler
        # Create a reference to RewardHandler.RewardWaitHandler object thread.
        self.reward_wait_handler = app_handler_thread.reward_wait_handler
        ## @var rreq_ids
        # List of all previously processed RREQ IDs.
        # Limit the max length of the list to 100.
        self.rreq_ids = deque(maxlen=100)
        ## @var rrep_ids
        # List of all previously processed RREP IDs.
        # Limit the max length of the list to 100.
        self.rrep_ids = deque(maxlen=100)
        ## @var reliable_packet_ids
        # List of all previously processed IDs of data packets have been sent reliably using ARQ.
        # Limit the max length of the list to 100.
        self.reliable_packet_ids = deque(maxlen=100)

    ## Main thread routine.
    # @param self The object pointer.
    # @return None
    def run(self):
        self.running = True
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

            elif dsr_type == 9:
                DATA_LOG.debug("Got reliable data packet: %s", str(dsr_message))
                self.handle_reliable_data_packet(src_mac, dsr_message, packet)

            else:
                DATA_LOG.error("INVALID DSR TYPE NUMBER HAS BEEN RECEIVED!!!")

    ## Default method for handling incoming unicast data packets from the network side.
    # Check the dst_mac from dsr_header. If it matches the node's own mac -> send it up to the virtual interface
    # If the packet carries the data, either send it to the next hop, or, if there is no such one, put it to the
    # AppQueue, or, if the dst_mac equals to the node's mac, send the packet up to the application.
    # @param self The object pointer.
    # @param src_mac Source MAC address of the received packet.
    # @param dsr_message RLRP unicast data packet header object from Messages module.
    # @param packet Raw data packet.
    # @return None
    def handle_data_packet(self, src_mac, dsr_message, packet):
        # Get src_ip, dst_ip from the incoming packet
        src_ip, dst_ip, packet = Transport.get_l3_addresses_from_packet(packet)

        # Check the destination address if it's inside or outside the network
        dst_ip = self.gateway_handler.check_destination_address(dst_ip)

        # Generate and send back a reward message
        self.reward_send_handler.send_reward(dst_ip, src_mac)

        # If the dst_ip matches the node's ip, send data to the App
        if dst_ip in self.table.current_node_ips:
            DATA_LOG.debug("Sending packet to the App... SRC_IP: %s, DST_IP: %s", src_ip, dst_ip)
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

    ## Method for handling incoming unicast data packets from the network if the application is running in the
    # monitoring mode (conf.MONITORING_MODE_FLAG is set to True).
    # Handle data packet, if in monitoring mode. If the dst_mac is the mac of the receiving node,
    # send the packet up to the application, otherwise, discard the packet.
    # @param self The object pointer.
    # @param src_mac Source MAC address of the received packet.
    # @param dsr_message RLRP unicast data packet header object from Messages module.
    # @param packet Raw data packet.
    # @return None
    def handle_data_packet_monitoring_mode(self, src_mac, dsr_message, packet):
        # Get src_ip, dst_ip from the incoming packet
        src_ip, dst_ip, packet = Transport.get_l3_addresses_from_packet(packet)

        # Check the destination address if it's inside or outside the network
        dst_ip = self.gateway_handler.check_destination_address(dst_ip)

        # Generate and send back a reward message
        self.reward_send_handler.send_reward(dst_ip, src_mac)

        # If the dst_ip matches the node's ip, send data to the App
        if dst_ip in self.table.current_node_ips:
            DATA_LOG.debug("Sending packet to the App... SRC_IP: %s, DST_IP: %s", src_ip, dst_ip)
            self.app_handler_thread.send_up(packet)

        # In all other cases, discard the packet
        else:
            DATA_LOG.debug("This data packet is not for me. Discarding the data packet, "
                           "since in Monitoring Mode. Dsr header: %s", dsr_message)

    ## Handle data packet, sent via ARQ.
    # @param self The object pointer.
    # @param src_mac Source MAC address of the received packet.
    # @param dsr_message RLRP unicast data packet header object from Messages module.
    # @param packet Raw data packet.
    # @return None
    def handle_reliable_data_packet(self, src_mac, dsr_message, packet):
        # Send back the ACK on the received packet in ALL cases
        self.arq_handler.send_ack(dsr_message, src_mac)

        if dsr_message.id in self.reliable_packet_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The Data Packet with this ID has been already processed. Sending the ACK back.")
            return None

        self.reliable_packet_ids.append(dsr_message.id)

        # Get src_ip, dst_ip from the incoming packet
        src_ip, dst_ip, packet = Transport.get_l3_addresses_from_packet(packet)

        # Check the destination address if it's inside or outside the network
        dst_ip = self.gateway_handler.check_destination_address(dst_ip)

        # Generate and send back a reward message
        self.reward_send_handler.send_reward(dst_ip, src_mac)

        # If the dst_ip matches the node's ip, send data to the App
        if dst_ip in self.table.current_node_ips:
            DATA_LOG.debug("Sending packet to the App... SRC_IP: %s, DST_IP: %s", src_ip, dst_ip)
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
                # Send the raw data with dsr_header to the next hop using ARQ
                self.arq_handler.arq_send(dsr_message, [next_hop_mac], payload=packet)

                # Process the packet through the reward_wait_handler
                self.reward_wait_handler.wait_for_reward(dst_ip, next_hop_mac)

    ## Handle data packet, sent via ARQ, if the monitoring mode is ON.
    # @param self The object pointer.
    # @param src_mac Source MAC address of the received packet.
    # @param dsr_message RLRP unicast data packet header object from Messages module.
    # @param packet Raw data packet.
    # @return None
    def handle_reliable_data_packet_monitoring_mode(self, src_mac, dsr_message, packet):
        # Send back the ACK on the received packet in ALL cases
        self.arq_handler.send_ack(dsr_message, src_mac)

        if dsr_message.id in self.reliable_packet_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The Data Packet with this ID has been already processed. Sending the ACK back.")
            return None

        self.reliable_packet_ids.append(dsr_message.id)

        # Get src_ip, dst_ip from the incoming packet
        src_ip, dst_ip, packet = Transport.get_l3_addresses_from_packet(packet)

        # Check the destination address if it's inside or outside the network
        dst_ip = self.gateway_handler.check_destination_address(dst_ip)

        # Generate and send back a reward message
        self.reward_send_handler.send_reward(dst_ip, src_mac)

        # If the dst_ip matches the node's ip, send data to the App
        if dst_ip in self.table.current_node_ips:
            DATA_LOG.debug("Sending packet to the App... SRC_IP: %s, DST_IP: %s", src_ip, dst_ip)
            self.app_handler_thread.send_up(packet)

        # In all other cases, discard the packet
        else:
            DATA_LOG.debug("This data packet is not for me. Discarding the data packet, "
                           "since in Monitoring Mode. Dsr header: %s", dsr_message)

    ## Handle the broadcast data packets, generated from the network application.
    # Check the broadcast_ttl with the defined max value, and either drop or forward it, accordingly.
    # @param self The object pointer.
    # @param dsr_message RLRP broadcast data packet header object from Messages module.
    # @param packet Raw data packet.
    # @return None
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

    ## Handle incoming RREQ messages.
    # @param self The object pointer.
    # @param src_mac Source MAC address of the received RREQ.
    # @param rreq RLRP RREQ service message header object from Messages module.
    # @return None
    def handle_rreq(self, src_mac, rreq):
        # Send back the ACK on the received RREQ in ALL cases
        self.arq_handler.send_ack(rreq, src_mac)

        if rreq.id in self.rreq_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The RREQ with this ID has been already processed. Sending the ACK back.")
            return None

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

    ## Handle incoming RREQs if the Monitoring Mode is ON.
    # Process only the RREQs, which have been sent for this node (dst_ip in node_ips).
    # Do not forward any other RREQs further.
    # @param self The object pointer.
    # @param src_mac Source MAC address of the received RREQ.
    # @param rreq RLRP RREQ service message header object from Messages module.
    # @return None
    def handle_rreq_monitoring_mode(self, src_mac, rreq):
        # Send back the ACK on the received RREQ in ALL cases
        self.arq_handler.send_ack(rreq, src_mac)

        if rreq.id in self.rreq_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The RREQ with this ID has been already processed. Sending the ACK back.")
            return None

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

    ## Handle incoming RREP messages.
    # @param self The object pointer.
    # @param src_mac Source MAC address of the received RREQ.
    # @param rrep RLRP RREP service message header object from Messages module.
    # @return None
    def handle_rrep(self, src_mac, rrep):
        # Send back the ACK on the received RREP in ALL cases
        self.arq_handler.send_ack(rrep, src_mac)

        if rrep.id in self.rrep_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The RREP with this ID has been already processed. Sending the ACK back.")
            return None

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

    ## Handle incoming RREPs if the Monitoring Mode is ON.
    # Receive the RREPs, which have been sent to this node, discard all other RREPs.
    # @param self The object pointer.
    # @param src_mac Source MAC address of the received RREQ.
    # @param rrep RLRP RREP service message header object from Messages module.
    # @return None
    def handle_rrep_monitoring_mode(self, src_mac, rrep):
        # Send back the ACK on the received RREP in ALL cases
        self.arq_handler.send_ack(rrep, src_mac)

        if rrep.id in self.rrep_ids:
            # Send the ACK back anyway, but do nothing with the message itself
            DATA_LOG.info("The RREP with this ID has been already processed. Sending the ACK back.")
            return None

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

    ## Handle incoming ACK messages.
    # @param self The object pointer.
    # @param ack_message RLRP ACK service message header object from Messages module.
    # @return None
    def handle_ack(self, ack_message):
        # Process the ACK by arq_handler
        self.arq_handler.process_ack(ack_message)

    ## Handle incoming reward messages.
    # @param self The object pointer.
    # @param reward_message RLRP reward service message header object from Messages module.
    # @return None
    def handle_reward(self, reward_message):
        self.reward_wait_handler.set_reward(reward_message)

    ## Stop and quit the thread operation.
    # @param self The object pointer.
    # @return None
    def quit(self):
        self.running = False
