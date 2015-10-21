#!/usr/bin/python

import threading
import socket
import time

import Queue

l = threading.Lock()

class SummingThread(threading.Thread):
    def __init__(self, port):
        super(SummingThread, self).__init__()
        self.port = port

    def run(self):

        sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock_recv.bind(("", self.port))
        
        l.acquire()
        
        print "Receiving data from port", self.port
        
        l.release()
        
        data = sock_recv.recvfrom(65535)
        
        print data

class Worker(threading.Thread):
    def __init__(self):
        super(Worker, self).__init__()
        
    def run(self):
        arr = []
        while True:
            item = q.get()
            if item == "False":
                q.get(False)
            l.acquire()
            print item, type(item)
            arr.append(item)
            print arr
            l.release()
            q.task_done()
        
        print q.qsize()
        print q.get()
        


q = Queue.Queue()

q.put([123,124])
q.put([123,124])
q.put([123,124])
q.put([123,124])


worker_thread = Worker()
worker_thread.start()

while True:
    print "Enter an item to insert"
    a = raw_input()
    q.put(a)
    




#thread1 = SummingThread(3000)
#thread2 = SummingThread(3001)

#thread1.start()
#thread2.start()

#time.sleep(0.2)
#print 123

#thread1._Thread__stop()
#thread2._Thread__stop()


#thread1.join()
#thread2.join()


# At this point, both threads have completed
#result = thread1.total + thread2.total
#print result


