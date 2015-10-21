#!/usr/bin/python
'''
Created on Sep 25, 2014

@author: dmitry
'''

import socket
import Messages
import pickle


IP = "192.168.1.100"
PORT = 3000

sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_recv.bind(("", PORT))
sock_recv.settimeout(1)

sock_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

msg = Messages.RouteRequest()
msg.dest_ip = "0.0.0.0"

msg = pickle.dumps(msg)
print msg

sock_send.sendto(msg, (IP, 3000))

while True:
    try:
        data = sock_recv.recvfrom(65535)
        data = pickle.loads(data[0])
        print data, data.dest_ip

    except socket.timeout:
        sock_send.sendto(msg, (IP, 3000))


