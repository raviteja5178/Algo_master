"""
SENSEX ATR-Adaptive Strategy Backtester — 6-Month Edition
===========================================================
Fetches up to 6 months of real SENSEX 5m + 15m candles from Zerodha
(chunked into 60-day windows to respect the API limit), then replays
the EXACT same EMA-crossover entry signals and ATR-based risk params
used by the live bot.

Exit reasons are classified into four distinct buckets:
  INITIAL_SL   — stop hit before break-even was reached  (pure loss)
  TRAILING_SL  — trailing stop hit after break-even      (locked-in profit / partial loss)
  TARGET_HIT   — price reached or exceeded the target reference
  EOD_EXIT     — forced exit at the configured force-exit time

Usage
-----
    python backtest_atr.py                          # last 180 days, defaults from .env
    python backtest_atr.py --days 90
    python backtest_atr.py --from 2024-07-01 --to 2025-01-01
    python backtest_atr.py --days 180 --spot-atr-sl 2.5 --spot-atr-target 3.0 --spot-atr-trail 0.5
    python backtest_atr.py --days 180 --csv results.csv
    python backtest_atr.py --days 180 --no-verbose   # summary only, no per-trade log

Risk mode (Mode C — SENSEX spot ATR × multiplier):
    SL     = SENSEX_ATR(period) × spot_atr_sl
    Target = SL × spot_atr_target  (R:R ratio)
    Trail  = SL × spot_atr_trail   (fraction of SL)
    BE     = SL × 0.5
"""

from __future__ import annotations

import argparse
import csv
import os
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

sys.path.insert(0, os.path.dirname(__file__))

from config import settings
from market.candle_builder import Candle
from market.indicators import ema as calc_ema, atr_at
from utils.price_utils import round_to_tick
from utils.time_utils import IST, parse_time_ist

# ── Colour output (Windows-safe) ──────────────────────────────────────────────
try:
    import colorama; colorama.init(autoreset=True)
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"
except ImportError:
    GREEN = RED = YELLOW = CYAN = BLUE = BOLD = DIM = RESET = ""


# ═════════════════════════════════════════════════════════════════════════════
# Signal helpers — bypass the date.today() guard in the live strategies
# ═════════════════════════════════════════════════════════════════════════════

def _is_ce_signal_backtest(candles_5m: list[Candle], candles_15m: list[Candle]) -> bool:
    """EMA crossover CE signal — identical to live, minus the date.today() guard."""
    if len(candles_5m) < 21 or len(candles_15m) < 21:
        return False
    latest = candles_5m[-1]
    ema21_5 = calc_ema(candles_5m, 20)[-1]
    ema9_5  = calc_ema(candles_5m, 9)[-1]
    if None in (ema21_5, ema9_5):
        return False
    ema21_15 = calc_ema(candles_15m, 20)[-1]
    if ema21_15 is None:
        return False
    return (
        latest.close  > ema21_5
        and ema9_5    > ema21_5
        and latest.close > candles_5m[-2].high
        and candles_15m[-1].close > ema21_15
    )


def _is_pe_signal_backtest(candles_5m: list[Candle], candles_15m: list[Candle]) -> bool:
    """EMA crossover PE signal — identical to live, minus the date.today() guard."""
    if len(candles_5m) < 21 or len(candles_15m) < 21:
        return False
    latest = candles_5m[-1]
    ema21_5 = calc_ema(candles_5m, 20)[-1]
    ema9_5  = calc_ema(candles_5m, 9)[-1]
    if None in (ema21_5, ema9_5):
        return False
    ema21_15 = calc_ema(candles_15m, 20)[-1]
    if ema21_15 is None:
        return False
    return (
        latest.close  < ema21_5
        and ema9_5    < ema21_5
        and latest.close < candles_5m[-2].low
        and candles_15m[-1].close < ema21_15
    )


# ═════════════════════════════════════════════════════════════════════════════
# Data structures
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class ATRTrade:
    num:          int
    direction:    Literal["CE", "PE"]
    entry_time:   datetime
    entry_price:  float          # SENSEX spot at entry candle close
    atr_at_entry: float | None   # ATR(14) value when trade was opened

    # Risk params (resolved at entry)
    sl_points:    float          # initial SL distance in index points
    be_points:    float          # break-even trigger distance
    trail_points: float          # trail step size
    target_pts:   float          # target distance from entry

    # Running state
    initial_sl:   float = 0.0
    current_stop: float = 0.0
    target_ref:   float = 0.0
    highest_ltp:  float = 0.0
    break_even:   bool  = False
    trail_steps:  int   = 0

    # Filled on close
    exit_time:    datetime | None = None
    exit_price:   float           = 0.0
    exit_reason:  str             = ""   # INITIAL_SL | TRAILING_SL | TARGET_HIT | EOD_EXIT
    pnl_pts:      float           = 0.0  # in index points (exit - entry)
    pnl_cash:     float           = 0.0  # pnl_pts × quantity

    def finalise(self, exit_price: float, exit_time: datetime,
                 reason: str, quantity: int) -> None:
        self.exit_price  = exit_price
        self.exit_time   = exit_time
        self.exit_reason = reason
        self.pnl_pts     = round(exit_price - self.entry_price, 2)
        self.pnl_cash    = round(self.pnl_pts * quantity, 2)

    @property
    def duration_mins(self) -> int:
        if not self.exit_time:
            return 0
        return int((self.exit_time - self.entry_time).total_seconds() / 60)


@dataclass
class AtrBacktestResult:
    trades:       list[ATRTrade] = field(default_factory=list)
    # Counters per exit type
    initial_sl:   int   = 0
    trailing_sl:  int   = 0
    target_hits:  int   = 0
    eod_exits:    int   = 0
    # P&L
    total_pnl_pts:  float = 0.0
    total_pnl_cash: float = 0.0
    peak_pnl_pts:   float = 0.0
    max_dd_pts:     float = 0.0
    ce_trades:      int   = 0
    pe_trades:      int   = 0


# ═════════════════════════════════════════════════════════════════════════════
# ATR risk resolver — Mode C (SENSEX spot ATR × multiplier)
# ═════════════════════════════════════════════════════════════════════════════

def _resolve_risk(
    candles_5m: list[Candle],
    entry_price: float,
    *,
    atr_period: int,
    sl_mult: float,
    target_rr: float,
    trail_rr: float,
    min_sl: float,
    min_target: float,
    min_trail: float,
) -> tuple[float, float, float, float, float | None]:
    """
    Returns (sl_pts, be_pts, trail_pts, target_pts, atr_value).
    Mode C: SL = SENSEX_ATR × sl_mult; Target = SL × target_rr; Trail = SL × trail_rr.
    Falls back to floor values when ATR is unavailable.
    """
    current_atr = atr_at(candles_5m, period=atr_period)

    if current_atr is None or current_atr <= 0:
        be = round_to_tick(min_sl * 0.5)
        return min_sl, be, min_trail, min_target, None

    sl    = max(min_sl,     round_to_tick(current_atr * sl_mult))
    tgt   = max(min_target, round_to_tick(sl * target_rr))
    trail = max(min_trail,  round_to_tick(sl * trail_rr))
    be    = max(min_sl * 0.5, round_to_tick(sl * 0.5))
    return sl, be, trail, tgt, round(current_atr, 2)


# ═════════════════════════════════════════════════════════════════════════════
# Backtester engine
# ═════════════════════════════════════════════════════════════════════════════

class AtrBacktester:
    def __init__(
        self, *,
        quantity:     int,
        atr_period:   int,
        sl_mult:      float,
        target_rr:    float,
        trail_rr:     float,
        min_sl:       float,
        min_target:   float,
        min_trail:    float,
        force_exit:   str,
        no_entry:     str,
        verbose:      bool,
    ) -> None:
        self.qty          = quantity
        self.atr_period   = atr_period
        self.sl_mult      = sl_mult
        self.target_rr    = target_rr
        self.trail_rr     = trail_rr
        self.min_sl       = min_sl
        self.min_target   = min_target
        self.min_trail    = min_trail
        self.force_exit   = parse_time_ist(force_exit)
        self.no_entry     = parse_time_ist(no_entry)
        self.verbose      = verbose

        self._buf5m:  deque[Candle] = deque(maxlen=200)
        self._buf15m: deque[Candle] = deque(maxlen=100)
        self._trade: ATRTrade | None = None
        self._trade_num = 0
        self.result = AtrBacktestResult()

    # ── public ────────────────────────────────────────────────────────────────

    def run(self, candles_5m: list[Candle], candles_15m: list[Candle]) -> AtrBacktestResult:
        buf15 = self._build_15m_lookup(candles_15m)

        for candle in candles_5m:
            ts = candle.timestamp
            self._buf5m.append(candle)
            c5 = list(self._buf5m)
            c15 = self._get_15m_at(buf15, ts)

            t_ist = ts.astimezone(IST)
            hhmm  = (t_ist.hour, t_ist.minute)

            # manage open position first
            if self._trade:
                self._manage_position(candle)

            # EOD check — close any open trade, skip new entries
            if hhmm >= (self.force_exit.hour, self.force_exit.minute):
                if self._trade:
                    self._close(candle.close, ts, "EOD_EXIT")
                continue

            # skip new entry while position is open
            if self._trade:
                continue

            # skip past no-entry time
            if hhmm >= (self.no_entry.hour, self.no_entry.minute):
                continue

            # need enough candles to warm up indicators
            if len(c5) < 22 or len(c15) < 21:
                continue

            # evaluate signals
            if _is_ce_signal_backtest(c5, c15):
                self._open("CE", candle.close, ts, c5)
            elif _is_pe_signal_backtest(c5, c15):
                self._open("PE", candle.close, ts, c5)

        # end of data — force close any open trade
        if self._trade and candles_5m:
            last = candles_5m[-1]
            self._close(last.close, last.timestamp, "EOD_EXIT")

        self._compute_summary()
        return self.result

    # ── position management ───────────────────────────────────────────────────

    def _open(self, direction: Literal["CE","PE"], price: float,
              ts: datetime, c5: list[Candle]) -> None:
        self._trade_num += 1
        sl_pts, be_pts, trail_pts, tgt_pts, atr_val = _resolve_risk(
            c5, price,
            atr_period=self.atr_period,
            sl_mult=self.sl_mult, target_rr=self.target_rr, trail_rr=self.trail_rr,
            min_sl=self.min_sl, min_target=self.min_target, min_trail=self.min_trail,
        )
        initial_sl = round_to_tick(price - sl_pts)
        target     = round_to_tick(price + tgt_pts)

        t = ATRTrade(
            num=self._trade_num, direction=direction,
            entry_time=ts, entry_price=price, atr_at_entry=atr_val,
            sl_points=sl_pts, be_points=be_pts, trail_points=trail_pts, target_pts=tgt_pts,
            initial_sl=initial_sl, current_stop=initial_sl,
            target_ref=target, highest_ltp=price,
        )
        self._trade = t

        if direction == "CE":
            self.result.ce_trades += 1
        else:
            self.result.pe_trades += 1

        if self.verbose:
            col = GREEN if direction == "CE" else RED
            atr_str = f"  atr={atr_val:.1f}" if atr_val else ""
            print(
                f"  {col}[{self._trade_num:>3}] ENTRY {direction}{RESET}  "
                f"{ts.strftime('%Y-%m-%d %H:%M')}  "
                f"entry={price:.1f}  sl={initial_sl:.1f} (-{sl_pts:.0f}pts)  "
                f"target={target:.1f} (+{tgt_pts:.0f}pts)  "
                f"trail_step={trail_pts:.0f}pts{atr_str}"
            )

    def _manage_position(self, candle: Candle) -> None:
        t = self._trade
        assert t is not None
        high, low = candle.high, candle.low

        # update highest LTP
        if high > t.highest_ltp:
            t.highest_ltp = high

        # ── check target first (use high as best-case) ─────────────────────
        if high >= t.target_ref:
            self._close(t.target_ref, candle.timestamp, "TARGET_HIT")
            return

        # ── compute new trailing stop ──────────────────────────────────────
        be_trigger = t.entry_price + t.be_points
        if t.highest_ltp >= be_trigger:
            above_be = t.highest_ltp - be_trigger
            steps    = int(above_be // t.trail_points)
            new_stop = round_to_tick(t.entry_price + steps * t.trail_points)

            if new_stop > t.current_stop:
                old = t.current_stop
                t.current_stop = new_stop
                if not t.break_even:
                    t.break_even = True
                    if self.verbose:
                        print(
                            f"        {YELLOW}BREAK-EVEN{RESET}  "
                            f"{candle.timestamp.strftime('%H:%M')}  "
                            f"stop: {old:.1f} → {new_stop:.1f}"
                        )
                else:
                    t.trail_steps += 1
                    t.target_ref  = round_to_tick(t.target_ref + t.trail_points)
                    if self.verbose:
                        print(
                            f"        {CYAN}TRAIL #{t.trail_steps}{RESET}  "
                            f"{candle.timestamp.strftime('%H:%M')}  "
                            f"stop: {old:.1f} → {new_stop:.1f}  "
                            f"target: {t.target_ref:.1f}"
                        )

        # ── check stop hit (use low as worst-case) ─────────────────────────
        if low <= t.current_stop:
            reason = "TRAILING_SL" if t.break_even else "INITIAL_SL"
            self._close(t.current_stop, candle.timestamp, reason)

    def _close(self, price: float, ts: datetime, reason: str) -> None:
        t = self._trade
        assert t is not None
        t.finalise(price, ts, reason, self.qty)
        self.result.trades.append(t)
        self._trade = None

        col = GREEN if t.pnl_pts >= 0 else RED
        sign = "+" if t.pnl_pts >= 0 else ""
        reason_col = {
            "TARGET_HIT":  GREEN,
            "INITIAL_SL":  RED,
            "TRAILING_SL": YELLOW,
            "EOD_EXIT":    BLUE,
        }.get(reason, RESET)

        if self.verbose:
            print(
                f"  {col}[{t.num:>3}] EXIT  "
                f"{reason_col}{reason:<12}{RESET}  "
                f"{ts.strftime('%Y-%m-%d %H:%M')}  "
                f"exit={price:.1f}  "
                f"pnl={col}{sign}{t.pnl_pts:.1f}pts  "
                f"{sign}{t.pnl_cash:.0f}₹{RESET}  "
                f"dur={t.duration_mins}m  trails={t.trail_steps}"
            )

    # ── summary ───────────────────────────────────────────────────────────────

    def _compute_summary(self) -> None:
        r = self.result
        cum_pts  = 0.0
        peak_pts = 0.0
        for t in r.trades:
            cum_pts  += t.pnl_pts
            peak_pts = max(peak_pts, cum_pts)
            r.max_dd_pts = min(r.max_dd_pts, cum_pts - peak_pts)
            if   t.exit_reason == "INITIAL_SL":  r.initial_sl  += 1
            elif t.exit_reason == "TRAILING_SL": r.trailing_sl += 1
            elif t.exit_reason == "TARGET_HIT":  r.target_hits += 1
            else:                                r.eod_exits   += 1
        r.total_pnl_pts  = round(cum_pts, 2)
        r.total_pnl_cash = round(sum(t.pnl_cash for t in r.trades), 2)
        r.peak_pnl_pts   = round(peak_pts, 2)
        r.max_dd_pts     = round(r.max_dd_pts, 2)

    # ── 15m alignment helpers ─────────────────────────────────────────────────

    @staticmethod
    def _bucket_15m(ts: datetime) -> str:
        t  = ts.astimezone(IST) if ts.tzinfo else IST.localize(ts)
        bm = (t.hour * 60 + t.minute) // 15 * 15
        return f"{t.date()} {bm // 60:02d}:{bm % 60:02d}"

    def _build_15m_lookup(self, candles_15m: list[Candle]) -> dict:
        lookup: dict[str, list[Candle]] = {}
        buf: list[Candle] = []
        for c in candles_15m:
            buf.append(c)
            lookup[self._bucket_15m(c.timestamp)] = list(buf)
        return lookup

    def _get_15m_at(self, lookup: dict, ts: datetime) -> list[Candle]:
        t = ts.astimezone(IST) if ts.tzinfo else IST.localize(ts)
        for delta in range(1, 10):
            bm = (t.hour * 60 + t.minute) - delta * 15
            if bm < 0:
                break
            key = f"{t.date()} {bm // 60:02d}:{bm % 60:02d}"
            if key in lookup:
                return lookup[key]
        return []


# ═════════════════════════════════════════════════════════════════════════════
# Historical data fetch — chunked for 6-month coverage
# ═════════════════════════════════════════════════════════════════════════════

def fetch_candles_chunked(
    days: int,
    from_date_str: str | None,
    to_date_str:   str | None,
    chunk_days:    int = 58,     # Zerodha allows ~60 days for 5m; use 58 for safety
) -> tuple[list[Candle], list[Candle]]:
    """
    Fetch SENSEX 5m and 15m candles over a long date range by splitting
    into chunks no wider than chunk_days. Deduplicates by timestamp.
    """
    from broker.kite_client import get_kite
    from market.historical_data import SENSEX_TOKEN

    kite    = get_kite()
    to_dt   = datetime.strptime(to_date_str,   "%Y-%m-%d") if to_date_str   else datetime.now()
    from_dt = datetime.strptime(from_date_str, "%Y-%m-%d") if from_date_str else to_dt - timedelta(days=days)

    print(
        f"\n  Fetching SENSEX candles: "
        f"{from_dt.date()} → {to_dt.date()}  "
        f"({(to_dt - from_dt).days} calendar days)"
    )

    def _fetch_chunk(interval: str, start: datetime, end: datetime) -> list[Candle]:
        records = kite.historical_data(
            instrument_token=SENSEX_TOKEN,
            from_date=start.strftime("%Y-%m-%d 09:00:00"),
            to_date=end.strftime("%Y-%m-%d 15:30:00"),
            interval=interval,
        )
        out = []
        for r in records:
            ts = IST.localize(r["date"]) if r["date"].tzinfo is None else r["date"]
            if (ts.hour, ts.minute) < (9, 15):    # drop pre-market
                continue
            out.append(Candle(
                timestamp=ts,
                open=float(r["open"]), high=float(r["high"]),
                low=float(r["low"]),   close=float(r["close"]),
                volume=int(r.get("volume", 0)),
            ))
        return out

    def _fetch_all(interval: str) -> list[Candle]:
        seen: set[datetime] = set()
        all_candles: list[Candle] = []
        cursor = from_dt
        chunk_n = 0
        while cursor < to_dt:
            chunk_end = min(cursor + timedelta(days=chunk_days), to_dt)
            chunk_n  += 1
            sys.stdout.write(
                f"\r    {interval}: chunk {chunk_n}  "
                f"{cursor.date()} → {chunk_end.date()} ...     "
            )
            sys.stdout.flush()
            chunk = _fetch_chunk(interval, cursor, chunk_end)
            for c in chunk:
                if c.timestamp not in seen:
                    seen.add(c.timestamp)
                    all_candles.append(c)
            cursor = chunk_end + timedelta(days=1)
        print(f"\r    {interval}: {len(all_candles)} candles loaded ({chunk_n} chunks)    ")
        return sorted(all_candles, key=lambda c: c.timestamp)

    c5m  = _fetch_all("5minute")
    c15m = _fetch_all("15minute")
    return c5m, c15m


# ═════════════════════════════════════════════════════════════════════════════
# Report printer
# ═════════════════════════════════════════════════════════════════════════════

def print_report(r: AtrBacktestResult, args: argparse.Namespace) -> None:
    total = len(r.trades)
    if not total:
        print(f"\n{RED}  No trades generated - check candle count / strategy conditions.{RESET}")
        return

    winners = sum(1 for t in r.trades if t.pnl_pts > 0)
    losers  = sum(1 for t in r.trades if t.pnl_pts < 0)
    be_cnt  = total - winners - losers
    wr      = winners / total * 100
    avg_pts = r.total_pnl_pts / total

    # avg per exit type
    def _avg(reason: str) -> float:
        ts = [t.pnl_pts for t in r.trades if t.exit_reason == reason]
        return round(sum(ts) / len(ts), 1) if ts else 0.0

    w = 62
    print()
    print("=" * w)
    print(f"  {BOLD}ATR BACKTEST RESULTS{RESET}")
    print("=" * w)

    # Date range
    if r.trades:
        first = r.trades[0].entry_time.strftime("%Y-%m-%d")
        last  = r.trades[-1].entry_time.strftime("%Y-%m-%d")
        print(f"  Period         {first}  to  {last}")

    # Mode C
    print(f"  Risk Mode      Mode C - SENSEX spot ATR({args.atr_period}) x multiplier")
    print(f"  Multipliers    SL x{args.spot_atr_sl}  | Target RR {args.spot_atr_target}  "
          f"| Trail RR {args.spot_atr_trail}")
    print(f"  Quantity       {args.qty}")
    print("-" * w)

    # Totals
    pnl_col = GREEN if r.total_pnl_pts >= 0 else RED
    print(f"  Total trades   {total}  "
          f"(CE: {r.ce_trades}  PE: {r.pe_trades})")
    print(f"  Win rate       {GREEN}{wr:.1f}%{RESET}  "
          f"({winners}W / {losers}L / {be_cnt}BE)")
    print(f"  Total P&L      {pnl_col}"
          f"{'+'if r.total_pnl_pts>=0 else ''}{r.total_pnl_pts:.1f} pts  "
          f"{'+'if r.total_pnl_cash>=0 else ''}{r.total_pnl_cash:,.0f} ₹{RESET}")
    print(f"  Avg P&L/trade  {'+'if avg_pts>=0 else ''}{avg_pts:.1f} pts")
    print(f"  Peak P&L       +{r.peak_pnl_pts:.1f} pts")
    print(f"  Max Drawdown   {r.max_dd_pts:.1f} pts")
    print("-" * w)

    # Exit breakdown
    print(f"  {BOLD}Exit Breakdown{RESET}")
    total_initial_sl_pnl  = sum(t.pnl_pts for t in r.trades if t.exit_reason == "INITIAL_SL")
    total_trailing_sl_pnl = sum(t.pnl_pts for t in r.trades if t.exit_reason == "TRAILING_SL")
    total_target_pnl      = sum(t.pnl_pts for t in r.trades if t.exit_reason == "TARGET_HIT")
    total_eod_pnl         = sum(t.pnl_pts for t in r.trades if t.exit_reason == "EOD_EXIT")

    rows = [
        ("INITIAL_SL",  r.initial_sl,  RED,    total_initial_sl_pnl,  _avg("INITIAL_SL")),
        ("TRAILING_SL", r.trailing_sl, YELLOW, total_trailing_sl_pnl, _avg("TRAILING_SL")),
        ("TARGET_HIT",  r.target_hits, GREEN,  total_target_pnl,      _avg("TARGET_HIT")),
        ("EOD_EXIT",    r.eod_exits,   BLUE,   total_eod_pnl,         _avg("EOD_EXIT")),
    ]
    for label, count, col, total_pnl, avg_pnl in rows:
        pct = count / total * 100 if total else 0
        sign = "+" if total_pnl >= 0 else ""
        print(
            f"    {col}{label:<14}{RESET}  "
            f"{count:>3} trades ({pct:4.1f}%)  "
            f"total {sign}{total_pnl:.1f}pts  "
            f"avg {'+' if avg_pnl >= 0 else ''}{avg_pnl:.1f}pts"
        )
    print("=" * w)


def print_trade_table(r: AtrBacktestResult) -> None:
    """Print full trade-by-trade table."""
    if not r.trades:
        return
    hdr = (f"  {'#':>3}  {'Dir':<3}  {'Entry Time':<16}  "
           f"{'Entry':>7}  {'Exit':>7}  {'SL':>7}  {'Target':>7}  "
           f"{'ATR':>6}  {'P&L pts':>8}  {'P&L ₹':>9}  {'Dur':>5}  {'Trails':>6}  Exit Reason")
    sep = "  " + "-" * (len(hdr) - 2)
    print()
    print(f"  {BOLD}TRADE LOG{RESET}")
    print(sep)
    print(hdr)
    print(sep)
    for t in r.trades:
        col   = GREEN if t.pnl_pts >= 0 else RED
        rsn_c = {"TARGET_HIT":GREEN, "INITIAL_SL":RED,
                 "TRAILING_SL":YELLOW, "EOD_EXIT":BLUE}.get(t.exit_reason, RESET)
        sign  = "+" if t.pnl_pts >= 0 else ""
        atr_s = f"{t.atr_at_entry:.0f}" if t.atr_at_entry else "  —"
        print(
            f"  {t.num:>3}  {t.direction:<3}  "
            f"{t.entry_time.strftime('%Y-%m-%d %H:%M'):<16}  "
            f"{t.entry_price:>7.1f}  {t.exit_price:>7.1f}  "
            f"{t.initial_sl:>7.1f}  {t.target_ref:>7.1f}  "
            f"{atr_s:>6}  "
            f"{col}{sign}{t.pnl_pts:>7.1f}{RESET}  "
            f"{col}{sign}{t.pnl_cash:>8,.0f}{RESET}  "
            f"{t.duration_mins:>4}m  {t.trail_steps:>6}  "
            f"{rsn_c}{t.exit_reason}{RESET}"
        )
    print(sep)


def save_csv(r: AtrBacktestResult, path: str) -> None:
    """Export all trades to CSV."""
    fields = [
        "num", "direction", "entry_time", "exit_time",
        "entry_price", "exit_price", "initial_sl", "target_ref",
        "atr_at_entry", "sl_points", "be_points", "trail_points", "target_pts",
        "highest_ltp", "break_even", "trail_steps",
        "pnl_pts", "pnl_cash", "duration_mins", "exit_reason",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in r.trades:
            w.writerow({
                "num":          t.num,
                "direction":    t.direction,
                "entry_time":   t.entry_time.strftime("%Y-%m-%d %H:%M"),
                "exit_time":    t.exit_time.strftime("%Y-%m-%d %H:%M") if t.exit_time else "",
                "entry_price":  t.entry_price,
                "exit_price":   t.exit_price,
                "initial_sl":   t.initial_sl,
                "target_ref":   t.target_ref,
                "atr_at_entry": t.atr_at_entry if t.atr_at_entry else "",
                "sl_points":    t.sl_points,
                "be_points":    t.be_points,
                "trail_points": t.trail_points,
                "target_pts":   t.target_pts,
                "highest_ltp":  t.highest_ltp,
                "break_even":   t.break_even,
                "trail_steps":  t.trail_steps,
                "pnl_pts":      t.pnl_pts,
                "pnl_cash":     t.pnl_cash,
                "duration_mins":t.duration_mins,
                "exit_reason":  t.exit_reason,
            })
    print(f"\n  {GREEN}CSV saved: {path}{RESET}  ({len(r.trades)} rows)")


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SENSEX ATR Backtest — 6-month edition",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    # Date range
    parser.add_argument("--days",  type=int,   default=180,
                        help="Calendar days of history (default 180 = ~6 months)")
    parser.add_argument("--from",  dest="from_date", default=None,
                        help="Start date YYYY-MM-DD (overrides --days)")
    parser.add_argument("--to",    dest="to_date",   default=None,
                        help="End date YYYY-MM-DD (default today)")

    # Mode C — SENSEX spot ATR × multiplier
    parser.add_argument("--atr-period",       type=int,   default=int(getattr(settings, "SPOT_ATR_PERIOD", 5)),
                        help="ATR lookback period (default from .env SPOT_ATR_PERIOD)")
    parser.add_argument("--spot-atr-sl",      type=float,
                        default=float(getattr(settings, "SPOT_ATR_SL_MULT", 2.5)),
                        help="SENSEX ATR SL multiplier (default from .env SPOT_ATR_SL_MULT)")
    parser.add_argument("--spot-atr-target",  type=float,
                        default=float(getattr(settings, "SPOT_ATR_TARGET_RR", 1.2)),
                        help="Target as R:R ratio of SL (default from .env SPOT_ATR_TARGET_RR)")
    parser.add_argument("--spot-atr-trail",   type=float,
                        default=float(getattr(settings, "SPOT_ATR_TRAIL_RR", 0.5)),
                        help="Trail step as fraction of SL (default from .env SPOT_ATR_TRAIL_RR)")

    # Floors
    parser.add_argument("--min-sl",     type=float, default=20.0,
                        help="Minimum SL points (default 20)")
    parser.add_argument("--min-target", type=float, default=30.0,
                        help="Minimum target points (default 30)")
    parser.add_argument("--min-trail",  type=float, default=5.0,
                        help="Minimum trail step points (default 5)")

    # Session
    parser.add_argument("--qty",   type=int, default=int(getattr(settings, "QUANTITY", 20)),
                        help="Lot quantity (default from .env)")
    parser.add_argument("--exit",  default=str(getattr(settings, "FORCE_EXIT_TIME", "15:15")),
                        help="Force-exit time HH:MM (default from .env)")
    parser.add_argument("--no-entry", default="15:00",
                        help="No new entries after HH:MM (default 15:00)")

    # Output
    parser.add_argument("--csv",        default=None,
                        help="Path to export CSV trade log (e.g. results.csv)")
    parser.add_argument("--no-verbose", action="store_true",
                        help="Suppress per-trade tick-by-tick output")
    parser.add_argument("--no-table",   action="store_true",
                        help="Suppress the full trade table at the end")

    args = parser.parse_args()

    print()
    print("+-----------------------------------------------------------+")
    print("|     SENSEX ATR Backtest - 6-Month Edition                 |")
    print("+-----------------------------------------------------------+")
    print(f"  Mode C (SENSEX spot ATR x mult)  SL x{args.spot_atr_sl}  "
          f"Target RR {args.spot_atr_target}  Trail RR {args.spot_atr_trail}  "
          f"Period={args.atr_period}")
    print(f"  Quantity={args.qty}  Force-exit={args.exit}  No-entry-after={args.no_entry}")

    try:
        candles_5m, candles_15m = fetch_candles_chunked(
            args.days, args.from_date, args.to_date
        )
    except Exception as exc:
        print(f"\n{RED}  ERROR fetching candles: {exc}{RESET}")
        print("  Make sure KITE_API_KEY and KITE_ACCESS_TOKEN are set in .env")
        sys.exit(1)

    if len(candles_5m) < 22:
        print(f"\n{RED}  Not enough 5m candles ({len(candles_5m)}) to run strategy.{RESET}")
        sys.exit(1)

    print(f"\n  Running strategy replay on {len(candles_5m)} x 5m candles ...\n")

    bt = AtrBacktester(
        quantity=args.qty,
        atr_period=args.atr_period,
        sl_mult=args.spot_atr_sl, target_rr=args.spot_atr_target, trail_rr=args.spot_atr_trail,
        min_sl=args.min_sl, min_target=args.min_target, min_trail=args.min_trail,
        force_exit=args.exit, no_entry=args.no_entry,
        verbose=not args.no_verbose,
    )

    result = bt.run(candles_5m, candles_15m)

    if not args.no_table:
        print_trade_table(result)

    print_report(result, args)

    if args.csv:
        save_csv(result, args.csv)


if __name__ == "__main__":
    main()
