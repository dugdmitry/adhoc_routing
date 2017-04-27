#!/usr/bin/python
"""
@package Messages
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
|  8   |          REWARD           |        8                |               Reward service message                    |
|      |                           |                         |                                                         |
|  9   |   Reliable Data Packet    |        4                |   Unicast data packet which is transmitted using ARQ    |
------------------------------------------------------------------------------------------------------------------------

The messages (headers) are described as CType classes with pre-defined fields, depending on a message type.
A detailed description of the fields and its functionality can be found in the documentation.
"""

# Import necessary python modules from the standard library
from random import randint
from socket import AF_INET6, inet_pton, inet_aton, inet_ntoa
from socket import error as sock_error
from math import ceil
import ctypes
import struct
import binascii


## @var DEFAULT_ROUTE
# Define a default address for the packets with outside destination.
DEFAULT_ROUTE = "0.0.0.0"
## @var DEFAULT_IPV6
# Define a default IPv6 address in order to correctly parse the value into RREQ6/RREP6 messages.
DEFAULT_IPV6 = "fe80::"


# Define static functions for packing and unpacking the message object to and from the binary dsr header.
## Pack the Message object to dsr header. Return the byte array.
# @param message Message object from Messages module.
# @return packed byte array bytearray() value.
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

    elif isinstance(message, ReliableDataPacket):
        return ReliableDataHeader().pack(message)

    else:
        return None


## Unpack the Message object from the dsr header' bytearray value. Return the message object from Messages module.
# @param binary_header Binary header (bytearray) with the packed message.
# @return Message object, length of the unpacked message.
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

    elif type_value == 9:
        return ReliableDataHeader().unpack(binary_header)

    else:
        return None


# TODO: make constructors for all messages
# Describe all message classes, whose instances will be used to manipulate and "pack" the data to dsr binary header.
## Unicast data packet.
class UnicastPacket:
    ## Type ID of Unicast Data Packet
    type = 0

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        ## @var id
        # Unique packet ID.
        # Max value is (2**20 - 1), since the id field size is 20 bits.
        self.id = randint(0, 1048575)
        ## @var hop_count
        # Current hop count value.
        self.hop_count = 0

    ## Default print method.
    # @param self The object pointer.
    # @return String with "TYPE: , ID: , HOP_COUNT: ".
    def __str__(self):
        out_tuple = (self.type, self.id, self.hop_count)
        out_string = "TYPE: %s, ID: %s, HOP_COUNT: %s" % out_tuple
        return out_string


## Broadcast data packet.
class BroadcastPacket:
    ## Type ID of Broadcast Data Packet
    type = 1

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        ## @var id
        # Unique packet ID.
        self.id = self.id = randint(0, 1048575)
        ## @var broadcast_ttl
        # Broadcast TTL counter.
        self.broadcast_ttl = 0

    ## Default print method.
    # @param self The object pointer.
    # @return String with "TYPE: , ID: , BROADCAST_TTL: ".
    def __str__(self):
        out_tuple = (self.type, self.id, self.broadcast_ttl)
        out_string = "TYPE: %s, ID: %s, BROADCAST_TTL: %s" % out_tuple
        return out_string


## Route Request service message.
# This service message is used for both IPv4 and IPv6 L3 addressing cases.
class RreqMessage:
    ## Type ID of RREQ message.
    # This type ID value is being set in Messages.pack_message function, depending on L3 addressing type this
    # message contains. In case of IPv4 - type ID is 2, in case of IPv6 - type ID is 3.
    type = int()

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        ## @var id
        # Unique message ID.
        self.id = randint(0, 1048575)
        ## @var src_ip
        # Source IP address in a string representation form of IPv4 or IPv6 addresses.
        self.src_ip = str()
        ## @var dst_ip
        # Destination IP address in a string representation form of IPv4 or IPv6 addresses.
        self.dst_ip = str()
        ## @var hop_count
        # Current hop count value.
        self.hop_count = 0

    ## Default print method.
    # @param self The object pointer.
    # @return String with "ID: , SRC_IP: , DST_IP: , HOP_COUNT: ".
    def __str__(self):
        out_tuple = (self.id, self.src_ip, self.dst_ip, self.hop_count)
        out_string = "ID: %s, SRC_IP: %s, DST_IP: %s, HOP_COUNT: %s" % out_tuple
        return out_string


## Route Reply service message.
# This service message is used for both IPv4 and IPv6 L3 addressing cases.
class RrepMessage:
    ## Type ID of RREP message.
    # This type ID value is being set in Messages.pack_message function, depending on L3 addressing type this
    # message contains. In case of IPv4 - type ID is 4, in case of IPv6 - type ID is 5.
    type = int()

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        ## @var id
        # Unique message ID.
        self.id = randint(0, 1048575)
        ## @var src_ip
        # Source IP address in a string representation form of IPv4 or IPv6 addresses.
        self.src_ip = str()
        ## @var dst_ip
        # Destination IP address in a string representation form of IPv4 or IPv6 addresses.
        self.dst_ip = str()
        ## @var hop_count
        # Current hop count value.
        self.hop_count = 0

    ## Default print method.
    # @param self The object pointer.
    # @return String with "TYPE: ,ID: , SRC_IP: , DST_IP: , HOP_COUNT: ".
    def __str__(self):
        out_tuple = (self.type, self.id, self.src_ip, self.dst_ip, self.hop_count)
        out_string = "TYPE: %s, ID: %s, SRC_IP: %s, DST_IP: %s, HOP_COUNT: %s" % out_tuple
        return out_string


## Hello service message.
class HelloMessage:
    ## Type ID of Hello service message.
    type = 6

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        ## @var ipv4_count
        # Amount of unicast IPv4 addresses, assigned to the virtual network interface.
        # There can be only one IPv4 addressed assigned to the network interface, therefore, all possible values of
        # this variable are: 0 - no IPv4 address assigned, 1 - IPv4 address is assigned.
        self.ipv4_count = 0
        ## @var ipv6_count
        # Amount of unicast IPv6 addresses, assigned to the virtual network interface.
        # In the current implementation of Messages.HelloHeader, there could be assigned up to 3 IPv6
        # addresses, which can then be transmitted inside the Hello message.
        # All possible values are:
        # 0 - no IPv6 address assigned.
        # 1 - 1 IPv6 address is assigned.
        # 2 - 2 IPv6 addresses are assigned.
        # 3 - 3 IPv6 addresses are assigned.
        self.ipv6_count = 0
        ## @var ipv4_address
        # IPv4 address in string representation.
        # If no IPv4 address is assigned to the network interface, the variable contains empty string "".
        self.ipv4_address = str()
        ## @var ipv6_addresses
        # List of all assigned IPv6 addresses, in string representation.
        # If no IPv6 addresses are assigned to the network interface, the variable contains empty list [].
        self.ipv6_addresses = list()
        ## @var tx_count
        # Number of message rebroadcast times.
        # Contains a number of times this particular Hello message has been rebroadcasted at the current moment.
        self.tx_count = 0
        ## @var gw_mode
        # Flag which indicates whether the node operates in the gateway mode or not.
        # Possible values:
        # 0 - GW_MODE is Off.
        # 1 - GW_MODE is On.
        self.gw_mode = 0

    ## Default print method.
    # @param self The object pointer.
    # @return String with "TYPE: , IPV4_ADDRESS: , IPV6_ADDRESSES: , TX_COUNT: ".
    def __str__(self):
        out_tuple = (self.type, self.ipv4_address, self.ipv6_addresses, self.tx_count, self.gw_mode)
        out_string = "TYPE: %s, IPV4_ADDRESS: %s, IPV6_ADDRESSES: %s, TX_COUNT: %s, GW_MODE: %s" % out_tuple
        return out_string


## Acknowledgement (ACK) service message.
class AckMessage:
    ## Type ID of ACK service message.
    type = 7

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        ## @var id
        # Unique message ID.
        self.id = randint(0, 1048575)
        ## @var tx_count
        # Number of message retransmission times.
        # Contains a number of times this particular ACK message has been retransmitted at the current moment.
        self.tx_count = 0
        ## @var msg_hash
        # Hash value of the data/service packet this ACK replies to.
        # This hash value is calculated from two attributes of the data/service packet: destination IP of the packet,
        # and the MAC address of a receiving node.
        self.msg_hash = 0

    ## Default print method.
    # @param self The object pointer.
    # @return String with "TYPE: , ID: , TX_COUNT: , MSG_HASH: ".
    def __str__(self):
        out_tuple = (self.type, self.id, self.tx_count, self.msg_hash)
        out_string = "TYPE: %s, ID: %s, TX_COUNT: %s, MSG_HASH: %s" % out_tuple
        return out_string


## Reward service message.
class RewardMessage:
    ## Type ID of reward service message.
    type = 8

    ## Constructor.
    # @param self The object pointer.
    # @param reward_value Assigned reward value.
    # @param msg_hash Hash value of the packet.
    # @return None
    def __init__(self, reward_value, msg_hash):
        ## @var id
        # Unique message ID.
        self.id = randint(0, 1048575)
        ## @var reward_value
        # Assigned reward value.
        # This reward value is calculated and sent back by a node after it has received the packet with a given
        # (destination IP + MAC address) pair.
        self.reward_value = int(ceil(reward_value))
        ## @var msg_hash
        # Hash value of the data packet this Reward message replies to.
        # This hash value is calculated from two attributes of the data/service packet: destination IP of the packet,
        # and the MAC address of a receiving node.
        self.msg_hash = msg_hash

    ## Default print method.
    # @param self The object pointer.
    # @return String with "TYPE: , ID: , REWARD_VALUE: , MSG_HASH: ".
    def __str__(self):
        out_tuple = (self.type, self.id, self.reward_value, self.msg_hash)
        out_string = "TYPE: %s, ID: %s, REWARD_VALUE: %s, MSG_HASH: %s" % out_tuple
        return out_string


## Unicast data packet, transmitted using ARQ module.
# This is a message for unicast data packets, which are enabled to be sent with the ARQ.
class ReliableDataPacket:
    ## Type ID of ARQ-based Unicast Data Packet.
    type = 9

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        ## @var id
        # Unique packet ID.
        # Max value is (2**20 - 1), since the id field size is 20 bits.
        self.id = randint(0, 1048575)
        ## @var hop_count
        # Current hop count value.
        self.hop_count = 0

    ## Default print method.
    # @param self The object pointer.
    # @return String with "TYPE: , ID: , HOP_COUNT: ".
    def __str__(self):
        out_tuple = (self.type, self.id, self.hop_count)
        out_string = "TYPE: %s, ID: %s, HOP_COUNT: %s" % out_tuple
        return out_string


#######################################################################################################################
# ## Describe DSR headers which will pack the initial message object and return a binary string ## #
## Unicast header.
class UnicastHeader:
    ## Unicast data header structure.
    # This sub-class describes a header structure for unicast data packet.
    # Fields structure:
    # TYPE: 4 bits, ID: 20 bits, HOP_COUNT: 8 bits. Total length: 32 bits.
    class Header(ctypes.LittleEndianStructure):
        _fields_ = [
            ("TYPE", ctypes.c_uint32, 4),
            ("ID", ctypes.c_uint32, 20),
            ("HOP_COUNT", ctypes.c_uint32, 8)
        ]

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        pass

    ## Pack the message object into the given structure.
    # @param self The object pointer.
    # @param unicast_message The Messages.UnicastPacket object.
    # @return A header binary string in hex representation.
    def pack(self, unicast_message):
        header = self.Header(unicast_message.type, unicast_message.id, unicast_message.hop_count)
        # Return the array in byte representation
        return bytearray(header)

    ## Unpack the message object from the binary string.
    # @param self The object pointer.
    # @param binary_header Binary string with the Header structure.
    # @return (message object, created from the binary string), (length of the unpacked header structure)
    def unpack(self, binary_header):
        # Cast the byte_array into the structure
        header_unpacked = self.Header.from_buffer_copy(binary_header)
        # Get values and create message object and fill up the fields
        message = UnicastPacket()
        message.id = header_unpacked.ID
        message.hop_count = header_unpacked.HOP_COUNT
        # Return the message
        return message, len(bytearray(header_unpacked))


## Broadcast header.
class BroadcastHeader:
    ## Broadcast data header structure.
    # This sub-class describes a header structure for broadcast data packet.
    # Fields structure:
    # TYPE: 4 bits, ID: 20 bits, BROADCAST_TTL: 8 bits. Total length: 32 bits.
    class Header(ctypes.LittleEndianStructure):
        _fields_ = [
            ("TYPE", ctypes.c_uint32, 4),
            ("ID", ctypes.c_uint32, 20),
            ("BROADCAST_TTL", ctypes.c_uint32, 8)
        ]

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        pass

    ## Pack the message object into the given structure.
    # @param self The object pointer.
    # @param broadcast_message The Messages.BroadcastPacket object.
    # @return A header binary string in hex representation.
    def pack(self, broadcast_message):
        header = self.Header(broadcast_message.type, broadcast_message.id, broadcast_message.broadcast_ttl)
        # Return the array in byte representation
        return bytearray(header)

    ## Unpack the message object from the binary string.
    # @param self The object pointer.
    # @param binary_header Binary string with the Header structure.
    # @return (message object, created from the binary string), (length of the unpacked header structure)
    def unpack(self, binary_header):
        # Cast the byte_array into the structure
        header_unpacked = self.Header.from_buffer_copy(binary_header)
        # Get values and create message object and fill up the fields
        message = BroadcastPacket()
        message.id = header_unpacked.ID
        message.broadcast_ttl = header_unpacked.BROADCAST_TTL
        # Return the message
        return message, len(bytearray(header_unpacked))


## RREQ4 header.
class Rreq4Header:
    ## RREQ4 header structure.
    # This sub-class describes a header structure for RREQ4 service message.
    # Fields structure:
    # TYPE: 4 bits, ID: 20 bits, HOP_COUNT: 8 bits, SRC_IP: 32 bits, DST_IP: 32 bits. Total length: 96 bits.
    class Header(ctypes.LittleEndianStructure):
        _fields_ = [
            ("TYPE", ctypes.c_uint32, 4),
            ("ID", ctypes.c_uint32, 20),
            ("HOP_COUNT", ctypes.c_uint32, 8),
            ("SRC_IP", ctypes.c_uint32, 32),
            ("DST_IP", ctypes.c_uint32, 32)
        ]

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        pass

    ## Pack the message object into the given structure.
    # @param self The object pointer.
    # @param rreq4_message The Messages.RreqMessage object.
    # @return A header binary string in hex representation.
    def pack(self, rreq4_message):
        # Turn string representations of IP addresses into an integer form
        src_ip = struct.unpack("!I", inet_aton(rreq4_message.src_ip))[0]
        dst_ip = struct.unpack("!I", inet_aton(rreq4_message.dst_ip))[0]
        header = self.Header(rreq4_message.type, rreq4_message.id, rreq4_message.hop_count, src_ip, dst_ip)
        # Return the array in byte representation
        return bytearray(header)

    ## Unpack the message object from the binary string.
    # @param self The object pointer.
    # @param binary_header Binary string with the Header structure.
    # @return (message object, created from the binary string), (length of the unpacked header structure)
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


## RREQ6 header.
class Rreq6Header:
    ## RREQ6 header structure.
    # This sub-class describes a header structure for RREQ6 service message.
    # Fields structure:
    # TYPE: 4 bits, ID: 20 bits, HOP_COUNT: 8 bits, SRC_IP1: 32 bits, SRC_IP2: 32 bits, SRC_IP3: 32 bits,
    # SRC_IP4: 32 bits, DST_IP1: 32 bits, DST_IP2: 32 bits, DST_IP3: 32 bits, DST_IP4: 32 bits. Total length: 288 bits.
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

    ## 64-bit mask constant.
    max_int64 = 0xFFFFFFFFFFFFFFFF
    ## 32-bit mask constant.
    max_int32 = 0xFFFFFFFF

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        pass

    ## Pack the message object into the given structure.
    # @param self The object pointer.
    # @param rreq6_message The Messages.RreqMessage object.
    # @return A header binary string in hex representation.
    def pack(self, rreq6_message):
        # Turn string representations of IP addresses into an integer form
        src_ip = int(binascii.hexlify(inet_pton(AF_INET6, rreq6_message.src_ip)), 16)
        # Check the destination IP if it is default address or not.
        # If yes, then change it to the corresponding IPv6 value.
        if rreq6_message.dst_ip == DEFAULT_ROUTE:
            rreq6_message.dst_ip = DEFAULT_IPV6

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

    ## Unpack the message object from the binary string.
    # @param self The object pointer.
    # @param binary_header Binary string with the Header structure.
    # @return (message object, created from the binary string), (length of the unpacked header structure)
    def unpack(self, binary_header):
        # Cast the byte_array into the structure
        header_unpacked = self.Header.from_buffer_copy(binary_header)
        # Get values and create message object and fill up the fields
        message = RreqMessage()
        message.type = header_unpacked.TYPE
        message.id = header_unpacked.ID
        message.hop_count = header_unpacked.HOP_COUNT
        # # Merge the parts of 128-bit IPv6 address together
        # src_ip_left_64 = (header_unpacked.SRC_IP1 << 32 | header_unpacked.SRC_IP2)
        # src_ip_right_64 = (header_unpacked.SRC_IP3 << 32 | header_unpacked.SRC_IP4)
        # dst_ip_left_64 = (header_unpacked.DST_IP1 << 32 | header_unpacked.DST_IP2)
        # dst_ip_right_64 = (header_unpacked.DST_IP3 << 32 | header_unpacked.DST_IP4)
        #
        # src_ip_packed_value = struct.pack(b"!QQ", src_ip_left_64, src_ip_right_64)
        # dst_ip_packed_value = struct.pack(b"!QQ", dst_ip_left_64, dst_ip_right_64)
        #
        # message.src_ip = inet_ntop(AF_INET6, src_ip_packed_value)
        # message.dst_ip = inet_ntop(AF_INET6, dst_ip_packed_value)

        # Set an empty string and avoid AF_INET6 ntop() processing, which is not available on Android.
        # This message will then be filtered out by IncomingTrafficHandler thread.
        message.src_ip = ""
        message.dst_ip = ""

        # # Check the destination IP if it is the default IPv6 value.
        # # If yes, then change it back to the value of the DEFAULT_ROUTE
        # if message.dst_ip == DEFAULT_IPV6:
        #     message.dst_ip = DEFAULT_ROUTE

        # Return the message
        return message, len(bytearray(header_unpacked))


## RREP4 header.
class Rrep4Header:
    ## RREP4 header structure.
    # This sub-class describes a header structure for RREP4 service message.
    # Fields structure:
    # TYPE: 4 bits, ID: 20 bits, HOP_COUNT: 8 bits, SRC_IP: 32 bits, DST_IP: 32 bits. Total length: 96 bits.
    class Header(ctypes.LittleEndianStructure):
        _fields_ = [
            ("TYPE", ctypes.c_uint32, 4),
            ("ID", ctypes.c_uint32, 20),
            ("HOP_COUNT", ctypes.c_uint32, 8),
            ("SRC_IP", ctypes.c_uint32, 32),
            ("DST_IP", ctypes.c_uint32, 32)
        ]

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        pass

    ## Pack the message object into the given structure.
    # @param self The object pointer.
    # @param rrep4_message The Messages.RrepMessage object.
    # @return A header binary string in hex representation.
    def pack(self, rrep4_message):
        # Turn string representations of IP addresses into an integer form
        src_ip = struct.unpack("!I", inet_aton(rrep4_message.src_ip))[0]
        dst_ip = struct.unpack("!I", inet_aton(rrep4_message.dst_ip))[0]
        header = self.Header(rrep4_message.type, rrep4_message.id, rrep4_message.hop_count, src_ip, dst_ip)
        # Return the array in byte representation
        return bytearray(header)

    ## Unpack the message object from the binary string.
    # @param self The object pointer.
    # @param binary_header Binary string with the Header structure.
    # @return (message object, created from the binary string), (length of the unpacked header structure)
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


## RREP6 header.
class Rrep6Header:
    ## RREP6 header structure.
    # This sub-class describes a header structure for RREP6 service message.
    # Fields structure:
    # TYPE: 4 bits, ID: 20 bits, HOP_COUNT: 8 bits, SRC_IP1: 32 bits, SRC_IP2: 32 bits, SRC_IP3: 32 bits,
    # SRC_IP4: 32 bits, DST_IP1: 32 bits, DST_IP2: 32 bits, DST_IP3: 32 bits, DST_IP4: 32 bits. Total length: 288 bits.
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

    ## 64-bit mask constant.
    max_int64 = 0xFFFFFFFFFFFFFFFF
    ## 32-bit mask constant.
    max_int32 = 0xFFFFFFFF

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        pass

    ## Pack the message object into the given structure.
    # @param self The object pointer.
    # @param rrep6_message The Messages.RrepMessage object.
    # @return A header binary string in hex representation.
    def pack(self, rrep6_message):
        # Turn string representations of IP addresses into an integer form
        # Check the source IP if it is default address or not.
        # If yes, then change it to the corresponding IPv6 value.
        if rrep6_message.src_ip == DEFAULT_ROUTE:
            rrep6_message.src_ip = DEFAULT_IPV6

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

    ## Unpack the message object from the binary string.
    # @param self The object pointer.
    # @param binary_header Binary string with the Header structure.
    # @return (message object, created from the binary string), (length of the unpacked header structure)
    def unpack(self, binary_header):
        # Cast the byte_array into the structure
        header_unpacked = self.Header.from_buffer_copy(binary_header)
        # Get values and create message object and fill up the fields
        message = RrepMessage()
        message.type = header_unpacked.TYPE
        message.id = header_unpacked.ID
        message.hop_count = header_unpacked.HOP_COUNT
        # # Merge the parts of 128-bit IPv6 address together
        # src_ip_left_64 = (header_unpacked.SRC_IP1 << 32 | header_unpacked.SRC_IP2)
        # src_ip_right_64 = (header_unpacked.SRC_IP3 << 32 | header_unpacked.SRC_IP4)
        # dst_ip_left_64 = (header_unpacked.DST_IP1 << 32 | header_unpacked.DST_IP2)
        # dst_ip_right_64 = (header_unpacked.DST_IP3 << 32 | header_unpacked.DST_IP4)
        #
        # src_ip_packed_value = struct.pack(b"!QQ", src_ip_left_64, src_ip_right_64)
        # dst_ip_packed_value = struct.pack(b"!QQ", dst_ip_left_64, dst_ip_right_64)
        #
        # message.src_ip = inet_ntop(AF_INET6, src_ip_packed_value)
        # message.dst_ip = inet_ntop(AF_INET6, dst_ip_packed_value)

        # Set an empty string and avoid AF_INET6 ntop() processing, which is not available on Android.
        # This message will then be filtered out by IncomingTrafficHandler thread.
        message.src_ip = ""
        message.dst_ip = ""

        # # Check the source IP if it is the default IPv6 value.
        # # If yes, then change it back to the value of the DEFAULT_ROUTE
        # if message.src_ip == DEFAULT_IPV6:
        #     message.src_ip = DEFAULT_ROUTE

        # Return the message
        return message, len(bytearray(header_unpacked))


## Hello message header.
class HelloHeader:
    ## Hello message fixed fields structure.
    # This structure defines fixed (constant) fields of the Hello header.
    # Fields structure:
    # TYPE: 4 bits, IPV4_COUNT: 1 bit, IPV6_COUNT: 2 bits, TX_COUNT: 25 bits. Total length: 32 bits.
    class FixedHeader(ctypes.LittleEndianStructure):
        _fields_ = [("TYPE", ctypes.c_uint32, 4),
                    ("IPV4_COUNT", ctypes.c_uint32, 1),
                    ("IPV6_COUNT", ctypes.c_uint32, 2),
                    ("TX_COUNT", ctypes.c_uint32, 24),
                    ("GW_MODE", ctypes.c_uint32, 1)
                    ]

    ## Hello message header structure if only IPv4 address is present.
    # Fields structure:
    # TYPE: 4 bits, IPV4_COUNT: 1 bit, IPV6_COUNT: 2 bits, TX_COUNT: 25 bits, IPV4_ADDRESS: 32 bits.
    # Total length: 64 bits.
    class OnlyIpv4Header(ctypes.LittleEndianStructure):
        _fields_ = [("TYPE", ctypes.c_uint32, 4),
                    ("IPV4_COUNT", ctypes.c_uint32, 1),
                    ("IPV6_COUNT", ctypes.c_uint32, 2),
                    ("TX_COUNT", ctypes.c_uint32, 24),
                    ("GW_MODE", ctypes.c_uint32, 1),
                    ("IPV4_ADDRESS", ctypes.c_uint32, 32)
                    ]

    ## 64-bit mask constant.
    max_int64 = 0xFFFFFFFFFFFFFFFF
    ## 32-bit mask constant.
    max_int32 = 0xFFFFFFFF

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        pass

    ## Pack the message object into the given structure.
    # @param self The object pointer.
    # @param hello_message The Messages.HelloMessage object.
    # @return A header binary string in hex representation.
    def pack(self, hello_message):
        args = [hello_message.type, hello_message.ipv4_count, hello_message.ipv6_count,
                hello_message.tx_count, hello_message.gw_mode]
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

    ## Unpack the message object from the binary string.
    # @param self The object pointer.
    # @param binary_header Binary string with the Hello Header structure.
    # @return (message object, created from the binary string), (length of the unpacked header structure)
    def unpack(self, binary_header):
        # Get the first fixed part of the header
        fixed_header_unpacked = self.FixedHeader.from_buffer_copy(binary_header)
        # Create and write to a message object
        message = HelloMessage()

        # Generate the rest of the part. Ignore IPV6_COUNT flag and skip all IPv6 addresses,
        # since Android has no AD_INET6 ntop() function for IPv6.
        if fixed_header_unpacked.IPV4_COUNT and fixed_header_unpacked.IPV6_COUNT == 0:
            header_unpacked = self.OnlyIpv4Header.from_buffer_copy(binary_header)
            message.ipv4_address = inet_ntoa(struct.pack("!I", header_unpacked.IPV4_ADDRESS))

        # Else, create a message without ip addresses
        else:
            message.tx_count = fixed_header_unpacked.TX_COUNT
            message.gw_mode = fixed_header_unpacked.GW_MODE
            message.ipv4_count = fixed_header_unpacked.IPV4_COUNT
            message.ipv6_count = 0
            # Return the message
            return message, len(bytearray(fixed_header_unpacked))

        message.ipv4_count = header_unpacked.IPV4_COUNT
        message.ipv6_count = 0
        message.tx_count = header_unpacked.TX_COUNT
        message.gw_mode = header_unpacked.GW_MODE

        # Return the message
        return message, len(bytearray(header_unpacked))


## ACK header.
class AckHeader:
    ## ACK header structure.
    # This sub-class describes a header structure for ACK message.
    # Fields structure:
    # TYPE: 4 bits, ID: 20 bits, TX_COUNT: 8 bits, MSG_HASH: 32 bits. Total length: 64 bits.
    class Header(ctypes.LittleEndianStructure):
        _fields_ = [
            ("TYPE", ctypes.c_uint32, 4),
            ("ID", ctypes.c_uint32, 20),
            ("TX_COUNT", ctypes.c_uint32, 8),
            ("MSG_HASH", ctypes.c_uint32, 32)
        ]

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        pass

    ## Pack the message object into the given structure.
    # @param self The object pointer.
    # @param ack_message The Messages.AckMessage object.
    # @return A header binary string in hex representation.
    def pack(self, ack_message):
        header = self.Header(ack_message.type, ack_message.id, ack_message.tx_count, ack_message.msg_hash)
        # Return the array in byte representation
        return bytearray(header)

    ## Unpack the message object from the binary string.
    # @param self The object pointer.
    # @param binary_header Binary string with the Header structure.
    # @return (message object, created from the binary string), (length of the unpacked header structure)
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


## Reward header.
class RewardHeader:
    ## Reward header structure.
    # This sub-class describes a header structure for Reward message.
    # Fields structure:
    # TYPE: 4 bits, ID: 20 bits, NEG_REWARD_FLAG: 1 bit, REWARD_VALUE: 7 bits, MSG_HASH: 32 bits.
    # Total length: 64 bits.
    class Header(ctypes.LittleEndianStructure):
        _fields_ = [
            ("TYPE", ctypes.c_uint32, 4),
            ("ID", ctypes.c_uint32, 20),
            ("NEG_REWARD_FLAG", ctypes.c_uint32, 1),
            ("REWARD_VALUE", ctypes.c_uint32, 7),
            ("MSG_HASH", ctypes.c_uint32, 32)
        ]

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        pass

    ## Pack the message object into the given structure.
    # @param self The object pointer.
    # @param reward_message The Messages.RewardMessage object.
    # @return A header binary string in hex representation.
    def pack(self, reward_message):
        if reward_message.reward_value < 0:
            header = self.Header(reward_message.type, reward_message.id, 1,
                                 abs(reward_message.reward_value), reward_message.msg_hash)
        else:
            header = self.Header(reward_message.type, reward_message.id, 0,
                                 reward_message.reward_value, reward_message.msg_hash)
        # Return the byte array
        return bytearray(header)

    ## Unpack the message object from the binary string.
    # @param self The object pointer.
    # @param binary_header Binary string with the Header structure.
    # @return (message object, created from the binary string), (length of the unpacked header structure)
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


## Reliable Unicast Data Header.
class ReliableDataHeader:
    ## Reward header structure.
    # This sub-class describes a header structure for reliable data message.
    # Fields structure:
    # TYPE: 4 bits, ID: 20 bits, HOP_COUNT: 8 bits. Total length: 32 bits.
    class Header(ctypes.LittleEndianStructure):
        _fields_ = [
            ("TYPE", ctypes.c_uint32, 4),
            ("ID", ctypes.c_uint32, 20),
            ("HOP_COUNT", ctypes.c_uint32, 8)
        ]

    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        pass

    ## Pack the message object into the given structure.
    # @param self The object pointer.
    # @param reliable_data_packet The Messages.ReliableDataPacket object.
    # @return A header binary string in hex representation.
    def pack(self, reliable_data_packet):
        header = self.Header(reliable_data_packet.type, reliable_data_packet.id, reliable_data_packet.hop_count)
        # Return the array in byte representation
        return bytearray(header)

    ## Unpack the message object from the binary string.
    # @param self The object pointer.
    # @param binary_header Binary string with the Header structure.
    # @return (message object, created from the binary string), (length of the unpacked header structure)
    def unpack(self, binary_header):
        # Cast the byte_array into the structure
        header_unpacked = self.Header.from_buffer_copy(binary_header)
        # Get values and create message object and fill up the fields
        message = ReliableDataPacket()
        message.id = header_unpacked.ID
        message.hop_count = header_unpacked.HOP_COUNT
        # Return the message
        return message, len(bytearray(header_unpacked))
