
import logging

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

print "qwerty: %s" % str(a)

print a.id
print b.id
print c.id
print c.id_counter

log = FooLogger()
log.create_logger()
log.create_logger()

