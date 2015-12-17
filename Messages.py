#!/usr/bin/python
'''
Created on Oct 6, 2014

@author: Dmitrii Dugaev
'''

from random import randint


class RouteRequest:
    def __init__(self):
        self.id = randint(1, 1000000)
        self.src_ip = ""
        self.dst_ip = ""
        self.dsn = 0
        self.hop_count = 0

    def __str__(self):
        out_tuple = (str(self.id), str(self.src_ip), str(self.dst_ip), str(self.dsn), str(self.hop_count))
        out_string = "ID: %s, SRC_IP: %s, DST_IP: %s, DSN: %s, HOP_COUNT: %s" % out_tuple

        return out_string


class RouteReply:
    def __init__(self):
        self.id = 0
        self.src_ip = ""
        self.dst_ip = ""
        self.dsn = 0
        self.hop_count = 0

    def __str__(self):
        out_tuple = (str(self.id), str(self.src_ip), str(self.dst_ip), str(self.dsn), str(self.hop_count))
        out_string = "ID: %s, SRC_IP: %s, DST_IP: %s, DSN: %s, HOP_COUNT: %s" % out_tuple

        return out_string


class HelloMessage:
    def __init__(self):
        self.id = randint(1, 1000000)
        self.mac = ""
        self.l3_addresses = []          # A list of L3 addresses, assigned to this node
        self.retries = 0


class DsrHeader:
    # # Increments every time a broadcast dsr header object is created
    # broadcast_id_counter = 0
    # header_format = "BBddd"
    # length = struct.calcsize(header_format)
    length = 32                                 # The length of DSR header (!!! FIXED FOR NOW !!!)
    # Unicast DSR header format: <Type><Length><Src_mac><Dst_mac><Tx_mac>
    unicast_header_format = "BBddd"
    # Broadcast DSR header format: <Type><Length><Src_mac><Tx_mac><Broadcast_ID><Broadcast_TTL>
    broadcast_header_format = "BBddii"

    def __init__(self, _type=0):
        # Available types: 0 - Data packet, 1 - HELLO Message, 2,3 - RREQ, RREP, 4 - Broadcast frame
        self.type = _type
        # !!! WARNING !!! #
        # !!! The header_format MUST ALWAYS have the same size for ANY dsr type !!! #
        # !!! This is because the transport creates new dsr header objects, assuming that the format is the same !!! #
        # !!! Hopefully, will be fixed later !!! #
        if self.type == 4:
            self.header_format = DsrHeader.broadcast_header_format
            self.src_mac = "00:00:00:00:00:00"
            self.tx_mac = "00:00:00:00:00:00"
            self.broadcast_id = randint(1, 1000000)
            self.broadcast_ttl = 0               # A number of hops the broadcast packets have gone through
            # self.broadcast_id = DsrHeader.broadcast_id_counter
            # DsrHeader.broadcast_id_counter += 1
        else:
            self.header_format = DsrHeader.unicast_header_format
            self.src_mac = "00:00:00:00:00:00"
            self.dst_mac = "00:00:00:00:00:00"
            self.tx_mac = "00:00:00:00:00:00"

    def __str__(self):
        if self.type == 4:
            out_tuple = (str(self.src_mac), str(self.tx_mac), str(self.broadcast_id), str(self.broadcast_ttl))
            out_string = "SRC_MAC: %s, TX_MAC: %s, BROADCAST_ID: %s, BROADCAST_TTL: %s" % out_tuple
            return out_string
        else:
            out_tuple = (str(self.src_mac), str(self.dst_mac), str(self.tx_mac))
            out_string = "SRC_MAC: %s, DST_MAC: %s, TX_MAC: %s" % out_tuple
            return out_string
