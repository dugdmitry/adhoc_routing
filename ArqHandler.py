#!/usr/bin/python
"""
Created on Jun 8, 2016

@author: Dmitrii
"""

import threading
import time
import pickle

import Messages
import routing_logging

lock = threading.Lock()

"""
This module is responsible for sending the incoming messages (data) to the given destination address using
a simple Stop-and-Go ARQ technique.
"""

ARQ_HANDLER_LOG = routing_logging.create_routing_log("routing.arq_handler.log", "arq_handler")


# Main object which sends data and processes corresponding ACKs
class ArqHandler:
    def __init__(self, raw_transport):
        # Prepare ack dsh header object
        self.dsr_ack_header = Messages.DsrHeader(5)                      # 5 corresponds to ACK dsr header type
        self.dsr_ack_header.src_mac = raw_transport.node_mac
        self.dsr_ack_header.tx_mac = raw_transport.node_mac
        # Create a dictionary which will contain a map between a (msg.id + dest_address) pair and the ArqRoutine object
        self.msg_thread_map = {}
        self.raw_transport = raw_transport

    # Start the ARQ routing for the given message and for each destination address in the dest_list
    # Now, the messages from the Messages module which have the unique ID field are supported (RREQ and RREP)
    def arq_send(self, message, dsr_header, dest_mac_list):
        for dst_address in dest_mac_list:
            # Add an entry to msg_thread_map and create a ArqRouting thread
            hash_str = hash(str(message.id) + dst_address)
            lock.acquire()
            self.msg_thread_map[hash_str] = ArqRoutine(hash_str, self.msg_thread_map,
                                                       self.raw_transport, message, dsr_header, dst_address)
            lock.release()
            self.msg_thread_map[hash_str].start()

    # Process the ACK message, received from the transport or some another receiving thread
    def process_ack(self, ack_message):
        hash_str = ack_message.msg_hash
        # Check if the given hash_str is in the msg_thread_map
        if hash_str in self.msg_thread_map:
            # If yes, stop the corresponding thread
            self.msg_thread_map[hash_str].quit()
            # Delete the entry
            lock.acquire()
            del self.msg_thread_map[hash_str]
            lock.release()
        else:
            # If no such hash in the map, just ignore it, and do nothing
            ARQ_HANDLER_LOG.info("No such ACK with this hash!!! Do nothing...")
            pass

    # Generate and send the ACK on the given service message to the dst_mac
    def send_ack(self, message, dst_mac):
        self.dsr_ack_header.dst_mac = dst_mac
        # Generate hash from the given message id
        hash_str = str(message.id) + self.raw_transport.node_mac
        # Create ACK message object
        ack_message = Messages.AckMessage(hash_str)
        # Send the message
        self.raw_transport.send_raw_frame(dst_mac, self.dsr_ack_header, pickle.dumps(ack_message))


# A routine ARQ thread which is responsible for sending the given message/data periodically in a timeout interval,
# if the corresponding ARQ hasn't been received yet
class ArqRoutine(threading.Thread):
    def __init__(self, hash_str, msg_thread_map, raw_transport, message, dsr_header, dst_address):
        super(ArqRoutine, self).__init__()
        self.running = True
        self.hash_str = hash_str
        self.msg_thread_map = msg_thread_map
        self.raw_transport = raw_transport

        self.dsr_header = dsr_header

        # # Create a dsr_header with the given type
        # self.dsr_header = Messages.DsrHeader(message.dsr_type)
        # self.dsr_header.src_mac = self.raw_transport.node_mac
        # self.dsr_header.tx_mac = self.raw_transport.node_mac

        self.serialized_message = pickle.dumps(message)
        self.dst_address = dst_address

        # Maximum number of retransmissions before dropping and failing the reliable transmission
        self.max_retries = 5
        self.timeout_interval = 0.5

    def run(self):
        count = 0
        while self.running:
            if count < self.max_retries:
                self.send_msg()
                time.sleep(self.timeout_interval)
            else:
                # Max retries reached. Delete corresponding message hashes msg_thread_map, stop the thread

                ARQ_HANDLER_LOG.info("Maximum ARQ retries reached!!! Deleting the ARQ thread...")

                lock.acquire()
                del self.msg_thread_map[self.hash_str]
                lock.release()
                # Stop the thread
                self.quit()

            count += 1

    # Send message (RREP or RREQ for now) with the dsr header to the dst_address
    def send_msg(self):
        self.raw_transport.send_raw_frame(self.dst_address, self.dsr_header, pickle.dumps(self.serialized_message))

    def quit(self):
        self.running = False
        self._Thread__stop()
