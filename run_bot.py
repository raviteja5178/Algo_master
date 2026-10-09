#!/usr/bin/env python3
"""
Persistent bot launcher with auto-restart.

Starts main.py and automatically restarts it if it exits unexpectedly.
A clean Ctrl+C (SIGINT) sent TWICE within 3 seconds stops both the bot
and this launcher permanently.

Usage:
    python run_bot.py

To stop:  Ctrl+C  (once = passes to bot for clean shutdown,
                   twice within 3s = stops launcher too)
"""

import subprocess
import sys
import time
import signal
import os
import atexit
from datetime import datetime, time as dtime

# ── Config ────────────────────────────────────────────────────────────────────
_LAUNCHER_PID_FILE   = ".launcher.pid"
RESTART_DELAY_SECS   = 10    # wait before restarting after unexpected exit
MARKET_OPEN_H        = 9     # don't restart before this hour (IST)
MARKET_CLOSE_H       = 15    # don't restart after this hour (IST)
MARKET_CLOSE_M       = 30    # don't restart after 15:30 IST

# ── State ─────────────────────────────────────────────────────────────────────
_stop_launcher = False
_last_ctrlc    = 0.0


def _acquire_launcher_lock() -> None:
    """
    Write this process's PID to .launcher.pid.

    If the file already exists and the recorded PID belongs to a running
    process, print an error and exit immediately — prevents two concurrent
    launcher instances from managing the same bot.

    The file is removed automatically on clean exit via atexit.
    """
    pid = os.getpid()

    if os.path.exists(_LAUNCHER_PID_FILE):
        try:
            existing_pid = int(open(_LAUNCHER_PID_FILE).read().strip())
        except (ValueError, OSError):
            existing_pid = None

        if existing_pid is not None and existing_pid != pid:
            # Check whether the recorded PID is actually alive.
            alive = False
            try:
                # os.kill(pid, 0) does NOT send a signal; it only checks
                # whether the process exists.  Raises OSError if it does not.
                os.kill(existing_pid, 0)
                alive = True
            except OSError:
                alive = False  # process is gone — stale lock file

            if alive:
                print(
                    f"[Launcher] ERROR: Another launcher is already running "
                    f"(PID {existing_pid}, found in {_LAUNCHER_PID_FILE}). "
                    f"Exiting to prevent duplicate bot instances.",
                    flush=True,
                )
                sys.exit(1)
            else:
                print(
                    f"[Launcher] Stale lock file found (PID {existing_pid} is not running). "
                    f"Removing and continuing.",
                    flush=True,
                )

    # Write our own PID.
    with open(_LAUNCHER_PID_FILE, "w") as fh:
        fh.write(str(pid))

    atexit.register(_release_launcher_lock)


def _release_launcher_lock() -> None:
    """Remove the .launcher.pid file on clean exit."""
    try:
        if os.path.exists(_LAUNCHER_PID_FILE):
            # Only remove if it still contains our own PID (guard against
            # an edge case where a new launcher overwrote the file first).
            try:
                recorded = int(open(_LAUNCHER_PID_FILE).read().strip())
            except (ValueError, OSError):
                recorded = None
            if recorded == os.getpid():
                os.remove(_LAUNCHER_PID_FILE)
    except OSError:
        pass

def _sigint_handler(sig, frame):
    global _stop_launcher, _last_ctrlc
    now = time.monotonic()
    if now - _last_ctrlc < 3.0:
        # Second Ctrl+C within 3 seconds → stop the launcher
        print("\n[Launcher] Second Ctrl+C — stopping launcher permanently.", flush=True)
        _stop_launcher = True
    else:
        print("\n[Launcher] Ctrl+C received — forwarding to bot (Ctrl+C again within 3s to stop launcher).", flush=True)
    _last_ctrlc = now

signal.signal(signal.SIGINT, _sigint_handler)


def _is_market_hours() -> bool:
    """Returns True during 09:00–15:30 IST window."""
    now = datetime.now()
    t = now.time()
    return dtime(MARKET_OPEN_H, 0) <= t <= dtime(MARKET_CLOSE_H, MARKET_CLOSE_M)


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    global _stop_launcher
    _acquire_launcher_lock()

    print("=" * 60)
    print("  SENSEX Auto-Trader — Persistent Launcher")
    print("  Bot restarts automatically on any unexpected exit.")
    print("  Ctrl+C once → clean bot shutdown (launcher keeps running)")
    print("  Ctrl+C twice within 3s → stop launcher permanently")
    print("=" * 60)

    restart_count = 0

    while not _stop_launcher:
        restart_count += 1
        print(f"\n[{_ts()}] [Launcher] Starting bot (run #{restart_count})...", flush=True)

        try:
            proc = subprocess.Popen(
                [sys.executable, "main.py"],
                # Inherit stdin/stdout/stderr so the bot's output is visible
            )

            # Wait for the process to finish
            while proc.poll() is None:
                if _stop_launcher:
                    print(f"[{_ts()}] [Launcher] Stop requested — terminating bot...", flush=True)
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    break
                time.sleep(1)

            exit_code = proc.returncode
            print(f"\n[{_ts()}] [Launcher] Bot exited with code {exit_code}.", flush=True)

        except Exception as exc:
            print(f"\n[{_ts()}] [Launcher] Error running bot: {exc}", flush=True)
            exit_code = -1

        if _stop_launcher:
            break

        # Don't restart after market hours
        if not _is_market_hours():
            print(f"[{_ts()}] [Launcher] Outside market hours (09:00–15:30) — not restarting.", flush=True)
            print(f"[{_ts()}] [Launcher] Launcher will resume restarts during next market session.", flush=True)
            # Sleep until market open instead of tight-looping
            while not _is_market_hours() and not _stop_launcher:
                time.sleep(30)
            if _stop_launcher:
                break
            print(f"[{_ts()}] [Launcher] Market hours resumed — restarting bot.", flush=True)
            continue

        print(f"[{_ts()}] [Launcher] Restarting in {RESTART_DELAY_SECS}s...", flush=True)
        for _ in range(RESTART_DELAY_SECS):
            if _stop_launcher:
                break
            time.sleep(1)

    print(f"\n[{_ts()}] [Launcher] Stopped.", flush=True)


if __name__ == "__main__":
    main()
