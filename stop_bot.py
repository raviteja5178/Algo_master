"""
Stop everything: the dashboard (ui/app.py), the launcher (run_bot.py) and the
bot (main.py), wherever they were started from.

Also pauses auto-starts, so nothing restarts the bot until you press Start on
the dashboard or run launch.bat / run_bot.py again.

Usage:  stop_bot.bat   (or: python stop_bot.py)
"""

from __future__ import annotations

import sys

from utils.process_control import stop_all


def main() -> int:
    print("Stopping SENSEX Auto-Trader (dashboard, launcher, bot)...")
    result = stop_all()
    for name, status in result.items():
        print(f"  {name:<10} {status}")
    if "STILL RUNNING" in result.values():
        print("Something is still running — check Task Manager for python.exe.")
        return 1
    print("All stopped. Auto-start is paused until you press Start or run launch.bat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
