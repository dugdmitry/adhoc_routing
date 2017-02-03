DEV = "wlan0"
VIRT_IFACE_NAME = "adhoc0"
LOG_LEVEL = "DEBUG"
SET_TOPOLOGY_FLAG = False
MONITORING_MODE_FLAG = False
GW_MODE = False
# Define type of the gateway mode (local or public). See the documentation for more info.
GW_TYPE = "local"
# Define a list of protocols and ports, for which to ENABLE reliable transmission of data packets over hops,
# in a format: {protocol_name: [port_numbers]}.
# "0" port number corresponds to the upper protocols, which don't use ports, e.g. ICMP
ENABLE_ARQ = True
ARQ_LIST = {"TCP": [22], "UDP": [30000, 30001], "ICMP6": [0], "ICMP4": [0]}
