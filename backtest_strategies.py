"""
Per-Strategy Comprehensive Backtester
======================================
Fetches up to 1 year of SENSEX historical data from Zerodha and runs
every strategy independently, reporting win/loss/BE ratio, P&L, and
trade details for each.

Usage
-----
    python backtest_strategies.py                     # last 365 days
    python backtest_strategies.py --days 180          # last 6 months
    python backtest_strategies.py --from 2025-10-01 --to 2026-09-26
    python backtest_strategies.py --strategy EMA      # single strategy

Strategies tested independently
---------------------------------
    EMA     — EMA9/EMA21 crossover (ce_strategy / pe_strategy)
    ORB     — Opening Range Breakout
    TRB     — Time Range Breakout (09:45 anchor)
    OB      — Order Block re-entry
    MOM     — Momentum Phase 2 (afternoon 13:30–14:30)
    VWAP    — VWAP Retest
    PDHL    — Previous Day High/Low Breakout

Each strategy is backtested on the SAME historical candle data so
results are directly comparable.
"""

from __future__ import annotations

import argparse
import sys
import os

# Force UTF-8 output on Windows so Unicode characters never cause a codec crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

sys.path.insert(0, os.path.dirname(__file__))

from config import settings
from market.candle_builder import Candle
from market.indicators import atr_at, ema as calc_ema
from utils.time_utils import IST, parse_time_ist
from utils.price_utils import round_to_tick

try:
    import colorama; colorama.init()
    G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"
    C = "\033[96m"; B = "\033[1m";  X = "\033[0m"
except ImportError:
    G = R = Y = C = B = X = ""


# ═══════════════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Trade:
    strategy:    str
    direction:   Literal["CE", "PE"]
    entry_time:  datetime
    entry_price: float
    exit_time:   datetime | None = None
    exit_price:  float = 0.0
    exit_reason: str = ""
    pnl:         float = 0.0
    quantity:    int = 20

    def close(self, price: float, ts: datetime, reason: str) -> None:
        self.exit_price  = price
        self.exit_time   = ts
        self.exit_reason = reason
        self.pnl = (price - self.entry_price) * self.quantity


@dataclass
class StrategyResult:
    name:        str
    trades:      list[Trade] = field(default_factory=list)
    total_pnl:   float = 0.0
    winners:     int = 0
    losers:      int = 0
    breakevens:  int = 0
    max_dd:      float = 0.0

    @property
    def total(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        return (self.winners / self.total * 100) if self.total else 0.0

    @property
    def avg_pnl(self) -> float:
        return (self.total_pnl / self.total) if self.total else 0.0

    def compute(self) -> None:
        cum = 0.0; peak = 0.0
        for t in self.trades:
            cum += t.pnl; peak = max(peak, cum)
            self.max_dd = min(self.max_dd, cum - peak)
            if t.pnl > 0:   self.winners += 1
            elif t.pnl < 0: self.losers  += 1
            else:            self.breakevens += 1
        self.total_pnl = cum


# ═══════════════════════════════════════════════════════════════════════════════
# Position manager (shared across all strategy engines)
# ═══════════════════════════════════════════════════════════════════════════════

class PositionManager:
    """Tracks one open trade at a time with SL / trail / target logic."""

    def __init__(self, sl: float, be: float, trail: float, qty: int,
                 force_exit: str = "15:25", no_entry: str = "15:00") -> None:
        self.sl_pts    = sl
        self.be_pts    = be
        self.trail_pts = trail
        self.qty       = qty
        self._force    = parse_time_ist(force_exit)
        self._no_entry = parse_time_ist(no_entry)
        self._trade: Trade | None = None

    @property
    def in_position(self) -> bool:
        return self._trade is not None

    def can_enter(self, ts: datetime) -> bool:
        t = ts.astimezone(IST).time()
        return (not self.in_position
                and (t.hour, t.minute) < (self._no_entry.hour, self._no_entry.minute))

    def open(self, strategy: str, direction: str, price: float, ts: datetime) -> Trade:
        self._trade = Trade(
            strategy=strategy, direction=direction,  # type: ignore
            entry_price=price, entry_time=ts, quantity=self.qty,
        )
        self._sl    = round_to_tick(price - self.sl_pts)
        self._high  = price
        self._be_on = False
        return self._trade

    def update(self, candle: Candle, result: StrategyResult) -> None:
        """Manage stop / trail intra-candle. Closes trade if stop hit or EOD."""
        t = self._trade
        if t is None:
            return
        ts = candle.timestamp
        tm = ts.astimezone(IST).time()

        # EOD force-exit
        if (tm.hour, tm.minute) >= (self._force.hour, self._force.minute):
            t.close(candle.close, ts, "EOD")
            result.trades.append(t)
            self._trade = None
            return

        # Update trailing stop
        self._high = max(self._high, candle.high)
        be_trigger = t.entry_price + self.be_pts
        if self._high >= be_trigger:
            above = self._high - be_trigger
            steps = int(above // self.trail_pts)
            new_sl = round_to_tick(t.entry_price + steps * self.trail_pts)
            self._sl = max(self._sl, new_sl)
            self._be_on = True

        # Stop hit?
        if candle.low <= self._sl:
            t.close(self._sl, ts, "SL_HIT")
            result.trades.append(t)
            self._trade = None


# ═══════════════════════════════════════════════════════════════════════════════
# 15m lookup helper (same as backtest.py)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_15m_lookup(candles_15m: list[Candle]) -> dict[str, list[Candle]]:
    lookup: dict[str, list[Candle]] = {}
    buf: list[Candle] = []
    for c in candles_15m:
        buf.append(c)
        t = c.timestamp.astimezone(IST)
        bm = (t.hour * 60 + t.minute) // 15 * 15
        key = f"{t.date()} {bm // 60:02d}:{bm % 60:02d}"
        lookup[key] = list(buf)
    return lookup


def _get_15m_at(lookup: dict, ts: datetime) -> list[Candle]:
    t = ts.astimezone(IST)
    for delta in range(1, 12):
        bm = (t.hour * 60 + t.minute) - delta * 15
        if bm < 0: break
        key = f"{t.date()} {bm // 60:02d}:{bm % 60:02d}"
        if key in lookup:
            return lookup[key]
    return []


# ═══════════════════════════════════════════════════════════════════════════════
# Previous-day HL tracker
# ═══════════════════════════════════════════════════════════════════════════════

def _build_daily_hl(candles_5m: list[Candle]) -> dict:
    """Build {date: (high, low)} from 5m candle data for PDHL strategy."""
    daily: dict = defaultdict(lambda: [None, None])
    for c in candles_5m:
        d = c.timestamp.astimezone(IST).date()
        h, l = daily[d]
        daily[d][0] = max(h, c.high) if h else c.high
        daily[d][1] = min(l, c.low)  if l else c.low
    return {d: (v[0], v[1]) for d, v in daily.items()}


# ═══════════════════════════════════════════════════════════════════════════════
# Main per-strategy replay
# ═══════════════════════════════════════════════════════════════════════════════

STRATEGY_NAMES = ["EMA", "ORB", "TRB", "OB", "MOM", "VWAP", "PDHL", "NATR"]


def run_all_strategies(
    candles_5m: list[Candle],
    candles_15m: list[Candle],
    sl: float = 30.0,
    be: float = 30.0,
    trail: float = 10.0,
    qty: int = 20,
    strategies: list[str] | None = None,
) -> dict[str, StrategyResult]:

    active = strategies or STRATEGY_NAMES
    results = {s: StrategyResult(name=s) for s in active}
    positions = {s: PositionManager(sl, be, trail, qty) for s in active}

    lookup_15m = _build_15m_lookup(candles_15m)
    daily_hl   = _build_daily_hl(candles_5m)

    # Per-strategy candle buffers (independent — each strategy runs in isolation)
    bufs: dict[str, deque] = {s: deque(maxlen=200) for s in active}

    # ORB state per day
    orb_state: dict = {}   # date -> {"fired": bool, "direction": str|None, "high": float, "low": float}

    # VWAP running state per day
    vwap_state: dict = {}  # date -> {"cum_tp_vol": float, "cum_vol": float, "vwap": float}

    print(f"\n{B}Replaying {len(candles_5m):,} 5m candles across {len(active)} strategies...{X}\n")

    for candle in candles_5m:
        ts  = candle.timestamp.astimezone(IST)
        d   = ts.date()
        c15 = _get_15m_at(lookup_15m, candle.timestamp)

        # ── VWAP update ─────────────────────────────────────────────────────────
        if d not in vwap_state:
            vwap_state[d] = {"cum_tp_vol": 0.0, "cum_vol": 0.0}
        vs = vwap_state[d]
        tp = (candle.high + candle.low + candle.close) / 3
        vs["cum_tp_vol"] += tp * (candle.volume or 1)
        vs["cum_vol"]    += (candle.volume or 1)
        vwap_val = vs["cum_tp_vol"] / vs["cum_vol"]

        # ── Previous-day HL ─────────────────────────────────────────────────────
        from datetime import timedelta as _td
        prev_d = d - _td(days=1)
        while prev_d not in daily_hl and prev_d > list(daily_hl.keys())[0]:
            prev_d -= _td(days=1)
        pdh, pdl = daily_hl.get(prev_d, (None, None))

        for strat in active:
            buf = bufs[strat]
            buf.append(candle)
            c5  = list(buf)
            res = results[strat]
            pos = positions[strat]

            # ── manage open position first ───────────────────────────────────────
            if pos.in_position:
                pos.update(candle, res)

            # ── can we enter? ────────────────────────────────────────────────────
            if not pos.can_enter(candle.timestamp):
                continue
            if len(c5) < 22 or len(c15) < 4:
                continue

            sig: str | None = None

            # ── EMA strategy ─────────────────────────────────────────────────────
            if strat == "EMA":
                from strategies.ce_strategy import is_ce_signal
                from strategies.pe_strategy import is_pe_signal
                if is_ce_signal(c5, c15):   sig = "CE"
                elif is_pe_signal(c5, c15): sig = "PE"

            # ── ORB strategy ─────────────────────────────────────────────────────
            elif strat == "ORB":
                from strategies.orb_strategy import is_orb_ce_signal, is_orb_pe_signal
                if d not in orb_state:
                    orb_state[d] = {"fired": False, "direction": None}
                if not orb_state[d]["fired"]:
                    orb_15m = c15
                    if is_orb_ce_signal(c5, orb_15m):
                        sig = "CE"; orb_state[d].update(fired=True, direction="CE")
                    elif is_orb_pe_signal(c5, orb_15m):
                        sig = "PE"; orb_state[d].update(fired=True, direction="PE")

            # ── TRB strategy ─────────────────────────────────────────────────────
            elif strat == "TRB":
                from strategies.trb_strategy import is_trb_ce_signal, is_trb_pe_signal
                if is_trb_ce_signal(c5, c15):   sig = "CE"
                elif is_trb_pe_signal(c5, c15): sig = "PE"

            # ── OB strategy ──────────────────────────────────────────────────────
            elif strat == "OB":
                from strategies.ob_strategy import is_ob_ce_signal, is_ob_pe_signal
                ob_kw = dict(swing_length=settings.OB_SWING_LENGTH,
                             max_atr_mult=settings.OB_MAX_ATR_MULT,
                             atr_period=settings.OB_ATR_PERIOD,
                             max_blocks=settings.OB_MAX_BLOCKS,
                             invalidation=settings.OB_INVALIDATION)
                if is_ob_ce_signal(c5, **ob_kw):   sig = "CE"
                elif is_ob_pe_signal(c5, **ob_kw): sig = "PE"

            # ── Momentum strategy ─────────────────────────────────────────────────
            elif strat == "MOM":
                from strategies.ce_momentum import is_ce_momentum_signal
                from strategies.pe_momentum import is_pe_momentum_signal
                from datetime import time as _time
                win_s = _time(13, 30); win_e = _time(14, 30)
                mb = float(getattr(settings, "MOMENTUM_MIN_BODY_PTS", 40.0))
                if is_ce_momentum_signal(c5, c15, min_body_pts=mb, window_start=win_s, window_end=win_e):
                    sig = "CE"
                elif is_pe_momentum_signal(c5, c15, min_body_pts=mb, window_start=win_s, window_end=win_e):
                    sig = "PE"

            # ── VWAP strategy ─────────────────────────────────────────────────────
            elif strat == "VWAP":
                from strategies.vwap_strategy import is_vwap_ce_signal, is_vwap_pe_signal
                vk = dict(retest_lookback=getattr(settings, "VWAP_RETEST_LOOKBACK", 3),
                          min_bounce_pts=getattr(settings, "VWAP_MIN_BOUNCE_PTS", 0))
                if is_vwap_ce_signal(c5, vwap_val, **vk):   sig = "CE"
                elif is_vwap_pe_signal(c5, vwap_val, **vk): sig = "PE"

            # ── PDHL strategy ─────────────────────────────────────────────────────
            elif strat == "PDHL":
                from strategies.pdhl_strategy import is_pdhl_ce_signal, is_pdhl_pe_signal
                buf_pts = getattr(settings, "PDHL_BUFFER_PTS", 0)
                if pdh and is_pdhl_ce_signal(c5, pdh, buffer_pts=buf_pts): sig = "CE"
                elif pdl and is_pdhl_pe_signal(c5, pdl, buffer_pts=buf_pts): sig = "PE"

            # ── NATR Trailing Stop strategy ───────────────────────────────────────
            elif strat == "NATR":
                from strategies.natr_strategy import is_natr_ce_signal, is_natr_pe_signal
                natr_kw = dict(
                    natr_period=getattr(settings, "NATR_PERIOD", 21),
                    natr_mult=float(getattr(settings, "NATR_MULT", 3.0)),
                )
                if is_natr_ce_signal(c5, **natr_kw):   sig = "CE"
                elif is_natr_pe_signal(c5, **natr_kw): sig = "PE"

            # ── open trade if signal fired ────────────────────────────────────────
            if sig:
                pos.open(strat, sig, candle.close, candle.timestamp)

    # ── force-close any still-open trades at end of data ─────────────────────
    if candles_5m:
        last = candles_5m[-1]
        for strat in active:
            pos = positions[strat]
            if pos.in_position and pos._trade:
                pos._trade.close(last.close, last.timestamp, "END_OF_DATA")
                results[strat].trades.append(pos._trade)

    # ── compute summary stats for each strategy ───────────────────────────────
    for r in results.values():
        r.compute()

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Report printer
# ═══════════════════════════════════════════════════════════════════════════════

def print_summary(results: dict[str, StrategyResult], from_dt: datetime, to_dt: datetime) -> None:
    period = f"{from_dt.date()} to {to_dt.date()}"
    print(f"\n{B}{'='*72}{X}")
    print(f"{B}  STRATEGY BACKTEST RESULTS   {period}{X}")
    print(f"{B}{'='*72}{X}")
    print(f"  {'Strategy':<8}  {'Trades':>6}  {'Win%':>6}  {'W':>4}  {'L':>4}  {'BE':>4}  "
          f"{'Total P&L':>10}  {'Avg/Trade':>9}  {'Max DD':>8}")
    print(f"  {'-'*8}  {'-'*6}  {'-'*6}  {'-'*4}  {'-'*4}  {'-'*4}  {'-'*10}  {'-'*9}  {'-'*8}")

    for name, r in results.items():
        if r.total == 0:
            print(f"  {name:<8}  {'':>6}  (no trades fired)")
            continue
        wr_c  = G if r.win_rate >= 50 else R
        pnl_c = G if r.total_pnl >= 0 else R
        sign  = "+" if r.total_pnl >= 0 else ""
        avg_s = f"{'+'if r.avg_pnl>=0 else ''}{r.avg_pnl:.1f}"
        print(
            f"  {B}{name:<8}{X}  {r.total:>6}  {wr_c}{r.win_rate:>5.1f}%{X}  "
            f"{G}{r.winners:>4}{X}  {R}{r.losers:>4}{X}  {r.breakevens:>4}  "
            f"{pnl_c}{sign}{r.total_pnl:>10.2f}{X}  {avg_s:>9}  {r.max_dd:>8.2f}"
        )

    print(f"{B}{'='*72}{X}\n")


def print_trade_detail(results: dict[str, StrategyResult]) -> None:
    for name, r in results.items():
        if not r.trades:
            continue
        print(f"\n{B}-- {name} -- {r.total} trades ------------------------------------------{X}")
        print(f"  {'#':>3}  {'Dir':<3}  {'Entry':<17}  {'Exit':<17}  "
              f"{'Entry Px':>8}  {'Exit Px':>8}  {'P&L':>8}  {'Reason'}")
        print(f"  {'-'*3}  {'-'*3}  {'-'*17}  {'-'*17}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*16}")
        for i, t in enumerate(r.trades, 1):
            pnl_c = G if t.pnl >= 0 else R
            sign  = "+" if t.pnl >= 0 else ""
            entry_s = t.entry_time.astimezone(IST).strftime("%Y-%m-%d %H:%M")
            exit_s  = t.exit_time.astimezone(IST).strftime("%Y-%m-%d %H:%M") if t.exit_time else "—"
            print(f"  {i:>3}  {t.direction:<3}  {entry_s:<17}  {exit_s:<17}  "
                  f"{t.entry_price:>8.2f}  {t.exit_price:>8.2f}  "
                  f"{pnl_c}{sign}{t.pnl:>8.2f}{X}  {t.exit_reason}")


# ═══════════════════════════════════════════════════════════════════════════════
# Historical data fetch (chunked to respect Zerodha 60-day intraday limit)
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_candles(from_dt: datetime, to_dt: datetime) -> tuple[list[Candle], list[Candle]]:
    from broker.kite_client import get_kite
    from market.historical_data import SENSEX_TOKEN

    kite = get_kite()
    print(f"Fetching SENSEX candles {from_dt.date()} to {to_dt.date()} (chunked)...")

    def _fetch_chunked(interval: str, chunk_days: int) -> list[Candle]:
        all_records = []
        cur = from_dt
        while cur < to_dt:
            end = min(cur + timedelta(days=chunk_days), to_dt)
            try:
                recs = kite.historical_data(
                    instrument_token=SENSEX_TOKEN,
                    from_date=cur.strftime("%Y-%m-%d 09:00:00"),
                    to_date=end.strftime("%Y-%m-%d 15:30:00"),
                    interval=interval,
                )
                all_records.extend(recs)
            except Exception as e:
                print(f"  {Y}Warning: chunk {cur.date()} to {end.date()} failed: {e}{X}")
            cur = end + timedelta(seconds=1)
        candles = []
        for r in all_records:
            ts = IST.localize(r["date"]) if r["date"].tzinfo is None else r["date"].astimezone(IST)
            # Drop pre-market / post-market
            hm = (ts.hour, ts.minute)
            if hm < (9, 15) or hm > (15, 30):
                continue
            candles.append(Candle(
                timestamp=ts,
                open=float(r["open"]),  high=float(r["high"]),
                low=float(r["low"]),    close=float(r["close"]),
                volume=int(r.get("volume") or 0),
            ))
        return candles

    c5m  = _fetch_chunked("5minute",  30)
    c15m = _fetch_chunked("15minute", 60)

    # Deduplicate + sort
    seen5: dict = {}
    for c in c5m:
        seen5[c.timestamp] = c
    c5m = sorted(seen5.values(), key=lambda c: c.timestamp)

    seen15: dict = {}
    for c in c15m:
        seen15[c.timestamp] = c
    c15m = sorted(seen15.values(), key=lambda c: c.timestamp)

    print(f"  5m candles: {len(c5m):,}   15m candles: {len(c15m):,}")
    return c5m, c15m


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    p = argparse.ArgumentParser(description="Per-strategy SENSEX backtest")
    p.add_argument("--days",     type=int,   default=365,   help="Calendar days to backtest (default 365)")
    p.add_argument("--from",     dest="from_date", default=None, help="Start date YYYY-MM-DD")
    p.add_argument("--to",       dest="to_date",   default=None, help="End date YYYY-MM-DD")
    p.add_argument("--sl",       type=float, default=30.0,  help="Initial SL points (default 30)")
    p.add_argument("--be",       type=float, default=30.0,  help="Break-even trigger points (default 30)")
    p.add_argument("--trail",    type=float, default=10.0,  help="Trail step points (default 10)")
    p.add_argument("--qty",      type=int,   default=20,    help="Quantity per trade (default 20)")
    p.add_argument("--strategy", type=str,   default=None,
                   help=f"Single strategy to test: {', '.join(STRATEGY_NAMES)}")
    p.add_argument("--detail",   action="store_true", help="Print individual trade list")
    args = p.parse_args()

    to_dt   = datetime.strptime(args.to_date,   "%Y-%m-%d") if args.to_date   else datetime.now()
    from_dt = datetime.strptime(args.from_date, "%Y-%m-%d") if args.from_date else to_dt - timedelta(days=args.days)

    strategies = None
    if args.strategy:
        s = args.strategy.upper()
        if s not in STRATEGY_NAMES:
            print(f"{R}Unknown strategy '{s}'. Valid: {', '.join(STRATEGY_NAMES)}{X}")
            sys.exit(1)
        strategies = [s]

    c5m, c15m = fetch_candles(from_dt, to_dt)
    if not c5m:
        print(f"{R}No candles fetched. Check Zerodha auth and date range.{X}")
        sys.exit(1)

    results = run_all_strategies(
        c5m, c15m,
        sl=args.sl, be=args.be, trail=args.trail, qty=args.qty,
        strategies=strategies,
    )

    print_summary(results, from_dt, to_dt)
    if args.detail:
        print_trade_detail(results)


if __name__ == "__main__":
    main()
