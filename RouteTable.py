#!/usr/bin/python
"""
Created on Aug 1, 2016

@author: Dmitrii Dugaev
"""

import copy

import rl_logic
import routing_logging

TABLE_LOG = routing_logging.create_routing_log("routing.route_table.log", "route_table")


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
        self.value_estimator = rl_logic.ValueEstimator()

    # Initialize the first values for the freshly added actions
    def init_values(self):
        for mac in self.local_neighbor_list:
            if mac not in self:
                # Assign initial estimated values
                self.update({mac: 0.0})

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


# A class of route table. Contains a list and methods for manipulating the entries and its values, which correspond to
# different src-dst pairs (routes).
class Table:
    def __init__(self, node_mac):
        # Define a filename to write the table to
        self.table_filename = "table.txt"

        self.node_mac = node_mac

        # Define a shared dictionary of current active neighbors. This dictionary is also used by the
        # ListenNeighbors class from the NeighborDiscovery module. Format: {mac: neighbor_object}
        self.neighbors_list = dict()

        # Define list of current route entries. Format: {dst_ip: Entry}
        self.entries_list = dict()

        # Store current ip addresses assigned to this node
        self.current_node_ips = list()

        # Create RL helper object, to handle the selection of the actions
        self.action_selector = rl_logic.ActionSelector()

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

    # Print out the contents of the route table to a specified file
    def print_table(self):
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
