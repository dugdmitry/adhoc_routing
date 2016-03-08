#!/usr/bin/python
"""
Created on Sep 30, 2014

@author: Dmitrii Dugaev
"""

from time import time
import routing_logging


TABLE_LOG = routing_logging.create_routing_log("routing.route_table.log", "route_table")
# TABLE_LOG = routing_logging.create_routing_log("routing.route_table.log", "root.route_table", LOG_LEVEL)


# test
class Entry:
    def __init__(self, dst_mac, next_hop_mac, n_hops):
        self.dst_mac = dst_mac                                      # MAC address of destination node
        self.next_hop_mac = next_hop_mac                            # Next hop mac address
        self.n_hops = n_hops                                        # Number of hops to destination
        self.last_activity = time()                                 # Timestamp of the last activity
        self.timeout = 60                                          # Timeout in seconds upon deleting an entry
        
    def __eq__(self, other):
        return (self.dst_mac == other.dst_mac and
                self.next_hop_mac == other.next_hop_mac and self.n_hops == other.n_hops)

    def __str__(self):
        out_tuple = (str(self.dst_mac), str(self.next_hop_mac),
                     str(self.n_hops), str(round((time() - self.last_activity), 2)))
        out_string = "DST_MAC: %s, NEXT_HOP_MAC: %s, N_HOPS: %s, IDLE_TIME: %s" % out_tuple

        return out_string


class Table:
    def __init__(self, node_mac):
        self.entries = {}                 # List of entries
        self.arp_table = {}               # A dictionary which maps current IP addresses with the devices' MAC addresses
        self.node_mac = node_mac
        
    # Add an entry to the route table and the arp_table
    def add_entry(self, dst_mac, next_hop_mac, n_hops):
        # Create new route entry object
        entry = Entry(dst_mac, next_hop_mac, n_hops)
        if dst_mac in self.entries:
            # Check if the identical entry already exists in the table
            for ent in self.entries[dst_mac]:
                # If yes, just refresh its last_activity time and return it
                if ent == entry:
                    ent.last_activity = time()
                    return ent
            
            self.entries[dst_mac].append(entry)
            
        else:
            self.entries[dst_mac] = [entry]
            # Print the route table
            # print "New entry has been added. Table updated."

            TABLE_LOG.info("New entry has been added. Table updated.")

            self.print_table()
        return entry
    
    def update_arp_table(self, ip, mac):
            self.arp_table.update({ip: mac})
    
    # Delete all entries where next_hop_mac matches the given mac
    def del_entries(self, mac):
        entries_to_delete = {}
        for dst_mac in self.entries:
            entries_to_delete.update({dst_mac: []})

            # entries_to_delete = []

            for entry in self.entries[dst_mac]:
                if entry.next_hop_mac == mac:
                    entries_to_delete[dst_mac].append(entry)

        # Deleting chosen entries from the list of entries with current dst_mac
        for dst_mac in entries_to_delete:
            for ent in entries_to_delete[dst_mac]:
                self.entries[dst_mac].remove(ent)
            # Check if that was the last existing entry. If yes -> delete the key from the dictionary
            if self.entries[dst_mac] == []:
                del self.entries[dst_mac]

        # print "All entries with given next_hop_mac have been removed. Table updated."

        TABLE_LOG.info("All entries with given next_hop_mac have been removed. Table updated.")

        self.print_table()

    # Print all entries of the route table to a file
    def print_table(self):
        f = open("table.txt", "w")
        f.write("-" * 90 + "\n")
        for dst_mac in self.entries:
            f.write("Towards destination MAC: %s \n" % dst_mac)
            f.write("<Dest_MAC> \t\t <Next_hop_MAC> \t\t <Hop_count> \t <IDLE Time>\n")
            for entry in self.entries[dst_mac]:
                string = "%s \t %s \t\t\t %s \t %s\n"
                values = (entry.dst_mac, entry.next_hop_mac, entry.n_hops,
                          str(round((time() - entry.last_activity), 2)))
                f.write(string % values)
            f.write("\n")

        f.write("-" * 90 + "\n")

    def print_entry(self, entry):
        TABLE_LOG.info("<Dest_MAC>: %s, <Next_hop_MAC>: %s, <Hop_count>: %s, <IDLE Time>: %s",
                       entry.dst_mac, entry.next_hop_mac, entry.n_hops, round((time() - entry.last_activity), 2))

    # Returns an entry with a given dest_ip and ID
    def get_entry_by_ID(self, dest_ip, ID):
        IDs = []
        if dest_ip in self.entries:
            for d in self.entries[dest_ip]:
                IDs.append(d.id)

        return self.entries[dest_ip][IDs.index(ID)]
    
    # Check the dst_ip in arp_table and in the route_table
    def lookup_mac_address(self, dst_ip):
        # Check the arp table
        if dst_ip in self.arp_table:
            return self.arp_table[dst_ip]
        else:
            return None
    
    def lookup_entry(self, dst_mac):
        if dst_mac == None:
            return None
        if dst_mac in self.entries:
            # Checking the age of the route entry
            self.check_expiry(dst_mac)
            return self.select_route(dst_mac)
        else:
            return None
    
    # Returns an entry with min amount of hops to the destination MAC address
    def select_route(self, dst_mac):
        hop_counts = []
        if dst_mac in self.entries:
            for a in self.entries[dst_mac]:
                hop_counts.append(a.n_hops)
                
            entry = self.entries[dst_mac][hop_counts.index(min(hop_counts))]
            entry.last_activity = time()
            return entry
        else:
            return None

    # Check the entry's last activity. If it exceeds the timeout, then delete it.
    def check_expiry(self, dst_mac):
        entries_to_delete = []
        if dst_mac in self.entries:
            for ent in self.entries[dst_mac]:
                if (time() - ent.last_activity) > ent.timeout:
                    entries_to_delete.append(ent)
                    # self.entries[dst_mac].remove(ent)
            for ent in entries_to_delete:
                self.entries[dst_mac].remove(ent)
            # If the list becomes empty, then delete it
            if self.entries[dst_mac] == []:
                del self.entries[dst_mac]

        else:
            print "This should never happen: RouteTable.check_expiry(dst_mac)"

            TABLE_LOG.warning("This should never happen: RouteTable.check_expiry(dst_mac)")
