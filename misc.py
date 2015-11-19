

class Resource:
    id_counter = 0

    def __init__(self, type=0):
        self.type = type
        self.id = Resource.id_counter
        Resource.id_counter += 1


c = Resource()
a = Resource()
b = Resource()

print a.id
print b.id
print c.id
print c.id_counter