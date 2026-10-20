"""
Stop, pause and find the bot (main.py), its launcher (run_bot.py) and the
dashboard (ui/app.py).

Each of the three holds a process lock (utils.process_lock) whose file holds
its PID, so a held lock is the reliable "is it running" signal — it works no
matter which window or program started the process.

Pause flag: a manual Stop writes .bot_paused.  While it exists, neither the
dashboard watchdog nor the launcher starts the bot; an explicit Start (the
dashboard Start button, or running run_bot.py) removes it.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time

from utils.process_lock import ROOT, lock_holder_pid, is_lock_held

logger = logging.getLogger(__name__)

PAUSE_FILE = ROOT / ".bot_paused"
# Written by the dashboard for bots it starts (the venv launcher's PID).
BOT_PID_FILE = ROOT / ".bot.pid"


# ── Pause flag ────────────────────────────────────────────────────────────────

def is_paused() -> bool:
    return PAUSE_FILE.exists()


def pause_bot(reason: str = "manual stop") -> None:
    try:
        PAUSE_FILE.write_text(reason + "\n")
    except OSError as exc:
        logger.warning("Could not write pause flag: %s", exc)


def resume_bot() -> None:
    try:
        PAUSE_FILE.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not clear pause flag: %s", exc)


# ── Process helpers ───────────────────────────────────────────────────────────

def kill_tree(pid: int) -> bool:
    """Kill *pid* and all its child processes. Returns True if the kill succeeded."""
    if not pid or pid == os.getpid():
        return False
    if sys.platform == "win32":
        # /T: the venv python.exe is a launcher that runs the real interpreter as
        # a child, so killing only the parent PID leaves the bot running.
        res = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return res.returncode == 0
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            return False
    return True


def _read_bot_pid_file() -> int | None:
    try:
        return int(BOT_PID_FILE.read_text().strip())
    except (OSError, ValueError):
        return None


def stop_bot_processes() -> bool:
    """
    Kill the bot wherever it came from: the PID holding the bot lock, plus the
    launcher PID the dashboard recorded.  Returns True if anything was killed.
    """
    killed = False
    lock_pid = lock_holder_pid("bot")
    if lock_pid:
        killed |= kill_tree(lock_pid)
    file_pid = _read_bot_pid_file()
    # Only trust .bot.pid while the bot lock is held (or was a moment ago) —
    # a stale file could name an unrelated process that reused the PID.
    if file_pid and file_pid != lock_pid and lock_pid:
        killed |= kill_tree(file_pid)
    try:
        BOT_PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    return killed


def wait_until_released(lock_name: str, timeout: float = 5.0) -> bool:
    """Wait for `lock_name` to be released. Returns True if it is free."""
    deadline = time.monotonic() + timeout
    while is_lock_held(lock_name):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)
    return True


def stop_all() -> dict[str, str]:
    """
    Stop the dashboard, launcher and bot, and pause auto-starts.
    The dashboard goes first so its watchdog cannot restart the bot.
    Returns {name: status} for reporting.
    """
    pause_bot("stop_bot.bat")
    result: dict[str, str] = {}
    for name in ("dashboard", "launcher", "bot"):
        pid = lock_holder_pid(name)
        if pid is None and not is_lock_held(name):
            result[name] = "not running"
            continue
        if name == "bot":
            stop_bot_processes()
        elif pid:
            kill_tree(pid)
        result[name] = "stopped" if wait_until_released(name) else "STILL RUNNING"
    return result
