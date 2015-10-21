'''
Created on Oct 16, 2015

@author: dmitry
'''

import socket
        
class UdsServer():
    def __init__(self):
        self.server_address = "uds_socket"
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        
        self.sock.bind(self.server_address)
        
    def receive(self):
        data = self.sock.recvfrom(4096)
        print data
        
server = UdsServer()

server.receive()

