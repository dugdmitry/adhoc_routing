
import logging
from random import randint

class Resource:
    id_counter = 0

    def __init__(self, type=0):
        self.type = type
        self.id = Resource.id_counter
        Resource.id_counter += 1

    def __str__(self):

        return "GOT YA!!!"


class FooLogger:
    def __init__(self):
        pass

    def create_logger(self):

        logger = logging.getLogger("test")

        if logger.handlers:
            print "YO"

        print logger, type(logger)


c = Resource()
a = Resource()
b = Resource()

# print "qwerty: %s" % str(a)
#
# print a.id
# print b.id
# print c.id
# print c.id_counter
#
# log = FooLogger()
# log.create_logger()
# log.create_logger()
#


# Test dict inheritance
class Entry(dict):
    def __init__(self, src_ip, dst_ip, neighbors_list):
        super(Entry, self).__init__()

        self.src_ip = src_ip
        self.dst_ip = dst_ip
        self.neighbors_list = neighbors_list

        self[src_ip + dst_ip] = neighbors_list

ent = Entry("src", "dst", [1, 2, 3, 4, 5])

print ent["srcdst"]


# Check hash function
class RouteRequest:
    dsr_type = 2

    def __init__(self):
        # self.id = randint(1, 1048575)   # Max value is 2**20 (20 bits)
        self.src_ip = ""
        self.dst_ip = ""
        self.dsn = 0
        self.hop_count = 0

    # def __str__(self):
    #     out_tuple = (str(self.id), str(self.src_ip), str(self.dst_ip), str(self.dsn), str(self.hop_count))
    #     out_string = "ID: %s, SRC_IP: %s, DST_IP: %s, DSN: %s, HOP_COUNT: %s" % out_tuple
    #
    #     return out_string


def create_obj():
    a = RouteRequest()
    print hash(a)
    del a

for i in range(10):
    create_obj()






