#!/usr/bin/python
"""
Created on Aug 1, 2016

@author: Dmitrii Dugaev
"""

import threading
import random
import copy
import time

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
        # Round it up
        estimated_value = round(estimated_value, 2)
        # Update the value
        self.actions[action_id][0] = estimated_value
        # Increment the counter
        self.actions[action_id][1] += 1
        # Return the value
        return estimated_value

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
    def __init__(self, dst_ip, neighbors_list):
        super(Entry, self).__init__()
        self.dst_ip = dst_ip
        # Store a copy of the initial neighbors_list
        self.local_neighbor_list = copy.deepcopy(neighbors_list)
        # Initialize the first values for the freshly added actions
        self.init_values()
        # Create an ValueEstimator object for keeping the updates for incoming rewards
        self.value_estimator = ValueEstimator()

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

    # Update estimated value on the action (mac) by the given reward
    def update_value(self, mac, reward):
        # Estimate the value and update the entry itself
        self[mac] = self.value_estimator.estimate_value(mac, reward)

    # Calculate and output the average of estimation values of itself
    def calc_avg_value(self):
        return sum(self.values()) / len(self)

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
    def __init__(self, node_mac):

        self.node_mac = node_mac

        # Define a shared dictionary of current active neighbors. This dictionary is also used by the
        # ListenNeighbors class from the NeighborDiscovery module. Format: {mac: neighbor_object}
        self.neighbors_list = dict()

        # Define list of current route entries. Format: {dst_ip: Entry}
        self.entries_list = dict()

        # Store current ip addresses assigned to this node
        self.current_node_ips = list()

        # Create RL helper object, to handle the selection of the actions
        self.action_selector = ActionSelector()

        # Create and start a thread for periodically printing out the route table contents
        self.print_table_thread = PrintTableThread(self.entries_list)
        self.print_table_thread.start()

    # This method selects a next hop for the packet with the given dst_ip.
    # The selection is being made from the current estimated values of the neighbors mac addresses,
    # using some of the available action selection algorithms - such as greedy, e-greedy, soft-max and so on.
    def get_next_hop_mac(self, dst_ip):
        if dst_ip in self.entries_list:
            # Update the neighbors and corresponding action values
            self.entries_list[dst_ip].update_neighbors(self.neighbors_list)
            # Select a next hop mac
            next_hop_mac = self.action_selector.select_action(self.entries_list[dst_ip])
            return next_hop_mac
        # If no such entry, return None
        else:
            return None

    # Update the estimation value of the given action_id (mac) by the given reward
    def update_entry(self, dst_ip, mac, reward):
        if dst_ip in self.entries_list:
            self.entries_list[dst_ip].update_value(mac, reward)
        else:
            TABLE_LOG.info("No such Entry to update. Creating and updating a new entry for dst_ip and mac: %s - %s",
                           dst_ip, mac)

            self.entries_list.update({dst_ip: Entry(dst_ip, self.neighbors_list)})
            self.entries_list[dst_ip].update_value(mac, reward)

    # Calculate and return the average estimated value of the given entry
    def get_avg_value(self, dst_ip):
        if dst_ip in self.entries_list:
            return self.entries_list[dst_ip].calc_avg_value()
        # Else, return 0 value with the warning
        else:
            TABLE_LOG.warning("CANNOT GET AVERAGE VALUE! NO SUCH ENTRY!!! Returning 0")
            return 0.0

    # Return the current list of neighbors
    def get_neighbors(self):
        neighbors_list = list(set(self.neighbors_list))

        TABLE_LOG.debug("Got list of neighbors: %s", neighbors_list)

        return neighbors_list

    # Return current entry assigned for given dst_ip
    def get_entry(self, dst_ip):
        if dst_ip in self.entries_list:
            return self.entries_list[dst_ip]
        else:
            return None


# A thread which periodically prints out or writes the content of route entries list to a specified file.
class PrintTableThread(threading.Thread):
    def __init__(self, entries_list):
        super(PrintTableThread, self).__init__()
        self.running = True
        self.entries_list = entries_list
        # Update interval, in seconds
        self.update_interval = 5
        # Define a filename to write the table to
        self.table_filename = "table.txt"

    def run(self):
        while self.running:
            current_entries_list = copy.deepcopy(self.entries_list)
            f = open(self.table_filename, "w")
            f.write("-" * 90 + "\n")

            for dst_ip in current_entries_list:
                f.write("Towards destination IP: %s \n" % dst_ip)
                f.write("<Next_hop_MAC> \t\t <Value>\n")
                for mac in current_entries_list[dst_ip]:
                    string = "%s \t %s \n"
                    values = (mac, current_entries_list[dst_ip][mac])
                    f.write(string % values)
                f.write("\n")
            f.write("-" * 90 + "\n")
            f.close()

            time.sleep(self.update_interval)
