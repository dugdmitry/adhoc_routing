#!/usr/bin/python
"""
Created on Oct 8, 2014

@author: Dmitrii Dugaev
"""

import time
import threading
import Messages

import routing_logging

lock = threading.Lock()

PATH_DISCOVERY_LOG = routing_logging.create_routing_log("routing.path_discovery.log", "path_discovery")


class PathDiscoveryHandler:
    def __init__(self, app_queue, arq_handler):
        self.rreq_thread_list = {}

        self.app_queue = app_queue
        self.arq_handler = arq_handler

    def run_path_discovery(self, src_ip, dst_ip, packet):

        # Check if the dst_ip in the current list of requests
        if dst_ip in self.rreq_thread_list:

            lock.acquire()
            self.rreq_thread_list[dst_ip].add_packet(packet)

            PATH_DISCOVERY_LOG.info("Added a delayed packet: %s", dst_ip)
            lock.release()

        # If the request is new, start a new request thread, append new request to rreq_list
        else:

            PATH_DISCOVERY_LOG.info("No DST_IP in rreq list: %s", dst_ip)

            lock.acquire()
            self.rreq_thread_list[dst_ip] = RreqRoutine(self.arq_handler, self.rreq_thread_list, src_ip, dst_ip)
            self.rreq_thread_list[dst_ip].add_packet(packet)
            lock.release()

            self.rreq_thread_list[dst_ip].start()

    # Provides interface for handling RREP which have been received by IncomingTrafficHandler from the net interface
    def process_rrep(self, rrep):
        src_ip = rrep.src_ip

        PATH_DISCOVERY_LOG.info("Got RREP. Deleting RREQ thread...")

        if src_ip in self.rreq_thread_list:
            lock.acquire()
            thread = self.rreq_thread_list[src_ip]
            lock.release()

            # Send the packets back to original app_queue
            for packet in thread.delayed_packets:
                PATH_DISCOVERY_LOG.info("Putting delayed packets back to app_queue...")
                PATH_DISCOVERY_LOG.debug("Packet dst_ip: %s", str(packet))

                self.app_queue.put(packet)

            lock.acquire()
            thread.quit()
            del self.rreq_thread_list[src_ip]
            lock.release()

    def quit(self):
        for i in self.rreq_thread_list:
            self.rreq_thread_list[i].quit()


# A routine thread for periodically broadcasting RREQs
class RreqRoutine(threading.Thread):
    def __init__(self, arq_handler, rreq_thread_list, src_ip, dst_ip):
        super(RreqRoutine, self).__init__()
        self.running = True

        self.arq_handler = arq_handler

        self.delayed_packets = list()

        self.rreq_thread_list = rreq_thread_list
        self.src_ip = src_ip
        self.dst_ip = dst_ip

        self.max_retries = 1
        self.interval = 10

    def run(self):
        count = 0
        while self.running:
            if count < self.max_retries:
                self.send_rreq()
                time.sleep(self.interval)
            else:
                # Max retries reached. Delete corresponding packets from rreq_list, stop the thread
                PATH_DISCOVERY_LOG.info("Maximum retries reached!!! Deleting the thread...")

                lock.acquire()
                if self.rreq_thread_list.get(self.dst_ip):
                    del self.rreq_thread_list[self.dst_ip]
                lock.release()

                # Stop the thread
                self.quit()
                
            count += 1

    # Add newly incoming packet to the list of delayed packets
    def add_packet(self, packet):
        self.delayed_packets.append(packet)
            
    # Generate and send RREQ
    def send_rreq(self):
        rreq = Messages.RreqMessage()
        rreq.src_ip = self.src_ip
        rreq.dst_ip = self.dst_ip
        rreq.hop_count = 1

        self.arq_handler.arq_broadcast_send(rreq)

        PATH_DISCOVERY_LOG.info("New  RREQ for IP: '%s' has been sent. Waiting for RREP", str(self.dst_ip))
        
    def quit(self):
        self.running = False
