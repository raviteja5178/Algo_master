"""
Cross-platform single-instance process lock.
Prevents multiple instances of the bot or launcher from running simultaneously.
"""

from __future__ import annotations

import atexit
import logging
import os
import sys

logger = logging.getLogger(__name__)

_HELD_LOCKS: dict[str, object] = {}


def acquire_process_lock(lock_name: str = "bot") -> bool:
    """
    Acquire an exclusive OS-level file lock for `lock_name`.
    Returns True if successfully acquired, or exits/returns False if already held.
    """
    lock_file_path = f".{lock_name}.lock"
    try:
        f = open(lock_file_path, "a+")
        if sys.platform == "win32":
            import msvcrt
            # Seek to start of file and lock 1 byte non-blocking
            f.seek(0)
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
                    f.seek(0)
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
