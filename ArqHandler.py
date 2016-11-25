#!/usr/bin/python
"""
@package ArqHandler
Created on Jun 8, 2016

@author: Dmitrii Dugaev


This module is responsible for sending the incoming messages (data) to the given destination address using
a simple Stop-and-Go ARQ technique.
"""

# Import necessary python modules from the standard library
import threading
import hashlib
import time

# Import the necessary modules of the program
import Messages
import routing_logging

## @var lock
# Store the global threading.Lock object.
lock = threading.Lock()

## @var ARQ_HANDLER_LOG
# Global routing_logging.LogWrapper object for logging ArqHandler activity.
ARQ_HANDLER_LOG = routing_logging.create_routing_log("routing.arq_handler.log", "arq_handler")

## @var max_int32
# 32-bit mask constant.
max_int32 = 0xFFFFFFFF


## Main class for sending data and processing the corresponding ACKs.
class ArqHandler:
    ## Constructor.
    # @param self The object pointer.
    # @param raw_transport Reference to Transport.RawTransport object.
    # @param table Reference to RouteTable.Table object.
    # @return None
    def __init__(self, raw_transport, table):
        # Create a dictionary which will contain a map between a (msg.id + dest_address) pair and the ArqRoutine object
        ## @var msg_thread_map
        # Dictionary with {hash(msg.id + dest_address) : ArqHandler.ArqRoutine object}.
        self.msg_thread_map = {}
        ## @var raw_transport
        # Reference to Transport.RawTransport object.
        self.raw_transport = raw_transport
        ## @var table
        # Reference to RouteTable.Table object.
        self.table = table

    # TODO: refactor those two methods into a single one to remove code redundancy.
    ## Start the ARQ send for the given message and for each destination address in the dest_list.
    # For now, only the messages with unique ID field are supported.
    # @param self The object pointer.
    # @param message Message object from Messages module.
    # @param dest_mac_list List of MAC addresses the message should be sent to.
    # @param payload Payload of the transmitted frame. Default is "".
    # @return None
    def arq_send(self, message, dest_mac_list, payload=""):
        for dst_address in dest_mac_list:
            ARQ_HANDLER_LOG.debug("ARQ_SEND for %s", dst_address)
            # Add an entry to msg_thread_map and create a ArqRoutine thread
            hash_str = hashlib.md5(str(message.id) + dst_address).hexdigest()
            # Convert hash_str from hex to 32-bit integer
            hash_int = int(hash_str, 16) & max_int32

            lock.acquire()
            self.msg_thread_map[hash_int] = ArqRoutine(hash_int, self.msg_thread_map, self.raw_transport,
                                                       message, payload, dst_address)
            lock.release()
            self.msg_thread_map[hash_int].start()

    ## Start the ARQ broadcast send for the given message.
    # The message will be sent to ALL current neighbors of the node.
    # For now, only the messages with unique ID field are supported.
    # @param self The object pointer.
    # @param message Message object from Messages module.
    # @param payload Payload of the transmitted frame. Default is "".
    # @return None
    def arq_broadcast_send(self, message, payload=""):
        dest_mac_list = self.table.get_neighbors()
        for dst_address in dest_mac_list:
            ARQ_HANDLER_LOG.debug("ARQ_SEND for %s", dst_address)
            # Add an entry to msg_thread_map and create a ArqRoutine thread
            hash_str = hashlib.md5(str(message.id) + dst_address).hexdigest()
            # Convert hash_str from hex to 32-bit integer
            hash_int = int(hash_str, 16) & max_int32

            lock.acquire()
            self.msg_thread_map[hash_int] = ArqRoutine(hash_int, self.msg_thread_map, self.raw_transport,
                                                       message, payload, dst_address)
            lock.release()
            self.msg_thread_map[hash_int].start()

    ## Process the ACK message, received from the transport or some another receiving thread.
    # @param self The object pointer.
    # @param ack_message Messages.AckMessage object received from the network.
    # @return None
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

    ## Generate and send the ACK back on the given message to the dst_mac.
    # @param self The object pointer.
    # @param message Message object from Messages module.
    # @param dst_mac Destination MAC address to send the ACK message to.
    # @return None
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


## A routine ARQ thread class which is responsible for sending the given message/data periodically in a timeout
# interval, until the corresponding ARQ has been received.
class ArqRoutine(threading.Thread):
    ## Constructor.
    # @param self The object pointer.
    # @param hash_int 32-bit hash value of message ID and destination IP pair.
    # @param msg_thread_map Reference to ArqHandler.ArqHandler.msg_thread_map dictionary.
    # @param raw_transport Reference to Transport.RawTransport object.
    # @param message Message from Messages module to send.
    # @param payload Payload string to the message.
    # @param dst_address Destination MAC address string.
    # @return None
    def __init__(self, hash_int, msg_thread_map, raw_transport, message, payload, dst_address):
        super(ArqRoutine, self).__init__()
        ## @var running
        # Thread running state bool() flag.
        self.running = False
        ## @var hash_int
        # 32-bit hash value of message ID and destination IP pair.
        self.hash_int = hash_int
        ## @var msg_thread_map
        # Reference to ArqHandler.ArqHandler.msg_thread_map dictionary.
        self.msg_thread_map = msg_thread_map
        ## @var raw_transport
        # Reference to Transport.RawTransport object.
        self.raw_transport = raw_transport
        ## @var dsr_message
        # Message from Messages module to send.
        self.dsr_message = message
        ## @var payload
        # Payload string to the message.
        self.payload = payload
        ## @var dst_address
        # Destination MAC address string.
        self.dst_address = dst_address
        # Maximum number of retransmissions before dropping and failing the reliable transmission
        ## @var max_retries
        # A number of maximum possible send retires if the ACK hasn't been received. int().
        self.max_retries = 5
        ## @var timeout_interval
        # Timeout interval after which the ACK message is considered to be lost, and, therefore, a message
        # retransmission attempt should be performed. float().
        self.timeout_interval = 0.5

    ## Main thread routine.
    # @param self The object pointer.
    # @return None
    def run(self):
        self.running = True
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

    ## Send message with the dsr header to the dst_address.
    # @param self The object pointer.
    # @return None
    def send_msg(self):
        self.raw_transport.send_raw_frame(self.dst_address, self.dsr_message, self.payload)
        ARQ_HANDLER_LOG.debug("Sent raw frame on: %s", self.dst_address)

    ## Stop and quit the thread operation.
    # @param self The object pointer.
    # @return None
    def quit(self):
        self.running = False
