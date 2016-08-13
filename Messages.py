#!/usr/bin/python
"""
Created on Oct 7, 2016

@author: Dmitrii Dugaev


This module describes all possible message types, which can be transmitted by the routing protocol.
All the message types are assigned with a unique type ID and a corresponding header, which contains
additional service information about the packet. The header is called "DSR-header" for now, since it is attached to
a packet between the L2 and L3 headers, as it is done in original DSR routing protocol.
But this is the last similarity with the DSR - our protocol doesn't have to do anything with the concept of
Dynamic Source Routing, and is based on its own concept of packet routing - based on the convergence of reactive
routing and the Reinforcement Learning method - to enable route selection based on current network conditions.
This routing protocol is close to a so-called concept of "Opportunistic Routing" where the nodes have more freedom
to select a next hop, not being completely relied on a current fixed route table state.

                                    CURRENT MESSAGE TYPES:
------------------------------------------------------------------------------------------------------------------------
| TYPE |         MESSAGE           |   LENGTH (BYTES)        |                   DESCRIPTION                           |
------------------------------------------------------------------------------------------------------------------------
|  0   |    Unicast Data Packet    |        4                |   Unicast data packet from the user (network) interface |
|      |                           |                         |                                                         |
|  1   |  Broadcast Data Packet    |        4                |  Broadcast data packet from the user (network) interface|
|      |                           |                         |                                                         |
|  2   |          RREQ4            |        12               |     Route Request service message for IPv4 destination  |
|      |                           |                         |                                                         |
|  3   |          RREQ6            |        36               |     Route Request service message for IPv6 destination  |
|      |                           |                         |                                                         |
|  4   |          RREP4            |        12               |      Route Reply service message for IPv4 destination   |
|      |                           |                         |                                                         |
|  5   |          RREP6            |        36               |      Route Reply service message for IPv6 destination   |
|      |                           |                         |                                                         |
|  6   |          HELLO            |        from 4 to 56     |               Hello service message                     |
|      |                           |                         |                                                         |
|  7   |           ACK             |        8                |       ACK service message for reliable transmission     |
|      |                           |                         |                                                         |
|  8   |          REWARD           |        6                |               Reward service message                    |
------------------------------------------------------------------------------------------------------------------------

The messages (headers) are described as CType classes with pre-defined fields, depending on a message type.
A detailed description of the fields and its functionality can be found in the documentation.
"""

from random import randint
from socket import AF_INET6, inet_pton, inet_aton, inet_ntoa, inet_ntop
from socket import error as sock_error
from math import ceil

import ctypes
import struct
import binascii


# Define static functions for packing and unpacking the message object to and from the binary dsr header.
# Pack the object to dsr header. Return the byte array.
def pack_message(message):
    if isinstance(message, UnicastPacket):
        return UnicastHeader().pack(message)

    elif isinstance(message, BroadcastPacket):
        return BroadcastHeader().pack(message)

    elif isinstance(message, RreqMessage):
        # Try to convert an address into binary form. If failed to convert from IPv4,
        # then assume that the address is IPv6.
        try:
            inet_aton(message.src_ip)
            message.type = 2
            return Rreq4Header().pack(message)

        except sock_error:
            message.type = 3
            return Rreq6Header().pack(message)

    elif isinstance(message, RrepMessage):
        # Try to convert an address into binary form. If failed to convert from IPv4,
        # then assume that the address is IPv6.
        try:
            inet_aton(message.src_ip)
            message.type = 4
            return Rrep4Header().pack(message)

        except sock_error:
            message.type = 5
            return Rrep6Header().pack(message)

    elif isinstance(message, HelloMessage):
        return HelloHeader().pack(message)

    elif isinstance(message, AckMessage):
        return AckHeader().pack(message)

    elif isinstance(message, RewardMessage):
        return RewardHeader().pack(message)

    else:
        return None


# Unpack an object from the dsr header. Return the message object.
def unpack_message(binary_header):
    class TypeField(ctypes.LittleEndianStructure):
        _fields_ = [
            ("TYPE", ctypes.c_uint32, 4),
        ]

    # Get a field with type value
    type_binary_field = binary_header[:4]
    type_field_unpacked = TypeField.from_buffer_copy(type_binary_field)
    type_value = type_field_unpacked.TYPE

    if type_value == 0:
        return UnicastHeader().unpack(binary_header)

    elif type_value == 1:
        return BroadcastHeader().unpack(binary_header)

    elif type_value == 2:
        return Rreq4Header().unpack(binary_header)

    elif type_value == 3:
        return Rreq6Header().unpack(binary_header)

    elif type_value == 4:
        return Rrep4Header().unpack(binary_header)

    elif type_value == 5:
        return Rrep6Header().unpack(binary_header)

    elif type_value == 6:
        return HelloHeader().unpack(binary_header)

    elif type_value == 7:
        return AckHeader().unpack(binary_header)

    elif type_value == 8:
        return RewardHeader().unpack(binary_header)

    else:
        return None


#######################################################################################################################
# TODO: make constructors for all messages
# Describe all message classes, whose instances will be used to manipulate and "pack" the data to dsr binary header.
# Unicast data packet
class UnicastPacket:
    type = 0

    def __init__(self):
        self.id = randint(0, 1048575)       # Max value is 2**20 (20 bits - id field size)
        self.hop_count = 0

    def __str__(self):
        out_tuple = (self.type, self.id, self.hop_count)
        out_string = "TYPE: %s, ID: %s, HOP_COUNT: %s" % out_tuple
        return out_string


# Broadcast data packet
class BroadcastPacket:
    type = 1

    def __init__(self):
        self.id = self.id = randint(0, 1048575)
        self.broadcast_ttl = 0

    def __str__(self):
        out_tuple = (self.type, self.id, self.broadcast_ttl)
        out_string = "TYPE: %s, ID: %s, BROADCAST_TTL: %s" % out_tuple
        return out_string


# Route Request service message for IPv4 and IPv6 L3 addressing
class RreqMessage:
    type = int()

    def __init__(self):
        self.id = randint(0, 1048575)
        self.src_ip = str()
        self.dst_ip = str()
        self.hop_count = 0

    def __str__(self):
        out_tuple = (self.id, self.src_ip, self.dst_ip, self.hop_count)
        out_string = "ID: %s, SRC_IP: %s, DST_IP: %s, HOP_COUNT: %s" % out_tuple
        return out_string


# Route Reply service message for IPv4 and IPv6 L3 addressing
class RrepMessage:
    type = int()

    def __init__(self):
        self.id = randint(0, 1048575)
        self.src_ip = str()
        self.dst_ip = str()
        self.hop_count = 0

    def __str__(self):
        out_tuple = (self.type, self.id, self.src_ip, self.dst_ip, self.hop_count)
        out_string = "TYPE: %s, ID: %s, SRC_IP: %s, DST_IP: %s, HOP_COUNT: %s" % out_tuple
        return out_string


# Hello service message
class HelloMessage:
    type = 6

    def __init__(self):
        self.ipv4_count = 0
        self.ipv6_count = 0
        self.ipv4_address = str()
        self.ipv6_addresses = list()
        self.tx_count = 0

    def __str__(self):
        out_tuple = (self.type, self.ipv4_address, self.ipv6_addresses, self.tx_count)
        out_string = "TYPE: %s, IPV4_ADDRESS: %s, IPV6_ADDRESSES: %s, TX_COUNT: %s" % out_tuple
        return out_string


# Acknowledgement message
class AckMessage:
    type = 7

    def __init__(self):
        self.id = randint(0, 1048575)
        self.tx_count = 0
        self.msg_hash = 0

    def __str__(self):
        out_tuple = (self.type, self.id, self.tx_count, self.msg_hash)
        out_string = "TYPE: %s, ID: %s, TX_COUNT: %s, MSG_HASH: %s" % out_tuple
        return out_string


# Reward message
class RewardMessage:
    type = 8

    def __init__(self, reward_value, msg_hash):
        self.id = randint(0, 1048575)
        self.reward_value = int(ceil(reward_value))
        self.msg_hash = msg_hash

    def __str__(self):
        out_tuple = (self.type, self.id, self.reward_value, self.msg_hash)
        out_string = "TYPE: %s, ID: %s, REWARD_VALUE: %s, MSG_HASH: %s" % out_tuple
        return out_string


#######################################################################################################################
# ## Describe DSR headers which will pack the initial message object and return a binary string ## #
# Unicast header
class UnicastHeader:
    class Header(ctypes.LittleEndianStructure):
        _fields_ = [
                ("TYPE", ctypes.c_uint32, 4),
                ("ID", ctypes.c_uint32, 20),
                ("HOP_COUNT", ctypes.c_uint32, 8)
            ]

    def __init__(self):
        # self.header = self.Header(unicast_message.type, unicast_message.id, unicast_message.hop_count)
        pass

    # Returns a header binary string in hex representation
    def pack(self, unicast_message):
        header = self.Header(unicast_message.type, unicast_message.id, unicast_message.hop_count)
        # Return the array in byte representation
        return bytearray(header)

    # Returns a message object, created from the binary data
    def unpack(self, binary_header):
        # Cast the byte_array into the structure
        header_unpacked = self.Header.from_buffer_copy(binary_header)
        # Get values and create message object and fill up the fields
        message = UnicastPacket()
        message.id = header_unpacked.ID
        message.hop_count = header_unpacked.HOP_COUNT
        # Return the message
        return message, len(bytearray(header_unpacked))


# Broadcast header
class BroadcastHeader:
    class Header(ctypes.LittleEndianStructure):
        _fields_ = [
            ("TYPE", ctypes.c_uint32, 4),
            ("ID", ctypes.c_uint32, 20),
            ("BROADCAST_TTL", ctypes.c_uint32, 8)
        ]

    def __init__(self):
        pass

    # Returns a header binary string in hex representation
    def pack(self, broadcast_message):
        header = self.Header(broadcast_message.type, broadcast_message.id, broadcast_message.broadcast_ttl)
        # Return the array in byte representation
        return bytearray(header)

    # Returns a message object, created from the binary data
    def unpack(self, binary_header):
        # Cast the byte_array into the structure
        header_unpacked = self.Header.from_buffer_copy(binary_header)
        # Get values and create message object and fill up the fields
        message = BroadcastPacket()
        message.id = header_unpacked.ID
        message.broadcast_ttl = header_unpacked.BROADCAST_TTL
        # Return the message
        return message, len(bytearray(header_unpacked))


# RREQ4 header
class Rreq4Header:
    class Header(ctypes.LittleEndianStructure):
        _fields_ = [
            ("TYPE", ctypes.c_uint32, 4),
            ("ID", ctypes.c_uint32, 20),
            ("HOP_COUNT", ctypes.c_uint32, 8),
            ("SRC_IP", ctypes.c_uint32, 32),
            ("DST_IP", ctypes.c_uint32, 32)
        ]

    def __init__(self):
        pass

    # Returns an integer with binary encoded data structure, created from the initial message
    def pack(self, rreq4_message):
        # Turn string representations of IP addresses into an integer form
        src_ip = struct.unpack("!I", inet_aton(rreq4_message.src_ip))[0]
        dst_ip = struct.unpack("!I", inet_aton(rreq4_message.dst_ip))[0]
        header = self.Header(rreq4_message.type, rreq4_message.id, rreq4_message.hop_count, src_ip, dst_ip)
        # Return the array in byte representation
        return bytearray(header)

    # Returns a message object, created from the binary data
    def unpack(self, binary_header):
        # Cast the byte_array into the structure
        header_unpacked = self.Header.from_buffer_copy(binary_header)
        # Get values and create message object and fill up the fields
        message = RreqMessage()
        message.type = header_unpacked.TYPE
        message.id = header_unpacked.ID
        message.hop_count = header_unpacked.HOP_COUNT
        message.src_ip = inet_ntoa(struct.pack("!I", header_unpacked.SRC_IP))
        message.dst_ip = inet_ntoa(struct.pack("!I", header_unpacked.DST_IP))
        # Return the message
        return message, len(bytearray(header_unpacked))


# RREQ6 header
class Rreq6Header:
    class Header(ctypes.LittleEndianStructure):
        _fields_ = [
            ("TYPE", ctypes.c_uint32, 4),
            ("ID", ctypes.c_uint32, 20),
            ("HOP_COUNT", ctypes.c_uint32, 8),
            ("SRC_IP1", ctypes.c_uint32, 32),
            ("SRC_IP2", ctypes.c_uint32, 32),
            ("SRC_IP3", ctypes.c_uint32, 32),
            ("SRC_IP4", ctypes.c_uint32, 32),
            ("DST_IP1", ctypes.c_uint32, 32),
            ("DST_IP2", ctypes.c_uint32, 32),
            ("DST_IP3", ctypes.c_uint32, 32),
            ("DST_IP4", ctypes.c_uint32, 32)
        ]

    max_int64 = 0xFFFFFFFFFFFFFFFF
    max_int32 = 0xFFFFFFFF

    def __init__(self):
        pass

    def pack(self, rreq6_message):
        # Turn string representations of IP addresses into an integer form
        src_ip = int(binascii.hexlify(inet_pton(AF_INET6, rreq6_message.src_ip)), 16)
        dst_ip = int(binascii.hexlify(inet_pton(AF_INET6, rreq6_message.dst_ip)), 16)
        # Split each IPv6 128-bit value into four 32-bit parts
        src_ip_left_64 = (src_ip >> 64) & self.max_int64
        src_ip_right_64 = src_ip & self.max_int64
        dst_ip_left_64 = (dst_ip >> 64) & self.max_int64
        dst_ip_right_64 = dst_ip & self.max_int64

        # Pack the values
        header = self.Header(rreq6_message.type, rreq6_message.id, rreq6_message.hop_count,
                             (src_ip_left_64 >> 32) & self.max_int32, src_ip_left_64 & self.max_int32,
                             (src_ip_right_64 >> 32) & self.max_int32, src_ip_right_64 & self.max_int32,
                             (dst_ip_left_64 >> 32) & self.max_int32, dst_ip_left_64 & self.max_int32,
                             (dst_ip_right_64 >> 32) & self.max_int32, dst_ip_right_64 & self.max_int32)

        # Return the array in byte representation
        return bytearray(header)

    # Returns a message object, created from the binary data
    def unpack(self, binary_header):
        # Cast the byte_array into the structure
        header_unpacked = self.Header.from_buffer_copy(binary_header)
        # Get values and create message object and fill up the fields
        message = RreqMessage()
        message.type = header_unpacked.TYPE
        message.id = header_unpacked.ID
        message.hop_count = header_unpacked.HOP_COUNT
        # Merge the parts of 128-bit IPv6 address together
        src_ip_left_64 = (header_unpacked.SRC_IP1 << 32 | header_unpacked.SRC_IP2)
        src_ip_right_64 = (header_unpacked.SRC_IP3 << 32 | header_unpacked.SRC_IP4)
        dst_ip_left_64 = (header_unpacked.DST_IP1 << 32 | header_unpacked.DST_IP2)
        dst_ip_right_64 = (header_unpacked.DST_IP3 << 32 | header_unpacked.DST_IP4)

        src_ip_packed_value = struct.pack(b"!QQ", src_ip_left_64, src_ip_right_64)
        dst_ip_packed_value = struct.pack(b"!QQ", dst_ip_left_64, dst_ip_right_64)

        message.src_ip = inet_ntop(AF_INET6, src_ip_packed_value)
        message.dst_ip = inet_ntop(AF_INET6, dst_ip_packed_value)
        # Return the message
        return message, len(bytearray(header_unpacked))


# RREP4 header
class Rrep4Header:
    class Header(ctypes.LittleEndianStructure):
        _fields_ = [
            ("TYPE", ctypes.c_uint32, 4),
            ("ID", ctypes.c_uint32, 20),
            ("HOP_COUNT", ctypes.c_uint32, 8),
            ("SRC_IP", ctypes.c_uint32, 32),
            ("DST_IP", ctypes.c_uint32, 32)
        ]

    def __init__(self):
        pass

    # Returns an integer with binary encoded data structure, created from the initial message
    def pack(self, rrep4_message):
        # Turn string representations of IP addresses into an integer form
        src_ip = struct.unpack("!I", inet_aton(rrep4_message.src_ip))[0]
        dst_ip = struct.unpack("!I", inet_aton(rrep4_message.dst_ip))[0]
        header = self.Header(rrep4_message.type, rrep4_message.id, rrep4_message.hop_count, src_ip, dst_ip)
        # Return the array in byte representation
        return bytearray(header)

    # Returns a message object, created from the binary data
    def unpack(self, binary_header):
        # Cast the byte_array into the structure
        header_unpacked = self.Header.from_buffer_copy(binary_header)
        # Get values and create message object and fill up the fields
        message = RrepMessage()
        message.type = header_unpacked.TYPE
        message.id = header_unpacked.ID
        message.hop_count = header_unpacked.HOP_COUNT
        message.src_ip = inet_ntoa(struct.pack("!I", header_unpacked.SRC_IP))
        message.dst_ip = inet_ntoa(struct.pack("!I", header_unpacked.DST_IP))
        # Return the message
        return message, len(bytearray(header_unpacked))


# RREP6 header
class Rrep6Header:
    class Header(ctypes.LittleEndianStructure):
        _fields_ = [
            ("TYPE", ctypes.c_uint32, 4),
            ("ID", ctypes.c_uint32, 20),
            ("HOP_COUNT", ctypes.c_uint32, 8),
            ("SRC_IP1", ctypes.c_uint32, 32),
            ("SRC_IP2", ctypes.c_uint32, 32),
            ("SRC_IP3", ctypes.c_uint32, 32),
            ("SRC_IP4", ctypes.c_uint32, 32),
            ("DST_IP1", ctypes.c_uint32, 32),
            ("DST_IP2", ctypes.c_uint32, 32),
            ("DST_IP3", ctypes.c_uint32, 32),
            ("DST_IP4", ctypes.c_uint32, 32)
        ]

    max_int64 = 0xFFFFFFFFFFFFFFFF
    max_int32 = 0xFFFFFFFF

    def __init__(self):
        pass

    def pack(self, rrep6_message):
        # Turn string representations of IP addresses into an integer form
        src_ip = int(binascii.hexlify(inet_pton(AF_INET6, rrep6_message.src_ip)), 16)
        dst_ip = int(binascii.hexlify(inet_pton(AF_INET6, rrep6_message.dst_ip)), 16)
        # Split each IPv6 128-bit value into four 32-bit parts
        src_ip_left_64 = (src_ip >> 64) & self.max_int64
        src_ip_right_64 = src_ip & self.max_int64
        dst_ip_left_64 = (dst_ip >> 64) & self.max_int64
        dst_ip_right_64 = dst_ip & self.max_int64

        # Pack the values
        header = self.Header(rrep6_message.type, rrep6_message.id, rrep6_message.hop_count,
                             (src_ip_left_64 >> 32) & self.max_int32, src_ip_left_64 & self.max_int32,
                             (src_ip_right_64 >> 32) & self.max_int32, src_ip_right_64 & self.max_int32,
                             (dst_ip_left_64 >> 32) & self.max_int32, dst_ip_left_64 & self.max_int32,
                             (dst_ip_right_64 >> 32) & self.max_int32, dst_ip_right_64 & self.max_int32)

        # Return the array in byte representation
        return bytearray(header)

    # Returns a message object, created from the binary data
    def unpack(self, binary_header):
        # Cast the byte_array into the structure
        header_unpacked = self.Header.from_buffer_copy(binary_header)
        # Get values and create message object and fill up the fields
        message = RrepMessage()
        message.type = header_unpacked.TYPE
        message.id = header_unpacked.ID
        message.hop_count = header_unpacked.HOP_COUNT
        # Merge the parts of 128-bit IPv6 address together
        src_ip_left_64 = (header_unpacked.SRC_IP1 << 32 | header_unpacked.SRC_IP2)
        src_ip_right_64 = (header_unpacked.SRC_IP3 << 32 | header_unpacked.SRC_IP4)
        dst_ip_left_64 = (header_unpacked.DST_IP1 << 32 | header_unpacked.DST_IP2)
        dst_ip_right_64 = (header_unpacked.DST_IP3 << 32 | header_unpacked.DST_IP4)

        src_ip_packed_value = struct.pack(b"!QQ", src_ip_left_64, src_ip_right_64)
        dst_ip_packed_value = struct.pack(b"!QQ", dst_ip_left_64, dst_ip_right_64)

        message.src_ip = inet_ntop(AF_INET6, src_ip_packed_value)
        message.dst_ip = inet_ntop(AF_INET6, dst_ip_packed_value)
        # Return the message
        return message, len(bytearray(header_unpacked))


# Hello message header
class HelloHeader:
    # Define fixed fields of the header structure
    class FixedHeader(ctypes.LittleEndianStructure):
        _fields_ = [("TYPE", ctypes.c_uint32, 4),
                    ("IPV4_COUNT", ctypes.c_uint32, 1),
                    ("IPV6_COUNT", ctypes.c_uint32, 2),
                    ("TX_COUNT", ctypes.c_uint32, 25)
                    ]

    # Header if only IPv4 address is present
    class OnlyIpv4Header(ctypes.LittleEndianStructure):
        _fields_ = [("TYPE", ctypes.c_uint32, 4),
                    ("IPV4_COUNT", ctypes.c_uint32, 1),
                    ("IPV6_COUNT", ctypes.c_uint32, 2),
                    ("TX_COUNT", ctypes.c_uint32, 25),
                    ("IPV4_ADDRESS", ctypes.c_uint32, 32)
                    ]

    max_int64 = 0xFFFFFFFFFFFFFFFF
    max_int32 = 0xFFFFFFFF

    def __init__(self):
        pass

    def pack(self, hello_message):
        args = [hello_message.type, hello_message.ipv4_count, hello_message.ipv6_count, hello_message.tx_count]
        # Add fields in the structure, depending on the given hello_message
        if hello_message.ipv4_count and hello_message.ipv6_count == 0:
            ipv4_address = struct.unpack("!I", inet_aton(hello_message.ipv4_address))[0]
            args.append(ipv4_address)
            header = self.OnlyIpv4Header(*args)

        elif hello_message.ipv6_count:
            fields = list(self.FixedHeader._fields_)
            if hello_message.ipv4_count:
                fields.append(("IPV4_ADDRESS", ctypes.c_uint32, 32))
                ipv4_address = struct.unpack("!I", inet_aton(hello_message.ipv4_address))[0]
                args.append(ipv4_address)

            for i in xrange(hello_message.ipv6_count):
                fields.append(("IPV6_ADDRESS_%s_1" % i, ctypes.c_uint32, 32))
                fields.append(("IPV6_ADDRESS_%s_2" % i, ctypes.c_uint32, 32))
                fields.append(("IPV6_ADDRESS_%s_3" % i, ctypes.c_uint32, 32))
                fields.append(("IPV6_ADDRESS_%s_4" % i, ctypes.c_uint32, 32))

                # Pack ipv6 addresses
                ipv6_address = int(binascii.hexlify(inet_pton(AF_INET6, hello_message.ipv6_addresses[i])), 16)
                ipv6_address_left = (ipv6_address >> 64) & self.max_int64
                ipv6_address_right = ipv6_address & self.max_int64

                args.extend([(ipv6_address_left >> 32) & self.max_int32, ipv6_address_left & self.max_int32,
                             (ipv6_address_right >> 32) & self.max_int32, ipv6_address_right & self.max_int32])

            # Define header structure
            class Header(ctypes.Structure):
                _fields_ = fields

            header = Header(*args)

        # Else, construct an empty header without IP addresses
        else:
            header = self.FixedHeader(*args)

        # Return the array in byte representation
        return bytearray(header)

    # Returns a message object, created from the binary data
    def unpack(self, binary_header):
        # Get the first fixed part of the header
        fixed_header_unpacked = self.FixedHeader.from_buffer_copy(binary_header)
        # Create and write to a message object
        message = HelloMessage()

        # Generate the rest of the part
        if fixed_header_unpacked.IPV4_COUNT and fixed_header_unpacked.IPV6_COUNT == 0:
            header_unpacked = self.OnlyIpv4Header.from_buffer_copy(binary_header)
            # # Create and write to a message object
            # message = HelloMessage()
            # message.ipv4_count = header_unpacked.IPV4_COUNT
            # message.ipv6_count = header_unpacked.IPV6_COUNT
            message.ipv4_address = inet_ntoa(struct.pack("!I", header_unpacked.IPV4_ADDRESS))
            # message.tx_count = header_unpacked.TX_COUNT

        elif fixed_header_unpacked.IPV6_COUNT:

            fields = list(self.FixedHeader._fields_)
            if fixed_header_unpacked.IPV4_COUNT:
                fields.append(("IPV4_ADDRESS", ctypes.c_uint32, 32))

            for i in xrange(fixed_header_unpacked.IPV6_COUNT):
                fields.append(("IPV6_ADDRESS_%s_1" % i, ctypes.c_uint32, 32))
                fields.append(("IPV6_ADDRESS_%s_2" % i, ctypes.c_uint32, 32))
                fields.append(("IPV6_ADDRESS_%s_3" % i, ctypes.c_uint32, 32))
                fields.append(("IPV6_ADDRESS_%s_4" % i, ctypes.c_uint32, 32))

            # Define header structure
            class Header(ctypes.Structure):
                _fields_ = fields

            # # Create and write to a message object
            # message = HelloMessage()

            header_unpacked = Header.from_buffer_copy(binary_header)

            if header_unpacked.IPV4_COUNT:
                message.ipv4_address = inet_ntoa(struct.pack("!I", header_unpacked.IPV4_ADDRESS))

            for i in xrange(header_unpacked.IPV6_COUNT):
                # Merge the parts of 128-bit IPv6 address together
                ipv6_left = (getattr(header_unpacked, "IPV6_ADDRESS_%s_1" % i) << 32 |
                             getattr(header_unpacked, "IPV6_ADDRESS_%s_2" % i))
                ipv6_right = (getattr(header_unpacked, "IPV6_ADDRESS_%s_3" % i) << 32 |
                              getattr(header_unpacked, "IPV6_ADDRESS_%s_4" % i))

                ipv6_packed_value = struct.pack(b"!QQ", ipv6_left, ipv6_right)

                message.ipv6_addresses.append(inet_ntop(AF_INET6, ipv6_packed_value))

            # message.tx_count = header_unpacked.TX_COUNT

        # Else, create a message without ip addresses
        else:
            # message = HelloMessage()
            message.tx_count = fixed_header_unpacked.TX_COUNT
            message.ipv4_count = fixed_header_unpacked.IPV4_COUNT
            message.ipv6_count = fixed_header_unpacked.IPV6_COUNT
            # Return the message
            return message, len(bytearray(fixed_header_unpacked))

        message.ipv4_count = header_unpacked.IPV4_COUNT
        message.ipv6_count = header_unpacked.IPV6_COUNT
        message.tx_count = header_unpacked.TX_COUNT

        # Return the message
        return message, len(bytearray(header_unpacked))


# ACK header
class AckHeader:
    class Header(ctypes.LittleEndianStructure):
        _fields_ = [
            ("TYPE", ctypes.c_uint32, 4),
            ("ID", ctypes.c_uint32, 20),
            ("TX_COUNT", ctypes.c_uint32, 8),
            ("MSG_HASH", ctypes.c_uint32, 32)
        ]

    def __init__(self):
        pass

    # Returns an integer with binary encoded data structure, created from the initial message
    def pack(self, ack_message):
        header = self.Header(ack_message.type, ack_message.id, ack_message.tx_count, ack_message.msg_hash)
        # Return the array in byte representation
        return bytearray(header)

    # Returns a message object, created from the binary data
    def unpack(self, binary_header):
        # Cast the byte_array into the structure
        header_unpacked = self.Header.from_buffer_copy(binary_header)
        # Get values and create message object and fill up the fields
        message = AckMessage()
        message.id = header_unpacked.ID
        message.tx_count = header_unpacked.TX_COUNT
        message.msg_hash = header_unpacked.MSG_HASH
        # Return the message
        return message, len(bytearray(header_unpacked))


# Reward header
class RewardHeader:
    class Header(ctypes.LittleEndianStructure):
        _fields_ = [
            ("TYPE", ctypes.c_uint32, 4),
            ("ID", ctypes.c_uint32, 20),
            ("NEG_REWARD_FLAG", ctypes.c_uint32, 1),
            ("REWARD_VALUE", ctypes.c_uint32, 7),
            ("MSG_HASH", ctypes.c_uint32, 32)
        ]

    def __init__(self):
        pass

    # Returns an integer with binary encoded data structure, created from the initial message
    def pack(self, reward_message):
        if reward_message.reward_value < 0:
            header = self.Header(reward_message.type, reward_message.id, 1,
                                 abs(reward_message.reward_value), reward_message.msg_hash)
        else:
            header = self.Header(reward_message.type, reward_message.id, 0,
                                 reward_message.reward_value, reward_message.msg_hash)
        # Return the byte array
        return bytearray(header)

    # Returns a message object, created from the binary data
    def unpack(self, binary_header):
        # Cast the byte_array into the structure
        header_unpacked = self.Header.from_buffer_copy(binary_header)
        if header_unpacked.NEG_REWARD_FLAG:
            message = RewardMessage(-1 * header_unpacked.REWARD_VALUE, header_unpacked.MSG_HASH)
            message.id = header_unpacked.ID
        else:
            message = RewardMessage(header_unpacked.REWARD_VALUE, header_unpacked.MSG_HASH)
            message.id = header_unpacked.ID

        # Return the message and initial header byte length
        return message, len(bytearray(header_unpacked))
