#!/usr/bin/python
"""
@package RouteTable
Created on Aug 1, 2016

@author: Dmitrii Dugaev


This module presents a routing table implementation of the protocol, with formats for routing entries, and with the
corresponding processing methods.
"""

# Import necessary python modules from the standard library
import copy

# Import the necessary modules of the program
import rl_logic
import routing_logging

## @var ABSOLUTE_PATH
# This constant stores a string with an absolute path to the program's main directory.
ABSOLUTE_PATH = routing_logging.ABSOLUTE_PATH

## @var TABLE_LOG
# Global routing_logging.LogWrapper object for logging RouteTable activity.
TABLE_LOG = routing_logging.create_routing_log("routing.route_table.log", "route_table")


## Class Entry represents a dictionary containing current estimated values for forwarding a packet to the given mac.
class Entry(dict):
    ## Constructor.
    # @param self The object pointer.
    # @param dst_ip Destination IP address of the route.
    # @param neighbors_list List of MAC addresses of currently accessible direct neighbors.
    # @return None
    def __init__(self, dst_ip, neighbors_list):
        super(Entry, self).__init__()
        ## @var dst_ip
        # Destination IP address of the route.
        self.dst_ip = dst_ip
        ## @var local_neighbor_list
        # Store a copy of the initial list of direct neighbors.
        self.local_neighbor_list = copy.deepcopy(neighbors_list)
        # Initialize the first estimation values for the freshly added actions/neighbors.
        self.init_values()
        ## @var value_estimator
        # Create rl_logic.ValueEstimator object for keeping the updates for incoming rewards.
        self.value_estimator = rl_logic.ValueEstimator()

    ## Initialize the first estimation values for the freshly added actions/neighbors.
    # @param self The object pointer.
    # @return None
    def init_values(self):
        for mac in self.local_neighbor_list:
            if mac not in self:
                # Assign initial estimated values
                self.update({mac: 0.0})

    ## Update the list of neighbors, according to a given neighbors list.
    # @param self The object pointer.
    # @param neighbors_list List of MAC addresses of currently accessible direct neighbors.
    # @return None
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

    ## Update estimation value on the action (mac) by the given reward.
    # @param self The object pointer.
    # @param mac MAC address of the neighbor (action ID).
    # @param reward Reward value to be assigned.
    # @return None
    def update_value(self, mac, reward):
        # Estimate the value and update the entry itself
        self[mac] = self.value_estimator.estimate_value(mac, reward)

    ## Calculate and output the average of estimation values of this entry itself.
    ## Initialize the first estimation values for the freshly added actions/neighbors.
    # @param self The object pointer.
    # @return Average estimation value: sum(self.values()) / len(self).
    def calc_avg_value(self):
        return sum(self.values()) / len(self)


## Route table class.
# Contains a list and methods for manipulating the entries and its values, which correspond to different src-dst
# pairs (routes).
class Table:
    ## Constructor.
    # @param self The object pointer.
    # @param node_mac MAC address of the node's network interface.
    # @return None
    def __init__(self, node_mac):
        ## @var table_filename
        # Define a filename to write the table entries to. Default filename is "table.txt".
        self.table_filename = "/table.txt"
        ## @var node_mac
        # MAC address of the node's network interface.
        self.node_mac = node_mac
        ## @var neighbors_list
        # Define a shared dictionary of current active neighbors. This dictionary is also used by the
        # ListenNeighbors class from the NeighborDiscovery module. Format: {mac: NeighborDiscovery.Neighbor object}.
        self.neighbors_list = dict()
        ## @var entries_list
        # Define list of current route entries. Format: {dst_ip: Entry}.
        self.entries_list = dict()
        ## @var current_node_ips
        # Store current ip addresses assigned to this node. list().
        self.current_node_ips = list()
        ## @var action_selector
        # Create RL-helper rl_logic.ActionSelector object, to handle the process of action selection.
        self.action_selector = rl_logic.ActionSelector("soft-max")
        TABLE_LOG.info("Chosen selection method: %s", self.action_selector.selection_method_id)

    ## This method selects a next hop for the packet with the given dst_ip.
    # The selection is being made from the current estimated values of the neighbors mac addresses,
    # using some of the available action selection algorithms - such as greedy, e-greedy, soft-max and so on.
    # @param self The object pointer.
    # @param dst_ip Destination IP address of the route.
    # @return (MAC address of the next hop) or None.
    def get_next_hop_mac(self, dst_ip):
        if dst_ip in self.entries_list:
            # Update the neighbors and corresponding action values
            self.entries_list[dst_ip].update_neighbors(self.neighbors_list)
            # Select a next hop mac
            next_hop_mac = self.action_selector.select_action(self.entries_list[dst_ip])
            TABLE_LOG.debug("Selected next_hop: %s, from available entries: %s",
                            next_hop_mac, self.entries_list[dst_ip])
            return next_hop_mac
        # If no such entry, return None
        else:
            return None

    ## Update the estimation value of the given action_id (mac) by the given reward.
    # @param self The object pointer.
    # @param dst_ip Destination IP address of the route.
    # @param mac MAC address of the neighbor (action ID).
    # @param reward Reward value to be assigned.
    # @return None
    def update_entry(self, dst_ip, mac, reward):
        if dst_ip in self.entries_list:
            self.entries_list[dst_ip].update_value(mac, reward)
        else:
            TABLE_LOG.info("No such Entry to update. Creating and updating a new entry for dst_ip and mac: %s - %s",
                           dst_ip, mac)

            self.entries_list.update({dst_ip: Entry(dst_ip, self.neighbors_list)})
            self.entries_list[dst_ip].update_value(mac, reward)

    ## Calculate and return the average estimation value of the given entry.
    # @param self The object pointer.
    # @param dst_ip Destination IP address of the route.
    # @return Average estimation value. float().
    def get_avg_value(self, dst_ip):
        if dst_ip in self.entries_list:
            avg_value = self.entries_list[dst_ip].calc_avg_value()
            TABLE_LOG.debug("Calculated average value towards dst_ip %s : %s", dst_ip, avg_value)
            return avg_value
        # Else, return 0 value with the warning
        else:
            TABLE_LOG.warning("CANNOT GET AVERAGE VALUE! NO SUCH ENTRY!!! Returning 0")
            return 0.0

    ## Return the current list of neighbors.
    # @param self The object pointer.
    # @return List of current neighbors. list().
    def get_neighbors(self):
        neighbors_list = list(set(self.neighbors_list))
        TABLE_LOG.debug("Current list of neighbors: %s", neighbors_list)
        return neighbors_list

    ## Return current entry assigned for given destination IP.
    # @param self The object pointer.
    # @param dst_ip Destination IP address of the route.
    # @return (Entry object) or None.
    def get_entry(self, dst_ip):
        if dst_ip in self.entries_list:
            return self.entries_list[dst_ip]
        else:
            return None

    ## Safe-copy and return a current list of entries.
    # @param self The object pointer.
    # @param return list() of entries.
    def get_list_of_entries(self):
        current_keys = self.entries_list.keys()
        current_values = self.entries_list.values()

        while len(current_keys) != len(current_values):
            current_keys = self.entries_list.keys()
            current_values = self.entries_list.values()

        map(dict, current_values)

        return dict(zip(current_keys, current_values))

    ## Safe-copy and return a list with L3 addresses of current neighbors.
    # @param self The object pointer.
    # @param return list() of L3 addresses.
    def get_neighbors_l3_addresses(self):
        # Make a safe-copy of the current list of neighbors
        keys = self.neighbors_list.keys()
        values = self.neighbors_list.values()

        while len(keys) != len(values):
            keys = self.neighbors_list.keys()
            values = self.neighbors_list.values()

        neighbors_list = dict(zip(keys, values))

        # Create a list with L3 addresses of each neighbor in a format: [[addr1, ... addrN], ... [addr1, ... addrN]]
        addresses_list = []
        for mac in neighbors_list:
            addresses_list.append([])
            for addr in neighbors_list[mac].l3_addresses:
                if addr:
                    addresses_list[-1].append(addr)

        return addresses_list

    ## Print out the contents of the route table to a specified file.
    # @param self The object pointer.
    # @return None
    def print_table(self):
        current_entries_list = self.get_list_of_entries()

        f = open(ABSOLUTE_PATH + self.table_filename, "w")
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
