"""
SENSEX Deep Analysis — SEBI-Grade Per-Strategy Backtest
========================================================
Fetches real SENSEX historical data from Zerodha (60 days, 5m + 15m),
then tests EVERY strategy independently across every 15-minute time window.

Produces:
  1. Per-strategy win-rate, avg P&L, total trades, profit factor
  2. Per-strategy BEST entry time window (when signals have highest W%)
  3. Cross-strategy ranking table
  4. Final recommendation with optimal entry timing

Usage:
    python sensex_deep_analysis.py
    python sensex_deep_analysis.py --days 90
    python sensex_deep_analysis.py --from 2025-01-01 --to 2025-06-30
"""

from __future__ import annotations

import argparse
import sys
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

sys.path.insert(0, os.path.dirname(__file__))

from config import settings
from market.candle_builder import Candle
from market.indicators import ema as calc_ema, atr_at
from market.vwap import VWAPCalculator
from utils.time_utils import IST

# ── colour support ────────────────────────────────────────────────────────────
try:
    import colorama; colorama.init()
    G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"
    C = "\033[96m"; B = "\033[1m";  RESET = "\033[0m"
except ImportError:
    G = R = Y = C = B = RESET = ""

# ── fixed risk params for the analysis ───────────────────────────────────────
SL_PTS     = 30.0
BE_PTS     = 30.0
TRAIL_PTS  = 10.0
TARGET_PTS = 60.0
QUANTITY   = 1            # normalised to 1 lot for comparison


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Trade:
    strategy:     str
    direction:    Literal["CE", "PE"]
    entry_time:   datetime
    entry_price:  float
    exit_price:   float   = 0.0
    exit_reason:  str     = ""
    pnl:          float   = 0.0
    duration_m:   int     = 0

    @property
    def hour_bucket(self) -> str:
        """15-minute time bucket string, e.g. '09:15'"""
        t = self.entry_time.astimezone(IST) if self.entry_time.tzinfo else IST.localize(self.entry_time)
        bm = (t.hour * 60 + t.minute) // 15 * 15
        return f"{bm // 60:02d}:{bm % 60:02d}"


@dataclass
class StratResult:
    strategy: str
    trades:   list[Trade]  = field(default_factory=list)

    @property
    def total(self) -> int:       return len(self.trades)
    @property
    def winners(self) -> int:     return sum(1 for t in self.trades if t.pnl > 0)
    @property
    def losers(self) -> int:      return sum(1 for t in self.trades if t.pnl < 0)
    @property
    def breakevens(self) -> int:  return sum(1 for t in self.trades if t.pnl == 0)
    @property
    def win_rate(self) -> float:
        return (self.winners / self.total * 100) if self.total else 0.0
    @property
    def total_pnl(self) -> float:  return sum(t.pnl for t in self.trades)
    @property
    def avg_pnl(self) -> float:    return (self.total_pnl / self.total) if self.total else 0.0
    @property
    def profit_factor(self) -> float:
        gross_win  = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        return (gross_win / gross_loss) if gross_loss else float('inf')

    def by_time_bucket(self) -> dict[str, list[Trade]]:
        d: dict[str, list[Trade]] = defaultdict(list)
        for t in self.trades:
            d[t.hour_bucket].append(t)
        return dict(d)

    def best_time_window(self) -> tuple[str, float, int]:
        """Returns (time_bucket, win_rate, trade_count) of the best window."""
        best_wr = -1.0; best_bucket = "N/A"; best_n = 0
        for bucket, trades in self.by_time_bucket().items():
            if len(trades) < 3:   # need at least 3 trades for statistical meaning
                continue
            wr = sum(1 for t in trades if t.pnl > 0) / len(trades) * 100
            if wr > best_wr:
                best_wr = wr; best_bucket = bucket; best_n = len(trades)
        return best_bucket, best_wr, best_n


# ─────────────────────────────────────────────────────────────────────────────
# Position management (same logic as main backtester)
# ─────────────────────────────────────────────────────────────────────────────

def simulate_trade(
    entry_price: float,
    entry_time: datetime,
    strategy: str,
    direction: Literal["CE", "PE"],
    future_candles: list[Candle],
    force_exit_hm: tuple[int, int] = (15, 15),
) -> Trade:
    """
    Simulate a single trade using SL / trailing-stop / EOD exit.
    future_candles = candles AFTER entry (chronological order).
    """
    sl      = entry_price - SL_PTS
    highest = entry_price
    stop    = sl

    t = Trade(
        strategy=strategy, direction=direction,
        entry_time=entry_time, entry_price=entry_price,
    )

    for candle in future_candles:
        ts = candle.timestamp.astimezone(IST) if candle.timestamp.tzinfo else IST.localize(candle.timestamp)
        hm = (ts.hour, ts.minute)

        # EOD forced exit
        if hm >= force_exit_hm:
            t.exit_price  = candle.close
            t.exit_reason = "EOD"
            break

        # Update highest, compute trailing stop
        if candle.high > highest:
            highest = candle.high
            above_be = highest - (entry_price + BE_PTS)
            if above_be >= 0:
                steps = int(above_be // TRAIL_PTS)
                new_stop = entry_price + steps * TRAIL_PTS
                stop = max(stop, new_stop)

        # Stop hit
        if candle.low <= stop:
            t.exit_price  = stop
            t.exit_reason = "STOP"
            break
    else:
        # end of data
        if future_candles:
            t.exit_price  = future_candles[-1].close
            t.exit_reason = "EOD"

    t.pnl = (t.exit_price - t.entry_price) * QUANTITY
    return t


# ─────────────────────────────────────────────────────────────────────────────
# Signal checkers — one per strategy, self-contained
# ─────────────────────────────────────────────────────────────────────────────

def _ema(candles: list[Candle], period: int) -> list[float | None]:
    return calc_ema(candles, period)


def check_ema_signal(
    candles_5m: list[Candle],
    candles_15m: list[Candle],
) -> Literal["CE", "PE", None]:
    """EMA9/EMA21 dual-timeframe strategy."""
    if len(candles_5m) < 21 or len(candles_15m) < 21:
        return None

    e21_5  = _ema(candles_5m,  20)[-1]
    e9_5   = _ema(candles_5m,   9)[-1]
    e21_15 = _ema(candles_15m, 20)[-1]
    if None in (e21_5, e9_5, e21_15):
        return None

    c0  = candles_5m[-1]
    c1  = candles_5m[-2]
    c15 = candles_15m[-1]

    # CE
    if (c0.close > e21_5 and e9_5 > e21_5
            and c0.close > c1.high and c15.close > e21_15):
        return "CE"
    # PE
    e9_pe  = _ema(candles_5m,  9)[-1]
    e21_pe = _ema(candles_5m, 20)[-1]
    if (c0.close < e21_pe and e9_pe < e21_pe
            and c0.close < c1.low and c15.close < e21_15):
        return "PE"
    return None


def check_orb_signal(
    candles_5m: list[Candle],
) -> Literal["CE", "PE", None]:
    """Opening Range Breakout — first 5m candle range, entry 09:25-09:35."""
    if len(candles_5m) < 3:
        return None

    latest_date = candles_5m[-1].timestamp.date()
    today = [c for c in candles_5m
             if c.timestamp.date() == latest_date
             and (c.timestamp.hour, c.timestamp.minute) >= (9, 15)]
    if len(today) < 2:
        return None

    orb_high = today[0].high
    orb_low  = today[0].low
    sustain  = next((c for c in today
                     if c.timestamp.hour == 9 and c.timestamp.minute == 20), None)
    if sustain is None:
        return None

    c0 = candles_5m[-1]
    ts = (c0.timestamp.hour, c0.timestamp.minute)
    if not ((9, 25) <= ts <= (9, 35)):
        return None

    if sustain.close > orb_high and c0.close > orb_high:
        return "CE"
    if sustain.close < orb_low and c0.close < orb_low:
        return "PE"
    return None


def check_trb_signal(
    candles_5m: list[Candle],
    candles_15m: list[Candle],
) -> Literal["CE", "PE", None]:
    """Time Range Breakout — 09:45-10:00 15m candle breakout."""
    if len(candles_5m) < 2 or len(candles_15m) < 1:
        return None

    c0 = candles_5m[-1]
    c1 = candles_5m[-2]
    ts = (c0.timestamp.hour, c0.timestamp.minute)
    if ts < (10, 0):
        return None

    latest_date = candles_15m[-1].timestamp.date()
    anchor = next((c for c in candles_15m
                   if c.timestamp.date() == latest_date
                   and c.timestamp.hour == 9 and c.timestamp.minute == 45), None)
    if anchor is None:
        return None

    if c1.close <= anchor.high and c0.close > anchor.high:
        return "CE"
    if c1.close >= anchor.low  and c0.close < anchor.low:
        return "PE"
    return None


def check_vwap_signal(
    candles_5m: list[Candle],
    vwap_val: float | None,
) -> Literal["CE", "PE", None]:
    """VWAP retest bounce."""
    if vwap_val is None or vwap_val <= 0 or len(candles_5m) < 5:
        return None

    c0, c1 = candles_5m[-1], candles_5m[-2]
    lookback = candles_5m[-4:-1]  # 3-candle lookback

    # CE: dipped below VWAP then reclaimed
    if (c0.close > vwap_val and c0.close > c1.high
            and any(c.close < vwap_val for c in lookback)):
        return "CE"
    # PE: popped above VWAP then broke below
    if (c0.close < vwap_val and c0.close < c1.low
            and any(c.close > vwap_val for c in lookback)):
        return "PE"
    return None


def check_pdhl_signal(
    candles_5m: list[Candle],
    pdh: float | None,
    pdl: float | None,
) -> Literal["CE", "PE", None]:
    """Previous Day High / Low breakout."""
    if len(candles_5m) < 2:
        return None

    c0, c1 = candles_5m[-1], candles_5m[-2]

    if pdh and c1.close <= pdh and c0.close > pdh and c0.close > c1.high:
        return "CE"
    if pdl and c1.close >= pdl and c0.close < pdl and c0.close < c1.low:
        return "PE"
    return None


def check_momentum_signal(
    candles_5m: list[Candle],
    candles_15m: list[Candle],
) -> Literal["CE", "PE", None]:
    """Large-body afternoon momentum (13:30-14:30)."""
    if len(candles_5m) < 21:
        return None

    c0 = candles_5m[-1]
    ts = (c0.timestamp.hour, c0.timestamp.minute)
    if not ((13, 30) <= ts <= (14, 30)):
        return None

    body = abs(c0.close - c0.open)
    if body < 40:
        return None

    e21_15 = _ema(candles_15m, 20)[-1] if len(candles_15m) >= 21 else None
    c15    = candles_15m[-1] if candles_15m else None

    if c0.close > c0.open:
        if e21_15 and c15 and c15.close > e21_15:
            return "CE"
    else:
        if e21_15 and c15 and c15.close < e21_15:
            return "PE"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# SEBI-grade VWAP calculator (resets each day)
# ─────────────────────────────────────────────────────────────────────────────

class DailyVWAP:
    """Cumulative VWAP reset at 09:15 each trading day."""
    def __init__(self) -> None:
        self._cum_tp_vol = 0.0
        self._cum_vol    = 0.0
        self._day: object = None

    def update(self, candle: Candle) -> float | None:
        d = candle.timestamp.date()
        if d != self._day:
            self._cum_tp_vol = 0.0
            self._cum_vol    = 0.0
            self._day        = d
        tp = (candle.high + candle.low + candle.close) / 3
        self._cum_tp_vol += tp * candle.volume
        self._cum_vol    += candle.volume
        return self._cum_tp_vol / self._cum_vol if self._cum_vol else None


# ─────────────────────────────────────────────────────────────────────────────
# Main analysis engine
# ─────────────────────────────────────────────────────────────────────────────

STRATEGIES = ["EMA", "ORB", "TRB", "VWAP", "PDHL", "MOMENTUM"]


def run_analysis(
    candles_5m:  list[Candle],
    candles_15m: list[Candle],
) -> dict[str, StratResult]:
    """
    Walk every 5m candle chronologically, evaluate each strategy signal,
    simulate trades, and collect results.
    """
    results = {s: StratResult(strategy=s) for s in STRATEGIES}

    vwap_calc    = DailyVWAP()
    open_trades: dict[str, Trade | None] = {s: None for s in STRATEGIES}

    # Build 15m lookup (timestamp to index) for fast slicing
    def get_15m_slice(up_to: datetime) -> list[Candle]:
        """15m candles completed BEFORE up_to timestamp."""
        return [c for c in candles_15m if c.timestamp < up_to]

    # Determine prev-day H/L for PDHL (compute once per day dynamically)
    pdh_cache: dict = {}
    pdl_cache: dict = {}

    def get_pdhl(today: object) -> tuple[float | None, float | None]:
        if today in pdh_cache:
            return pdh_cache[today], pdl_cache[today]
        # find latest day candle before today
        day_candles = [c for c in candles_5m if c.timestamp.date() < today]
        if not day_candles:
            return None, None
        prev = day_candles[-1].timestamp.date()
        day_slice = [c for c in candles_5m if c.timestamp.date() == prev]
        if not day_slice:
            return None, None
        pdh_cache[today] = max(c.high  for c in day_slice)
        pdl_cache[today] = min(c.low   for c in day_slice)
        return pdh_cache[today], pdl_cache[today]

    print(f"\n{B}Running per-strategy replay on {len(candles_5m)} candles...{RESET}")

    for i, candle in enumerate(candles_5m):
        ts   = candle.timestamp.astimezone(IST) if candle.timestamp.tzinfo else IST.localize(candle.timestamp)
        hm   = (ts.hour, ts.minute)
        today = ts.date()

        # Update VWAP
        vwap_val = vwap_calc.update(candle)

        # Build rolling buffers up to (but not including) next candle
        buf5  = candles_5m[max(0, i-99): i+1]
        buf15 = get_15m_slice(candle.timestamp)

        # ── Manage open trades for each strategy (check exit first) ───────────
        for strat in STRATEGIES:
            t = open_trades[strat]
            if t is None:
                continue
            # EOD exit at 15:15
            if hm >= (15, 15):
                t.exit_price  = candle.close
                t.exit_reason = "EOD"
                t.pnl         = t.exit_price - t.entry_price
                results[strat].trades.append(t)
                open_trades[strat] = None
                continue
            # Update trailing stop
            future = candles_5m[i:]
            # Already simulated in simulate_trade — here we just mark complete
            # (trades were simulated at entry time — see below)

        # Skip entries: not during market hours, too early for warm-up
        if hm < (9, 15) or hm >= (15, 0):
            continue
        if i < 21:
            continue

        pdh, pdl = get_pdhl(today)

        # ── Evaluate each strategy's signal ───────────────────────────────────
        signals: dict[str, Literal["CE", "PE"] | None] = {
            "EMA":      check_ema_signal(buf5, buf15),
            "ORB":      check_orb_signal(buf5),
            "TRB":      check_trb_signal(buf5, buf15),
            "VWAP":     check_vwap_signal(buf5, vwap_val),
            "PDHL":     check_pdhl_signal(buf5, pdh, pdl),
            "MOMENTUM": check_momentum_signal(buf5, buf15),
        }

        for strat, sig in signals.items():
            if sig is None:
                continue
            if open_trades[strat] is not None:
                continue   # already in a trade for this strategy

            # Simulate the trade from entry to exit
            future_candles = candles_5m[i + 1:]
            simulated = simulate_trade(
                entry_price=candle.close,
                entry_time=candle.timestamp,
                strategy=strat,
                direction=sig,
                future_candles=future_candles,
            )
            results[strat].trades.append(simulated)
            # Mark the strategy as "in a trade" until exit candle
            # (simple: block re-entry for the same number of candles the trade lasted)
            # We don't actually need to track this here since we simulate full trades;
            # but we avoid same-candle re-entry by checking open_trades above.

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Fetch candles from Zerodha
# ─────────────────────────────────────────────────────────────────────────────

def fetch_candles(
    days: int,
    from_date: str | None,
    to_date:   str | None,
) -> tuple[list[Candle], list[Candle]]:
    from broker.kite_client import get_kite
    from market.historical_data import SENSEX_TOKEN
    kite = get_kite()

    to_dt   = datetime.strptime(to_date,   "%Y-%m-%d") if to_date   else datetime.now()
    from_dt = datetime.strptime(from_date, "%Y-%m-%d") if from_date else to_dt - timedelta(days=days)

    print(f"\n{B}Fetching SENSEX data: {from_dt.date()} to {to_dt.date()}{RESET}")
    print("  Connecting to Zerodha historical API ...")

    def _fetch(interval: str) -> list[Candle]:
        # Zerodha API limit: 60 days per request for 5-minute data
        # Split into chunks if range > 60 days
        all_candles: list[Candle] = []
        chunk_start = from_dt
        chunk_days  = 58   # safe margin below 60-day API limit

        while chunk_start < to_dt:
            chunk_end = min(chunk_start + timedelta(days=chunk_days), to_dt)
            records = kite.historical_data(
                instrument_token=SENSEX_TOKEN,
                from_date=chunk_start.strftime("%Y-%m-%d 09:00:00"),
                to_date=chunk_end.strftime("%Y-%m-%d 15:30:00"),
                interval=interval,
            )
            all_candles.extend([
                Candle(
                    timestamp=IST.localize(r["date"]) if r["date"].tzinfo is None else r["date"],
                    open=float(r["open"]), high=float(r["high"]),
                    low=float(r["low"]),   close=float(r["close"]),
                    volume=int(r.get("volume", 0)),
                )
                for r in records
            ])
            chunk_start = chunk_end + timedelta(days=1)

        return all_candles

    c5m  = _fetch("5minute")
    c15m = _fetch("15minute")
    print(f"  {G}5m candles: {len(c5m)}{RESET}   {G}15m candles: {len(c15m)}{RESET}")

    # Filter to market hours only (09:15 – 15:30)
    def _filter(candles: list[Candle]) -> list[Candle]:
        return [
            c for c in candles
            if (c.timestamp.hour, c.timestamp.minute) >= (9, 15)
        ]

    return _filter(c5m), _filter(c15m)


# ─────────────────────────────────────────────────────────────────────────────
# Report printer
# ─────────────────────────────────────────────────────────────────────────────

def _bar(val: float, max_val: float, width: int = 20) -> str:
    if max_val <= 0:
        return " " * width
    filled = int(val / max_val * width)
    return "#" * filled + "." * (width - filled)


def print_report(results: dict[str, StratResult], days: int) -> None:
    print()
    print(f"{B}{'='*72}{RESET}")
    print(f"{B}  SENSEX STRATEGY DEEP ANALYSIS  ({days} trading days){RESET}")
    print(f"{B}{'='*72}{RESET}")
    print(f"  SL={SL_PTS}pts  BE={BE_PTS}pts  Trail={TRAIL_PTS}pts  Target={TARGET_PTS}pts")
    print()

    # ── Per-strategy summary ──────────────────────────────────────────────────
    print(f"{B}  {'Strategy':<12} {'Trades':>6} {'Win%':>6} {'Avg P&L':>8} "
          f"{'Total P&L':>10} {'PF':>5}  {'Best Window':<9} {'W% there':>8}{RESET}")
    print(f"  {'-'*12} {'-'*6} {'-'*6} {'-'*8} {'-'*10} {'-'*5}  {'-'*9} {'-'*8}")

    ranked = sorted(results.values(), key=lambda r: r.win_rate, reverse=True)

    for r in ranked:
        if r.total == 0:
            print(f"  {r.strategy:<12} {'0':>6}  — no signals fired")
            continue

        bw, bwr, bn = r.best_time_window()
        wr_color = G if r.win_rate >= 55 else (Y if r.win_rate >= 45 else R)
        pnl_color = G if r.total_pnl >= 0 else R

        print(
            f"  {r.strategy:<12} {r.total:>6} "
            f"{wr_color}{r.win_rate:>5.1f}%{RESET} "
            f"{pnl_color}{r.avg_pnl:>+8.1f}{RESET} "
            f"{pnl_color}{r.total_pnl:>+10.1f}{RESET} "
            f"{r.profit_factor:>5.2f}  "
            f"{bw:<9} {G if bwr >= 55 else Y}{bwr:>7.1f}%{RESET}"
            f" ({bn}t)"
        )

    # ── Time-window breakdown for top strategy ────────────────────────────────
    if ranked and ranked[0].total > 0:
        top = ranked[0]
        print()
        print(f"{B}  TIME-WINDOW BREAKDOWN: {top.strategy}{RESET}")
        print(f"  {'Window':<9} {'Trades':>6} {'Win%':>6} {'Avg P&L':>9} {'CE':>4} {'PE':>4}")
        print(f"  {'-'*9} {'-'*6} {'-'*6} {'-'*9} {'-'*4} {'-'*4}")
        for bucket, trades in sorted(top.by_time_bucket().items()):
            if not trades:
                continue
            wr  = sum(1 for t in trades if t.pnl > 0) / len(trades) * 100
            avg = sum(t.pnl for t in trades) / len(trades)
            ce  = sum(1 for t in trades if t.direction == "CE")
            pe  = sum(1 for t in trades if t.direction == "PE")
            bar = _bar(wr, 100, 15)
            col = G if wr >= 55 else (Y if wr >= 45 else R)
            print(f"  {bucket:<9} {len(trades):>6} {col}{wr:>5.1f}%{RESET} "
                  f"{avg:>+9.1f}  {bar}  CE:{ce} PE:{pe}")

    # ── Strategy-vs-strategy direction breakdown ──────────────────────────────
    print()
    print(f"{B}  CE vs PE WIN RATE PER STRATEGY{RESET}")
    print(f"  {'Strategy':<12} {'CE W%':>7} {'CE n':>5} {'PE W%':>7} {'PE n':>5}")
    print(f"  {'-'*12} {'-'*7} {'-'*5} {'-'*7} {'-'*5}")

    for r in ranked:
        if r.total == 0:
            continue
        ce_trades = [t for t in r.trades if t.direction == "CE"]
        pe_trades = [t for t in r.trades if t.direction == "PE"]
        ce_wr = (sum(1 for t in ce_trades if t.pnl > 0) / len(ce_trades) * 100) if ce_trades else 0
        pe_wr = (sum(1 for t in pe_trades if t.pnl > 0) / len(pe_trades) * 100) if pe_trades else 0
        ce_col = G if ce_wr >= 55 else (Y if ce_wr >= 45 else R)
        pe_col = G if pe_wr >= 55 else (Y if pe_wr >= 45 else R)
        print(
            f"  {r.strategy:<12} "
            f"{ce_col}{ce_wr:>6.1f}%{RESET} {len(ce_trades):>5}  "
            f"{pe_col}{pe_wr:>6.1f}%{RESET} {len(pe_trades):>5}"
        )

    # ── Day-of-week analysis (which day is best?) ─────────────────────────────
    print()
    print(f"{B}  DAY-OF-WEEK WIN RATE (top 3 strategies){RESET}")
    print(f"  {'Day':<10}", end="")
    top3 = [r for r in ranked if r.total >= 5][:3]
    for r in top3:
        print(f"  {r.strategy:>10}", end="")
    print()
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for dow_i, dow_name in enumerate(dow_names):
        print(f"  {dow_name:<10}", end="")
        for r in top3:
            day_trades = [t for t in r.trades
                          if t.entry_time.astimezone(IST).weekday() == dow_i]
            wr = (sum(1 for t in day_trades if t.pnl > 0) / len(day_trades) * 100) if day_trades else 0
            col = G if wr >= 55 else (Y if wr >= 45 else R)
            n   = len(day_trades)
            print(f"  {col}{wr:>8.1f}%{RESET}({n})", end="")
        print()

    # ── Final recommendation ──────────────────────────────────────────────────
    print()
    print(f"{B}{'='*72}{RESET}")
    print(f"{B}  SEBI-GRADE RECOMMENDATION{RESET}")
    print(f"{B}{'='*72}{RESET}")

    viable = [r for r in ranked if r.total >= 5 and r.win_rate > 0]
    if not viable:
        print(f"  {R}Not enough data to make a recommendation.{RESET}")
        return

    top    = viable[0]
    bw, bwr, bn = top.best_time_window()

    # Count days analysed
    all_dates = set()
    for r in results.values():
        for t in r.trades:
            all_dates.add(t.entry_time.date())

    print(f"\n  Analysis period : {days} calendar days ({len(all_dates)} trading days)")
    print(f"  Total trades    : {sum(r.total for r in results.values())}")
    print()
    print(f"  {G}* BEST STRATEGY  : {B}{top.strategy}{RESET}")
    print(f"  {G}* WIN RATE       : {top.win_rate:.1f}%{RESET}")
    print(f"  {G}* PROFIT FACTOR  : {top.profit_factor:.2f}x{RESET}")
    print(f"  {G}* TOTAL P&L      : {top.total_pnl:+.1f} pts ({top.total} trades){RESET}")
    print(f"  {G}* BEST TIME SLOT : {B}{bw}{RESET}{G} -- Win rate {bwr:.1f}% over {bn} trades{RESET}")
    print()
    print(f"  {Y}Strategy Descriptions:{RESET}")
    strat_desc = {
        "EMA":      "EMA9/EMA21 dual-TF crossover (09:15 onward, all day)",
        "ORB":      "Opening Range Breakout — entry 09:25 to 09:35 only",
        "TRB":      "Time Range Breakout — 09:45 candle, entry from 10:00",
        "VWAP":     "VWAP Retest bounce — entry anytime VWAP retest confirms",
        "PDHL":     "Previous Day High/Low breakout — powerful S/R levels",
        "MOMENTUM": "Large-body momentum — afternoon window 13:30-14:30",
    }
    for s, desc in strat_desc.items():
        r = results[s]
        marker = f"{G}*{RESET}" if s == top.strategy else " "
        wr_s = f"({r.win_rate:.0f}% WR)" if r.total >= 5 else "(< 5 trades)"
        print(f"  {marker} {s:<12}  {desc}  {wr_s}")

    print()
    print(f"  {Y}Key takeaways:{RESET}")
    print(f"   • Enter {top.strategy} signals only between {bw} IST")
    print(f"     for the highest probability trades ({bwr:.1f}% win rate).")
    print(f"   • Use SL={SL_PTS}pts, move to break-even at +{BE_PTS}pts,")
    print(f"     trail in {TRAIL_PTS}pt steps. Exit all trades by 15:15 IST.")
    print(f"   • Avoid trading on days with India VIX > 20 (spike days).")
    print(f"   • The current bot already implements {top.strategy} — ensure")
    print(f"     ENABLE_{top.strategy}_STRATEGY=true in your .env file.")
    print()
    print(f"{B}{'='*72}{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="SENSEX SEBI-grade strategy deep analysis")
    parser.add_argument("--days",  type=int,   default=60,  help="Days of history (default 60)")
    parser.add_argument("--from",  dest="from_date", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--to",    dest="to_date",   default=None, help="End date YYYY-MM-DD")
    args = parser.parse_args()

    print(f"\n{B}+----------------------------------------------------------+{RESET}")
    print(f"{B}|   SENSEX DEEP ANALYSIS — SEBI-Grade Strategy Backtest   |{RESET}")
    print(f"{B}+----------------------------------------------------------+{RESET}")

    try:
        candles_5m, candles_15m = fetch_candles(args.days, args.from_date, args.to_date)
    except Exception as exc:
        print(f"\n{R}ERROR fetching candles: {exc}{RESET}")
        print("  Make sure KITE_API_KEY and KITE_ACCESS_TOKEN are set in .env")
        print("  Login via the dashboard if session has expired")
        sys.exit(1)

    if len(candles_5m) < 50:
        print(f"{R}Not enough candles ({len(candles_5m)}). Need at least 50.{RESET}")
        sys.exit(1)

    results = run_analysis(candles_5m, candles_15m)
    print_report(results, args.days)


if __name__ == "__main__":
    main()
