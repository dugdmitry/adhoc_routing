#!/usr/bin/python
"""
@package Transport
Created on Oct 8, 2014

@author: Dmitrii Dugaev


The Transport module is responsible for all the actual interaction with network interfaces (both virtual and real),
including frame generation, frame parsing, socket creation/closing/binding/receiving, raw packet processing, frame
filtering as well as providing methods for working with Linux networking stack via system calls.
"""

# Import necessary python modules from the standard library
import socket
import threading
import subprocess
import os
from fcntl import ioctl
import struct

# Import the necessary modules of the program
import routing_logging
import Messages
from conf import VIRT_IFACE_NAME, SET_TOPOLOGY_FLAG, GW_MODE

## @var TRANSPORT_LOG
# Global routing_logging.LogWrapper object for logging Transport activity.
TRANSPORT_LOG = routing_logging.create_routing_log("routing.transport.log", "transport")


# Syscall ids for managing network interfaces via ioctl.
## @var TUNSETIFF
# Set tun interface ID.
TUNSETIFF = 0x400454ca
## @var IFF_TUN
# The tun interface flag.
IFF_TUN = 0x0001
## @var SIOCSIFADDR
# Set the address of the device.
SIOCSIFADDR = 0x8916
## @var SIOCSIFNETMASK
# Set the network mask for a device.
SIOCSIFNETMASK = 0x891C
## @var SIOCSIFMTU
# Set the MTU (Maximum Transfer Unit) of a device.
SIOCSIFMTU = 0x8922
## @var SIOCSIFFLAGS
# Set the active flag word of the device.
SIOCSIFFLAGS = 0x8914
## @var IFF_UP
# Interface is running flag.
IFF_UP = 0x1
## @var SIOCGIFINDEX
# Retrieve the interface index of the interface.
SIOCGIFINDEX = 0x8933
## @var SIOCGIFADDR
# Get the address of the device.
SIOCGIFADDR = 0x8915

# IDs of supported L3 protocols, going through virtual interface.
## @var IP4_ID
# IPv4 protocol ID on the L2 layer.
IP4_ID = 0x0800
## @var IP6_ID
# IPv6 protocol ID on the L2 layer.
IP6_ID = 0x86DD

## @var PROTOCOL_IDS
# Define protocols ID list over IP layer, according to the RFCs:
# https://en.wikipedia.org/wiki/List_of_IP_protocol_numbers.
PROTOCOL_IDS = {"ICMP4": 1, "ICMP6": 58, "TCP": 6, "UDP": 17}


## Get MAC address from the network interface.
# Define a static function which will return a mac address from the given network interface name.
# @param interface_name Name of the network interface.
# @return MAC address in "xx:xx:xx:xx:xx:xx" format.
def get_mac(interface_name):
    # Return the MAC address of interface
    try:
        string = open('/sys/class/net/%s/address' % interface_name).readline()
    except IOError:
        string = "00:00:00:00:00:00"
    return string[:17]


## Get L3 addresses from the network interface.
# Define a static function which will return a list of ip addresses assigned to the virtual interface (in a form of:
# [<ipv4 address>, <ipv6 address1>,  <ipv6 address2>,  <ipv6 addressN>]).
# @return [<ipv4 address>, <ipv6 address1>,  <ipv6 address2>,  <ipv6 addressN>].
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

    # If the GW_MODE flag is on, then append a default "0.0.0.0" IP address to the list.
    # In that way, the other nodes in the network will get a route for the packets with outside destination.
    if GW_MODE:
        addresses.append(Messages.DEFAULT_ROUTE)

    return filter(None, addresses)


## Ger L3 addresses from the data packet.
# Define a static function which will return src and dst L3 addresses of the given packet.
# For now, only IPv4 and IPv6 protocols are supported.
# @param packet Raw data packet received from network interface.
# @return [src_ip, dst_ip].
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


## Get L4 protocol ID and port from the data packet.
# Define a static function which will return upper protocol ID and port number (if any) of the given packet.
# For now, only IPv4 and IPv6 protocols are supported on L3 layer, and UDP, TCP and ICMP on the upper level.
# @param packet Raw data packet received from network interface.
# @return (L4 protocol name), (port number).
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


## Unix Domain Socket (UDS) client class.
# This class will be used for future on-the-fly configuration of the running application instance.
class UdsClient:
    ## Constructor.
    # @param self The object pointer.
    # @param server_address UDS file location.
    # @return None
    def __init__(self, server_address):
        ## @var server_address
        # UDS file location.
        self.server_address = server_address
        ## @var sock
        # Create a UDS socket.
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)

    ## Send message via UDS.
    # @param self The object pointer.
    # @param message Message to be sent.
    # @return None
    def send(self, message):
        self.sock.sendto(message, self.server_address)


## Unix Domain Socket (UDS) server class.
# UdsServer is needed for updating interface parameters in real time by receiving commands via UDS.
class UdsServer(threading.Thread):
    ## Constructor.
    # @param self The object pointer.
    # @param server_address UDS file location.
    # @return None
    def __init__(self, server_address):
        super(UdsServer, self).__init__()
        ## @var running
        # Thread running state bool() flag.
        self.running = False
        ## @var server_address
        # UDS file location.
        self.server_address = server_address
        ## @var FNULL
        # Create file descriptor for forwarding all the output to /dev/null from subprocess calls.
        self.FNULL = open(os.devnull, "w")
        # Delete the previous uds_socket if it still exists on this address.
        subprocess.call("rm %s" % self.server_address, shell=True, stdout=self.FNULL, stderr=subprocess.STDOUT)
        TRANSPORT_LOG.info("Deleted: %s", self.server_address)
        ## @var sock
        # Create a UDS socket.
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(self.server_address)
        ## @var iface
        # Store the name of the virtual interface.
        self.iface = VIRT_IFACE_NAME

    ## Main thread routine.
    # @param self The object pointer.
    # @return None
    def run(self):
        self.running = True
        while self.running:
            data = self.sock.recvfrom(4096)[0]
            _id, addr = data.split("-")
            if _id == "ipv4":
                self.set_ip_addr4(addr)

            elif _id == "ipv6":
                self.set_ip_addr6(addr)
                
            else:
                TRANSPORT_LOG.error("Unsupported command via UDS! This should never happen!")

    ## Set IPv4 address to the virtual interface.
    # @param self The object pointer.
    # @param ip4 IPv4 address in string representation.
    # @return None
    def set_ip_addr4(self, ip4):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        bin_ip = socket.inet_aton(ip4)
        ifreq = struct.pack('16sH2s4s8s', self.iface, socket.AF_INET, '\x00'*2, bin_ip, '\x00'*8)
        ioctl(sock, SIOCSIFADDR, ifreq)
        # Setting the netmask. FIXED FOR NOW !!!
        bin_mask = socket.inet_aton("255.255.255.0")
        ifreq = struct.pack('16sH2s4s8s', self.iface, socket.AF_INET, '\x00'*2, bin_mask, '\x00'*8)
        ioctl(sock, SIOCSIFNETMASK, ifreq)

    ## Set IPv6 address to the virtual interface.
    # @param self The object pointer.
    # @param ip6 IPv6 address in string representation.
    # @return None
    def set_ip_addr6(self, ip6):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        bin_ipv6 = socket.inet_pton(socket.AF_INET6, ip6)
        ifreq = struct.pack('16si', self.iface, 0)
        ifreq = ioctl(sock, SIOCGIFINDEX, ifreq)
        if_index = struct.unpack("i", ifreq[16: 16 + 4])[0]
        ifreq = struct.pack('16sii', bin_ipv6, 64, if_index)
        ioctl(sock, SIOCSIFADDR, ifreq)

    ## Stop and quit the thread operation.
    # @param self The object pointer.
    # @return None
    def quit(self):
        self.running = False
        self.sock.close()
        # Removing the uds socket
        subprocess.call("rm %s" % self.server_address, shell=True, stdout=self.FNULL, stderr=subprocess.STDOUT)


## Class for interaction with virtual network interface.
class VirtualTransport:
    ## Constructor.
    # @param self The object pointer.
    # @return None
    def __init__(self):
        # Creating virtual tun interface.
        # See the documentation: https://www.kernel.org/doc/Documentation/networking/tuntap.txt
        tun_mode = IFF_TUN
        f = os.open("/dev/tun", os.O_RDWR)
        ioctl(f, TUNSETIFF, struct.pack("16sH", VIRT_IFACE_NAME, tun_mode))

        self.set_mtu(VIRT_IFACE_NAME, 1400)      # !!! MTU value is fixed for now. !!!
        self.interface_up(VIRT_IFACE_NAME)

        ## @var f
        # Store a file descriptor to the virtual interface.
        self.f = f
        ## @var virtual_socket
        # Create raw socket for sending the packets back to the interface.
        self.virtual_socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
        self.virtual_socket.bind((VIRT_IFACE_NAME, 0))

    ## Set MTU value.
    # @param self The object pointer.
    # @param iface Name of the virtual interface.
    # @param mtu MTU value.
    # @return None
    def set_mtu(self, iface, mtu):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ifreq = struct.pack('16sI', iface, int(mtu))
        ioctl(sock, SIOCSIFMTU, ifreq)
        
    ## Up the interface.
    # @param self The object pointer.
    # @param iface Name of the virtual interface.
    # @return None
    def interface_up(self, iface):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ifreq = struct.pack('16sH', iface, IFF_UP)
        ioctl(sock, SIOCSIFFLAGS, ifreq)

    ## Send data packet to the application.
    # @param self The object pointer.
    # @param packet Raw packet data.
    # @return None
    def send_to_app(self, packet):
        os.write(self.f, packet)

    ## Send data packet back to the virtual interface.
    # Provides interface for sending back the packets to initial virtual interface.
    # @param self The object pointer.
    # @param packet Raw packet data.
    # @return None
    def send_to_interface(self, packet):
        self.virtual_socket.send(packet)

    ## Receive raw data from virtual interface.
    # @return List in a form: [src_ip, dst_ip, raw_data].
    def recv_from_app(self):
        output = os.read(self.f, 65000)
        return output


## Class for interacting with raw sockets of the real network interface.
class RawTransport:
    ## Constructor.
    # @param self The object pointer.
    # @param dev Name of physical network interface.
    # @param node_mac The node's own MAC address.
    # @param topology_neighbors List of neighbors MAC addresses to be accepted if the filtering is On.
    # @return None
    def __init__(self, dev, node_mac, topology_neighbors):
        ## @var send_socket
        # Create a send raw socket.
        # Type 0x7777 corresponds to the chosen "protocol_type" in our custom ethernet frame.
        # In this way, the socket can only receive packets with 0x7777 protocol type.
        self.send_socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
        self.send_socket.bind((dev, 0x7777))
        ## @var proto
        # Custom protocol ID on L2 layer.
        self.proto = [0x77, 0x77]
        ## @var node_mac
        # The node's own MAC address.
        self.node_mac = node_mac
        ## @var broadcast_mac
        # Default value of the broadcast MAC address.
        self.broadcast_mac = "ff:ff:ff:ff:ff:ff"
        ## @var topology_neighbors
        # List of neighbors MAC addresses to be accepted if the filtering is On.
        self.topology_neighbors = topology_neighbors
        ## @var running
        # Thread running state bool() flag.
        self.running = True
        ## @var recv_socket
        # For receiving incoming raw frames.
        self.recv_socket = self.send_socket
        ## @var recv_data
        # Define which RawTransport.recv_data method will be used, depending on the SET_TOPOLOGY_FLAG flag value.
        if SET_TOPOLOGY_FLAG:
            self.recv_data = self.recv_data_with_filter
        else:
            self.recv_data = self.recv_data_no_filter

    ## Receive and return source mac, dsr_header and upper layer data from the interface.
    # This method listens for any incoming raw frames from the interface, and outputs the list containing a source mac,
    # dsr_header and the upper_raw_data of the frame received.
    # @param self The object pointer.
    # @return [src_mac, dsr_header_obj, upper_raw_data].
    def recv_data(self):
        pass

    ## Send raw frame to the network.
    # @param self The object pointer.
    # @param dst_mac Destination MAC address.
    # @param dsr_message Message object from Messages module.
    # @param payload User/Service payload after the protocol's header.
    # @return None
    def send_raw_frame(self, dst_mac, dsr_message, payload):
        eth_header = self.gen_eth_header(self.node_mac, dst_mac)
        # Pack the initial dsr_message object and get the dsr_binary_header from it
        dsr_bin_header = Messages.pack_message(dsr_message)
        self.send_socket.send(eth_header + dsr_bin_header + payload)

    ## Generate ethernet header.
    # @param self The object pointer.
    # @param src_mac Source MAC address.
    # @param dst_mac Destination MAC address.
    # @return Ethernet header in binary string representation.
    def gen_eth_header(self, src_mac, dst_mac):
        src = [int(x, 16) for x in src_mac.split(":")]
        dst = [int(x, 16) for x in dst_mac.split(":")]
        return b"".join(map(chr, dst + src + self.proto))

    ## Receive frames with filtering.
    # Receive and return source mac, dsr_header and upper layer data from the interface, filter out the mac addresses,
    # which are not in the RawTransport.topology_neighbors list.
    # @param self The object pointer.
    # @return [src_mac, dsr_header_obj, upper_raw_data].
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

    ## Receive all frames without filtering.
    # Receive and return source mac, dsr_header and upper layer data from the interface from ANY mac address without
    # filtering.
    # @param self The object pointer.
    # @return [src_mac, dsr_header_obj, upper_raw_data].
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

    ## Get source MAC address from the given ethernet header.
    # @param self The object pointer.
    # @param eth_header Ethernet header in binary representation.
    # @return MAC address in "xx:xx:xx:xx:xx:xx" format.
    def get_src_mac(self, eth_header):
        src_mac = ""
        data = struct.unpack("!6B", eth_header[6:12])

        for i in data:
            byte = str(hex(i))[2:]
            if len(byte) == 1:
                byte = "0" + byte
            src_mac = src_mac + byte + ":"
        
        return src_mac[:-1]

    ## Stop reading from the receiving socket and close it.
    # @param self The object pointer.
    # @return None
    def close_raw_recv_socket(self):
        self.running = False
        self.recv_socket.close()
        TRANSPORT_LOG.info("Raw socket closed")
