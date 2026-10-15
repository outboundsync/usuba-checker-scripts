"""Safe reads of evidence files the sandboxed plugin could have replaced (audit C2).

hc_signal.py runs OUTSIDE the sandbox on files the plugin could write. A plugin can replace ``toggle.txt`` etc. with a symlink
to any host file (or a FIFO / /dev/zero) and have it copied into the results you send back. These readers accept regular files
only, never follow a symlink, never block on a FIFO, and cap the size."""
import os
import stat

MAX_READ = 1_000_000


def safe_read_bytes(path, cap=MAX_READ):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return b""
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return b""
        data = b""
        while len(data) < cap:
            chunk = os.read(fd, min(65536, cap - len(data)))
            if not chunk:
                break
            data += chunk
        return data
    except OSError:
        return b""
    finally:
        os.close(fd)


def safe_lines(path, cap=MAX_READ):
    return safe_read_bytes(path, cap).decode("utf-8", "replace").splitlines()
