#!/usr/bin/python
'''
Created on Sep 30, 2014

@author: Dmitrii Dugaev
'''

from time import time


class Entry:
    def __init__(self, dst_mac, next_hop_mac, n_hops):

        self.dst_mac = dst_mac                                      # MAC address of destination node
        self.next_hop_mac = next_hop_mac                            # Next hop mac address
        self.n_hops = n_hops                                        # Number of hops to destination
        self.last_activity = time()                                 # Timestamp of the last activity
        self.timeout = 240                                          # Timeout in seconds upon deleting an entry
        
    def __eq__(self, other):
        return (self.dst_mac == other.dst_mac and self.next_hop_mac == other.next_hop_mac and self.n_hops == other.n_hops)


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
                # If yes, replace it with the new one and return it
                if ent == entry:
                    ent = entry             # TODO: Fix the entry replacement method
                    return entry
            
            self.entries[dst_mac].append(entry)
            
        else:
            self.entries[dst_mac] = [entry]
            # Print the route table
            print "New entry has been added. Table updated:"
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

        print "All entries with given next_hop_mac have been removed. Table updated:"
        self.print_table()

    # Print all entries of the route table
    def print_table(self):
        print "-" * 90
        for dst_mac in self.entries:
            print "Towards destination MAC:", dst_mac
            print "<Dest_MAC>", "\t\t<Next_hop_MAC>", "\t\t<Hop_count>", "\t<IDLE Time>"
            for entry in self.entries[dst_mac]:
                print entry.dst_mac, "\t", entry.next_hop_mac, "\t    ", entry.n_hops, "\t\t    ", round((time() - entry.last_activity), 2)
        print "-" * 90
        
    def print_entry(self, entry):
        print "<Dest_MAC>", "\t\t<Next_hop_MAC>", "\t\t<Hop_count>", "\t<IDLE Time>"
        print entry.dst_mac, "\t", entry.next_hop_mac, "\t    ", entry.n_hops, "\t\t    ", round((time() - entry.last_activity), 2)

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

