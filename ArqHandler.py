#!/usr/bin/python
"""
Created on Jun 8, 2016

@author: Dmitrii Dugaev


This module is responsible for sending the incoming messages (data) to the given destination address using
a simple Stop-and-Go ARQ technique.
"""

import threading
import hashlib
import time

import Messages
import routing_logging

lock = threading.Lock()

ARQ_HANDLER_LOG = routing_logging.create_routing_log("routing.arq_handler.log", "arq_handler")

max_int32 = 0xFFFFFFFF


# Main object which sends data and processes corresponding ACKs
class ArqHandler:
    def __init__(self, raw_transport, table):
        # Create a dictionary which will contain a map between a (msg.id + dest_address) pair and the ArqRoutine object
        self.msg_thread_map = {}
        self.raw_transport = raw_transport
        self.table = table

    # Start the ARQ send for the given message and for each destination address in the dest_list.
    # For now, only the messages with unique ID field are supported.
    def arq_send(self, message, dest_mac_list):
        for dst_address in dest_mac_list:
            ARQ_HANDLER_LOG.debug("ARQ_SEND for %s", dst_address)
            # Add an entry to msg_thread_map and create a ArqRoutine thread
            hash_str = hashlib.md5(str(message.id) + dst_address).hexdigest()
            # Convert hash_str from hex to 32-bit integer
            hash_int = int(hash_str, 16) & max_int32

            lock.acquire()
            self.msg_thread_map[hash_int] = ArqRoutine(hash_int, self.msg_thread_map,
                                                       self.raw_transport, message, dst_address)
            lock.release()
            self.msg_thread_map[hash_int].start()

    # Start the ARQ broadcast send for the given message.
    # The message will be sent to ALL current neighbors of the node.
    # For now, only the messages with unique ID field are supported.
    def arq_broadcast_send(self, message):
        dest_mac_list = self.table.get_neighbors()
        for dst_address in dest_mac_list:
            ARQ_HANDLER_LOG.debug("ARQ_SEND for %s", dst_address)
            # Add an entry to msg_thread_map and create a ArqRoutine thread
            hash_str = hashlib.md5(str(message.id) + dst_address).hexdigest()
            # Convert hash_str from hex to 32-bit integer
            hash_int = int(hash_str, 16) & max_int32

            lock.acquire()
            self.msg_thread_map[hash_int] = ArqRoutine(hash_int, self.msg_thread_map,
                                                       self.raw_transport, message, dst_address)
            lock.release()
            self.msg_thread_map[hash_int].start()

    # Process the ACK message, received from the transport or some another receiving thread
    def process_ack(self, ack_message):
        hash_int = ack_message.msg_hash
        # Check if the given hash_int is in the msg_thread_map
        if hash_int in self.msg_thread_map:
            # If yes, stop the corresponding thread
            self.msg_thread_map[hash_int].quit()
            # Delete the entry
            lock.acquire()
            if self.msg_thread_map.get(hash_int):
                del self.msg_thread_map[hash_int]
            lock.release()
        else:
            # If no such hash in the map, just ignore it, and do nothing
            ARQ_HANDLER_LOG.info("No such ACK with this hash!!! Do nothing...")

    # Generate and send the ACK on the given service message to the dst_mac
    def send_ack(self, message, dst_mac):
        ARQ_HANDLER_LOG.info("Sending ACK back on the message %s", str(message))
        # Generate hash from the given message id
        hash_str = hashlib.md5(str(message.id) + self.raw_transport.node_mac).hexdigest()
        # Convert hash_str from hex to 32-bit integer
        hash_int = int(hash_str, 16) & max_int32

        # Create ACK message object
        ack_message = Messages.AckMessage()
        ack_message.msg_hash = hash_int
        # Send the message
        self.raw_transport.send_raw_frame(dst_mac, ack_message, "")


# A routine ARQ thread which is responsible for sending the given message/data periodically in a timeout interval,
# if the corresponding ARQ hasn't been received yet
class ArqRoutine(threading.Thread):
    def __init__(self, hash_int, msg_thread_map, raw_transport, message, dst_address):
        super(ArqRoutine, self).__init__()
        self.running = True
        self.hash_int = hash_int
        self.msg_thread_map = msg_thread_map
        self.raw_transport = raw_transport

        self.dsr_message = message
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
                if self.msg_thread_map.get(self.hash_int):
                    del self.msg_thread_map[self.hash_int]
                lock.release()
                # Stop the thread
                self.quit()

            count += 1

    # Send message (RREP or RREQ for now) with the dsr header to the dst_address
    def send_msg(self):

        self.raw_transport.send_raw_frame(self.dst_address, self.dsr_message, "")

        ARQ_HANDLER_LOG.debug("Sent raw frame on: %s", self.dst_address)

    def quit(self):
        self.running = False
