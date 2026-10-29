"""Nonblocking OS-owned lock, released even if the owning process crashes."""
import errno
import os


def acquire_directory_lock(directory):
    handle = (directory / 'server.lock').open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            # Windows permits locking beyond EOF. Always lock byte zero;
            # do not rewrite/truncate a lock file owned by another process.
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        handle.close()
        if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            raise SystemExit('This data directory is already in use. Stop the other server or use --data-dir.') from None
        raise
    return handle
