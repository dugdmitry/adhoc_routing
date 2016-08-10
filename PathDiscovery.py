#!/usr/bin/python
"""
Created on Oct 8, 2014

@author: Dmitrii Dugaev
"""

import Messages

import routing_logging

PATH_DISCOVERY_LOG = routing_logging.create_routing_log("routing.path_discovery.log", "path_discovery")


# TODO: implement a deletion mechanism of old entries, which didn't receive the RREP for some reason.
class PathDiscoveryHandler:
    def __init__(self, app_queue, arq_handler):
        # List of delayed packets until the RREP isn't received. Format: {dst_ip: [packet1, ..., packetN]}
        self.delayed_packets_list = {}

        self.app_queue = app_queue
        self.arq_handler = arq_handler

    def run_path_discovery(self, src_ip, dst_ip, packet):
        # Check if the dst_ip in the current list
        if dst_ip in self.delayed_packets_list:
            self.delayed_packets_list[dst_ip].append(packet)
            PATH_DISCOVERY_LOG.info("Added a delayed packet: %s", dst_ip)

        # If the request is new, create a new entry, append delayed packets, and send RREQ message
        else:
            PATH_DISCOVERY_LOG.info("No DST_IP in rreq list: %s", dst_ip)
            self.delayed_packets_list.update({dst_ip: [packet]})
            # Send RREQ
            self.send_rreq(src_ip, dst_ip)

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

                self.app_queue.put(packet)

            # Delete the entry
            del self.delayed_packets_list[src_ip]
