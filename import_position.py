"""
Import an existing live Zerodha position into the bot's trades.db
so the bot can take over trailing stop management.

Usage:
    python import_position.py

What it does:
  1. Fetches your live open positions from Zerodha
  2. Lets you pick which one to import
  3. Asks for the original entry price (your avg cost)
  4. Inserts it into trades.db as an OPEN trade
  5. Bot on next start will reconcile and resume trailing management

Run ONCE. Do not run again for the same position — it checks for duplicates.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import settings
from persistence.models import init_db, upsert_trade, fetch_active_trade
from broker.kite_client import get_kite
from broker.instrument_repository import find_instrument, load_instruments
from utils.time_utils import IST
from utils.price_utils import round_to_tick


# ── helpers ────────────────────────────────────────────────────────────────────

def ask(prompt: str, default: str = "") -> str:
    val = input(f"  {prompt} [{default}]: ").strip()
    return val if val else default


def ask_float(prompt: str, default: float) -> float:
    while True:
        raw = ask(prompt, str(default))
        try:
            return float(raw)
        except ValueError:
            print(f"    Invalid number '{raw}' — try again.")


def ask_int(prompt: str, default: int) -> int:
    while True:
        raw = ask(prompt, str(default))
        try:
            return int(raw)
        except ValueError:
            print(f"    Invalid integer '{raw}' — try again.")


def confirm(prompt: str) -> bool:
    ans = input(f"  {prompt} [y/N]: ").strip().lower()
    return ans in ("y", "yes")


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print()
    print("+--------------------------------------------------+")
    print("|   Import Live Position into Bot (trades.db)      |")
    print("+--------------------------------------------------+")
    print()

    # ── Guard: check no active trade already exists ───────────────────────────
    init_db()
    active = fetch_active_trade()
    if active:
        print(f"  ERROR: An OPEN trade already exists in trades.db:")
        print(f"    trade_id = {active['trade_id']}")
        print(f"    symbol   = {active['option_symbol']}")
        print()
        print("  Close or remove it before importing another position.")
        print("  You can mark it closed with:")
        print("    python -c \"from persistence.models import mark_trade_closed; "
              "mark_trade_closed('<trade_id>', 0, '', 0)\"")
        sys.exit(1)

    # ── Fetch live positions ──────────────────────────────────────────────────
    print("  Fetching live positions from Zerodha...")
    kite = get_kite()
    try:
        positions = kite.positions().get("day", [])
    except Exception as exc:
        print(f"  ERROR: Could not fetch positions: {exc}")
        print("  Make sure KITE_ACCESS_TOKEN is valid and not expired.")
        sys.exit(1)

    open_pos = [p for p in positions if int(p.get("quantity", 0)) > 0]

    if not open_pos:
        print("  No open BUY positions found in your Zerodha account today.")
        print("  Only net-positive (BUY) positions can be imported.")
        sys.exit(0)

    # ── Show open positions ───────────────────────────────────────────────────
    print()
    print("  Open positions found:")
    print()
    print(f"    {'#':<3}  {'Symbol':<32}  {'Qty':>4}  {'Avg Price':>10}  {'LTP':>10}  {'P&L':>10}")
    print(f"    {'---':<3}  {'-'*32}  {'----':>4}  {'----------':>10}  {'----------':>10}  {'----------':>10}")
    for idx, p in enumerate(open_pos):
        pnl  = p.get("pnl", 0)
        sign = "+" if pnl >= 0 else ""
        print(f"    {idx+1:<3}  {p['tradingsymbol']:<32}  {p['quantity']:>4}  "
              f"{p.get('average_price',0):>10.2f}  "
              f"{p.get('last_price',0):>10.2f}  "
              f"{sign}{pnl:>9.2f}")

    print()
    choice = ask_int(f"Select position to import (1-{len(open_pos)})", 1)
    if choice < 1 or choice > len(open_pos):
        print("  Invalid choice. Exiting.")
        sys.exit(1)

    pos = open_pos[choice - 1]
    symbol   = pos["tradingsymbol"]
    qty      = int(pos["quantity"])
    avg_cost = float(pos.get("average_price", 0))
    ltp      = float(pos.get("last_price", 0))

    print()
    print(f"  Selected: {symbol}  qty={qty}  avg={avg_cost:.2f}  ltp={ltp:.2f}")

    # ── Determine strategy type (CE / PE) ─────────────────────────────────────
    if symbol.endswith("CE"):
        strategy_type = "CE"
    elif symbol.endswith("PE"):
        strategy_type = "PE"
    else:
        strategy_type = ask("Strategy type", "CE").upper()

    print(f"  Strategy type: {strategy_type}")

    # ── Lookup instrument token ────────────────────────────────────────────────
    print()
    print("  Looking up instrument token...")
    load_instruments()
    instrument = find_instrument(symbol)

    if instrument:
        token = int(instrument["instrument_token"])
        print(f"  Instrument token: {token}")
    else:
        print(f"  WARNING: '{symbol}' not found in instrument master.")
        token = ask_int("Enter instrument token manually", 0)
        if token == 0:
            print("  Cannot proceed without a valid token. Exiting.")
            sys.exit(1)

    # ── Confirm / override entry price ────────────────────────────────────────
    print()
    print(f"  Your average cost from Zerodha: {avg_cost:.2f}")
    entry_price = ask_float(
        "Entry price to use (press Enter to use avg cost)",
        avg_cost,
    )

    # ── Risk parameters ───────────────────────────────────────────────────────
    print()
    print("  Risk parameters (from .env — press Enter to accept):")
    sl_points   = ask_float(f"Initial SL points",          settings.INITIAL_SL_POINTS)
    be_points   = ask_float(f"Break-even trigger points",  settings.BREAK_EVEN_TRIGGER_POINTS)
    trail_pts   = ask_float(f"Trail step points",          settings.TRAIL_STEP_POINTS)
    target_pts  = ask_float(f"Initial target offset pts",  settings.INITIAL_TARGET_OFFSET_POINTS)

    current_stop   = round_to_tick(entry_price - sl_points)
    target_ref     = entry_price + target_pts

    # Ask for current highest LTP (for recovering trailing position)
    print()
    print(f"  Current LTP is {ltp:.2f}.")
    highest_ltp = ask_float(
        "Highest LTP since your entry (for trailing stop recovery)",
        max(ltp, entry_price),
    )

    # Recompute current stop based on highest_ltp
    if highest_ltp >= entry_price + be_points:
        above_be     = highest_ltp - (entry_price + be_points)
        steps        = int(above_be // trail_pts)
        current_stop = round_to_tick(entry_price + steps * trail_pts)
        target_ref   = (entry_price + target_pts) + steps * trail_pts
        print(f"  Trailing stop already moved to: {current_stop:.2f}  (target ref: {target_ref:.2f})")
    else:
        print(f"  Protective stop: {current_stop:.2f}  (not yet at break-even)")

    # ── Summary + confirm ─────────────────────────────────────────────────────
    print()
    print("  +----------------------------------------------+")
    print("  |  Import Summary                              |")
    print("  +----------------------------------------------+")
    print(f"  |  Symbol      : {symbol:<28} |")
    print(f"  |  Type        : {strategy_type:<28} |")
    print(f"  |  Token       : {str(token):<28} |")
    print(f"  |  Qty         : {str(qty):<28} |")
    print(f"  |  Entry price : {entry_price:<28.2f} |")
    print(f"  |  Current SL  : {current_stop:<28.2f} |")
    print(f"  |  Highest LTP : {highest_ltp:<28.2f} |")
    print(f"  |  Target ref  : {target_ref:<28.2f} |")
    print(f"  |  Mode        : {settings.TRADING_MODE:<28} |")
    print("  +----------------------------------------------+")
    print()

    if not confirm("Import this position into trades.db?"):
        print("  Cancelled.")
        sys.exit(0)

    # ── Write to DB ───────────────────────────────────────────────────────────
    now_ist = datetime.now(IST).isoformat()
    trade_id = f"TRADE_{strategy_type}_IMPORTED_{datetime.now(IST).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    upsert_trade({
        "trade_id":          trade_id,
        "strategy_type":     strategy_type,
        "signal_timestamp":  now_ist,
        "option_symbol":     symbol,
        "instrument_token":  token,
        "quantity":          qty,
        "entry_order_id":    "IMPORTED",
        "entry_price":       entry_price,
        "entry_time":        now_ist,
        "stop_order_id":     None,
        "current_stop":      current_stop,
        "highest_ltp":       highest_ltp,
        "target_reference":  target_ref,
        "status":            "OPEN",
    })

    print()
    print(f"  SUCCESS! Trade imported as: {trade_id}")
    print()
    print("  Next steps:")
    print(f"  1. Set TRADING_MODE=LIVE in your .env")
    print(f"  2. Make sure KITE_ACCESS_TOKEN is fresh")
    print(f"  3. Run: python main.py")
    print()
    print("  The bot will:")
    print(f"    - Detect the OPEN trade in trades.db on startup")
    print(f"    - Reconcile qty={qty} with your Zerodha position")
    print(f"    - Place a stop-loss order at {current_stop:.2f}")
    print(f"    - Resume trailing stop management from highest_ltp={highest_ltp:.2f}")
    print(f"    - Exit automatically if stop is hit or at 15:15 IST")
    print()


if __name__ == "__main__":
    main()
