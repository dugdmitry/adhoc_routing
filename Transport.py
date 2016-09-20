#!/usr/bin/python
"""
Created on Oct 8, 2014

@author: Dmitrii Dugaev
"""

import socket
import threading
import subprocess
import os
from fcntl import ioctl
import struct
import routing_logging

import Messages
from conf import VIRT_IFACE_NAME, SET_TOPOLOGY_FLAG

TRANSPORT_LOG = routing_logging.create_routing_log("routing.transport.log", "transport")


# Syscall ids for managing network interfaces via ioctl
TUNSETIFF = 0x400454ca
IFF_TUN = 0x0001
SIOCSIFADDR = 0x8916
SIOCSIFNETMASK = 0x891C
SIOCSIFMTU = 0x8922
SIOCSIFFLAGS = 0x8914
IFF_UP = 0x1
SIOCGIFINDEX = 0x8933
SIOCGIFADDR = 0x8915

# IDs of supported L3 protocols, going through virtual interface
IP4_ID = 0x0800
IP6_ID = 0x86DD

# Define protocols ID list over IP layer, according to the RFCs:
# https://en.wikipedia.org/wiki/List_of_IP_protocol_numbers
PROTOCOL_IDS = {"ICMP4": 1, "ICMP6": 58, "TCP": 6, "UDP": 17}


# Define a static function which will return a mac address from the given network interface name
def get_mac(interface_name):
    # Return the MAC address of interface
    try:
        string = open('/sys/class/net/%s/address' % interface_name).readline()
    except IOError:
        string = "00:00:00:00:00:00"
    return string[:17]


# Define a static function which will return a list of ip addresses assigned to the virtual interface (in a form of:
# [<ipv4 address>, <ipv6 address1>,  <ipv6 address2>,  <ipv6 addressN>])
def get_l3_addresses_from_interface():
    def get_ipv4_address():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            ipv4_addr = ioctl(s.fileno(), SIOCGIFADDR, struct.pack('256s', VIRT_IFACE_NAME[:15]))[20:24]
        except IOError:
            # No IPv4 address was assigned"
            TRANSPORT_LOG.debug("No IPv4 address assigned!")
            return None

        return socket.inet_ntoa(ipv4_addr)

    def get_ipv6_address():
        ipv6_addresses = list()
        f = open("/proc/net/if_inet6", "r")
        data = f.read().split("\n")[:-1]

        for row in data:
            if row.split(" ")[-1] == VIRT_IFACE_NAME:
                ipv6_addresses.append(row.split(" ")[0])

        if ipv6_addresses:
            output = []
            for ipv6_addr in ipv6_addresses:
                ipv6_addr = ":".join([ipv6_addr[i:i + 4] for i in range(0, len(ipv6_addr), 4)])
                ipv6_addr = socket.inet_pton(socket.AF_INET6, ipv6_addr)
                output.append(socket.inet_ntop(socket.AF_INET6, ipv6_addr))
            return output
        else:
            # No IPv6 addresses were assigned"
            TRANSPORT_LOG.debug("No IPv6 address assigned!")

            return [None]

    addresses = list()
    addresses.append(get_ipv4_address())
    for addr in get_ipv6_address():
        addresses.append(addr)

    return filter(None, addresses)


# Define a static function which will return src and dst L3 addresses of the given packet.
# For now, only IPv4 and IPv6 protocols are supported.
def get_l3_addresses_from_packet(packet):
    def get_data_from_ipv4_header(ipv4_packet):
        ipv4_format = "bbHHHBBHII"  # IPv4 header mask for parsing from binary data
        data = struct.unpack("!" + ipv4_format, ipv4_packet[4:24])
        src_ip = int2ipv4(data[-2])
        dst_ip = int2ipv4(data[-1])

        TRANSPORT_LOG.debug("SRC and DST IPs got from the packet: %s, %s", src_ip, dst_ip)

        return [src_ip, dst_ip]

    def get_data_from_ipv6_header(ipv6_packet):
        ipv6_format = "IHBB16s16s"  # IPv6 header mask for parsing from binary data

        data = struct.unpack("!" + ipv6_format, ipv6_packet[4:44])  # 40 bytes is the ipv6 header size

        src_ip = int2ipv6(data[-2])
        dst_ip = int2ipv6(data[-1])

        TRANSPORT_LOG.debug("SRC and DST IPs got from the packet: %s, %s", src_ip, dst_ip)

        return [src_ip, dst_ip]

    def int2ipv4(addr):
        return socket.inet_ntoa(struct.pack("!I", addr))

    def int2ipv6(addr):
        return socket.inet_ntop(socket.AF_INET6, addr)

    # Get L3 protocol identifier. This is the L3 ID which is being prepended to every packet,
    # sent to virtual tun interface (packet information flag, IFF_NO_PI set to False, by default).
    # For more info, see: https://www.kernel.org/doc/Documentation/networking/tuntap.txt
    l3_id = struct.unpack("!H", packet[2:4])[0]

    if l3_id == int(IP4_ID):
        addresses = get_data_from_ipv4_header(packet)
        return addresses[0], addresses[1], packet

    elif l3_id == int(IP6_ID):
        addresses = get_data_from_ipv6_header(packet)
        return addresses[0], addresses[1], packet

    # If the ID is 0, it means that the packet has been sent back to tun interface again, using raw socket.
    # So, the tun driver set the ID to 0, since it was the pure raw data, sent via raw socket.
    elif l3_id == 0:
        # So, remove the first 4 bytes and get the L3 addresses again,
        return get_l3_addresses_from_packet(packet[4:])

    else:
        # The packet has UNSUPPORTED L3 protocol, drop it
        TRANSPORT_LOG.error("The packet has UNSUPPORTED L3 protocol, dropping the packet")
        return None


# Define a static function which will return upper protocol ID and port number (if any) of the given packet.
# For now, only IPv4 and IPv6 protocols are supported on L3 layer, and UDP, TCP and ICMP on the upper level.
def get_upper_proto_info(packet):
    def get_proto_id_from_ipv4(ipv4_packet):
        return struct.unpack("!B", ipv4_packet[13])[0]

    def get_proto_id_from_ipv6(ipv6_packet):
        return struct.unpack("!B", ipv6_packet[10])[0]

    # Gets "upper_data" - a sliced packet without L3 header - outputs a destination port number of UDP
    def get_port_from_udp(udp_upper_data):
        return struct.unpack("!H", udp_upper_data[2:4])[0]

    # Gets "upper_data" - a sliced packet without L3 header - outputs a destination port number of TCP
    def get_port_from_tcp(tcp_upper_data):
        return struct.unpack("!H", tcp_upper_data[2:4])[0]

    # Get L3 protocol identifier. This is the L3 ID which is being prepended to every packet,
    # sent to virtual tun interface (packet information flag, IFF_NO_PI set to False, by default).
    # For more info, see: https://www.kernel.org/doc/Documentation/networking/tuntap.txt
    l3_id = struct.unpack("!H", packet[2:4])[0]

    if l3_id == int(IP4_ID):
        proto_id = int(get_proto_id_from_ipv4(packet))

        if proto_id == PROTOCOL_IDS["UDP"]:
            # Get the IHL value in order to slice the packet from the IPv4 header
            ihl = int(struct.unpack("!B", packet[4])[0]) & 0xf
            upper_data = packet[4 + ihl * 4:]
            return "UDP", int(get_port_from_udp(upper_data))

        elif proto_id == PROTOCOL_IDS["TCP"]:
            # Get the IHL value in order to slice the packet from the IPv4 header
            ihl = int(struct.unpack("!B", packet[4])[0]) & 0xf
            upper_data = packet[4 + ihl * 4:]
            return "TCP", int(get_port_from_tcp(upper_data))

        elif proto_id == PROTOCOL_IDS["ICMP4"]:
            # Return 0 as port number
            return "ICMP4", 0

        else:
            # Unknown protocol id, return 0 as port number
            TRANSPORT_LOG.warning("Unknown upper protocol id: %s", proto_id)
            return "UNKNOWN", 0

    elif l3_id == int(IP6_ID):
        proto_id = int(get_proto_id_from_ipv6(packet))

        if proto_id == PROTOCOL_IDS["UDP"]:
            # IHL value in IPv6 is fixed and equal to 40 octets (10 x 32-bit words)
            ihl = 10
            upper_data = packet[4 + ihl * 4:]
            return "UDP", int(get_port_from_udp(upper_data))

        elif proto_id == PROTOCOL_IDS["TCP"]:
            # IHL value in IPv6 is fixed and equal to 40 octets (10 x 32-bit words)
            ihl = 10
            upper_data = packet[4 + ihl * 4:]
            return "TCP", int(get_port_from_tcp(upper_data))

        elif proto_id == PROTOCOL_IDS["ICMP6"]:
            # Return 0 as port number
            return "ICMP6", 0

        else:
            # Unknown protocol id, return 0 as port number
            TRANSPORT_LOG.warning("Unknown upper protocol id: %s", proto_id)
            return "UNKNOWN", 0

    # If the ID is 0, it means that the packet has been sent back to tun interface again, using raw socket.
    # So, the tun driver set the ID to 0, since it was the pure raw data, sent via raw socket.
    # # This code should never be executed, since the function is called always after the packet has been checked.
    elif l3_id == 0:
        # So, remove the first 4 bytes and get the L3 addresses again,
        return get_upper_proto_info(packet[4:])

    else:
        # The packet has UNSUPPORTED L3 protocol, drop it.
        # This code should never be executed, since the function is called always after the packet has been checked
        TRANSPORT_LOG.error("The packet has UNSUPPORTED L3 protocol, dropping the packet")
        return None


class UdsClient:
    def __init__(self, server_address):
        self.server_address = server_address
        # Create a UDS socket
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        
    def send(self, message):
        self.sock.sendto(message, self.server_address)


# UdsServer needed for updating interface parameters in real time by receiving commands via UDS
class UdsServer(threading.Thread):
    def __init__(self, server_address):
        super(UdsServer, self).__init__()
        self.running = True
        self.server_address = server_address
        # Create file descriptor for forwarding all the output to /dev/null from subprocess calls
        self.FNULL = open(os.devnull, "w")
        # Delete the previous uds_socket if it still exists on this address.
        subprocess.call("rm %s" % self.server_address, shell=True, stdout=self.FNULL, stderr=subprocess.STDOUT)
        TRANSPORT_LOG.info("Deleted: %s", self.server_address)

        # Create a UDS socket
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(self.server_address)
        self.iface = VIRT_IFACE_NAME
        
    def run(self):
        while self.running:
            data = self.sock.recvfrom(4096)[0]
            _id, addr = data.split("-")
            if _id == "ipv4":
                self.set_ip_addr4(addr)

            elif _id == "ipv6":
                self.set_ip_addr6(addr)
                
            else:
                TRANSPORT_LOG.error("Unsupported command via UDS! This should never happen!")

    def set_ip_addr4(self, ip4):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        bin_ip = socket.inet_aton(ip4)
        ifreq = struct.pack('16sH2s4s8s', self.iface, socket.AF_INET, '\x00'*2, bin_ip, '\x00'*8)
        ioctl(sock, SIOCSIFADDR, ifreq)
        # Setting the netmask. FIXED FOR NOW !!!
        bin_mask = socket.inet_aton("255.255.255.0")
        ifreq = struct.pack('16sH2s4s8s', self.iface, socket.AF_INET, '\x00'*2, bin_mask, '\x00'*8)
        ioctl(sock, SIOCSIFNETMASK, ifreq)

    def set_ip_addr6(self, ip6):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        bin_ipv6 = socket.inet_pton(socket.AF_INET6, ip6)
        ifreq = struct.pack('16si', self.iface, 0)
        ifreq = ioctl(sock, SIOCGIFINDEX, ifreq)
        if_index = struct.unpack("i", ifreq[16: 16 + 4])[0]
        ifreq = struct.pack('16sii', bin_ipv6, 64, if_index)
        ioctl(sock, SIOCSIFADDR, ifreq)
        
    def quit(self):
        self.running = False
        self.sock.close()
        # Removing the uds socket
        subprocess.call("rm %s" % self.server_address, shell=True, stdout=self.FNULL, stderr=subprocess.STDOUT)


# Class for virtual interface
class VirtualTransport:
    def __init__(self):
        # Creating virtual tun interface.
        # See the documentation: https://www.kernel.org/doc/Documentation/networking/tuntap.txt
        tun_mode = IFF_TUN
        f = os.open("/dev/net/tun", os.O_RDWR)
        ioctl(f, TUNSETIFF, struct.pack("16sH", VIRT_IFACE_NAME, tun_mode))

        self.set_mtu(VIRT_IFACE_NAME, 1400)      # !!! MTU value is fixed for now. !!!
        self.interface_up(VIRT_IFACE_NAME)
        
        self.f = f

        # Create raw socket for sending the packets back to the interface
        self.virtual_socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
        self.virtual_socket.bind((VIRT_IFACE_NAME, 0))

    def set_mtu(self, iface, mtu):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ifreq = struct.pack('16sI', iface, int(mtu))
        ioctl(sock, SIOCSIFMTU, ifreq)
        
    # Up the interface
    def interface_up(self, iface):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ifreq = struct.pack('16sH', iface, IFF_UP)
        ioctl(sock, SIOCSIFFLAGS, ifreq)

    def send_to_app(self, packet):
        os.write(self.f, packet)

    # Provides interface for sending back the packets to initial virtual interface
    def send_to_interface(self, packet):
        self.virtual_socket.send(packet)

    # Receive raw data from virtual interface. Return a list in a form: [src_ip, dst_ip, raw_data]
    def recv_from_app(self):
        output = os.read(self.f, 65000)
        return output


# Class for interacting with raw sockets
class RawTransport:
    def __init__(self, dev, node_mac, topology_neighbors):
        self.send_socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)

        # Type 0x7777 corresponds to the chosen "protocol_type" in our custom ethernet frame
        # In this way, the socket can only receive packets with 0x7777 protocol type
        self.send_socket.bind((dev, 0x7777))
        self.proto = [0x77, 0x77]
                                                        
        self.node_mac = node_mac
        self.broadcast_mac = "ff:ff:ff:ff:ff:ff"

        self.topology_neighbors = topology_neighbors
        self.running = True

        # For receiving handlers
        self.recv_socket = self.send_socket

        # Define which self.recv_data method will be used, depending on the SET_TOPOLOGY_FLAG flag value
        if SET_TOPOLOGY_FLAG:
            self.recv_data = self.recv_data_with_filter
        else:
            self.recv_data = self.recv_data_no_filter

    # Receive and return dsr_header and upper layer data from the interface
    def recv_data(self):
        """
        This method listens for any incoming raw frames from the interface, and outputs the list containing a
        dsr_header and the upper_raw_data of the frame received
        """
        pass

    def send_raw_frame(self, dst_mac, dsr_message, payload):
        eth_header = self.gen_eth_header(self.node_mac, dst_mac)

        # Pack the initial dsr_message object and get the dsr_binary_header from it
        dsr_bin_header = Messages.pack_message(dsr_message)

        self.send_socket.send(eth_header + dsr_bin_header + payload)

    def gen_eth_header(self, src_mac, dst_mac):
        src = [int(x, 16) for x in src_mac.split(":")]
        dst = [int(x, 16) for x in dst_mac.split(":")]

        return b"".join(map(chr, dst + src + self.proto))

    # Receive and return dsr_header and upper layer data from the interface, filter out the mac addresses,
    # which are not in the self.topology_neighbors list
    def recv_data_with_filter(self):
        while self.running:
            # Receive raw frame from the interface
            data = self.recv_socket.recv(65535)

            # ## Filtering the mac addresses according to the given topology ## #
            # Get a src_mac address from the frame
            src_mac = self.get_src_mac(data[:14])

            # Check if the mac in the list of topology_neighbors. If not - just drop it.
            if src_mac in self.topology_neighbors:
                # Get and return dsr_header object and upper layer raw data
                # Create dsr_header object
                TRANSPORT_LOG.debug("SRC_MAC from the received frame: %s", src_mac)

                # 56 bytes is the maximum possible length of DSR header.
                # Skip first 14 bytes since this is Ethernet header fields.
                dsr_header_obj, dsr_header_length = Messages.unpack_message(data[14: 14 + 56])

                # Get upper raw data
                upper_raw_data = data[(14 + dsr_header_length):]

                return src_mac, dsr_header_obj, upper_raw_data

            elif src_mac == self.node_mac:
                TRANSPORT_LOG.debug("!!! THIS IS MY OWN MAC, YOBBA !!! %s", src_mac)

            # Else, do nothing with the received frame
            else:
                TRANSPORT_LOG.debug("!!! THIS MAC HAS BEEN FILTERED !!! %s", src_mac)

    # Receive and return dsr_header and upper layer data from the interface from ANY mac address without filtering
    def recv_data_no_filter(self):
        while self.running:
            # Receive raw frame from the interface
            data = self.recv_socket.recv(65535)

            # Get a src_mac address from the frame
            src_mac = self.get_src_mac(data[:14])

            if src_mac == self.node_mac:
                # This situation normally is not supposed to happen.
                # Otherwise, it would mean that there are two or more nodes with the same MAC address, which is bad.
                TRANSPORT_LOG.error("!!! THIS IS MY OWN MAC, YOBBA !!! %s", src_mac)

            # Else, return the data
            else:
                # Get and return dsr_header object and upper layer raw data
                # Create dsr_header object
                TRANSPORT_LOG.debug("SRC_MAC from the received frame: %s", src_mac)
                # Skip first 14 bytes since this is Ethernet header fields.
                dsr_header_obj, dsr_header_length = Messages.unpack_message(data[14: 14 + 56])

                # Get upper raw data
                upper_raw_data = data[(14 + dsr_header_length):]

                return src_mac, dsr_header_obj, upper_raw_data

    # Get the src_mac address from the given ethernet header
    def get_src_mac(self, eth_header):
        src_mac = ""
        data = struct.unpack("!6B", eth_header[6:12])

        for i in data:
            byte = str(hex(i))[2:]
            if len(byte) == 1:
                byte = "0" + byte
            src_mac = src_mac + byte + ":"
        
        return src_mac[:-1]
    
    def close_raw_recv_socket(self):
        self.running = False
        self.recv_socket.close()
        TRANSPORT_LOG.info("Raw socket closed")
