import asyncio
from time import time_ns
from data_structures import *
from wrapper import *


# Routine to set the files that will recognize the superblock within the file
# system stored in the self-chat of your Telegram account.
async def make():
    # Creates an empty superblock that handles 1000 inodes.
    # The inode id 1 is given to the root directory and the others
    # are left for the contents of the file system.
    s = Superblock(1000)
    # get the inode reserved for the root directory
    ino = s.get_inode_by_number(1)
    # init its attributes
    entry = ino.attributes
    entry.st_mode = (stat.S_IFDIR | 0o755)
    stamp = time_ns()
    entry.st_atime_ns = stamp
    entry.st_ctime_ns = stamp
    entry.st_mtime_ns = stamp
    entry.st_gid = os.getgid()
    entry.st_uid = os.getuid()
    # create and initialize the root directory with the
    # parent inode id and current inode id being itself, 1.
    dd = DirectoryData(1, 1)
    entry.st_size = len(dd)
    # write the directory
    message_id = await w.write_data(dd, 'ROOT directory data')
    # save the pointer in the inode
    ino.data_pointer = message_id
    # write the superblock
    await w.write_superblock(s)

# Initializes the client to communicate with Telegram. The argument
# passed is your phone number.
w = TgFuseWrapper(sys.argv[1])

asyncio.get_event_loop().run_until_complete(make())
