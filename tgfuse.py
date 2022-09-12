import pyfuse3
import pyfuse3_asyncio
import errno
import asyncio
import itertools

from argparse import ArgumentParser
from time import time_ns
from collections import defaultdict
from wrapper import *
from data_structures import *

pyfuse3_asyncio.enable()


# Class that contains all methods to recognize and manage the file system.
# It inherits from the pyfuse3.Operations class. Is initialized with a
# phone number associated to a Telegram account.
class TgFuseFs(pyfuse3.Operations):
    def __init__(self, number: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # create the wrapper
        self.wrapper = TgFuseWrapper(number)
        # synchronously get the superblock
        self.superblock = asyncio.get_event_loop().run_until_complete(self.wrapper.read_superblock())
        assert self.superblock is not None
        # create a mutex lock for the superblock
        self.sb_lock = asyncio.Lock()
        # init a counter
        self.counter = itertools.count()
        # create open files and dirs dict
        self.open_dirs = {}
        self.open_files = {}
        # create a lookup counter dict defaulting to 0
        self.lookup_counters = defaultdict(int)
        # create a list deferred removal
        self.deferred = []

    async def getattr(self, inode_n, ctx):
        # acquire superblock mutex and call internal method
        async with self.sb_lock:
            return await self._getattr(inode_n, ctx)

    async def _getattr(self, inode_n, ctx=None):
        # try to get the requested inode and if succeeded
        inode = self.superblock.get_inode_by_number(inode_n)
        if inode is not None:
            # return the requested attributes
            return inode.attributes
        # otherwise raise ENOENT
        raise FUSEError(errno.ENOENT)

    async def setattr(self, inode_n, new_attr, fields, fh, ctx):
        # acquire superblock mutex
        async with self.sb_lock:
            # try to get the requested inode
            inode = self.superblock.get_inode_by_number(inode_n)
            # get its attributes
            attr = inode.attributes
            # update the required fields
            attr.st_atime_ns = new_attr.st_atime_ns if fields.update_atime else attr.st_atime_ns
            attr.st_mtime_ns = new_attr.st_mtime_ns if fields.update_mtime else attr.st_mtime_ns
            attr.st_ctime_ns = new_attr.st_ctime_ns if fields.update_ctime else time_ns()  # now if not specified
            attr.st_mode = new_attr.st_mode if fields.update_mode else attr.st_mode
            attr.st_uid = new_attr.st_uid if fields.update_uid else attr.st_uid
            attr.st_gid = new_attr.st_gid if fields.update_gid else attr.st_gid
            attr.st_size = new_attr.st_size if fields.update_size else attr.st_size
            # return the attributes
            return attr

    async def lookup(self, parent_inode_n, name, ctx):
        # acquire superblock mutex
        async with self.sb_lock:
            # try to lookup (may raise exceptions)
            result = await self._lookup(parent_inode_n, name, ctx)
            # increase the lookup count (if no exceptions occurred)
            self.lookup_counters[result.st_ino] += 1
            return result

    async def _lookup(self, parent_inode_n, name, ctx=None):
        # try to get the requested inode
        parent_inode = self.superblock.get_inode_by_number(parent_inode_n)
        # get directory data
        dd = await self.wrapper.read_data(parent_inode.data_pointer)
        # try to get the entry inode number and if succeeded
        entry_inode_n = dd.entries.get(name, None)
        if entry_inode_n is not None:
            # FOUND: get attr and return
            return await self._getattr(entry_inode_n, ctx)
        # entry not found: raise ENOENT
        raise FUSEError(errno.ENOENT)

    async def opendir(self, inode_n, ctx):

        # acquire superblock mutex
        async with self.sb_lock:
            # try to get the requested inode
            inode = self.superblock.get_inode_by_number(inode_n)
            # if completely failed
            if inode is None:
                # raise ENOENT
                raise FUSEError(errno.ENOENT)
            # else if succeeded but is not a directory
            elif not stat.S_ISDIR(inode.attributes.st_mode):
                # raise ENOTDIR
                raise FUSEError(errno.ENOTDIR)
            # else, it's a directory, good!
            # get directory data
            dd = await self.wrapper.read_data(inode.data_pointer)
            # get next counter value as fh
            fh = next(self.counter)
            # save current DD status in open dirs (cache) and return the key
            self.open_dirs[fh] = (inode, dd)
            return fh

    async def readdir(self, fh, start_id, token):
        # acquire superblock mutex
        async with self.sb_lock:
            # get directory data from cache and its inode
            (dir_inode, dd) = self.open_dirs[fh]
            # init an index as start id
            index = start_id
            # iterate over the entries from the given offset
            for (name, inode_n) in list(dd.entries.items())[start_id:]:
                # get attributes for the current inode
                attr = await self._getattr(inode_n)
                # reply and if necessary stop the iteration
                if not readdir_reply(token, name, attr, index + 1):
                    break
                # increase lookup counter only if not '.' nor '..'
                if name != b'.' and name != b'..':
                    self.lookup_counters[inode_n] += 1
                index += 1
            # update atime
            dir_inode.attributes.st_atime_ns = time_ns()

    async def releasedir(self, fh):
        # remove the cached DD status
        del self.open_dirs[fh]

    async def _update_directory(self, dir_ino_n, entries):
        # get directory data
        dir_ino = self.superblock.get_inode_by_number(dir_ino_n)
        dir_dd = await self.wrapper.read_data(dir_ino.data_pointer)
        # for each entry
        for (action, name, inode_n) in entries:
            # if action is an add ('+')
            if action == '+':
                # add the new entry
                dir_dd.entries[name] = inode_n
            # otherwise is a delete
            else:
                assert dir_dd.entries[name] == inode_n
                # remove the entry
                del dir_dd.entries[name]
        # update parent directory size
        dir_ino.attributes.st_size = len(dir_dd)
        # update ctime and mtime
        now = time_ns()
        dir_ino.attributes.st_ctime_ns = now
        dir_ino.attributes.st_mtime_ns = now
        # write and save parent directory data
        dir_ino.data_pointer = await self.wrapper.write_data(dir_dd, old_to_delete=dir_ino.data_pointer)

    async def mkdir(self, parent_inode_n, name, mode, ctx):
        # acquire superblock mutex and call internal method
        async with self.sb_lock:
            return await self._create(parent_inode_n, name, mode, ctx)

    async def mknod(self, parent_inode_n, name, mode, rdev, ctx):
        # acquire superblock mutex and call internal method
        async with self.sb_lock:
            # special file are not supported: rdev is ignored
            return await self._create(parent_inode_n, name, mode, ctx)

    async def _create(self, parent_inode_n, name, mode, ctx):
        # get a new inode for the new file or directory
        new_ino = self.superblock.get_new_inode()
        # if none (no more inodes) raise ENOSPC
        if new_ino is None:
            raise FUSEError(errno.ENOSPC)
        # init metadata
        new_ino.attributes.st_mode = mode
        new_ino.attributes.st_uid = ctx.uid
        new_ino.attributes.st_gid = ctx.gid
        now = time_ns()
        new_ino.attributes.st_atime_ns = now
        new_ino.attributes.st_mtime_ns = now
        new_ino.attributes.st_ctime_ns = now
        # if we are creating a directory
        if new_ino.is_directory():
            # create DirectoryData with only add '.' and '..'
            data = DirectoryData(new_ino.attributes.st_ino, parent_inode_n)
        # if we are creating a regular file
        elif new_ino.is_regular_file():
            # create empty FileData
            data = FileData()
        else:
            # we don't implement this case:
            # free the inode and raise ENOSYS
            self.superblock.free_inode(new_ino.attributes.st_ino)
            raise FUSEError(errno.ENOSYS)
        # write the file data and save the id as pointer
        new_ino.data_pointer = await self.wrapper.write_data(data)
        # save the size
        new_ino.attributes.st_size = len(data)
        # update parent directory
        await self._update_directory(parent_inode_n, [('+', name, new_ino.attributes.st_ino)])
        # increase the lookup counter and return the attributes
        self.lookup_counters[new_ino.attributes.st_ino] += 1
        return new_ino.attributes

    async def open(self, file_inode_n, flags, ctx):
        # acquire superblock mutex
        async with self.sb_lock:
            # try to get the file and open count from local open cache
            (inode, fd, dirty, count) = self.open_files.get(file_inode_n, (None, None, False, 0))
            # if failed then populate it
            if fd is None:
                # get the inode
                inode = self.superblock.get_inode_by_number(file_inode_n)
                # get file data from Telegram
                fd = await self.wrapper.read_data(inode.data_pointer)
            # dirty already false and count already 0
            # update (or create) entry in cache
            self.open_files[file_inode_n] = (inode, fd, dirty, count + 1)
            # return the inode number as fh
            return FileInfo(fh=file_inode_n)

    async def read(self, fh, off, size):
        # acquire superblock mutex
        async with self.sb_lock:
            # get inode and fd from the cache
            (inode, fd, _, _) = self.open_files[fh]
            # update atime and return the requested data
            inode.attributes.st_atime_ns = time_ns()
            return fd.raw_data[off:off + size]

    async def write(self, fh, off, buf):
        # acquire superblock mutex
        async with self.sb_lock:
            # get inode and fd from the cache
            (inode, fd, _, count) = self.open_files[fh]
            # if the resulting file would be too big raise EFBIG
            if max(off + len(buf), len(fd)) > 1.5E9:
                raise FUSEError(errno.EFBIG)
            # write to cache, set as dirty and update size
            fd.raw_data = fd.raw_data[:off] + buf + fd.raw_data[off + len(buf):]
            self.open_files[fh] = (inode, fd, True, count)
            inode.attributes.st_size = len(fd)
            # update timestamps and return the amount of data written
            now = time_ns()
            inode.attributes.st_ctime_ns = now
            inode.attributes.st_mtime_ns = now
            return len(buf)

    async def release(self, fh):
        # acquire superblock mutex
        async with self.sb_lock:
            # get inode and fd from the cache
            (inode, fd, dirty, count) = self.open_files[fh]
            # if is the last "open"
            if count == 1:
                # if the cache is dirty (invalid remote data)
                if dirty:
                    # write (replace) data and save pointer
                    inode.data_pointer = await self.wrapper.write_data(fd, old_to_delete=inode.data_pointer)
                    # delete from cache
                del self.open_files[fh]
                # otherwise just reduce the counter
            else:
                self.open_files[fh] = (inode, fd, dirty, count - 1)

    async def rmdir(self, parent_inode_n, name, ctx):
        # acquire superblock mutex
        async with self.sb_lock:
            await self._remove(parent_inode_n, name, ctx, is_dir=True)

    async def unlink(self, parent_inode_n, name, ctx):
        # acquire superblock mutex
        async with self.sb_lock:
            await self._remove(parent_inode_n, name, ctx)

    async def _remove(self, parent_inode_n, name, ctx, is_dir=False):
        # try to lookup (may raise ENOENT)
        attr = await self._lookup(parent_inode_n, name, ctx)
        # if we are removing a directory
        if is_dir:
            # ensure it's actually a directory otherwise raise ENOENT
            if not stat.S_ISDIR(attr.st_mode):
                raise FUSEError(errno.ENOTDIR)
            # else if is not empty (only . and ..) raise ENOTEMPTY
            elif attr.st_size > 2:
                raise FUSEError(errno.ENOTEMPTY)
        # if the lookup count is zero
        if self.lookup_counters[attr.st_ino] == 0:
            # get the inode
            inode = self.superblock.get_inode_by_number(attr.st_ino)
            # remove the file data and free its inode
            await self.wrapper.delete_data(inode.data_pointer)
            self.superblock.free_inode(attr.st_ino)
        else:
            # defer deletion
            self.deferred.append(attr.st_ino)
        # update the parent directory
        await self._update_directory(parent_inode_n, [('-', name, attr.st_ino)])

    async def forget(self, inode_list):
        # acquire superblock mutex
        async with self.sb_lock:
            # iterate over the list
            for (inode_n, amount) in inode_list:
                # decrease the counter by the given amount
                self.lookup_counters[inode_n] -= amount
                # if the lookup count is 0 and the removal is deferred
                if self.lookup_counters[inode_n] == 0 and inode_n in self.deferred:
                    # remove the file data and free its inode
                    await self.wrapper.delete_data(self.superblock.get_inode_by_number(inode_n).data_pointer)
                    self.superblock.free_inode(inode_n)
                    # remove it from the deferred list
                    self.deferred.remove(inode_n)

    async def close(self):
        # we assume this is called only when not running the fs
        # for this reason we don't need to acquire the mutex
        # force-forget any deferred inode with non-zero lookup count
        await self.forget(
            [(inode_n, self.lookup_counters[inode_n]) for inode_n in self.deferred]
        )
        # write the superblock
        await self.wrapper.write_superblock(self.superblock, True)


def main():
    # parse arguments from command line
    options = parse_args()
    # instance a TgFuseFs with the given number
    tgfusefs = TgFuseFs(options.phone_number)
    # add fuse options including debug if necessary
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add('fsname=tgfuse')
    if options.debug_fuse:
        fuse_options.add('debug')
    # init pyfuse3 with our filesystem implementation and options
    pyfuse3.init(tgfusefs, options.mountpoint, fuse_options)
    loop = asyncio.get_event_loop()
    try:
        # run pyfuse3.main and then tgfusefs.close
        loop.run_until_complete(pyfuse3.main())
        loop.run_until_complete(tgfusefs.close())
    except:
        pyfuse3.close(unmount=True)
        raise
    finally:
        loop.close()
    # close pyfuse3 normally
    pyfuse3.close()


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('mountpoint', type=str, help='Where to mount the file system')
    parser.add_argument('phone_number', type=str, help='Phone number like +XXXXXXXXXXXX')
    parser.add_argument('--debug-fuse', action='store_true', default=False, help='Enable FUSE debugging output')
    return parser.parse_args()


if __name__ == '__main__':
    main()
