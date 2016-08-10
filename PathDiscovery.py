#!/usr/bin/python
"""
Created on Oct 8, 2014

@author: Dmitrii Dugaev
"""

import time
import threading
import Messages
import Queue

import routing_logging

lock = threading.Lock()

PATH_DISCOVERY_LOG = routing_logging.create_routing_log("routing.path_discovery.log", "path_discovery")


class PathDiscoveryHandler:
    def __init__(self, app_queue, arq_handler):
        self.rreq_list = {}
        self.rreq_thread_list = {}

        self.arq_handler = arq_handler

        # Creating a queue for receiving RREPs
        self.rrep_queue = Queue.Queue()

        # Starting a thread for handling incoming RREP requests
        self.rrep_handler_thread = RrepHandler(app_queue, self.rrep_queue, self.rreq_list, self.rreq_thread_list)
        self.rrep_handler_thread.start()

    def run_path_discovery(self, src_ip, dst_ip, packet):

        # Check if the dst_ip in the current list of requests
        if dst_ip in self.rreq_list:

            lock.acquire()
            self.rreq_list[dst_ip].append(packet)

            PATH_DISCOVERY_LOG.info("Got DST_IP in rreq list: %s", dst_ip)
            PATH_DISCOVERY_LOG.debug("RREQ LIST: %s", self.rreq_list[dst_ip])

            lock.release()

        # If the request is new, start a new request thread, append new request to rreq_list
        else:

            PATH_DISCOVERY_LOG.info("No DST_IP in rreq list: %s", dst_ip)

            lock.acquire()
            self.rreq_list[dst_ip] = [packet]
            self.rreq_thread_list[dst_ip] = RreqRoutine(self.arq_handler, self.rreq_list,
                                                        self.rreq_thread_list, src_ip, dst_ip)
            lock.release()

            self.rreq_thread_list[dst_ip].start()

    # Provides interface for handling RREP which have been received by IncomingTrafficHandler from the net interface
    def process_rrep(self, rrep):
        self.rrep_queue.put(rrep.src_ip)

    def quit(self):
        # Stopping RREP handler
        self.rrep_handler_thread.quit()
        for i in self.rreq_thread_list:
            self.rreq_thread_list[i].quit()


# A routine thread for periodically broadcasting RREQs
class RreqRoutine(threading.Thread):
    def __init__(self, arq_handler, rreq_list, rreq_thread_list, src_ip, dst_ip):
        super(RreqRoutine, self).__init__()
        self.running = True

        self.arq_handler = arq_handler

        self.rreq_list = rreq_list
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
                if self.rreq_list.get(self.dst_ip):
                    del self.rreq_list[self.dst_ip]
                if self.rreq_thread_list.get(self.dst_ip):
                    del self.rreq_thread_list[self.dst_ip]
                lock.release()

                # Stop the thread
                self.quit()
                
            count += 1
            
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


# TODO: remove the thread
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

            PATH_DISCOVERY_LOG.info("Got RREP. Deleting RREQ thread...")

            if src_ip in self.rreq_list:
                lock.acquire()
                # Get the packets from the rreq_list
                data = self.rreq_list[src_ip]
                thread = self.rreq_thread_list[src_ip]
                # Delete the entry from rreq_list and stop corresponding rreq_thread
                del self.rreq_list[src_ip]
                thread.quit()
                del self.rreq_thread_list[src_ip]
                lock.release()

                # Send the packets back to original app_queue
                for packet in data:

                    PATH_DISCOVERY_LOG.info("Putting delayed packets back to app_queue...")
                    PATH_DISCOVERY_LOG.debug("Packet dst_ip: %s", str(packet))

                    self.app_queue.put(packet)
                
    def quit(self):
        self.running = False
