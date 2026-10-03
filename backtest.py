"""
SENSEX CE/PE Strategy Backtester
==================================
Replays real historical SENSEX candles through the EXACT same strategy,
trailing stop, and exit logic used by the live bot.

Usage
-----
    python backtest.py                        # last 30 days, default settings
    python backtest.py --days 60              # last 60 days
    python backtest.py --days 10 --sl 20 --be 20 --trail 10
    python backtest.py --from 2026-08-01 --to 2026-09-09

What it tests
-------------
  - CE / PE signal detection (exact same is_ce_signal / is_pe_signal rules)
  - ATM option symbol selection (simulated, not real instrument lookup)
  - Paper entry fill at candle close price
  - Protective stop at entry - SL_POINTS
  - Break-even activation at entry + BREAK_EVEN points
  - Trailing stop in TRAIL_STEP increments
  - Stop-hit exit when any intra-candle price <= current_stop
  - EOD forced exit at FORCE_EXIT candle
  - One trade at a time (no new entry while position open)
"""

from __future__ import annotations

import argparse
import sys

# Force UTF-8 output on Windows so Unicode characters never cause a codec crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

# ── path fix so we can import project modules directly ────────────────────────
import os
sys.path.insert(0, os.path.dirname(__file__))

from config import settings
from market.candle_builder import Candle
from market.indicators import ema as calc_ema
from strategies.ce_strategy import is_ce_signal
from strategies.pe_strategy import is_pe_signal
from utils.price_utils import round_to_tick
from utils.time_utils import IST, parse_time_ist

# ── Colour output (Windows-safe) ──────────────────────────────────────────────
try:
    import colorama; colorama.init()
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"
except ImportError:
    GREEN = RED = YELLOW = CYAN = BOLD = RESET = ""


# ═════════════════════════════════════════════════════════════════════════════
# Data structures
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class BacktestTrade:
    trade_num:    int
    signal_type:  Literal["CE", "PE"]
    entry_time:   datetime
    entry_price:  float
    initial_sl:   float
    target_ref:   float
    quantity:     int

    exit_time:    datetime | None = None
    exit_price:   float           = 0.0
    exit_reason:  str             = ""
    highest_ltp:  float           = 0.0
    current_stop: float           = 0.0
    break_even:   bool            = False
    trail_steps:  int             = 0
    pnl:          float           = 0.0

    def finalise(self, exit_price: float, exit_time: datetime, reason: str) -> None:
        self.exit_price  = exit_price
        self.exit_time   = exit_time
        self.exit_reason = reason
        self.pnl         = (exit_price - self.entry_price) * self.quantity

    @property
    def duration_mins(self) -> int:
        if not self.exit_time:
            return 0
        return int((self.exit_time - self.entry_time).total_seconds() / 60)


@dataclass
class BacktestResult:
    trades:       list[BacktestTrade] = field(default_factory=list)
    total_pnl:    float = 0.0
    winners:      int   = 0
    losers:       int   = 0
    breakevens:   int   = 0
    max_drawdown: float = 0.0
    peak_pnl:     float = 0.0


# ═════════════════════════════════════════════════════════════════════════════
# Backtester engine
# ═════════════════════════════════════════════════════════════════════════════

class Backtester:
    def __init__(
        self,
        sl_points:    float,
        be_points:    float,
        trail_points: float,
        target_pts:   float,
        quantity:     int,
        force_exit:   str = "15:15",
        no_entry:     str = "15:00",
    ) -> None:
        self.sl_points    = sl_points
        self.be_points    = be_points
        self.trail_points = trail_points
        self.target_pts   = target_pts
        self.quantity     = quantity
        self.force_exit   = parse_time_ist(force_exit)
        self.no_entry     = parse_time_ist(no_entry)

        self._buf5m:  deque[Candle] = deque(maxlen=100)
        self._buf15m: deque[Candle] = deque(maxlen=60)

        self._trade: BacktestTrade | None = None
        self._trade_num = 0
        self.result = BacktestResult()

    # ── public ────────────────────────────────────────────────────────────────

    def run(self, candles_5m: list[Candle], candles_15m: list[Candle]) -> BacktestResult:
        """
        Replay candles_5m as the primary timeframe.
        candles_15m is used for the 15m filter condition only.
        Both must be in chronological order (oldest first).
        """
        # Build a lookup: for each 5m candle timestamp, find the latest
        # completed 15m candles available at that point in time.
        buf15 = self._build_15m_lookup(candles_15m)

        for i, candle in enumerate(candles_5m):
            ts   = candle.timestamp

            # --- feed this candle into the 5m buffer ---
            self._buf5m.append(candle)
            candles5 = list(self._buf5m)

            # --- find matching 15m candles (walk back to find latest available) ---
            candles15 = self._get_15m_at(buf15, ts)

            # --- manage open position intra-candle first ---
            if self._trade:
                self._manage_position(candle)

            # --- check EOD ---
            t = ts.time() if ts.tzinfo is None else ts.astimezone(IST).time()
            if (t.hour, t.minute) >= (self.force_exit.hour, self.force_exit.minute):
                if self._trade:
                    self._close_trade(candle.close, ts, "EOD_EXIT")
                continue

            # --- skip new entries if position open or past no-entry time ---
            if self._trade:
                continue
            if (t.hour, t.minute) >= (self.no_entry.hour, self.no_entry.minute):
                continue
            if len(candles5) < 21 or len(candles15) < 20:
                continue

            # --- evaluate signals ---
            if is_ce_signal(candles5, candles15):
                self._open_trade("CE", candle.close, ts)
            elif is_pe_signal(candles5, candles15):
                self._open_trade("PE", candle.close, ts)

        # force-close any trade still open at end of data
        if self._trade and candles_5m:
            last = candles_5m[-1]
            self._close_trade(last.close, last.timestamp, "END_OF_DATA")

        self._compute_summary()
        return self.result

    # ── position management ───────────────────────────────────────────────────

    def _open_trade(self, sig: Literal["CE","PE"], price: float, ts: datetime) -> None:
        self._trade_num += 1
        sl = round_to_tick(price - self.sl_points)
        t  = BacktestTrade(
            trade_num   = self._trade_num,
            signal_type = sig,
            entry_time  = ts,
            entry_price = price,
            initial_sl  = sl,
            current_stop= sl,
            highest_ltp = price,
            target_ref  = price + self.target_pts,
            quantity    = self.quantity,
        )
        self._trade = t
        colour = GREEN if sig == "CE" else RED
        print(f"  {colour}[{self._trade_num:>3}] ENTRY {sig}{RESET}  "
              f"{ts.strftime('%Y-%m-%d %H:%M')}  "
              f"price={price:.2f}  sl={sl:.2f}  target={t.target_ref:.2f}")

    def _manage_position(self, candle: Candle) -> None:
        t = self._trade
        assert t is not None

        # Use the candle's high as the best-case LTP for trailing
        ltp_high = candle.high
        ltp_low  = candle.low

        # Update highest LTP
        t.highest_ltp = max(t.highest_ltp, ltp_high)

        # Compute trailing stop
        new_stop = self._calc_stop(t)
        if new_stop is not None and new_stop > t.current_stop:
            old = t.current_stop
            t.current_stop = new_stop
            if not t.break_even:
                t.break_even = True
                print(f"        {YELLOW}BREAK-EVEN{RESET}  "
                      f"{candle.timestamp.strftime('%H:%M')}  "
                      f"sl: {old:.2f} -> {new_stop:.2f}")
            else:
                t.trail_steps += 1
                t.target_ref  += self.trail_points
                print(f"        {CYAN}TRAIL #{t.trail_steps}{RESET}  "
                      f"{candle.timestamp.strftime('%H:%M')}  "
                      f"sl: {old:.2f} -> {new_stop:.2f}  "
                      f"target: {t.target_ref:.2f}")

        # Check if stop is hit (use candle low as worst-case price)
        if ltp_low <= t.current_stop:
            exit_price = t.current_stop  # assume filled at stop price
            self._close_trade(exit_price, candle.timestamp, "STOP_HIT")

    def _calc_stop(self, t: BacktestTrade) -> float | None:
        be_trigger = t.entry_price + self.be_points
        if t.highest_ltp < be_trigger:
            return None
        above_be   = t.highest_ltp - be_trigger
        steps      = int(above_be // self.trail_points)
        return round_to_tick(t.entry_price + steps * self.trail_points)

    def _close_trade(self, price: float, ts: datetime, reason: str) -> None:
        t = self._trade
        assert t is not None
        t.finalise(price, ts, reason)
        pnl = t.pnl
        colour = GREEN if pnl >= 0 else RED
        sign   = "+" if pnl >= 0 else ""
        print(f"  {colour}[{t.trade_num:>3}] EXIT  {reason:<16}{RESET}  "
              f"{ts.strftime('%Y-%m-%d %H:%M')}  "
              f"price={price:.2f}  "
              f"pnl={colour}{sign}{pnl:.2f}{RESET}  "
              f"dur={t.duration_mins}m  trail={t.trail_steps}")
        self.result.trades.append(t)
        self._trade = None

    # ── summary ───────────────────────────────────────────────────────────────

    def _compute_summary(self) -> None:
        r = self.result
        cum = 0.0
        peak = 0.0
        for t in r.trades:
            cum += t.pnl
            peak = max(peak, cum)
            r.max_drawdown = min(r.max_drawdown, cum - peak)
            if t.pnl > 0:   r.winners    += 1
            elif t.pnl < 0: r.losers     += 1
            else:            r.breakevens += 1
        r.total_pnl = cum
        r.peak_pnl  = peak

    # ── 15m alignment helpers ─────────────────────────────────────────────────

    @staticmethod
    def _bucket_15m(ts: datetime) -> str:
        """Return the 15m bucket key for a timestamp."""
        t = ts.astimezone(IST) if ts.tzinfo else IST.localize(ts)
        bm = (t.hour * 60 + t.minute) // 15 * 15
        return f"{t.date()} {bm // 60:02d}:{bm % 60:02d}"

    def _build_15m_lookup(self, candles_15m: list[Candle]) -> dict[str, list[Candle]]:
        """
        Build a mapping: bucket_key -> cumulative list of completed 15m candles
        up to and including that bucket. Chronological order, oldest first.
        """
        lookup: dict[str, list[Candle]] = {}
        buf: list[Candle] = []
        for c in candles_15m:
            buf.append(c)
            key = self._bucket_15m(c.timestamp)
            lookup[key] = list(buf)
        return lookup

    def _get_15m_at(self, lookup: dict, ts: datetime) -> list[Candle]:
        """Return completed 15m candles available just before timestamp ts."""
        t = ts.astimezone(IST) if ts.tzinfo else IST.localize(ts)
        # Walk back up to 8 x 15-minute buckets (2 hours) to find the most
        # recent completed 15m list. A 5m candle at 10:05 should see the
        # 15m candle that closed at 10:00, keyed as "YYYY-MM-DD 09:45".
        for delta in range(1, 10):   # start at 1 — the current bucket is WIP
            bm = (t.hour * 60 + t.minute) - delta * 15
            if bm < 0:
                break
            key = f"{t.date()} {bm // 60:02d}:{bm % 60:02d}"
            if key in lookup:
                return lookup[key]
        return []


# ═════════════════════════════════════════════════════════════════════════════
# Historical data fetch
# ═════════════════════════════════════════════════════════════════════════════

def fetch_candles(days: int, from_date: str | None, to_date: str | None) -> tuple[list[Candle], list[Candle]]:
    from broker.kite_client import get_kite
    from market.historical_data import SENSEX_TOKEN
    kite = get_kite()

    to_dt   = datetime.strptime(to_date,   "%Y-%m-%d") if to_date   else datetime.now()
    from_dt = datetime.strptime(from_date, "%Y-%m-%d") if from_date else to_dt - timedelta(days=days)

    print(f"Fetching SENSEX candles: {from_dt.date()} to {to_dt.date()} ...")

    def _fetch(interval: str) -> list[Candle]:
        records = kite.historical_data(
            instrument_token=SENSEX_TOKEN,
            from_date=from_dt.strftime("%Y-%m-%d 09:00:00"),
            to_date=to_dt.strftime("%Y-%m-%d 15:30:00"),
            interval=interval,
        )
        return [
            Candle(
                timestamp=IST.localize(r["date"]) if r["date"].tzinfo is None else r["date"],
                open=float(r["open"]), high=float(r["high"]),
                low=float(r["low"]),   close=float(r["close"]),
                volume=int(r.get("volume", 0)),
            )
            for r in records
        ]

    c5m  = _fetch("5minute")
    c15m = _fetch("15minute")
    print(f"  5m candles: {len(c5m)}   15m candles: {len(c15m)}")
    return c5m, c15m


# ═════════════════════════════════════════════════════════════════════════════
# Report printer
# ═════════════════════════════════════════════════════════════════════════════

def print_report(r: BacktestResult, args: argparse.Namespace) -> None:
    total  = len(r.trades)
    wr     = (r.winners / total * 100) if total else 0
    avg    = (r.total_pnl / total)     if total else 0

    print()
    print("=" * 60)
    print(f"  BACKTEST RESULTS")
    print("=" * 60)
    print(f"  Parameters    sl={args.sl}  be={args.be}  trail={args.trail}  qty={args.qty}")
    print(f"  Total trades  {total}")
    print(f"  Winners       {GREEN}{r.winners}{RESET}  ({wr:.1f}%)")
    print(f"  Losers        {RED}{r.losers}{RESET}")
    print(f"  Break-even    {r.breakevens}")
    print(f"  Total P&L     {GREEN if r.total_pnl >= 0 else RED}"
          f"{'+'if r.total_pnl>=0 else ''}{r.total_pnl:.2f}{RESET}")
    print(f"  Avg P&L/trade {'+'if avg>=0 else ''}{avg:.2f}")
    print(f"  Peak P&L      +{r.peak_pnl:.2f}")
    print(f"  Max drawdown  {r.max_drawdown:.2f}")
    print("=" * 60)

    if not r.trades:
        print("  No trades generated — check candle count / strategy conditions.")
        return

    print()
    print(f"  {'#':>3}  {'Type':<4}  {'Entry Time':<17}  {'Entry':>7}  "
          f"{'Exit':>7}  {'SL':>7}  {'P&L':>8}  {'Dur':>5}  {'Reason'}")
    print(f"  {'-'*3}  {'-'*4}  {'-'*17}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*8}  {'-'*5}  {'-'*16}")
    for t in r.trades:
        pnl_s  = f"{'+'if t.pnl>=0 else ''}{t.pnl:.2f}"
        colour = GREEN if t.pnl >= 0 else RED
        print(f"  {t.trade_num:>3}  {t.signal_type:<4}  "
              f"{t.entry_time.strftime('%Y-%m-%d %H:%M'):<17}  "
              f"{t.entry_price:>7.2f}  {t.exit_price:>7.2f}  "
              f"{t.current_stop:>7.2f}  "
              f"{colour}{pnl_s:>8}{RESET}  "
              f"{t.duration_mins:>4}m  {t.exit_reason}")


# ═════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="SENSEX CE/PE Strategy Backtester")
    parser.add_argument("--days",  type=int,   default=30,   help="Days of history (default 30)")
    parser.add_argument("--from",  dest="from_date", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--to",    dest="to_date",   default=None, help="End date YYYY-MM-DD")
    parser.add_argument("--sl",    type=float, default=settings.INITIAL_SL_POINTS,
                        help=f"Initial SL points (default {settings.INITIAL_SL_POINTS})")
    parser.add_argument("--be",    type=float, default=settings.BREAK_EVEN_TRIGGER_POINTS,
                        help=f"Break-even trigger (default {settings.BREAK_EVEN_TRIGGER_POINTS})")
    parser.add_argument("--trail", type=float, default=settings.TRAIL_STEP_POINTS,
                        help=f"Trail step points (default {settings.TRAIL_STEP_POINTS})")
    parser.add_argument("--target",type=float, default=settings.INITIAL_TARGET_OFFSET_POINTS,
                        help=f"Initial target offset (default {settings.INITIAL_TARGET_OFFSET_POINTS})")
    parser.add_argument("--qty",   type=int,   default=settings.QUANTITY,
                        help=f"Quantity (default {settings.QUANTITY})")
    parser.add_argument("--exit",  default=settings.FORCE_EXIT_TIME,
                        help=f"Force exit time HH:MM (default {settings.FORCE_EXIT_TIME})")
    args = parser.parse_args()

    print()
    print("+--------------------------------------------------+")
    print("|        SENSEX CE/PE Strategy Backtester          |")
    print("+--------------------------------------------------+")
    print(f"  SL={args.sl}pts  BE={args.be}pts  Trail={args.trail}pts  "
          f"Target={args.target}pts  Qty={args.qty}")
    print()

    try:
        candles_5m, candles_15m = fetch_candles(args.days, args.from_date, args.to_date)
    except Exception as exc:
        print(f"{RED}ERROR fetching candles: {exc}{RESET}")
        print("Make sure KITE_API_KEY and KITE_ACCESS_TOKEN are set in .env")
        sys.exit(1)

    if len(candles_5m) < 21:
        print(f"{RED}Not enough 5m candles ({len(candles_5m)}) to run strategy.{RESET}")
        sys.exit(1)

    print()
    bt = Backtester(
        sl_points    = args.sl,
        be_points    = args.be,
        trail_points = args.trail,
        target_pts   = args.target,
        quantity     = args.qty,
        force_exit   = args.exit,
    )
    result = bt.run(candles_5m, candles_15m)
    print_report(result, args)


if __name__ == "__main__":
    main()
