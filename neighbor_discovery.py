'''
Created on Sep 25, 2014

@author: Dmitrii Dugaev

This script implements a neighbor discovery procedure,
used for locating a direct neighbors of the same wifi adhoc network.
Uses UDP packets for sending service packets.
'''

import socket
from socket import SOL_SOCKET, SO_BROADCAST
import time

from RouteTable import Table

# Setting a bunch of global parameters
BROADCAST_IP = "192.255.255.255"
BROADCAST_PORT = 3000
NODE_IP = ""
MSG = "HELLO_NEIGHBOR_DISCOVERY"                                # Hello message

# Creating socket objects for sending and receiving messages
sock_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_send.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)               # Set up to work with broadcast addresses

sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_recv.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
sock_recv.bind(("", BROADCAST_PORT))
sock_recv.setblocking(False)                       # Setting an unblocking socket

# Creating a Table() class for handling neighbors
table = Table()

def run():
    nodes = []      # A list containing ip addresses of neighbor nodes
    while True:
        # Sending first broadcast request
        sock_send.sendto(MSG, (BROADCAST_IP, BROADCAST_PORT))
        try:
            data = sock_recv.recvfrom(65535)
            ip = data[1][0]
            while ip == NODE_IP:
                try:
                    data = sock_recv.recvfrom(65535)
                    ip = data[1][0]
                except socket.error:
                    break
            
            if ip != NODE_IP:
                table.add_neighbor(ip)
            
            if ip not in nodes and ip != NODE_IP:
                nodes.append(ip)
                sock_send.sendto(MSG, (BROADCAST_IP, BROADCAST_PORT))

            print nodes
                
        except socket.error:
            print "Nothing in the buffer"
            
            # There should be some logic with the routing table
            
        time.sleep(0.5)
            
