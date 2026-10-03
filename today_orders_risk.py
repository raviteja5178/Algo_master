"""
Today's Orders with ATR-based Risk Parameters
----------------------------------------------
Fetches ALL orders placed today (COMPLETE, REJECTED, CANCELLED, open)
and shows Target / Stop-Loss / Break-Even for every BUY order using
the same ATR-adaptive risk engine the live bot uses.

Risk modes (mirror execution/atr_risk.py exactly):

  Mode D  -- swing high/low as SL  (USE_SWING_SL=true)  [highest priority]
      SL  at nearest structural pivot; falls back to Mode C when unavailable.

  Mode C  -- SENSEX spot ATR × multiplier  (USE_SPOT_ATR_RISK=true)  [default]
      SL        = ATR(5, SENSEX 5m) × SPOT_ATR_SL_MULT × ATM_delta(0.4)
      Target    = SL × SPOT_ATR_TARGET_RR
      Trail     = SL × SPOT_ATR_TRAIL_RR

  Fixed   -- fallback when ATR is unavailable (cold start / insufficient candles)
      Uses INITIAL_SL_POINTS / INITIAL_TARGET_OFFSET_POINTS from .env

SELL orders show fill price only (no risk block — they are exits, not entries).

Usage:
    python today_orders_risk.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime

from config import settings
from broker.kite_client import get_kite
from market.candle_builder import Candle
from market.historical_data import fetch_historical_candles, SENSEX_TOKEN
from execution.atr_risk import compute_risk_params
from execution.trailing_stop import TrailingStopManager

SEP  = "-" * 72
SEP2 = "  " + "." * 68


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_all_today_orders() -> list[dict]:
    """Return every order for today regardless of status."""
    kite = get_kite()
    try:
        orders = kite.orders()
    except Exception as exc:
        print(f"ERROR fetching orders: {exc}", file=sys.stderr)
        sys.exit(1)

    today_str = date.today().strftime("%Y-%m-%d")
    today_orders = [
        o for o in orders
        if _order_date(o) == today_str
    ]
    # Fallback: if date filtering yields nothing return everything
    return today_orders if today_orders else list(orders)


def _order_date(o: dict) -> str:
    ts = o.get("order_timestamp") or o.get("exchange_timestamp") or ""
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d")
    return str(ts)[:10]


# Cache candles per symbol so we don't re-fetch for repeated orders
_candle_cache: dict[str, list[Candle]] = {}

def _candles_for(tradingsymbol: str, exchange: str) -> list[Candle]:
    if tradingsymbol in _candle_cache:
        return _candle_cache[tradingsymbol]

    from broker.instrument_repository import find_instrument
    instr = find_instrument(tradingsymbol)
    if instr:
        token = int(instr["instrument_token"])
    else:
        print(f"  [warn] token not found for {tradingsymbol}, using SENSEX spot for ATR")
        token = SENSEX_TOKEN

    try:
        candles = fetch_historical_candles(token, interval="5minute", days_back=5)
    except Exception as exc:
        print(f"  [warn] candle fetch failed for {tradingsymbol}: {exc}")
        candles = []

    _candle_cache[tradingsymbol] = candles
    return candles


def _risk_for(order: dict, candles: list[Candle]) -> dict:
    """Compute risk params exactly as the live bot does."""
    avg_price = float(order.get("average_price") or 0)
    entry = avg_price if avg_price > 0 else 0.0

    params = compute_risk_params(
        candles,
        fixed_sl=settings.INITIAL_SL_POINTS,
        fixed_target=settings.INITIAL_TARGET_OFFSET_POINTS,
        fixed_trail=settings.TRAIL_STEP_POINTS,
        min_sl_pts=settings.MIN_SL_POINTS,
        min_target_pts=settings.MIN_TARGET_POINTS,
        min_trail_pts=settings.MIN_TRAIL_POINTS,
        entry_price=entry,
        use_spot_atr=settings.USE_SPOT_ATR_RISK,
        spot_atr_period=settings.SPOT_ATR_PERIOD,
        spot_sl_mult=settings.SPOT_ATR_SL_MULT,
        target_rr=settings.SPOT_ATR_TARGET_RR,
        trail_rr=settings.SPOT_ATR_TRAIL_RR,
        use_swing_sl=settings.USE_SWING_SL,
    )

    filled = entry > 0

    # Determine mode label
    if settings.USE_SWING_SL:
        mode_label = f"D - swing SL → fallback C  (ATR={params.atr_value})"
    elif params.atr_value:
        mode_label = f"C - spot ATR×{settings.SPOT_ATR_SL_MULT}  (ATR={params.atr_value})"
    else:
        mode_label = "fixed (ATR unavailable)"

    return {
        "filled":      filled,
        "entry":       entry,
        "mode":        mode_label,
        "atr":         params.atr_value,
        "sl_pts":      params.initial_sl_points,
        "tgt_pts":     params.initial_target_points,
        "be_pts":      params.break_even_trigger_points,
        "trail_pts":   params.trail_step_points,
        "sl_price":    round(entry - params.initial_sl_points, 2)  if filled else None,
        "tgt_price":   round(entry + params.initial_target_points, 2) if filled else None,
        "be_price":    round(entry - params.break_even_trigger_points, 2) if filled else None,
    }


def _status_badge(status: str) -> str:
    badges = {
        "COMPLETE":  "[COMPLETE]",
        "REJECTED":  "[REJECTED]",
        "CANCELLED": "[CANCELLED]",
        "OPEN":      "[OPEN]",
        "TRIGGER PENDING": "[TRIGGER PENDING]",
    }
    return badges.get(status, f"[{status}]")


# ---------------------------------------------------------------------------
# Config snapshot
# ---------------------------------------------------------------------------

def _print_config() -> None:
    print(f"\n  ATR Risk Config (from .env)")
    if settings.USE_SWING_SL:
        print(f"  Active mode: D — swing SL (length={settings.SWING_SL_LENGTH}) → fallback Mode C")
    else:
        print(f"  Active mode: C — SENSEX spot ATR × {settings.SPOT_ATR_SL_MULT}  (period={settings.SPOT_ATR_PERIOD})")
    print(f"  {'USE_SPOT_ATR_RISK':<30} = {settings.USE_SPOT_ATR_RISK}")
    print(f"  {'SPOT_ATR_PERIOD':<30} = {settings.SPOT_ATR_PERIOD}")
    print(f"  {'SPOT_ATR_SL_MULT':<30} = {settings.SPOT_ATR_SL_MULT}")
    print(f"  {'SPOT_ATR_TARGET_RR':<30} = {settings.SPOT_ATR_TARGET_RR}")
    print(f"  {'SPOT_ATR_TRAIL_RR':<30} = {settings.SPOT_ATR_TRAIL_RR}")
    print(f"  {'USE_SWING_SL':<30} = {settings.USE_SWING_SL}")
    print(f"  {'MIN_SL_POINTS':<30} = {settings.MIN_SL_POINTS}")
    print(f"  {'MIN_TARGET_POINTS':<30} = {settings.MIN_TARGET_POINTS}")
    print(f"  {'INITIAL_SL_POINTS':<30} = {settings.INITIAL_SL_POINTS}  (fixed fallback)")
    print(f"  {'INITIAL_TARGET_OFFSET_POINTS':<30} = {settings.INITIAL_TARGET_OFFSET_POINTS}  (fixed fallback)")
    ust = settings.USE_TRAILING_STOP_EXIT
    ust_status = "ENABLED  [OK]" if ust else "DISABLED [WARNING: positions have no trailing stop]"
    print(f"  {'USE_TRAILING_STOP_EXIT (UST)':<30} = {ust}  -> {ust_status}")
    print(f"  {'QUANTITY':<30} = {settings.QUANTITY}")
    print(f"  {'TRADING_MODE':<30} = {settings.TRADING_MODE}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(SEP)
    print(f"  TODAY'S ORDERS + ATR RISK  --  {date.today()}")
    print(SEP)
    _print_config()
    print()
    print(SEP)

    orders = _fetch_all_today_orders()
    if not orders:
        print("  No orders found for today.")
        return

    # Group: show BUY entries first, then SELLs
    buys  = [o for o in orders if o.get("transaction_type") == "BUY"]
    sells = [o for o in orders if o.get("transaction_type") == "SELL"]
    other = [o for o in orders if o.get("transaction_type") not in ("BUY", "SELL")]

    print(f"  Total orders today : {len(orders)}"
          f"  (BUY={len(buys)}  SELL={len(sells)}  other={len(other)})\n")

    all_orders = buys + sells + other
    for idx, o in enumerate(all_orders, 1):
        symbol   = o.get("tradingsymbol", "?")
        exchange = o.get("exchange", "BFO")
        status   = o.get("status", "?")
        txn      = o.get("transaction_type", "?")
        qty      = o.get("quantity", 0)
        avg_px   = float(o.get("average_price") or 0)
        order_id = o.get("order_id", "?")
        order_ts = o.get("order_timestamp", "")
        reason   = (o.get("status_message") or o.get("status_message_raw") or "").strip()
        badge    = _status_badge(status)

        print(f"  [{idx:02d}] {badge} {txn}  {symbol}  qty={qty}")
        print(f"        order_id : {order_id}")
        print(f"        time     : {order_ts}")
        if avg_px > 0:
            print(f"        fill px  : {avg_px:.2f}")
        if reason:
            print(f"        reason   : {reason}")

        if txn == "BUY":
            candles = _candles_for(symbol, exchange)
            risk    = _risk_for(o, candles)
            mode    = risk["mode"]
            atr     = risk["atr"]
            filled  = risk["filled"]

            # -- ATR Risk block -----------------------------------------------
            print(f"        -- ATR Risk params  (mode: {mode}) --")
            if filled:
                print(f"        Entry        : {risk['entry']:.2f}")
                print(f"        Stop-Loss    : {risk['sl_price']:.2f}  "
                      f"(-{risk['sl_pts']:.1f} pts from entry)")
                print(f"        Target       : {risk['tgt_price']:.2f}  "
                      f"(+{risk['tgt_pts']:.1f} pts from entry)")
                print(f"        Break-Even   : {risk['be_price']:.2f}  "
                      f"(-{risk['be_pts']:.1f} pts from entry, move SL here after +{risk['be_pts']:.1f} pts gain)")
                print(f"        Trail step   : {risk['trail_pts']:.1f} pts")
                if atr:
                    print(f"        ATR(14) 5m   : {atr:.2f}")
            else:
                note = f"order {status} -- no fill price"
                print(f"        Entry        : N/A  ({note})")
                print(f"        Stop-Loss    : {risk['sl_pts']:.1f} pts  (absolute price needs fill)")
                print(f"        Target       : {risk['tgt_pts']:.1f} pts  (absolute price needs fill)")
                print(f"        Break-Even   : {risk['be_pts']:.1f} pts  (absolute price needs fill)")
                print(f"        Trail step   : {risk['trail_pts']:.1f} pts")
                if atr:
                    print(f"        ATR(14) 5m   : {atr:.2f}")

            # -- UST (Trailing Stop) block ------------------------------------
            ust_enabled = settings.USE_TRAILING_STOP_EXIT
            ust_flag    = "ENABLED  [OK]" if ust_enabled else "DISABLED [WARNING: no trailing stop]"
            print(f"        -- USE_TRAILING_STOP_EXIT (UST) = {ust_enabled}  -> {ust_flag} --")
            if ust_enabled:
                sl_pts    = risk["sl_pts"]
                be_pts    = risk["be_pts"]
                trail_pts = risk["trail_pts"]
                if filled:
                    entry = risk["entry"]
                    tsm = TrailingStopManager(
                        entry_price=entry,
                        initial_sl_points=sl_pts,
                        break_even_trigger_points=be_pts,
                        trail_step_points=trail_pts,
                    )
                    print(f"        UST initial stop : {tsm.current_stop:.2f}  "
                          f"(entry {entry:.2f} - {sl_pts:.1f} pts)")
                    print(f"        UST BE triggers  : LTP >= {entry + be_pts:.2f}  "
                          f"(+{be_pts:.1f} pts)  -> stop moves to {entry:.2f}")
                    print(f"        UST trail step   : every +{trail_pts:.1f} pts above BE, "
                          f"stop rises by {trail_pts:.1f} pts")
                    print(f"        UST trail levels :")
                    for step in range(1, 4):
                        ltp_needed = entry + be_pts + (step * trail_pts)
                        stop_at    = entry + (step * trail_pts)
                        print(f"          step {step}: LTP >= {ltp_needed:.2f}  -> stop = {stop_at:.2f}")
                else:
                    print(f"        UST would use    : SL={sl_pts:.1f} pts  "
                          f"BE={be_pts:.1f} pts  trail={trail_pts:.1f} pts")
                    print(f"        UST initial stop : entry - {sl_pts:.1f} pts  (needs fill price)")
                    print(f"        UST BE triggers  : entry + {be_pts:.1f} pts  (needs fill price)")
            else:
                print(f"        [UST disabled -- no trailing stop for this order]")

        else:
            # SELL / exit order — show fill only, no risk block
            direction = "exit/SL order"
            print(f"        [{direction} -- no risk block for SELL]")

        print()

    print(SEP)


if __name__ == "__main__":
    main()
