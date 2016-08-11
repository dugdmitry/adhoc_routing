
import logging
from random import randint

# import Transport
import Messages
import ctypes
import binascii


class Resource:
    id_counter = 0

    def __init__(self, type=0):
        self.type = type
        self.id = Resource.id_counter
        Resource.id_counter += 1

    def __str__(self):

        return "GOT YA!!!"


class FooLogger:
    def __init__(self):
        pass

    def create_logger(self):

        logger = logging.getLogger("test")

        if logger.handlers:
            print "YO"

        print logger, type(logger)


c = Resource()
a = Resource()
b = Resource()

# print "qwerty: %s" % str(a)
#
# print a.id
# print b.id
# print c.id
# print c.id_counter
#
# log = FooLogger()
# log.create_logger()
# log.create_logger()
#


# Check binary representation

# rreq6_msg = Messages.Rreq6Message()
# rreq6_msg.src_ip = "fe80::da5d:4cff:fe95:5114"
# rreq6_msg.dst_ip = "fe80::7a20:bd16:551a:9622"
# rreq6_msg.hop_count = 5
#
#
# rreq6_header = Messages.Rreq6Header(rreq6_msg)
#
# bin_header = rreq6_header.pack()
# print bin_header, ",", len(bin_header)

#
# rreq4_msg = Messages.Rreq4Message()
# rreq4_msg.src_ip = "10.10.10.10"
# rreq4_msg.dst_ip = "255.255.255.110"
# rreq4_msg.hop_count = 11
#
# header = Messages.Rreq4Header()
#
# bin_header = header.pack(rreq4_msg)
#
# print bin_header
#
#
# msg = Messages.Rreq4Header().unpack(bin_header)
#
# print msg
#
# #####################
#
# unicast_packet = Messages.UnicastPacket()
# # unicast_packet.id = 1048577
# unicast_packet.hop_count = 0
#
# header = Messages.UnicastHeader()
#
# bin_header = header.pack(unicast_packet)
#
# print bin_header
#
#
# msg = Messages.UnicastHeader().unpack(bin_header)
#
# print msg
#
# #####################
#
# broadcast_packet = Messages.BroadcastPacket()
# # broadcast_packet.id = 1048576
# broadcast_packet.broadcast_ttl = 112
#
# header = Messages.BroadcastHeader()
#
# bin_header = header.pack(broadcast_packet)
#
# print bin_header
#
#
# msg = Messages.BroadcastHeader().unpack(bin_header)
#
# print msg
#
# #####################
#
# rreq6_msg = Messages.Rreq6Message()
# rreq6_msg.src_ip = "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
# rreq6_msg.dst_ip = "fe80::346e:ed29:5340:8c64"
# rreq6_msg.hop_count = 11
#
# header = Messages.Rreq6Header()
#
# bin_header = header.pack(rreq6_msg)
#
# print bin_header
#
#
# msg = Messages.Rreq6Header().unpack(bin_header)
#
# print msg
#
# #####################
#
# hello_msg = Messages.HelloMessage()
# hello_msg.ipv6_count = 3
# hello_msg.ipv4_count = 1
# hello_msg.tx_count = 33554
# hello_msg.ipv4_address = "255.255.255.111"
# hello_msg.ipv6_addresses = ["2001:0db8:85a3:0000:0000:8a2e:0370:7334",
#                             "fe80::346e:ed29:5340:8c64", "3731:54:65fe:2::a7"]
# # rreq6_msg.dst_ip = "fe80::346e:ed29:5340:8c64"
#
# header = Messages.HelloHeader()
#
# bin_header = header.pack(hello_msg)
#
# print bin_header
#
#
# msg = Messages.HelloHeader().unpack(bin_header)
#
# print msg
#
#
# #####################
#
# ack_msg = Messages.AckMessage()
# ack_msg.tx_count = 257
# ack_msg.id = 777
# # ack_msg.msg_hash = hash("asdasasdaqsdasdadadsad") & 0xffffffff
# ack_msg.msg_hash = 4294967295
# # print ack_msg.msg_hash
#
# header = Messages.AckHeader()
#
# bin_header = header.pack(ack_msg)
#
# # print bin_header
#
#
# msg = Messages.AckHeader().unpack(bin_header)
#
# print msg
#
# #####################
#
# reward_msg = Messages.RewardMessage()
# reward_msg.id = 257
# reward_msg.reward_value = -64
# # ack_msg.msg_hash = hash("asdasasdaqsdasdadadsad") & 0xffffffff
# reward_msg.msg_hash = 429496
# # print ack_msg.msg_hash
#
# header = Messages.RewardHeader()
#
# bin_header = header.pack(reward_msg)
#
# # print bin_header
#
#
# msg = Messages.RewardHeader().unpack(bin_header)
#
# print msg
#
#
# def gen_eth_header(src_mac, dst_mac):
#     src = [int(x, 16) for x in src_mac.split(":")]
#     dst = [int(x, 16) for x in dst_mac.split(":")]
#
#     return b"".join(map(chr, dst + src + [0x77, 0x77]))
#
#
# eth_header = gen_eth_header("c4:7d:46:13:9e:88", "52:54:00:3b:55:18")
#
# print eth_header, binascii.hexlify(eth_header), int(binascii.hexlify(eth_header), 16), binascii.a2b_hex(binascii.hexlify(eth_header))
#
# print Messages.RewardHeader().unpack(int(binascii.hexlify(eth_header), 16))


import hashlib

m = hashlib.md5("asdasdasdas")

print int(hashlib.md5("asdasdasdas").hexdigest(), 16)
print int(hashlib.md5("asdasdasdas").hexdigest(), 16) & 0xffffffff

print int(m.hexdigest(), 16)
print int(m.hexdigest(), 16) & 0xffffffff





























