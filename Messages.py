#!/usr/bin/python
"""
Created on Oct 6, 2014

@author: Dmitrii Dugaev
"""

from random import randint


class RouteRequest:
    dsr_type = 2

    def __init__(self):
        self.id = randint(1, 1048575)   # Max value is 2**20 (20 bits)
        self.src_ip = ""
        self.dst_ip = ""
        self.dsn = 0
        self.hop_count = 0

    def __str__(self):
        out_tuple = (str(self.id), str(self.src_ip), str(self.dst_ip), str(self.dsn), str(self.hop_count))
        out_string = "ID: %s, SRC_IP: %s, DST_IP: %s, DSN: %s, HOP_COUNT: %s" % out_tuple

        return out_string


class RouteReply:
    dsr_type = 3

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
        self.id = randint(1, 1048575)
        self.mac = str()
        self.l3_addresses = []      # A list of L3 addresses, assigned to this node
        self.retries = 0

    def __str__(self):
        out_tuple = (self.id, self.mac, self.l3_addresses, self.retries)
        out_string = "ID: %s, MAC: %s, L3_addresses: %s, Retries_count: %s" % out_tuple

        return out_string


# Describes an ACK message from one of the service messages
class AckMessage:
    def __init__(self, msg_hash):
        self.msg_hash = msg_hash       # Contains a unique hash, created from the original msg_id and the dest_address

    def __str__(self):
        out_tuple = (str(self.msg_hash))
        out_string = "ACK hash: %s" % out_tuple

        return out_string


# Describes a reward message, which is being generated and sent back to the node upon
# receiving a packet with a given dst_ip.
class RewardMessage:
    def __init__(self):
        self.id = randint(1, 1048575)
        self.msg_hash = int()
        self.reward_value = float()

    def __str__(self):
        out_tuple = (self.id, self.msg_hash, self.reward_value)
        out_string = "ID: %s, MSG_HASH: %s, REWARD_VALUE: %s" % out_tuple

        return out_string


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
        # Available types: 0 - Data packet, 1 - HELLO Message, 2,3 - RREQ, RREP, 4 - Broadcast frame, 5 - ACK frame,
        #                                   6 - Reward Message
        self.type = _type
        # !!! WARNING !!! #
        # !!! The header_format MUST ALWAYS have the same size for ANY dsr type !!! #
        # !!! This is because the transport creates new dsr header objects, assuming that the format is the same !!! #
        # !!! Hopefully, will be fixed later !!! #
        if self.type == 4:
            self.header_format = DsrHeader.broadcast_header_format
            self.src_mac = "00:00:00:00:00:00"
            self.tx_mac = "00:00:00:00:00:00"
            self.broadcast_id = randint(1, 1048575)
            self.broadcast_ttl = 0               # A number of hops the broadcast packets have gone through
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
