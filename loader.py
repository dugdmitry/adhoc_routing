'''
Created on Sep 26, 2014

@author: Dmitrii Dugaev
'''

'''
This script loads the modules from the working copy to the beaglebones and virtual machines
'''

import os

wd_path = "/home/dmitry/workspace_adhoc/AdhocRouting/"
script_names = ["Node_init.py", "NeighborDiscovery.py", "DataHandler.py", "RouteTable.py", 
                "Transport.py", "Messages.py", "PathDiscovery.py"]

beaglebones = ["adhoc-wifi-1", "adhoc-wifi-2", "adhoc-wifi-3", "adhoc-wifi-4"]
vms = ["adhoc1", "adhoc2", "adhoc3", "adhoc4"]

def load_on_beaglebones():
    for ip in beaglebones:
        for name in script_names:
            cmd = "scp " + wd_path + name + " root@" + ip + ":~/adhoc/"
            os.system(cmd)
            print "Loaded " + name + " to " + ip
    print "Finished"

def load_on_vms():
    for vm in vms:
        names = ""
        for name in script_names:
            names = names + name + " "
        os.system("scp " + wd_path + names + " " + vm + ":~/adhoc/")
        print "Loaded " + names + "to " + vm
    print "Finished"
    
load_on_vms()
#load_on_beaglebones()
