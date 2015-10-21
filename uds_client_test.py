'''
Created on Oct 16, 2015

@author: dmitry
'''


import socket

class UdsClient():
    def __init__(self):
        self.server_address = "./uds_socket"
        self.message = "helllooo"
        # Create a UDS socket
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        
    def send(self):
        self.sock.sendto(self.message, self.server_address)


client = UdsClient()
client.send()


