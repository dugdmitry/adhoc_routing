#!/usr/bin/python
"""
@package PathDiscovery
Created on Oct 8, 2014

@author: Dmitrii Dugaev


This module is responsible for sending out initial RREQ messages into the network, and waiting until the corresponding
RREP messages are received.
"""

# Import necessary python modules from the standard library
import time

# Import the necessary modules of the program
import Messages
import routing_logging

## @var PATH_DISCOVERY_LOG
# Global routing_logging.LogWrapper object for logging PathDiscovery activity.
PATH_DISCOVERY_LOG = routing_logging.create_routing_log("routing.path_discovery.log", "path_discovery")


## Main class for dealing with sending/receiving RREQ/RREP service messages.
class PathDiscoveryHandler:
    ## Constructor.
    # @param self The object pointer.
    # @param app_transport Reference to Transport.VirtualTransport object.
    # @param arq_handler Reference to ArqHandler.ArqHandler object.
    # @return None
    def __init__(self, app_transport, arq_handler):
        ## @var delayed_packets_list
        # Dictionary of delayed packets until the RREP isn't received. Format: {dst_ip: [packet1, ..., packetN]}.
        self.delayed_packets_list = {}
        ## @var entry_deletion_timeout
        # Entry deletion timeout, in seconds, in case of the RREP hasn't been received.
        self.entry_deletion_timeout = 3
        ## @var creation_timestamps
        # Dictionary of entry creation timestamps. Format: {dst_ip: TS}.
        self.creation_timestamps = {}
        ## @var app_transport
        # Reference to Transport.VirtualTransport object.
        self.app_transport = app_transport
        ## @var arq_handler
        # Reference to ArqHandler.ArqHandler object.
        self.arq_handler = arq_handler

    ## Start path discovery procedure by sending out initial RREQ message.
    # @param self The object pointer.
    # @param src_ip Source IP address of the route.
    # @param dst_ip Destination IP address of the route.
    # @param packet Raw packet data from the virtual interface, which should be sent to this destination IP.
    # @return None
    def run_path_discovery(self, src_ip, dst_ip, packet):
        # Check if the dst_ip in the current list
        if dst_ip in self.delayed_packets_list:
            # Check if the timeout has been reached
            if (time.time() - self.creation_timestamps[dst_ip]) > self.entry_deletion_timeout:
                # If yes, Delete the entry with all delayed packets
                del self.delayed_packets_list[dst_ip]
                # Delete the timestamp
                del self.creation_timestamps[dst_ip]
                # Run path discovery for the current packet again
                self.run_path_discovery(src_ip, dst_ip, packet)

            else:
                # If no, append the packet to the delayed list
                self.delayed_packets_list[dst_ip].append(packet)
                PATH_DISCOVERY_LOG.info("Added a delayed packet: %s", dst_ip)

        # If the request is new, create a new entry, append delayed packets, and send RREQ message
        else:
            PATH_DISCOVERY_LOG.info("No DST_IP in rreq list: %s", dst_ip)
            # Create a new entry
            self.delayed_packets_list.update({dst_ip: [packet]})
            # Set the timestamp of creation
            self.creation_timestamps.update({dst_ip: time.time()})
            # Send RREQ
            self.send_rreq(src_ip, dst_ip)
            # Set the timestamp
            self.creation_timestamps[dst_ip] = time.time()

    ## Generate and send RREQ message.
    # @param self The object pointer.
    # @param src_ip Source IP address of the route.
    # @param dst_ip Destination IP address of the route.
    # @return None
    def send_rreq(self, src_ip, dst_ip):
        rreq = Messages.RreqMessage()
        rreq.src_ip = src_ip
        rreq.dst_ip = dst_ip
        rreq.hop_count = 1

        self.arq_handler.arq_broadcast_send(rreq)
        PATH_DISCOVERY_LOG.info("New  RREQ for IP: '%s' has been sent. Waiting for RREP", dst_ip)

    ## Process an incoming RREP message.
    # Provides interface for handling RREP which have been received by IncomingTrafficHandler from the net interface.
    # @param self The object pointer.
    # @param rrep Messages.RrepMessage object.
    # @return None
    def process_rrep(self, rrep):
        src_ip = rrep.src_ip

        PATH_DISCOVERY_LOG.info("Got RREP. Deleting RREQ thread...")

        if src_ip in self.delayed_packets_list:
            # Send the packets back to original app_queue
            for packet in self.delayed_packets_list[src_ip]:
                PATH_DISCOVERY_LOG.info("Putting delayed packets back to app_queue...")
                PATH_DISCOVERY_LOG.debug("Packet dst_ip: %s", src_ip)

                self.app_transport.send_to_interface(packet)

            # Delete the entry
            del self.delayed_packets_list[src_ip]
            # Delete the timestamp
            del self.creation_timestamps[src_ip]
