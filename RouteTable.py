#!/usr/bin/python
"""
Created on Aug 1, 2016

@author: Dmitrii Dugaev
"""

from time import time
import threading
import random
import copy
import numpy as np

import routing_logging

TABLE_LOG = routing_logging.create_routing_log("routing.route_table.log", "route_table")

lock = threading.Lock()


# Class for assigning current estimated value for a given action.
# Provides method for returning this value.
class ValueEstimator:
    def __init__(self, est_method_id="sample_average"):
        # Store current action ids and their current estimated value and step: {action_id: [est_value, step_count]}
        self.actions = dict()
        # Override the default method
        if est_method_id == "sample_average":
            self.estimate_value = self.estimate_value_by_sample_average
            TABLE_LOG.info("An estimation method has been assigned: %s", est_method_id)
        else:
            TABLE_LOG.error("INVALID ESTIMATION METHOD IS SPECIFIED!!!")
            TABLE_LOG.info("Assigning the default estimation method...")
            self.estimate_value = self.estimate_value_by_sample_average

    def estimate_value(self):
        """
        Main method which returns current estimated value. It is overridden in the init().
        Input: action_id - some action identifier; reward - value of the assigned reward.
        Output: current estimated value.
        """
        pass

    # Estimate value by using a simple "sample average" method.
    # Reference to the method can be found in R.Sutton's book: Reinforcement Learning: An Introduction
    def estimate_value_by_sample_average(self, action_id, reward):
        if action_id not in self.actions:
            # Assign initial values
            self.actions.update({action_id: [0.0, 0]})

        # Calculate the estimated value
        estimated_value = (self.actions[action_id][0] * self.actions[action_id][1] + reward) \
                          / (self.actions[action_id][1] + 1)
        # Update the value
        self.actions[action_id][0] = estimated_value
        # Increment the counter
        self.actions[action_id][1] += 1

    # Delete an action_id from the current actions list
    def delete_action_id(self, action_id):
        if action_id in self.actions:
            del self.actions[action_id]


# Class for selecting the action from the list of actions and their corresponding values.
# The interface is provided via select_action() method.
class ActionSelector:
    def __init__(self, selection_method_id="greedy"):
        # Override the default method
        if selection_method_id == "greedy":
            self.select_action = self.select_action_greedy
            TABLE_LOG.info("A selection method has been assigned: %s", selection_method_id)

        elif selection_method_id == "e-greedy":
            # Set some parameters of e-greedy method
            self.eps = 0.1
            self.select_action = self.select_action_e_greedy
            TABLE_LOG.info("A selection method has been assigned: %s", selection_method_id)

        elif selection_method_id == "soft-max":
            self.select_action = self.select_action_softmax
            TABLE_LOG.info("A selection method has been assigned: %s", selection_method_id)

        else:
            TABLE_LOG.error("INVALID SELECTION METHOD IS SPECIFIED!!!")
            TABLE_LOG.info("Assigning the default selection method...")
            self.select_action = self.select_action_greedy

    def select_action(self):
        """
        Default method for selecting the action. It is overridden in init().
        Input: {action_id: value}
        Output: action_id
        """
        pass

    # Select an action using "greedy" algorithm
    def select_action_greedy(self, action_values):
        if len(action_values) == 0:
            return None
        # Simply return the action_id with the maximum value
        return max(action_values, key=action_values.get)

    # Select an action using "e-greedy" algorithm
    def select_action_e_greedy(self, action_values):
        if len(action_values) == 0:
            return None
        # In (eps * 100) percent of cases, select an action with maximum value (use greedy method)
        # Otherwise, choose some other random action.
        greedy_action_id = self.select_action_greedy(action_values)
        if random.random() > self.eps:
            return greedy_action_id
        else:
            # Randomly choose some other action
            chosen_action_id = random.choice(action_values.keys())
            # Check the the selected action is not the "greedy" choice
            while action_values[chosen_action_id] == greedy_action_id and len(action_values) != 1:
                chosen_action_id = random.choice(action_values.keys())
            return chosen_action_id

    # Select an action using "soft-max" algorithm. It is based on Gibbs (Boltzmann) distribution.
    # See the reference in R.Sutton's book: Reinforcement Learning: An Introduction.
    def select_action_softmax(self, action_values):
        if len(action_values) == 0:
            return None
        # TODO: implement soft-max selection here.
        pass


# Class Entry represents a dictionary containing current estimated values for forwarding a packet to the given mac.
class Entry(dict):
    def __init__(self, src_ip, dst_ip, neighbors_list):
        super(Entry, self).__init__()
        self.src_ip = src_ip
        self.dst_ip = dst_ip
        # Store a copy of the initial neighbors_list
        self.local_neighbor_list = copy.deepcopy(neighbors_list)
        # # Create initial estimated values for current list of neighbors macs
        # self.est_values = dict()
        # Initialize the first values for the freshly added actions
        self.init_values()
        # # Initialize the main dictionary
        # self.update(self.est_values)

        # Create an ValueEstimator object for keeping the updates for incoming rewards
        self.value_estimator = ValueEstimator()

        # self.dst_mac = dst_mac                                  # MAC address of destination node
        # self.next_hop_mac = next_hop_mac                        # Next hop mac address
        # self.n_hops = n_hops                                    # Number of hops to destination
        # self.last_activity = time()                             # Timestamp of the last activity
        # self.timeout = 10                                       # Timeout in seconds upon deleting an entry

    # Initialize the first values for the freshly added actions
    def init_values(self):
        # lock.acquire()
        for mac in self.local_neighbor_list:
            if mac not in self:
                # Assign initial estimated values
                self.update({mac: 0.0})
        # lock.release()

    # Update the list of neighbors, according to a given neighbors list
    def update_neighbors(self, neighbors_list):
        if self.local_neighbor_list == neighbors_list:
            pass
        else:
            # Merge the old list with the given one
            self.local_neighbor_list.update(neighbors_list)
            # Delete the old keys
            keys_to_delete = set(self.local_neighbor_list) - set(neighbors_list)
            for key in keys_to_delete:
                # Delete a key
                del self.local_neighbor_list[key]
                # Delete a corresponding estimated value from the ValueEstimator object
                self.value_estimator.delete_action_id(key)

            # Initialize the est_values for new macs
            self.init_values()
            # # Update the entry itself
            # self.update(self.est_values)

    # Update estimated value on the action (mac) by the given reward
    def update_value(self, mac, reward):
        self.value_estimator.estimate_value(mac, reward)

    # Calculate and output the average of estimation values of itself
    def calc_avg_value(self):
        return np.array(self.values()).mean()

    # def __eq__(self, other):
    #     return (self.dst_mac == other.dst_mac and
    #             self.next_hop_mac == other.next_hop_mac and self.n_hops == other.n_hops)

    # def __str__(self):
    #     out_tuple = (str(self.dst_mac), str(self.next_hop_mac),
    #                  str(self.n_hops), str(round((time() - self.last_activity), 2)))
    #     out_string = "DST_MAC: %s, NEXT_HOP_MAC: %s, N_HOPS: %s, IDLE_TIME: %s" % out_tuple
    #
    #     return out_string


# A class of route table. Contains a list and methods for manipulating the entries and its values, which correspond to
# different src-dst pairs (routes).
class Table:
    def __init__(self):
        # Define a shared dictionary of current active neighbors. This dictionary is also used by the
        # ListenNeighbors class from the NeighborDiscovery module. Format: {mac: neighbor_object}
        self.neighbors_list = dict()

        # Define list of current route entries. Format: {hash(src_ip + dst_ip): Entry}
        self.entries_list = dict()

        # Create RL helper object, to handle the calculation of values and select the actions
        self.value_estimator = ValueEstimator()
        self.action_selector = ActionSelector()

        # self.node_mac = node_mac
        # self.entries = {}             # List of entries
        # self.arp_table = {}           # A dictionary which maps current IP addresses with the devices' MAC addresses

    # This method selects a next hop for the packet with the given src_ip - dst_ip pair.
    # The selection is being made from the current estimated values of the neighbors mac addresses,
    # using some of the available action selection algorithms - such as greedy, e-greedy, soft-max and so on.
    def get_next_hop_mac(self, src_ip, dst_ip):
        hash_key = hash(src_ip + dst_ip)
        if hash_key in self.entries_list:
            # Update the neighbors and corresponding action values
            self.entries_list[hash_key].update_neighbors(self.neighbors_list)
        # Add the entry if it is not already in the list
        else:
            self.entries_list.update({hash_key: Entry(src_ip, dst_ip, self.neighbors_list)})
        # Select a next hop mac
        next_hop_mac = self.action_selector.select_action(self.entries_list[hash_key])
        return next_hop_mac

    # Update the estimation value of the given action_id (mac) by the given reward
    def update_entry(self, src_ip, dst_ip, mac, reward):
        hash_key = hash(src_ip + dst_ip)
        if hash_key in self.entries_list:
            self.entries_list[hash_key].update_value(mac, reward)
        else:
            TABLE_LOG.error("NO SUCH SRC-DST PAIR TO UPDATE!!!")

    # Calculate and return the average estimated value of the given entry
    def get_avg_value(self, src_ip, dst_ip):
        hash_key = hash(src_ip + dst_ip)
        if hash_key in self.entries_list:
            return self.entries_list[hash_key].calc_avg_value()
        # Else, return 0 value with the warning
        else:
            TABLE_LOG.warning("CANNOT GET AVERAGE VALUE! NO SUCH ENTRY!!! Returning 0")
            return 0.0

    # # Add an entry to the route table and the arp_table
    # def add_entry(self, dst_mac, next_hop_mac, n_hops):
    #     # Create new route entry object
    #     entry = Entry(dst_mac, next_hop_mac, n_hops)
    #     if dst_mac in self.entries:
    #         # Check if the identical entry already exists in the table
    #         for ent in self.entries[dst_mac]:
    #             # If yes, just refresh its last_activity time and return it
    #             if ent == entry:
    #                 ent.last_activity = time()
    #                 return ent
    #
    #         self.entries[dst_mac].append(entry)
    #
    #     else:
    #         self.entries[dst_mac] = [entry]
    #
    #         TABLE_LOG.info("New entry has been added. Table updated.")
    #
    #         self.print_table()
    #
    #     return entry
    #
    # def update_arp_table(self, ip, mac):
    #
    #     self.arp_table.update({ip: mac})
    #
    # # Delete all entries where next_hop_mac matches the given mac
    # def del_entries(self, mac):
    #
    #     entries_to_delete = {}
    #     for dst_mac in self.entries:
    #         entries_to_delete.update({dst_mac: []})
    #
    #         for entry in self.entries[dst_mac]:
    #             if entry.next_hop_mac == mac:
    #                 entries_to_delete[dst_mac].append(entry)
    #
    #     # Deleting chosen entries from the list of entries with current dst_mac
    #     for dst_mac in entries_to_delete:
    #         for ent in entries_to_delete[dst_mac]:
    #             self.entries[dst_mac].remove(ent)
    #         # Check if that was the last existing entry. If yes -> delete the key from the dictionary
    #         if self.entries[dst_mac] == []:
    #             del self.entries[dst_mac]
    #
    #     TABLE_LOG.info("All entries with given next_hop_mac have been removed. Table updated.")
    #
    #     self.print_table()
    #
    # # Return the current list of neighbors
    # def get_neighbors(self):
    #     neighbors_list = []
    #     for dst_mac in self.entries:
    #         for entry in self.entries[dst_mac]:
    #             if entry.n_hops == 1:
    #                 neighbors_list.append(entry.next_hop_mac)
    #
    #     TABLE_LOG.info("Got list of neighbors: %s", neighbors_list)
    #
    #     return neighbors_list

    # Print all entries of the route table to a file
    def print_table(self):
        f = open("table.txt", "w")
        f.write("-" * 90 + "\n")

        # Store current entries list in local variable in order to avoid modification
        # from another threads
        current_entries = self.entries.copy()

        for dst_mac in current_entries:
            f.write("Towards destination MAC: %s \n" % dst_mac)
            f.write("<Dest_MAC> \t\t <Next_hop_MAC> \t\t <Hop_count> \t <IDLE Time>\n")
            for entry in current_entries[dst_mac]:
                string = "%s \t %s \t\t\t %s \t %s\n"
                values = (entry.dst_mac, entry.next_hop_mac, entry.n_hops,
                          str(round((time() - entry.last_activity), 2)))
                f.write(string % values)
            f.write("\n")

        f.write("-" * 90 + "\n")

    def print_entry(self, entry):
        TABLE_LOG.info("<Dest_MAC>: %s, <Next_hop_MAC>: %s, <Hop_count>: %s, <IDLE Time>: %s",
                       entry.dst_mac, entry.next_hop_mac, entry.n_hops, round((time() - entry.last_activity), 2))

    # # Returns an entry with a given dest_ip and ID
    # def get_entry_by_ID(self, dest_ip, ID):
    #     IDs = []
    #
    #     if dest_ip in self.entries:
    #         for d in self.entries[dest_ip]:
    #             IDs.append(d.id)
    #
    #     output_list = self.entries[dest_ip][IDs.index(ID)]
    #
    #     return output_list
    #
    # # Check the dst_ip in arp_table and in the route_table
    # def lookup_mac_address(self, dst_ip):
    #     # Check the arp table
    #     if dst_ip in self.arp_table:
    #         output = self.arp_table[dst_ip]
    #     else:
    #         output = None
    #
    #     return output
    #
    # def lookup_entry(self, dst_mac):
    #     if dst_mac == None:
    #         return None
    #
    #     if dst_mac in self.entries:
    #         # Checking the age of the route entry
    #         self.check_expiry(dst_mac)
    #         output = self.select_route(dst_mac)
    #     else:
    #         output = None
    #
    #     return output
    #
    # # Returns an entry with min amount of hops to the destination MAC address
    # def select_route(self, dst_mac):
    #     hop_counts = []
    #     if dst_mac in self.entries:
    #         for a in self.entries[dst_mac]:
    #             hop_counts.append(a.n_hops)
    #
    #         entry = self.entries[dst_mac][hop_counts.index(min(hop_counts))]
    #         entry.last_activity = time()
    #         return entry
    #     else:
    #         return None
    #
    # # Check the entry's last activity. If it exceeds the timeout, then delete it.
    # def check_expiry(self, dst_mac):
    #     entries_to_delete = []
    #     if dst_mac in self.entries:
    #         for ent in self.entries[dst_mac]:
    #             if ((time() - ent.last_activity) > ent.timeout) and ent.n_hops != 1:
    #                 entries_to_delete.append(ent)
    #         for ent in entries_to_delete:
    #             self.entries[dst_mac].remove(ent)
    #         # If the list becomes empty, then delete it
    #         if self.entries[dst_mac] == []:
    #             del self.entries[dst_mac]
    #
    #         self.print_table()
    #
    #     else:
    #         TABLE_LOG.warning("This should never happen: RouteTable.check_expiry(dst_mac)")
