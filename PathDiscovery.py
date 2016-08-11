#!/usr/bin/python
"""
Created on Oct 8, 2014

@author: Dmitrii Dugaev
"""

import time

import Messages
import routing_logging

PATH_DISCOVERY_LOG = routing_logging.create_routing_log("routing.path_discovery.log", "path_discovery")


class PathDiscoveryHandler:
    def __init__(self, app_transport, arq_handler):
        # List of delayed packets until the RREP isn't received. Format: {dst_ip: [packet1, ..., packetN]}
        self.delayed_packets_list = {}
        # Entry deletion timeout, in seconds, in case of the RREP hasn't been received
        self.entry_deletion_timeout = 3
        # List of entry creation timestamps. Format: {dst_ip: TS}
        self.creation_timestamps = {}

        self.app_transport = app_transport
        self.arq_handler = arq_handler

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

    # Generate and send RREQ
    def send_rreq(self, src_ip, dst_ip):
        rreq = Messages.RreqMessage()
        rreq.src_ip = src_ip
        rreq.dst_ip = dst_ip
        rreq.hop_count = 1

        self.arq_handler.arq_broadcast_send(rreq)
        PATH_DISCOVERY_LOG.info("New  RREQ for IP: '%s' has been sent. Waiting for RREP", dst_ip)

    # Provides interface for handling RREP which have been received by IncomingTrafficHandler from the net interface
    def process_rrep(self, rrep):
        src_ip = rrep.src_ip

        PATH_DISCOVERY_LOG.info("Got RREP. Deleting RREQ thread...")

        if src_ip in self.delayed_packets_list:
            # Send the packets back to original app_queue
            for packet in self.delayed_packets_list[src_ip]:
                PATH_DISCOVERY_LOG.info("Putting delayed packets back to app_queue...")
                PATH_DISCOVERY_LOG.debug("Packet dst_ip: %s", str(packet))

                self.app_transport.send_to_interface(packet)

            # Delete the entry
            del self.delayed_packets_list[src_ip]
            # Delete the timestamp
            del self.creation_timestamps[src_ip]
