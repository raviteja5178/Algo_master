"""
Live Order Test — place a small real order and watch SL + trailing stop
=======================================================================
This places ONE real BUY order on Zerodha (smallest qty=1), then loops
printing live LTP, current SL, trailing status, and target every second.
You press Enter to manually exit at any time.

Usage:
    python test_live_order.py

What it does:
  1. Asks which symbol to buy (defaults to your current open position)
  2. Asks quantity (default 1 for testing)
  3. Places a real MARKET BUY order via Zerodha
  4. Waits for fill confirmation
  5. Places a real SL-M stop order
  6. Polls LTP every second and applies trailing stop logic
  7. Shows live P&L, SL distance, target distance
  8. Exits (MARKET SELL + cancel SL) when:
     - SL is hit automatically
     - You press Enter
     - Target is reached
"""

from __future__ import annotations

import sys
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import settings
from broker.kite_client import get_kite
from execution.order_manager import OrderManager
from execution.paper_broker import PaperBroker
from execution.trailing_stop import TrailingStopManager
from execution.target_manager import DynamicTargetManager
from utils.price_utils import round_to_tick

# ── colour helpers ────────────────────────────────────────────────────────────
try:
    import colorama; colorama.init()
    G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"
    B = "\033[1m";  RESET = "\033[0m"
except ImportError:
    G = R = Y = C = B = RESET = ""

SEP = "-" * 64


def ask(prompt: str, default: str = "") -> str:
    v = input(f"  {prompt} [{default}]: ").strip()
    return v if v else default


def ask_float(prompt: str, default: float) -> float:
    while True:
        try:
            return float(ask(prompt, str(default)))
        except ValueError:
            print("    Invalid number — try again.")


def ask_int(prompt: str, default: int) -> int:
    while True:
        try:
            return int(ask(prompt, str(default)))
        except ValueError:
            print("    Invalid integer — try again.")


# ── fetch current LTP via REST ────────────────────────────────────────────────

def get_ltp(kite, exchange_symbol: str) -> float:
    try:
        q = kite.quote([exchange_symbol])
        return float(q[exchange_symbol]["last_price"])
    except Exception as exc:
        print(f"  LTP fetch error: {exc}")
        return 0.0


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print("+--------------------------------------------------+")
    print("|  Live Order Test — SL + Trailing Stop + Target  |")
    print("+--------------------------------------------------+")
    print()
    print(f"  Mode: {settings.TRADING_MODE}")
    if settings.TRADING_MODE != "LIVE":
        print(f"  {R}WARNING: TRADING_MODE is not LIVE — orders will NOT be sent.{RESET}")
        print(f"  Set TRADING_MODE=LIVE and ENABLE_LIVE_TRADING=true in .env first.")
        if ask("  Continue anyway in read-only simulation? (no orders placed)", "n").lower() != "y":
            sys.exit(0)

    kite   = get_kite()
    if settings.TRADING_MODE == "PAPER":
        broker = PaperBroker()  # type: ignore
    else:
        broker = OrderManager()

    # ── Step 1: choose symbol ─────────────────────────────────────────────────
    print()
    print("  Fetching your open positions...")
    try:
        positions = kite.positions().get("day", [])
        open_buys = [p for p in positions if int(p.get("quantity", 0)) > 0]
    except Exception as exc:
        print(f"  Could not fetch positions: {exc}")
        open_buys = []

    default_symbol = open_buys[0]["tradingsymbol"] if open_buys else "SENSEX2691075100CE"
    default_exchange = "BFO"

    print()
    symbol   = ask("Symbol to buy", default_symbol).upper().strip()
    exchange = ask("Exchange", default_exchange).upper().strip()
    qty      = ask_int("Quantity (use 1 for testing)", 1)

    # ── Step 2: risk params ───────────────────────────────────────────────────
    print()
    sl_pts     = ask_float(f"Initial SL points      (from .env={settings.INITIAL_SL_POINTS})",
                           settings.INITIAL_SL_POINTS)
    be_pts     = ask_float(f"Break-even trigger pts (from .env={settings.BREAK_EVEN_TRIGGER_POINTS})",
                           settings.BREAK_EVEN_TRIGGER_POINTS)
    trail_pts  = ask_float(f"Trail step points      (from .env={settings.TRAIL_STEP_POINTS})",
                           settings.TRAIL_STEP_POINTS)
    target_pts = ask_float(f"Target offset points   (from .env={settings.INITIAL_TARGET_OFFSET_POINTS})",
                           settings.INITIAL_TARGET_OFFSET_POINTS)

    # ── Step 3: live LTP before placing ──────────────────────────────────────
    print()
    exchange_symbol = f"{exchange}:{symbol}"
    ltp = get_ltp(kite, exchange_symbol)
    if ltp > 0:
        print(f"  Current LTP: {B}{ltp:.2f}{RESET}")
        est_sl     = round_to_tick(ltp - sl_pts)
        est_target = ltp + target_pts
        print(f"  Estimated SL:     {R}{est_sl:.2f}{RESET}")
        print(f"  Estimated target: {G}{est_target:.2f}{RESET}")
    else:
        print(f"  Could not fetch LTP for {exchange_symbol}")

    print()
    confirm = ask("Place BUY order now? This is a REAL order", "n").lower()
    if confirm != "y":
        print("  Cancelled.")
        sys.exit(0)

    # ── Step 4: place BUY ────────────────────────────────────────────────────
    print()
    print(f"  Placing MARKET BUY  {symbol}  qty={qty} ...")
    fill = broker.place_buy_order(symbol, qty, exchange=exchange, ltp_hint=ltp if settings.TRADING_MODE == "PAPER" else None)

    if fill["status"] != "COMPLETE" or fill["filled_qty"] == 0:
        print(f"  {R}BUY FAILED: {fill}{RESET}")
        sys.exit(1)

    entry_price = fill["average_price"]
    filled_qty  = fill["filled_qty"]
    order_id    = fill["order_id"]
    print(f"  {G}FILLED{RESET}  price={B}{entry_price:.2f}{RESET}  qty={filled_qty}  order_id={order_id}")

    # ── Step 5: place SL-M ───────────────────────────────────────────────────
    sl_price = round_to_tick(entry_price - sl_pts)
    print()
    print(f"  Placing SL-M order at {R}{sl_price:.2f}{RESET} ...")
    sl_order_id = broker.place_stop_order(symbol, filled_qty, sl_price, exchange=exchange)
    print(f"  SL order placed: {sl_order_id}")

    # ── Step 6: init trailing stop + target managers ─────────────────────────
    trailing = TrailingStopManager(entry_price, sl_pts, be_pts, trail_pts)
    target   = DynamicTargetManager(entry_price, target_pts, trail_pts)

    print()
    print(SEP)
    print(f"  {B}POSITION OPEN{RESET}  {symbol}  entry={B}{entry_price:.2f}{RESET}  "
          f"sl={R}{sl_price:.2f}{RESET}  target={G}{entry_price+target_pts:.2f}{RESET}")
    print(f"  Press Enter at any time to exit manually.")
    print(SEP)

    # ── Step 7: enter-key watcher in background ───────────────────────────────
    _manual_exit = threading.Event()

    def _watch_enter():
        input()
        _manual_exit.set()

    threading.Thread(target=_watch_enter, daemon=True).start()

    # ── Step 8: live loop ─────────────────────────────────────────────────────
    exit_reason = ""
    prev_stop   = trailing.current_stop
    iteration   = 0

    while True:
        time.sleep(1)
        iteration += 1

        ltp = get_ltp(kite, exchange_symbol)
        if ltp <= 0:
            continue

        if settings.TRADING_MODE == "PAPER":
            broker.update_ltp(symbol, ltp)

        upnl      = (ltp - entry_price) * filled_qty
        upnl_sign = "+" if upnl >= 0 else ""
        upnl_col  = G if upnl >= 0 else R

        # Check if SL order was hit by the broker (external trigger)
        sl_status = broker.get_order_status(sl_order_id)
        if sl_status == "COMPLETE":
            exit_reason = "STOP_LOSS_HIT"
            break

        # Apply trailing stop logic
        new_stop = trailing.update(ltp)
        if new_stop is not None and new_stop > prev_stop:
            ok = broker.modify_stop_order(sl_order_id, new_stop)
            if ok:
                target.sync_trail_steps(trailing.trail_steps_completed)
                action = f"{Y}BREAK-EVEN{RESET}" if not trailing.break_even_activated else f"{C}TRAIL #{trailing.trail_steps_completed}{RESET}"
                print(f"\n  {action}  SL: {R}{prev_stop:.2f}{RESET} -> {R}{new_stop:.2f}{RESET}  "
                      f"Target: {G}{target.target_reference:.2f}{RESET}")
                prev_stop = new_stop
            else:
                print(f"\n  {R}WARN: SL modify failed — keeping old SL{RESET}")

        # Check manual exit
        if _manual_exit.is_set():
            exit_reason = "MANUAL_EXIT"
            break

        # Check target hit
        if ltp >= target.target_reference:
            exit_reason = "TARGET_HIT"
            break

        # Print live status every 5 seconds
        if iteration % 5 == 0:
            sl_dist     = ltp - trailing.current_stop
            target_dist = target.target_reference - ltp
            be_status   = f"{G}BE-ON{RESET}" if trailing.break_even_activated else f"{Y}BE-OFF{RESET}"
            print(f"  LTP={B}{ltp:>8.2f}{RESET}  "
                  f"SL={R}{trailing.current_stop:>8.2f}{RESET} ({sl_dist:+.1f})  "
                  f"Target={G}{target.target_reference:>8.2f}{RESET} ({target_dist:+.1f})  "
                  f"P&L={upnl_col}{upnl_sign}{upnl:.2f}{RESET}  "
                  f"Trail={trailing.trail_steps_completed}  {be_status}")

    # ── Step 9: exit ──────────────────────────────────────────────────────────
    print()
    print(SEP)
    print(f"  Exit triggered: {B}{exit_reason}{RESET}")

    if exit_reason != "STOP_LOSS_HIT":
        # Cancel SL order first, then market sell
        print(f"  Cancelling SL order {sl_order_id} ...")
        broker.cancel_order(sl_order_id)
        time.sleep(0.5)
        print(f"  Placing MARKET SELL  {symbol}  qty={filled_qty} ...")
        sell_fill = broker.place_sell_order(symbol, filled_qty, exchange=exchange, tag=exit_reason, ltp_hint=ltp if settings.TRADING_MODE == "PAPER" else None)
        exit_price = sell_fill.get("average_price", 0.0)
    else:
        # SL was hit — get fill price from the SL order itself
        orders = kite.orders()
        sl_order = next((o for o in orders if str(o["order_id"]) == str(sl_order_id)), {})
        exit_price = float(sl_order.get("average_price", trailing.current_stop))

    pnl      = (exit_price - entry_price) * filled_qty
    pnl_sign = "+" if pnl >= 0 else ""
    pnl_col  = G if pnl >= 0 else R

    print(SEP)
    print(f"  {B}TRADE CLOSED{RESET}")
    print(f"  Entry:  {entry_price:.2f}")
    print(f"  Exit:   {exit_price:.2f}  ({exit_reason})")
    print(f"  Qty:    {filled_qty}")
    print(f"  P&L:    {pnl_col}{B}{pnl_sign}{pnl:.2f}{RESET}")
    print(f"  Trail steps completed: {trailing.trail_steps_completed}")
    print(f"  Highest LTP seen:      {trailing.highest_ltp:.2f}")
    print(SEP)
    print()


if __name__ == "__main__":
    main()
