#!/usr/bin/python
"""
@package RewardHandler
Created on Aug 6, 2016

@author: Dmitrii Dugaev


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

# Import necessary python modules from the standard library
import threading
import hashlib
import time

# Import the necessary modules of the program
import Messages

## @var lock
# Store the global threading.Lock object.
lock = threading.Lock()

## @var max_int32
# 32-bit mask constant.
max_int32 = 0xFFFFFFFF


## A class which handles a reward reception for each sent packet.
class RewardWaitHandler:
    ## Constructor.
    # @param self The object pointer.
    # @param table Reference to RouteTable.Table object.
    # @return None
    def __init__(self, table):
        ## @var table
        # Reference to RouteTable.Table object.
        self.table = table
        ## @var reward_wait_list
        # Define a structure for handling reward wait threads for given dst_ips.
        # Format: {hash(dst_ip + next_hop_mac): thread_object}. Hash is 32-bit integer, generated from md5 hash.
        # A reward value is being forwarded to the thread via a queue_object.
        self.reward_wait_list = dict()

    ## Start a waiting thread until the Reward message is received.
    # Check if the waiting process for such dst_ip and next_hop_mac has already been initiated or not.
    # If yes - do nothing. Else - start the reward waiting thread.
    # @param self The object pointer.
    # @param dst_ip Destination IP of the route for this packet.
    # @param mac MAC address of the node where the packet had been sent for getting the reward.
    # @return None
    def wait_for_reward(self, dst_ip, mac):
        hash_str = hashlib.md5(dst_ip + mac).hexdigest()
        # Convert hash_str from hex to 32-bit integer
        hash_value = int(hash_str, 16) & max_int32

        if hash_value not in self.reward_wait_list:
            reward_wait_thread = RewardWaitThread(dst_ip, mac, self.table, self.reward_wait_list)
            self.reward_wait_list.update({hash_value: reward_wait_thread})
            # Start the thread
            reward_wait_thread.start()

    ## Set a reward value to a specified entry, based on the received object of Messages.RewardMessage.msg_hash.
    # @param self The object pointer.
    # @param reward_message Messages.RewardMessage object.
    # @return None
    def set_reward(self, reward_message):
        lock.acquire()
        try:
            self.reward_wait_list[reward_message.msg_hash].process_reward(reward_message.reward_value)

        # If the key is not present, then pass
        except KeyError:
            pass

        finally:
            lock.release()


## Thread for waiting for an incoming reward messages on the given dst_ip.
class RewardWaitThread(threading.Thread):
    ## Constructor.
    # @param self The object pointer.
    # @param dst_ip Destination IP of the route for this packet.
    # @param mac MAC address of the node where the packet had been sent for getting the reward.
    # @param table Reference to RouteTable.Table object.
    # @param reward_wait_list Reference to the shared RewardWaitHandler.reward_wait_list dictionary.
    # @return None
    def __init__(self, dst_ip, mac, table, reward_wait_list):
        super(RewardWaitThread, self).__init__()
        ## @var dst_ip
        # Destination IP of the route for this packet. Represented in a string format.
        self.dst_ip = dst_ip
        ## @var mac
        # MAC address of the node where the packet had been sent for getting the reward.
        # Represented in "xx:xx:xx:xx:xx:xx" string format.
        self.mac = mac
        ## @var table
        # Reference to RouteTable.Table object.
        self.table = table
        ## @var reward_wait_list
        # Reference to the shared RewardWaitHandler.reward_wait_list dictionary.
        self.reward_wait_list = reward_wait_list
        ## @var reward_is_received
        # Define flag whether the reward has been received or not. bool().
        self.reward_is_received = False
        ## @var wait_timeout
        # Wait timeout value after which a negative reward is initiated towards the dst_ip.
        self.wait_timeout = 3

    ## Main thread routine.
    # @param self The object pointer.
    # @return None
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

        lock.acquire()
        try:
            del self.reward_wait_list[hash_value]

        # If key is not present, then pass
        except KeyError:
            pass

        finally:
            lock.release()

    ## Process an incoming reward value.
    # @param self The object pointer.
    # @param reward_value Reward value.
    # @return None
    def process_reward(self, reward_value):
        self.reward_is_received = True
        self.table.update_entry(self.dst_ip, self.mac, reward_value)


## A class which handles a reward generation and sending back to the sender node.
class RewardSendHandler:
    ## Constructor.
    # @param self The object pointer.
    # @param table Reference to RouteTable.Table object.
    # @param raw_transport Reference to Transport.RawTransport object.
    # @return None
    def __init__(self, table, raw_transport):
        ## @var table
        # Reference to RouteTable.Table object.
        self.table = table
        ## @var raw_transport
        # Reference to Transport.RawTransport object.
        self.raw_transport = raw_transport
        ## @var node_mac
        # Reference to the node's own MAC address, stored in Transport.RawTransport.node_mac.
        self.node_mac = raw_transport.node_mac
        ## @var reward_send_list
        # Define a structure for handling reward sends for given dst_ips.
        # Format: {hash(dst_ip + mac): last_sent_ts}. Hash is 32-bit integer, generated from md5 hash.
        self.reward_send_list = dict()
        ## @var hold_on_timeout
        # A timeout after which the reward value is sent back to the sender. This is done in order to decrease a number
        # of reward messages being sent back in a case when the incoming packet stream is too intensive.
        self.hold_on_timeout = 2

    ## Send the reward back to the sender node after some "hold on" time interval.
    # This timeout is needed to control a number of generated reward messages for some number of
    # the received packets with the same dst_ip.
    # @param self The object pointer.
    # @param dst_ip Destination IP of the route for this packet.
    # @param mac MAC address of the node where the packet had been sent for getting the reward.
    # @return None
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

    ## Generate and send the reward message back to the originating node.
    # @param self The object pointer.
    # @param dst_ip Destination IP of the route for this packet.
    # @param mac MAC address of the node where the packet had been sent for getting the reward.
    # @return None
    def send_back(self, dst_ip, mac):
        # Calculate its own average value of the estimated reward towards the given dst_ip
        avg_value = self.table.get_avg_value(dst_ip)
        hash_str = hashlib.md5(dst_ip + self.node_mac).hexdigest()
        hash_value = int(hash_str, 16) & max_int32
        # Generate and send the reward back
        dsr_reward_message = Messages.RewardMessage(avg_value, hash_value)
        # Send it back to the node which has sent the packet
        self.raw_transport.send_raw_frame(mac, dsr_reward_message, "")
