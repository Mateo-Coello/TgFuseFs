from pyfuse3 import *
import stat


# The inode object contains the metadata of a file.
# In this implementation an inode recognizes either a regular file
# or a directory. An inode object has a unique id to recognize a
# file within the file system.
class Inode:
    def __init__(self, number):
        # inode attributes like 'stat'
        self.attributes = EntryAttributes()
        # pointer to data (message id) or data when inlining
        self.data_pointer = 0
        # init the number in attributes
        self.attributes.st_ino = number

    def is_directory(self):
        # check mode and return
        return stat.S_ISDIR(self.attributes.st_mode)

    def is_regular_file(self):
        # check mode and return
        return stat.S_ISREG(self.attributes.st_mode)


# The superblock contains all the information of a mounted file system.
# It stores a list of all inodes and has the methods to create, delete
# and fetch for an inode.
class Superblock:
    def __init__(self, inode_n):
        # init inode dict with the root inode and free set
        self.inodes = {1: Inode(1)}
        self.free_set = set(range(2, inode_n + 1))

    def get_new_inode(self):
        # if there are free inodes
        if self.free_set:
            # get a free inode number
            free_n = self.free_set.pop()
            # add a new inode with the given number to the dict
            self.inodes[free_n] = Inode(free_n)
            # return the new inode
            return self.inodes[free_n]
        # return None otherwise
        return None

    def free_inode(self, number):
        # delete the inode from the dictionary
        del self.inodes[number]
        # add the inode number to the free set
        self.free_set.add(number)

    def get_inode_by_number(self, number):
        # return the inode if exists, None otherwise
        return self.inodes.get(number, None)


# It contains the metadata of a directory entry, that is, a filename and
# its linking to a corresponding file. A reference to the parent inode and
# to the current directory inode is kept for each directory created.
class DirectoryData:
    def __init__(self, self_inode_n, parent_inode_n):
        # init directory entries with '.' and '..'
        self.entries = {b'.': self_inode_n, b'..': parent_inode_n}

    def __len__(self):
        return len(self.entries)


# Stores the contents of a file in bytes. It is initialized with no contents.
class FileData:
    def __init__(self, initial_data=b''):
        self.raw_data = initial_data

    def __len__(self):
        return len(self.raw_data)
