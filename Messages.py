#!/usr/bin/python
'''
Created on Oct 6, 2014

@author: Dmitrii Dugaev
'''

from random import randint
import struct

class RouteRequest:
    def __init__(self):
        self.id = randint(1, 1000000)
        self.src_ip = ""
        self.dst_ip = ""
        self.dsn = 0
        self.hop_count = 0

class RouteReply:
    def __init__(self):
        self.id = 0
        self.src_ip = ""
        self.dst_ip = ""
        self.dsn = 0
        self.hop_count = 0
        
class HelloMessage:
    def __init__(self):
        self.id = randint(1, 1000000)
        self.mac = ""
        self.retries = 0
        
class DsrHeader():
    def __init__(self):
        self.header_format = "BBddd"          # DSR header format: <Type><Length><Src_mac><Dst_mac><Tx_mac>
        # Available types: 0 - Data packet, 1 - HELLO Message, 2,3 - RREQ, RREP
        self.type = 0
        self.length = struct.calcsize(self.header_format)
        self.src_mac = "00:00:00:00:00:00"
        self.dst_mac = "00:00:00:00:00:00"
        self.tx_mac = "00:00:00:00:00:00"
        
    
    
    
    
    
    
    
    