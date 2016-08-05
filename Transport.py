#!/usr/bin/python
"""
Created on Oct 8, 2014

@author: Dmitrii
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
IFF_TUN   = 0x0001
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
                self.setIpAddr4(addr)

            elif _id == "ipv6":
                self.setIpAddr6(addr)
                
            else:
                print "This should never happen."
                TRANSPORT_LOG.warning("This should never happen.")

    def setIpAddr4(self, ip4):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        bin_ip = socket.inet_aton(ip4)
        ifreq = struct.pack('16sH2s4s8s', self.iface, socket.AF_INET, '\x00'*2, bin_ip, '\x00'*8)
        ioctl(sock, SIOCSIFADDR, ifreq)
        # Setting the netmask. FIXED FOR NOW !!!
        bin_mask = socket.inet_aton("255.255.255.0")
        ifreq = struct.pack('16sH2s4s8s', self.iface, socket.AF_INET, '\x00'*2, bin_mask, '\x00'*8)
        ioctl(sock, SIOCSIFNETMASK, ifreq)
        
    def setIpAddr6(self, ip6):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        bin_ipv6 = socket.inet_pton(socket.AF_INET6, ip6)
        ifreq = struct.pack('16si', self.iface, 0)
        ifreq = ioctl(sock, SIOCGIFINDEX, ifreq)
        if_index = struct.unpack("i", ifreq[16 : 16 + 4])[0]
        ifreq = struct.pack('16sii', bin_ipv6, 64, if_index)
        ioctl(sock, SIOCSIFADDR, ifreq)
        
    def quit(self):
        self.running = False
        # self._Thread__stop()
        self.sock.close()
        # Removing the uds socket
        subprocess.call("rm %s" % self.server_address, shell=True, stdout=self.FNULL, stderr=subprocess.STDOUT)


# Class for virtual interface
class VirtualTransport:
    def __init__(self):
        tun_mode = IFF_TUN
        f = os.open("/dev/net/tun", os.O_RDWR)
        ioctl(f, TUNSETIFF, struct.pack("16sH", VIRT_IFACE_NAME, tun_mode))

        self.setMtu(VIRT_IFACE_NAME, 1400)      # !!! MTU value is fixed for now. !!!
        self.interfaceUp(VIRT_IFACE_NAME)
        
        self.f = f
                
    def setMtu(self, iface, mtu):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ifreq = struct.pack('16sI', iface, int(mtu))
        ioctl(sock, SIOCSIFMTU, ifreq)
        
    # Up the interface
    def interfaceUp(self, iface):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ifreq = struct.pack('16sH', iface, IFF_UP)
        ioctl(sock, SIOCSIFFLAGS, ifreq)
    
    # Returns a list of ip addresses assigned to the virtual interface (in a form of:
    # [<ipv4 address>, <ipv6 address1>,  <ipv6 address2>,  <ipv6 addressN>])
    def get_L3_addresses_from_interface(self):
        addresses = list()
        addresses.append(self.get_ipv4_address())
        for addr in self.get_ipv6_address():
            addresses.append(addr)

        return filter(None, addresses)
        
    def get_ipv4_address(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            addr = ioctl(s.fileno(), SIOCGIFADDR, struct.pack('256s', VIRT_IFACE_NAME[:15]))[20:24]
        except IOError:
            # No IPv4 address was assigned"
            TRANSPORT_LOG.debug("No IPv4 address assigned!")
            return None

        return socket.inet_ntoa(addr)
    
    def get_ipv6_address(self):
        addresses = []
        f = open("/proc/net/if_inet6", "r")
        data = f.read().split("\n")[:-1]

        for row in data:
            if row.split(" ")[-1] == VIRT_IFACE_NAME:
                addresses.append(row.split(" ")[0])
            
        if addresses != []:
            output = []
            for addr in addresses:
                addr = ":".join([addr[i:i+4] for i in range(0, len(addr), 4)])
                addr = socket.inet_pton(socket.AF_INET6, addr)
                output.append(socket.inet_ntop(socket.AF_INET6, addr))
            return output
        else:
            # No IPv6 addresses were assigned"
            TRANSPORT_LOG.debug("No IPv6 address assigned!")

            return [None]
        
    def get_L3_addresses_from_packet(self, packet):
        l3_id = struct.unpack("!H", packet[2:4])[0]

        TRANSPORT_LOG.debug("L3 PROTO ID: %s", hex(l3_id))
        
        if l3_id == int(IP4_ID):
            addresses = self.get_data_from_ipv4_header(packet)
            return addresses
        elif l3_id == int(IP6_ID):
            addresses = self.get_data_from_ipv6_header(packet)
            return addresses
        else:
            # The packet has UNSUPPORTED L3 protocol, drop it
            TRANSPORT_LOG.warning("The packet has UNSUPPORTED L3 protocol, dropping the packet")
            pass
        
    def get_data_from_ipv4_header(self, packet):
        ipv4_format = "bbHHHBBHII"       # IPv4 header mask for parsing from binary data
        data = struct.unpack("!" + ipv4_format, packet[4:24])
        src_ip = self.int2ipv4(data[-2])
        dst_ip = self.int2ipv4(data[-1])
        return [src_ip, dst_ip]
    
    def get_data_from_ipv6_header(self, packet):
        ipv6_format = "IHBB16s16s"       # IPv6 header mask for parsing from binary data
        
        data = struct.unpack("!" + ipv6_format, packet[4:44])       # 40 bytes is the ipv6 header size
                
        src_ip = self.int2ipv6(data[-2])
        dst_ip = self.int2ipv6(data[-1])
        
        return [src_ip, dst_ip]
    
    def int2ipv4(self, addr):
        return socket.inet_ntoa(struct.pack("!I", addr))

    def int2ipv6(self, addr):
        return socket.inet_ntop(socket.AF_INET6, addr)
    
    def send_to_app(self, data):
        os.write(self.f, data)
        
    # Receive raw data from virtual interface. Return a list in a form: [src_ip, dst_ip, raw_data]
    def recv_from_app(self):
        output = os.read(self.f, 65000)
        addresses = self.get_L3_addresses_from_packet(output)

        TRANSPORT_LOG.debug("SRC and DST IPs got from the packet: %s", addresses)

        return addresses + [output]


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

    def send_raw_frame(self, dst_mac, dsr_header, payload):
        eth_header = self.gen_eth_header(self.node_mac, dst_mac)

        TRANSPORT_LOG.debug("Generating dsr bin header...")

        dsr_bin_header = self.gen_dsr_header(dsr_header)

        TRANSPORT_LOG.debug("Dsr bin header is generated!")

        self.send_socket.send(eth_header + dsr_bin_header + payload)
    
    def gen_dsr_header(self, dsr_header):
        if dsr_header.type == 4:
            dsr_bin_string = struct.pack(dsr_header.header_format, dsr_header.type, dsr_header.length,
                                         self.mac2int(dsr_header.src_mac), self.mac2int(dsr_header.tx_mac),
                                         int(dsr_header.broadcast_id), int(dsr_header.broadcast_ttl))
        else:

            dsr_bin_string = struct.pack(dsr_header.header_format, dsr_header.type, dsr_header.length,
                                         self.mac2int(dsr_header.src_mac), self.mac2int(dsr_header.dst_mac),
                                         self.mac2int(dsr_header.tx_mac))

        return dsr_bin_string
    
    def gen_eth_header(self, src_mac, dst_mac):
        src = [int(x, 16) for x in src_mac.split(":")]
        dst = [int(x, 16) for x in dst_mac.split(":")]

        return b"".join(map(chr, dst + src + self.proto))
    
    def mac2int(self, mac):
        return int(mac.replace(":", ""), 16)
    
    def int2mac(self, mac_int):
        s = hex(mac_int)
        # !!! WARNING !!! #
        # This method works ONLY with MAC-48 addresses!!! Need to be rewritten if Zigbee will be used (MAC-64)
        # This is why there comes up this "14" number in the line below:
        # 12 chars of MAC address + 2 first chars of "0x"
        # This "14" number restricts any additional chars at the end of the integer, like:
        # the "L" character appearing in 32-bit processors
        mac = ":".join([s[i:i+2] for i in range(2, 14, 2)])
        return mac
    
    def int2ip(self, addr):
        return socket.inet_ntoa(struct.pack("!I", addr))

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
                dsr_header_obj = self.create_dsr_object(data)

                # Get upper raw data
                upper_raw_data = data[(14 + dsr_header_obj.length):]

                return dsr_header_obj, upper_raw_data

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
                dsr_header_obj = self.create_dsr_object(data)

                # Get upper raw data
                upper_raw_data = data[(14 + dsr_header_obj.length):]

                return dsr_header_obj, upper_raw_data

    def create_dsr_object(self, data):
        # header_format = Messages.DsrHeader.header_format
        length = Messages.DsrHeader.length
        # Skip the Ethernet header, which length is equaled to 14
        # Get the type of the DSR header
        dsr_header_str = data[14:(14 + length)]
        dsr_type = struct.unpack("B", dsr_header_str[:1])[0]   # Read the first byte from the header

        TRANSPORT_LOG.debug("GOT DSR TYPE: %s", dsr_type)

        # If it is a broadcast frame, form special dsr header for the broadcasts
        if dsr_type == 4:
            # Unpack dsr_data from the dsr filed in the frame according to the format of dsr type 4
            dsr_data = struct.unpack(Messages.DsrHeader.broadcast_header_format, dsr_header_str)
            dsr_header_obj = Messages.DsrHeader(dsr_type)
            dsr_header_obj.src_mac = self.int2mac(int(dsr_data[2]))
            dsr_header_obj.tx_mac = self.int2mac(int(dsr_data[3]))
            dsr_header_obj.broadcast_id = int(dsr_data[4])
            dsr_header_obj.broadcast_ttl = int(dsr_data[5])

        else:
            # Unpack dsr_data from the dsr filed in the frame according to the format of dsr types 0, 1, 2 and 3
            dsr_data = struct.unpack(Messages.DsrHeader.unicast_header_format, dsr_header_str)
            dsr_header_obj = Messages.DsrHeader(dsr_type)
            dsr_header_obj.src_mac = self.int2mac(int(dsr_data[2]))
            dsr_header_obj.dst_mac = self.int2mac(int(dsr_data[3]))
            dsr_header_obj.tx_mac = self.int2mac(int(dsr_data[4]))

        TRANSPORT_LOG.debug("Created DSR object: %s", str(dsr_header_obj))

        return dsr_header_obj

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
