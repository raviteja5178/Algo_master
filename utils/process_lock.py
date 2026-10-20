"""
Cross-platform single-instance process lock.
Prevents multiple instances of the bot or launcher from running simultaneously.

The lock file lives in the project root and contains the owner's PID.  On
Windows the lock covers one byte far past the PID text (msvcrt locks are
mandatory, so locking byte 0 would make the PID unreadable to other processes).
"""

from __future__ import annotations

import atexit
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent

# Byte offset of the Windows lock region — well past the PID text.
LOCK_OFFSET = 1 << 20

_HELD_LOCKS: dict[str, object] = {}


def lock_path(lock_name: str) -> Path:
    return ROOT / f".{lock_name}.lock"


def acquire_process_lock(lock_name: str = "bot") -> bool:
    """
    Acquire an exclusive OS-level file lock for `lock_name`.
    Returns True if successfully acquired, or exits/returns False if already held.
    """
    lock_file_path = lock_path(lock_name)
    try:
        f = open(lock_file_path, "a+")
        if sys.platform == "win32":
            import msvcrt
            # Lock 1 byte non-blocking, far past the PID text
            f.seek(LOCK_OFFSET)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        # Write current PID into lock file
        f.seek(0)
        f.truncate()
        f.write(f"{os.getpid()}\n")
        f.flush()

        _HELD_LOCKS[lock_name] = f

        def _cleanup():
            try:
                if sys.platform == "win32":
                    import msvcrt
                    f.seek(LOCK_OFFSET)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                f.close()
                if os.path.exists(lock_file_path):
                    os.remove(lock_file_path)
            except Exception:
                pass

        atexit.register(_cleanup)
        return True
    except (OSError, IOError):
        logger.error(
            "Another instance of '%s' is already running (locked by %s). Exiting.",
            lock_name, lock_file_path
        )
        return False


def _region_locked(f, offset: int) -> bool:
    """True if another process holds the 1-byte lock at *offset* of open file *f*."""
    if sys.platform == "win32":
        import msvcrt
        try:
            f.seek(offset)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return True
        f.seek(offset)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        return False
    import fcntl
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return True
    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return False


def is_lock_held(lock_name: str) -> bool:
    """True if some live process currently holds the `lock_name` lock."""
    if lock_name in _HELD_LOCKS:
        return True
    path = lock_path(lock_name)
    if not path.exists():
        return False
    try:
        with open(path, "a+") as f:
            # Byte 0 is checked too, for instances started before LOCK_OFFSET existed.
            return _region_locked(f, LOCK_OFFSET) or (
                sys.platform == "win32" and _region_locked(f, 0)
            )
    except OSError:
        return True


def lock_holder_pid(lock_name: str) -> int | None:
    """PID of the process holding the `lock_name` lock, or None if not held / unknown."""
    if not is_lock_held(lock_name):
        return None
    try:
        return int(lock_path(lock_name).read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None
