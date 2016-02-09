#!/usr/bin/python
"""
Created on Oct 8, 2014

@author: Dmitrii
"""

import time
import threading
import pickle
import Messages

import logging
import routing_logging


# Set logging level
LOG_LEVEL = logging.DEBUG
# Set up logging
# path_discovery_log_handler = routing_logging.create_routing_handler("routing.path_discovery.log", LOG_LEVEL)
# PATH_DISCOVERY_LOG = logging.getLogger("root.path_discovery")
# PATH_DISCOVERY_LOG.setLevel(LOG_LEVEL)
# PATH_DISCOVERY_LOG.addHandler(path_discovery_log_handler)

PATH_DISCOVERY_LOG = routing_logging.create_routing_log("routing.path_discovery.log", "path_discovery", LOG_LEVEL)
# PATH_DISCOVERY_LOG = routing_logging.create_routing_log("routing.path_discovery.log", "root.path_discovery", LOG_LEVEL)


class PathDiscoveryHandler(threading.Thread):
    def __init__(self, app_queue, wait_queue, rrep_queue, raw_transport):
        super(PathDiscoveryHandler, self).__init__()
        self.wait_queue = wait_queue
        self.rreq_list = {}
        self.rreq_thread_list = {}
        self.running = True
        self.raw_transport = raw_transport
        self.node_mac = raw_transport.node_mac

        # Starting a thread for handling incoming RREP requests
        self.rrep_handler_thread = RrepHandler(app_queue, rrep_queue, self.rreq_list, self.rreq_thread_list)
        self.rrep_handler_thread.start()
        
    def run(self):
        while self.running:
            src_ip, dst_ip, raw_data = self.wait_queue.get()
            # Check if the dst_ip in the current list of requests
            if dst_ip in self.rreq_list:
                self.rreq_list[dst_ip].append([src_ip, dst_ip, raw_data])
            # If the request is new, start a new request thread, append new request to rreq_list
            else:
                self.rreq_list[dst_ip] = [[src_ip, dst_ip, raw_data]]
                self.rreq_thread_list[dst_ip] = RreqRoutine(self.raw_transport, self.rreq_list, self.rreq_thread_list, src_ip, dst_ip, self.node_mac)
                self.rreq_thread_list[dst_ip].start()

    def quit(self):
        self.running = False
        # Stopping RREP handler
        self.rrep_handler_thread.quit()
        self.rrep_handler_thread._Thread__stop()
        # Stopping all running rreq_routines
        for i in self.rreq_thread_list:
            self.rreq_thread_list[i].quit()


# A routine thread for periodically broadcasting RREQs
class RreqRoutine(threading.Thread):
    def __init__(self, raw_transport, rreq_list, rreq_thread_list, src_ip, dst_ip, node_mac):
        super(RreqRoutine, self).__init__()
        self.running = True
        self.raw_transport = raw_transport
        self.rreq_list = rreq_list
        self.rreq_thread_list = rreq_thread_list
        self.src_ip = src_ip
        self.dst_ip = dst_ip
        self.node_mac = node_mac
        self.broadcast_mac = "ff:ff:ff:ff:ff:ff"
        self.dsr_header = Messages.DsrHeader(2)       # Type 2 corresponds to RREQ service message
        self.max_retries = 3
        self.interval = 1

    def run(self):
        count = 0
        while self.running:
            if count < self.max_retries:
                self.send_RREQ()
                time.sleep(self.interval)
            else:
                # Max retries reached. Delete corresponding packets from rreq_list, stop the thread
                # print "Maximum retries reached!!! Deleting the thread..."

                PATH_DISCOVERY_LOG.info("Maximum retries reached!!! Deleting the thread...")

                del self.rreq_list[self.dst_ip]
                del self.rreq_thread_list[self.dst_ip]
                # Stop the thread
                self.quit()
                
            count += 1
            
    # Generate and send RREQ
    def send_RREQ(self):
        RREQ = Messages.RouteRequest()
        RREQ.src_ip = self.src_ip
        RREQ.dst_ip = self.dst_ip
        RREQ.dsn = 1
        RREQ.hop_count = 1
        
        # Prepare a dsr_header
        self.dsr_header.src_mac = self.node_mac
        self.dsr_header.tx_mac = self.node_mac
        
        self.raw_transport.send_raw_frame(self.broadcast_mac, self.dsr_header, pickle.dumps(RREQ))

        # print "New  RREQ for IP: '%s' has been sent. Waiting for RREP" % self.dst_ip

        PATH_DISCOVERY_LOG.info("New  RREQ for IP: '%s' has been sent. Waiting for RREP", str(self.dst_ip))
        
    def quit(self):
        self.running = False
        self._Thread__stop()


# Class for handling incoming RREP messages
class RrepHandler(threading.Thread):
    def __init__(self, app_queue, rrep_queue, rreq_list, rreq_thread_list):
        super(RrepHandler, self).__init__()
        self.app_queue = app_queue
        self.rrep_queue = rrep_queue
        self.rreq_list = rreq_list
        self.rreq_thread_list = rreq_thread_list
        self.running = True
        
    def run(self):
        while self.running:
            src_ip = self.rrep_queue.get()

            # print "Got RREP. Deleting RREQ thread..."

            PATH_DISCOVERY_LOG.info("Got RREP. Deleting RREQ thread...")

            # Get the packets from the rreq_list
            data = self.rreq_list[src_ip]
            thread = self.rreq_thread_list[src_ip]
            # Delete the entry from rreq_list and stop corresponding rreq_thread
            del self.rreq_list[src_ip]
            thread.quit()
            del self.rreq_thread_list[src_ip]
            # Send the packets back to original app_queue
            for packet in data:
                # print "Putting delayed packets in app_queue:"
                # print packet

                PATH_DISCOVERY_LOG.info("Putting delayed packets in app_queue...")
                PATH_DISCOVERY_LOG.debug("Packet dst_ip: %s", str(packet[1]))

                self.app_queue.put(packet)
                
    def quit(self):
        self.running = False