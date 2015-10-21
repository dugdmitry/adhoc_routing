#!/usr/bin/env python3

#Last change: Fr 16.07.2015


#Import of modules______________________________________________________________________________
import subprocess	#Access to linux shell
import re 			#Regular expressions
import sys			#System commands
import logging		#Log errors
import os			#Use system commands
import argparse 	#Handling input arguments

#Global variables_______________________________________________________________________________
TEST_MODE		= 1
MASTER_ID		= 1

STATUS_SUCCESS	= 0

STATUS_ERROR_NETWORK_IFACE_DOES_NOT_EXIST	= -2
STATUS_ERROR_FILEACCESS_FAILED				= -3
STATUS_ERROR_SUBPROCESS_FAILED				= -4
STATUS_ERROR_MODUEL_NAME_COLLISION			= -5
STATUS_ERROR_INVALID_INPUT_ARGUMENTS		= -6

#Classes________________________________________________________________________________________
class NetworkAnalysis():

	def ReadNetworkIfaces(self):
		#Returns a list of all network interfaces available on the local machine
		try:
			cmdl = subprocess.check_output('ip addr | grep -oE [[:digit:]]:[[:blank:]].*:[[:blank:]]\< | grep -oE [[:alpha:]].*[[:digit:]]', shell=True, stderr=subprocess.STDOUT)
		except subprocess.CalledProcessError as err:
			logger.error((err.output).decode('utf-8'))
			return None, STATUS_ERROR_SUBPROCESS_FAILED

		return cmdl, STATUS_SUCCESS

	def DiscoverNodeId(self, working_net_iface):
		#Returns all occupied node IDs in the network
		try:																		
			cmdl = subprocess.check_output('ping6 -c 2 -L -I ' + working_net_iface + ' ff02::1 | grep -Eo from.*ttl=.*t', shell=True, stderr=subprocess.STDOUT)
			return cmdl, STATUS_SUCCESS
		except subprocess.CalledProcessError as err:
			logger.error((err.output).decode('utf-8'))
			return None, STATUS_ERROR_SUBPROCESS_FAILED

		return cmdl, STATUS_SUCCESS

	def GetHopsToMasterNode(self, master_ip):
		#Returns number of hops to master node
		try:
			cmdl = subprocess.check_output('tracepath6 ' + str(master_ip) + ' | grep -Eo hops[[:blank:]][[:digit:]] | grep -Eo [[:digit:]]', shell=True,stderr=subprocess.STDOUT)
		except subprocess.CalledProcessError as err:
			logger.error(err.output.decode('utf-8'))
			return None, STATUS_ERROR_SUBPROCESS_FAILED
			
		return cmdl, STATUS_SUCCESS

	def RestartNetworkIfaces(self, working_net_iface):
		#Restarts network interface 'working_net_iface' on local machine
		try:
			subprocess.call('ifdown ' + working_net_iface, shell = True, stderr=subprocess.STDOUT)
			subprocess.call('ifup ' + working_net_iface, shell = True, stderr=subprocess.STDOUT)
		except subprocess.CalledProcessError as err:
			logger.error(err.output.decode('utf-8'))
			return STATUS_ERROR_SUBPROCESS_FAILED
		
		return STATUS_SUCCESS

class FileAccess():

	def OpenFile(self, filename, access_type):
		try:
			fh = open(filename, access_type)
		except IOError as err:
			logger.error(err)
			return None, STATUS_ERROR_FILEACCESS_FAILED
			
		return fh, STATUS_SUCCESS

	def CloseFile(self, filehandle):
		try:
			filehandle.close()
		except IOError as err:
			logger.error(err)
			return STATUS_ERROR_FILEACCESS_FAILED
			
		return STATUS_SUCCESS

	def CopyFile(self, source_folder, dest_folder):
		try:
			subprocess.check_output('cp ' + source_folder + ' ' + dest_folder, shell=True, stderr=subprocess.STDOUT)
		except subprocess.CalledProcessError as err:
			logger.error(err.output.decode('utf-8'))
			return STATUS_ERROR_SUBPROCESS_FAILED
			
		return STATUS_SUCCESS

	def ReadFile(self, filehandle):
		try:
			file_content = filehandle.readlines()
		except IOError as err:
			logger.error(err)
			return None, STATUS_ERROR_FILEACCESS_FAILED
		
		return file_content, STATUS_SUCCESS

	def WriteToFile(self, filehandle, write_str):
		
		try:
			filehandle.write(write_str)
		except IOError as err:
			logger.error(err)
			return STATUS_ERROR_FILEACCESS_FAILED
			
		return STATUS_SUCCESS

	def FindString(self, filename, search_str):
		try:
			idx = filename.index(search_str)
		except ValueError as err:
			logger.error(err)
			return None, STATUS_ERROR_FILEACCESS_FAILED
			
		return idx, STATUS_SUCCESS

#Subroutines____________________________________________________________________________________
#Create a logfile handler that will write info, warnings and errors to a logfile
def CreateLogfileHandler(curr_working_dir, logfile_name):

	logging.basicConfig(filename=curr_working_dir + '/' + logfile_name, level=logging.DEBUG, 
	                    format='%(asctime)s %(levelname)s %(module)s line:%(lineno)s msg:%(message)s')

	logger=logging.getLogger(__name__)

	return logger

#Check, if used module names are equal to module names
#located in the current working directory
def CheckModuleNameCollisions():

	curr_working_dir = os.getcwd()

	if (curr_working_dir + '/logging.py') == (logging.__file__):
		logging.error('Name collision of built-in module logging.py with ' + curr_working_dir + '/logging.py' + ' in current folder!')
		return STATUS_ERROR_MODUEL_NAME_COLLISION, None

	if (curr_working_dir + '/subprocess.py') == (subprocess.__file__):
		logging.error('Name collision of built-in module subprocess.py with ' + curr_working_dir + '/subprocess.py' + ' in current folder!')
		return STATUS_ERROR_MODUEL_NAME_COLLISION, None

	return STATUS_SUCCESS, curr_working_dir

#Handle command line arguments provided to the script
def HandleArguments():

	parser = argparse.ArgumentParser(
			description="""ip6_autoconfig.py' is a tool for an automatic configuration of a network interface
							using IPv6-addresses. The configuration is accomplished according to the requirements
							of the smartlighting concept, which means that certain parameters are encoded into
							the resulting IPv6-address. These parameters are x- and y-coordinate of the
							current node / pc, number of hops to master node of network, node ID.""")

	parser.add_argument('x', help='x coordinate to encode into ipv6-address')
	parser.add_argument('y', help='y coordinate to encode into ipv6-address')
	parser.add_argument('wniface', type=str, help='network interface which is connected to working network')
	#parser.add_argument('gateway', help='IPv6 address of gateway')
	parser.add_argument('-l', '--log', default='logfile_ip6_auto_config.log', type=str, help='name of logfile')
	parser.add_argument('-t', '--test', default='0', choices=[0, 1], type=int, help='use test file instead of /etc/network/interfaces')

	args = parser.parse_args()

	x_coord	= args.x
	y_coord	= args.y
	working_net_iface = args.wniface
	#gateway = args.gateway
	logfile = args.log
	test 	= int(args.test)

	#return x_coord, y_coord, working_net_iface, gateway, logfile, test
	return x_coord, y_coord, working_net_iface, logfile, test

#Check if x- and y- coordinates are hexadecimal and of length 1-4 byte
def ValidateCoordinate(coordinate):

	if not len(coordinate) > 4:													#Length of x- and y-coordinates must not be longer than 2 bytes
		if not re.search(r'\b[a-fA-F0-9]{1,4}\b',coordinate):					#Coordinates must be hexadecimal (digits: 0-9, letters: a-f or A-F)
			logging.error('Input of coordinates not correct! Use hexadecimal digits only!')
			return STATUS_ERROR_INVALID_INPUT_ARGUMENTS
	else:
		logging.error('Coordinates must not be longer than 2 bytes!')
		return STATUS_ERROR_INVALID_INPUT_ARGUMENTS

	return STATUS_SUCCESS

#Check for an available node ID in the network and generate the successive ID
def GetNodeId(working_net_iface):

	cmdl, exit_status = NetworkAnalyser.ReadNetworkIfaces()								#Read all available network interfaces on computer
	if exit_status != STATUS_SUCCESS: return exit_status, None, None, None, None

	nw_ifaces = cmdl.decode('utf-8').split()											#Convert result from 'subprocess.check_output' to string and put to list

	if working_net_iface not in nw_ifaces:												#Check, if the provided network interface does exist
		logging.error('Network interface ' + working_net_iface + ' does not exist!')	#If network interface does not exist, log error message
		return STATUS_ERROR_NETWORK_IFACE_DOES_NOT_EXIST, None, None, None, None

	logging.info('Checking for available node IDs...')

	cmdl, exit_status = NetworkAnalyser.DiscoverNodeId(working_net_iface)		#Perform an IPv6 broadcast ping to discover all occupied node IDs in the network
																				#Output e.g.:'from fe80::a9e:1ff:fef7:321c: icmp_seq=2 ttl=64'
	if exit_status != STATUS_SUCCESS:											#If no further node was found in network
		my_id = str(MASTER_ID)													#set my ID to master ID
		master_ip = None
		logging.info('No further nodes in network..')
		logging.info('Available node id: ' + my_id)
	else:
		net_nodes = cmdl.decode('utf-8').split('\n')							#Decode output of ping (byte code->string) and write to list
		del net_nodes[-2:]														#Remove last two elements (one is empty, one is duplicate)
		net_nodes = map(lambda n: n[:-2], net_nodes) 							#Remove [[:blank:]]t from end
		list_ip6 = []															#Create IPv6-address-list
		list_hops = []															#Create Hop list
		#net_nodes: 'from fe80::a9e:1ff:fef7:321c: icmp_seq=2 ttl=64'
		for idx, nwn in enumerate(net_nodes):									#Extract IPv6-address and ttl from string and write to created lists
			nwn = nwn[5:]														#Remove 'from' at beginning of string
			i = nwn.rfind(':')													#Find position of ':' after ip address
			k = nwn.rfind('=')													#Find position of '=' after ttl
			list_ip6.append(str(nwn[:i]))										#Write IPv6-address to ipv6-list
			list_hops.append(str(nwn[k+1:]))									#Write ttl/hop-count to hop-list
		master_ip = None
		node_id_int_list = []													#Create node id list
		for nwn in list_ip6:													#Put all node ids as integeer in node_id_int_list
			i = nwn.rfind(':')													#Find last double dot in ipv6 address
			node_id_int = int(nwn[i+1:], 16)									#Convert all hexadecimal node IDs to integer
			node_id_int_list.append(node_id_int)								#Write integer IDs to node id list
			if node_id_int == 1:												#If a node is = 1, it will become master node
				master_ip = nwn
				logging.info('Master node in network found! (' + master_ip + ')')

		max_id  = int(max(node_id_int_list))									#Get highest occupied node ID in network
		all_ids = set(range(1,max_id+2))										#Generate a set of all possible IDs up to maximum_ID + 1
		my_id   = min(all_ids.difference(set(map(int, node_id_int_list))))		#Convert integer node ID list to set
																				#Compare set of network node IDs with generated set of possible node IDs
																				#The smallest ID in the set of possible IDs that differs from the occupied network IDs
																				#is an available node ID that is going to be chosen as the own node ID
		logging.info('Change own ID to: ' + str(my_id))

	return STATUS_SUCCESS, my_id, master_ip

#Count number of hops to master node
def CountHopsToMasterNode(master_ip):

	if not master_ip:															#Configuration as non-master-node
		hops_to_master = 0														#Number of hops to master node = 0
		logging.info('Configuring the station as master node...')
		logging.info('Number of hops: 0')	
	else:																		#Configuration as master node
		logging.info('Counting number of hops to master node...')
		cmdl, exit_status = NetworkAnalyser.GetHopsToMasterNode(master_ip)		#Count number of hops to master node
		if exit_status != STATUS_SUCCESS: return exit_status, None
		hops_to_master = int(cmdl.decode('utf-8').rstrip())						#Decode byte string to usual string,remove /n at the end and convert to integer
		hops_to_master = hex(hops_to_master)[2:]								#Remove '0x' from 0xno_of_hops and write to var 'hops'
		logging.info('Number of hops to master: ' + str(hops_to_master))

	return STATUS_SUCCESS, hops_to_master


#Generate IPv6 address
def GenerateIpv6Address(x_coord, y_coord, hops_to_master, my_id, test):

	ipv6_net_addr = 'fe80'																											#IPv6 network address
	ipv6_iface_addr = ipv6_net_addr + '::' + str(x_coord) + ':' + str(y_coord) + ':' + str(hops_to_master) + ':' + str(my_id) 		#IPv6 interface address
	ipv6_netmask = '64'																												#IPv6 netmask
#	ipv6_gw_addr = gateway																											#Prompt user to type in gateway address

	if test == TEST_MODE:

		exit_status = FileAccessor.CopyFile('/etc/network/interfaces', 'sudo_file')		#Copy /etc/network/interfaces to current folder and rename it so sudo_file
		if exit_status != STATUS_SUCCESS:  return exit_status

		exit_status = FileAccessor.CopyFile('sudo_file', 'sudo_file_backup')			#Create backup_file of test file sudo_file
		if exit_status != STATUS_SUCCESS: return exit_status

		fh, exit_status = FileAccessor.OpenFile('sudo_file','r')						#Open sudo_file as readable stream
		if exit_status != STATUS_SUCCESS: return exit_status

	else: 
		exit_status = FileAccessor.CopyFile('/etc/network/interfaces', '/etc/network/interfaces_backup')		#Create a back up file of /etc/network/interfaces
		if exit_status != STATUS_SUCCESS: return exit_status

		fh, exit_status = FileAccessor.OpenFile('/etc/network/interfaces','r')			#Open the file /etc/network/interfaces as a readable stream
		if exit_status != STATUS_SUCCESS: return exit_status

	file_ifaces, exit_status = FileAccessor.ReadFile(fh)								#Read all lines from file /etc/network/interfaces or from test fiĺe
	if exit_status != STATUS_SUCCESS: return exit_status

	exit_status = FileAccessor.CloseFile(fh)
	if exit_status != STATUS_SUCCESS: return exit_status 								#Close writable stream

	'''
	idx, exit_status = FileAccessor.FindString(file_ifaces ,'iface ' + working_net_iface + ' inet6 static\n')	#Search in file /etc/network/interfaces for line 'iface XXXX inet6 static'
	if exit_status != STATUS_SUCCESS: return exit_status

	file_ifaces[idx+1] = '\taddress ' + ipv6_iface_addr + '\n'							#Write to next line the ipv6 address that is to be configured
	file_ifaces[idx+2] = '\tnetmask ' + ipv6_netmask    + '\n'							#Write to next line ipv6 netmask that is to be configured
	file_ifaces[idx+3] = '\tgateway ' + ipv6_gw_addr    + '\n'							#Write to next line ipv6 gateway of the network that is to be configured
	'''

	'''
	if test == TEST_MODE:
		fh, exit_status = FileAccessor.OpenFile('sudo_file','w')						#Open sudo_file as readable stream
		if exit_status != STATUS_SUCCESS: return exit_status
	else:
		fh, exit_status = FileAccessor.OpenFile('/etc/network/interfaces','w')			#Open sudo_file as readable stream
		if exit_status != STATUS_SUCCESS: return exit_status

	exit_status = FileAccessor.WriteToFile(fh, ''.join(file_ifaces))					#Write the changed file to /etc/network/interfaces
	if exit_status != STATUS_SUCCESS: return exit_status

	exit_status = FileAccessor.CloseFile(fh)											#Close writable stream
	if exit_status != STATUS_SUCCESS: return exit_status
	'''

	# Add IPv6 address via ifconfig
	os.system("sudo ifconfig %s inet6 add %s/%s" % (working_net_iface, ipv6_iface_addr, ipv6_netmask))
	



	logging.info('File /etc/network/interfaces successfully updated!')
	logging.info('Restarting network interface ' + working_net_iface + '...')
	
	'''
	exit_status = NetworkAnalyser.RestartNetworkIfaces(working_net_iface)				#Restart network interface to activate the changes
	if exit_status != STATUS_SUCCESS: return exit_status
	'''

	logging.info('Network interface successfully updated!')
	logging.info('IP auto-configuration complete!')

	my_ip = ipv6_iface_addr

	logging.info('Creating file: my_ip')
	fh, exit_status = FileAccessor.OpenFile('my_ip', 'w')
	if exit_status != STATUS_SUCCESS: return exit_status
	exit_status = FileAccessor.WriteToFile(fh, my_ip)
	if exit_status != STATUS_SUCCESS: return exit_status
	exit_status = FileAccessor.CloseFile(fh)
	if exit_status != STATUS_SUCCESS: return exit_status

	return STATUS_SUCCESS


#Main___________________________________________________________________________________________
if __name__ == '__main__':

	#x_coord, y_coord, working_net_iface, gateway, logfile, test = HandleArguments()
	x_coord, y_coord, working_net_iface, logfile, test = HandleArguments()
	
	exit_status, curr_working_dir = CheckModuleNameCollisions()
	if exit_status != STATUS_SUCCESS: sys.exit(exit_status)

	logger = CreateLogfileHandler(curr_working_dir, logfile)

	logging.info('IPv6 auto-configuration has been started!')

	exit_status = ValidateCoordinate(x_coord)
	if exit_status != STATUS_SUCCESS: sys.exit(exit_status)

	ValidateCoordinate(y_coord)
	if exit_status != STATUS_SUCCESS: sys.exit(exit_status)

	NetworkAnalyser = NetworkAnalysis()
	FileAccessor = FileAccess()

	exit_status, my_id, master_ip = GetNodeId(working_net_iface)
	if exit_status != STATUS_SUCCESS: sys.exit(exit_status)

	exit_status, hops_to_master = CountHopsToMasterNode(master_ip)
	if exit_status != STATUS_SUCCESS: sys.exit(exit_status)

	#exit_status = GenerateIpv6Address(x_coord, y_coord, hops_to_master, my_id, gateway, test)
	exit_status = GenerateIpv6Address(x_coord, y_coord, hops_to_master, my_id, test)
	if exit_status != STATUS_SUCCESS: sys.exit(exit_status)	