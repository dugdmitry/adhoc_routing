#!/usr/bin/python
"""
Created on Aug 6, 2016

@author: Dmitrii Dugaev
"""

import threading
import Queue
import pickle
import time

import Messages

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
        # Wait timeout after which initiate negative reward on the dst_ip
        self.wait_timeout = 3

    def run(self):
        try:
            reward = self.reward_wait_queue.get(timeout=self.wait_timeout)
            # Update value by received reward
            self.table.update_entry(self.dst_ip, self.mac, reward)
        # Update with a "bad" reward, if the timeout has been reached
        except Queue.Empty:
            self.table.update_entry(self.dst_ip, self.mac, 0)
        # Finally, delete its own entry from the reward_wait_list
        finally:
            # lock.acquire()
            del self.reward_wait_list[hash(self.dst_ip + self.mac)]
            # lock.release()

    def set_reward(self, reward):
        self.reward_wait_queue.put(reward)


# Thread for generating and sending back a reward message upon receiving a packet with a corresponding dst_ip
# from the network interface.
class RewardSendThread(threading.Thread):
    def __init__(self, dst_ip, mac, table, raw_transport, reward_send_list):
        super(RewardSendThread, self).__init__()
        self.dst_ip = dst_ip
        self.mac = mac
        self.node_mac = raw_transport.node_mac
        self.table = table
        self.raw_transport = raw_transport
        self.reward_send_list = reward_send_list
        # Create a reward message object
        self.reward_message = Messages.RewardMessage()
        # Create a dsr_header object
        self.dsr_header = Messages.DsrHeader(6)         # Type 6 corresponds to Reward Message
        # A time interval the thread waits for, ere generating and sending back the RewardMessage.
        # This timeout is needed to control a number of generated reward messages for some number of
        # the received packets with the same dst_ip.
        self.hold_on_timeout = 2

    def run(self):
        # Sleep for the hold_on_timeout value
        time.sleep(self.hold_on_timeout)
        # Calculate its own average value of the estimated reward towards the given dst_ip
        avg_value = self.table.get_avg_value(self.dst_ip)
        # Assign a reward to the reward message
        self.reward_message.reward_value = avg_value
        self.reward_message.msg_hash = hash(self.dst_ip + self.node_mac)
        # Send it back to the node which has sent the packet
        self.raw_transport.send_raw_frame(self.mac, self.dsr_header, pickle.dumps(self.reward_message))
        # Delete its own entry from the reward_send_list
        # lock.acquire()
        del self.reward_send_list[hash(self.dst_ip + self.mac)]
        # lock.release()



