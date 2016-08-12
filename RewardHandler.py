#!/usr/bin/python
"""
Created on Aug 6, 2016

@author: Dmitrii Dugaev
"""

import threading
import hashlib
import Queue
import time

import Messages

lock = threading.Lock()

max_int32 = 0xFFFFFFFF

"""
This module is responsible for a reward distribution between the nodes. It means both reception and transmission of
the generated reward values, depending on current state of RouteTable entries towards a given destination L3 address.
There are two main behaviors here.

The first is RewardWaitHandler - which is waiting for the reward from the neighbor where the packet had been
sent to earlier. If the reward wasn't received within a defined timeout interval - the handler assumes that
the packet has been lost, therefore, it triggers a negative reward value for the corresponding RouteTable entry.

The second is RewardSendHandler - it generates and sends back the reward to a source node after waiting for some
"hold on" time interval, which is needed to control a number of generated reward messages for some number of
the received packets with the same dst_ip address.
"""


# A class which handles a reward reception for each sent packet.
class RewardWaitHandler:
    def __init__(self, table):
        self.table = table
        # Define a structure for handling reward wait threads for given dst_ips.
        # Format: {hash(dst_ip + next_hop_mac): thread_object}. Hash is 32-bit integer, generated from md5 hash.
        # A reward value is being forwarded to the thread via a queue_object.
        self.reward_wait_list = dict()

    # Check if the waiting process for such dst_ip and next_hop_mac has already been initiated or not.
    # If yes - do nothing. Else - start the reward waiting thread.
    def wait_for_reward(self, dst_ip, mac):
        hash_str = hashlib.md5(dst_ip + mac).hexdigest()
        # Convert hash_str from hex to 32-bit integer
        hash_value = int(hash_str, 16) & max_int32

        if hash_value not in self.reward_wait_list:
            reward_wait_thread = RewardWaitThread(dst_ip, mac, self.table, self.reward_wait_list)
            # lock.acquire()
            self.reward_wait_list.update({hash_value: reward_wait_thread})
            # lock.release()
            # Start the thread
            reward_wait_thread.start()

    # Set a reward value to a specified entry, based on msg_hash
    def set_reward(self, reward_message):
        if reward_message.msg_hash in self.reward_wait_list:
            self.reward_wait_list[reward_message.msg_hash].process_reward(reward_message.reward_value)


# Thread for waiting for an incoming reward messages on the given dst_ip.
# It receives a reward value via the queue, and updates the RouteTable.
class RewardWaitThread(threading.Thread):
    def __init__(self, dst_ip, mac, table, reward_wait_list):
        super(RewardWaitThread, self).__init__()
        self.dst_ip = dst_ip
        self.mac = mac
        self.table = table
        self.reward_wait_list = reward_wait_list
        self.reward_wait_queue = Queue.Queue()
        # Define flag whether the reward has been received or not
        self.reward_is_received = False

        # Wait timeout after which initiate negative reward on the dst_ip
        self.wait_timeout = 3

    def run(self):

        time.sleep(self.wait_timeout)

        # If the reward has been received while sleeping, just do nothing
        if self.reward_is_received:
            pass
        # Else, if the reward hasn't been received, update the table with "bad" reward
        else:
            self.table.update_entry(self.dst_ip, self.mac, 0)

        # Finally, finish and delete the thread
        hash_str = hashlib.md5(self.dst_ip + self.mac).hexdigest()
        # Convert hash_str from hex to 32-bit integer
        hash_value = int(hash_str, 16) & max_int32

        del self.reward_wait_list[hash_value]

    def process_reward(self, reward_value):
        self.reward_is_received = True
        self.table.update_entry(self.dst_ip, self.mac, reward_value)


# A class which handles a reward generation and sending back to the sender node.
class RewardSendHandler:
    def __init__(self, table, raw_transport):
        self.table = table
        self.raw_transport = raw_transport
        self.node_mac = raw_transport.node_mac
        # Define a structure for handling reward sends for given dst_ips.
        # Format: {hash(dst_ip + mac): last_sent_ts}. Hash is 32-bit integer, generated from md5 hash.
        self.reward_send_list = dict()

        self.hold_on_timeout = 2

    # Send the reward back to the sender node after some "hold on" time interval.
    # This timeout is needed to control a number of generated reward messages for some number of
    # the received packets with the same dst_ip.
    def send_reward(self, dst_ip, mac):

        hash_str = hashlib.md5(dst_ip + mac).hexdigest()
        # Convert hash_str from hex to 32-bit integer
        hash_value = int(hash_str, 16) & max_int32

        if hash_value not in self.reward_send_list:
            # Create a new entry with current timestamp
            self.reward_send_list.update({hash_value: time.time()})
            self.send_back(dst_ip, mac)

        # If a timestamp of the given hash_value already exists, check if the timestamp is too old, according to the
        # hold on timeout. If too old - refresh the timestamp and send the reward again.
        # If no, just do nothing.
        else:
            if (time.time() - self.reward_send_list[hash_value]) > self.hold_on_timeout:
                # Create a new entry with current timestamp
                self.reward_send_list.update({hash_value: time.time()})
                self.send_back(dst_ip, mac)

    # Generate and send the reward message back to the originating node
    def send_back(self, dst_ip, mac):
        # Calculate its own average value of the estimated reward towards the given dst_ip
        avg_value = self.table.get_avg_value(dst_ip)
        hash_str = hashlib.md5(dst_ip + self.node_mac).hexdigest()
        hash_value = int(hash_str, 16) & max_int32
        # Generate and send the reward back
        dsr_reward_message = Messages.RewardMessage(avg_value, hash_value)

        # Send it back to the node which has sent the packet
        self.raw_transport.send_raw_frame(mac, dsr_reward_message, "")
