
'''
Created on Feb 27, 2015

@author: dmitry
'''

'''
from construct import *
ip = Struct("ip_header",
    EmbeddedBitStruct(
        Const(Nibble("version"), 4),
        Nibble("header_length"),
    ),
    BitStruct("tos",
        Bits("dscp", 6),
        Bits("ecn", 2),
    ),
    UBInt16("total_length"),
    UBInt16("identification"),
    BitStruct("flags",
        Bits("flags", 3),
        Bits("fragment_offset", 13),
    ),
    BitStruct("ttl",
        Bits("ttl", 8),
        Bits("protocol", 8),
    ),
    UBInt16("header_checksum"),
    UBInt32("source_ip"),
    UBInt32("destination_ip"),
 )

icmp = Struct("icmp_header",
    UBInt8("type"),
    UBInt8("code"),
    UBInt16("checksum"),
    UBInt32("rest_of_header"),
 )

###############################
layer4icmp = Struct("layer4",
   Embed(icmp),
   # ... payload
)
 
layer3ip = Struct("layer3",
    Embed(ip),
    Switch("next", lambda ctx: ctx["protocol"],
        {
            "icmp" : layer4icmp,
        }
    ),
)

#tcpip_stack = layer3ip
#pkt = tcpip_stack.parse(repr(raw))
#raw_data = tcpip_stack.build(pkt)
'''

from struct import *
import socket
import pickle

#def ip2int(addr):                                                               
#    return socket.htonl(unpack("!I", socket.inet_aton(addr))[0])                       


def int2ip(addr):                                                               
    return socket.inet_ntoa(pack("!I", addr))

def gen_eth_frame(src_mac, dst_mac, upper_proto):
    src = [int(x, 16) for x in src_mac.split(":")]
    dst = [int(x, 16) for x in dst_mac.split(":")]
    if upper_proto is not "ip":
        print "This upper protocol is not supported!!!"
        return 0
    else:
        proto = [0x08, 0x00]
    return repr(b"".join(map(chr, src + dst + proto)))

f = open("packet_dump", "rb")

raw = f.read(-1)

print repr(raw)
print len(raw)

#icmp = "bbhhhlllllll"
icmp = "bbhl"
ip = "bbHHHBBHII"

print calcsize(ip)
print calcsize(icmp)
#print calcsize(ip + icmp)
#print calcsize(icmp + ip)

print unpack("!"+ip, raw[4:24])
versionihl, dscp, totallength, identification, flagsoffset, ttl, protocol, chksum, sip, dip = unpack("!"+ip, raw[4:24])
print versionihl, dscp, totallength, identification, flagsoffset, ttl, protocol, chksum, int2ip(sip), int2ip(dip)

print unpack(icmp, raw[24:40])

#print len(raw[25:])
#print unpack("!"+icmp, raw[24:24+calcsize("!"+icmp)])

#print unpack(ip + icmp, raw)


ethernet_packet = [0x52, 0x54, 0x00, 0x12, 0x35, 0x02, 0xfe, 0xed, 0xfa,
                         0xce, 0xbe, 0xef, 0x08, 0x00]

#ethernet_packet = []

src_mac = "52:54:00:1d:59:c9"
dst_mac = "52:54:00:ec:17:6e"
prot_type = "ip"

print gen_eth_frame(src_mac, dst_mac, prot_type)




