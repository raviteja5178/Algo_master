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
from datetime import datetime, time as dtime

# ── Config ────────────────────────────────────────────────────────────────────
RESTART_DELAY_SECS   = 10    # wait before restarting after unexpected exit
MARKET_OPEN_H        = 9     # don't restart before this hour (IST)
MARKET_CLOSE_H       = 15    # don't restart after this hour (IST)
MARKET_CLOSE_M       = 30    # don't restart after 15:30 IST

# ── State ─────────────────────────────────────────────────────────────────────
_stop_launcher = False
_last_ctrlc    = 0.0

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
