'''
Created on Jul 2, 2015

@author: dmitry
'''



f = open("topology_list.txt", "r")

text = f.read()[:-1]

entries = text.split("\n\n")
print entries

#print entries

for ent in entries:
    arr = ent.split("\n")
    print arr
    print arr[1:]
    




















