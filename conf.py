DEV = "eth0"
VIRT_IFACE_NAME = "dsr0"
# UDS_ADDRESS = "/tmp/uds_socket"
# ABSOLUTE_PATH = "/home/fila/AdhocRouting/"
LOG_LEVEL = "DEBUG"
SET_TOPOLOGY_FLAG = True
MONITORING_MODE_FLAG = False
# Define a list of protocols and ports, for which to ENABLE reliable transmission of data packets over hops,
# in a format: {protocol_name: [port_numbers]}.
# "0" port number corresponds to the upper protocols, which don't use ports, such as ICMP
ENABLE_ARQ = True
ARQ_LIST = {"TCP": [22], "UDP": [30000, 30001], "ICMP6": [0], "ICMP4": [0]}
