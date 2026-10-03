"""
SENSEX Multi-Strategy Comparison Backtest
==========================================
Fetches 6 months of real SENSEX candles from Zerodha (auto-chunked),
runs each strategy independently in isolation, and prints a ranked
side-by-side ratio table so you can compare them on equal footing.

Strategies tested (each run separately, one at a time):
  EMA   — 4-rule EMA crossover + prev-high/low breakout
  ORB   — Opening Range Breakout (09:15 first candle, entry 09:25–09:35)
  OB    — Order Block re-entry (Flux Charts logic)
  MOM   — Momentum Phase 2 (large-body candle, 13:30–14:30 window)
  TRB   — Time Range Breakout (09:45 15m anchor candle)
  VWAP  — VWAP Retest + bounce
  PDHL  — Previous Day High/Low breakout

For each strategy the report shows:
  Trades / Win% / Avg P&L / Total P&L
  INITIAL_SL%  TRAILING_SL%  TARGET_HIT%  EOD_EXIT%
  Profit Factor / Max Drawdown / Avg Duration
  CE count / PE count

Usage
-----
    python backtest_compare.py                          # last 180 days
    python backtest_compare.py --days 90
    python backtest_compare.py --from 2024-07-01 --to 2025-01-01
    python backtest_compare.py --days 180 --spot-atr-sl 2.5 --spot-atr-target 1.2
    python backtest_compare.py --days 180 --csv compare.csv
    python backtest_compare.py --days 180 --only EMA ORB MOM   # subset
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
from datetime import datetime, time, timedelta
from typing import Callable, Literal

sys.path.insert(0, os.path.dirname(__file__))

from config import settings
from market.candle_builder import Candle
from market.indicators import ema as calc_ema, atr_at
from utils.price_utils import round_to_tick
from utils.time_utils import IST, parse_time_ist

# ── Colour output ─────────────────────────────────────────────────────────────
try:
    import colorama; colorama.init(autoreset=True)
    G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"
    C = "\033[96m"; B = "\033[94m"; W = "\033[97m"
    BOLD = "\033[1m"; DIM = "\033[2m"; RST = "\033[0m"
except ImportError:
    G = R = Y = C = B = W = BOLD = DIM = RST = ""


# ═════════════════════════════════════════════════════════════════════════════
# Trade data structure (same as backtest_atr.py)
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class Trade:
    num:          int
    strategy:     str
    direction:    str          # CE | PE
    entry_time:   datetime
    entry_price:  float
    atr_at_entry: float | None
    sl_pts:       float
    be_pts:       float
    trail_pts:    float
    target_pts:   float
    initial_sl:   float        = 0.0
    current_stop: float        = 0.0
    target_ref:   float        = 0.0
    highest_ltp:  float        = 0.0
    break_even:   bool         = False
    trail_steps:  int          = 0
    exit_time:    datetime | None = None
    exit_price:   float           = 0.0
    exit_reason:  str             = ""
    pnl_pts:      float           = 0.0
    pnl_cash:     float           = 0.0

    def finalise(self, exit_price: float, ts: datetime, reason: str, qty: int) -> None:
        self.exit_price  = exit_price
        self.exit_time   = ts
        self.exit_reason = reason
        self.pnl_pts     = round(exit_price - self.entry_price, 2)
        self.pnl_cash    = round(self.pnl_pts * qty, 2)

    @property
    def duration_mins(self) -> int:
        if not self.exit_time:
            return 0
        return int((self.exit_time - self.entry_time).total_seconds() / 60)


# ═════════════════════════════════════════════════════════════════════════════
# Risk resolver — Mode C (SENSEX spot ATR × multiplier)
# ═════════════════════════════════════════════════════════════════════════════

def resolve_risk(
    c5: list[Candle], entry: float, *,
    atr_period: int, sl_mult: float, target_rr: float, trail_rr: float,
    min_sl: float, min_tgt: float, min_trail: float,
) -> tuple[float, float, float, float, float | None]:
    """Returns (sl, be, trail, target, atr_val). Mode C: SL=ATR×sl_mult, Target=SL×target_rr."""
    atr_val = atr_at(c5, period=atr_period)
    if not atr_val or atr_val <= 0:
        be = round_to_tick(min_sl * 0.5)
        return min_sl, be, min_trail, min_tgt, None
    sl    = max(min_sl,    round_to_tick(atr_val * sl_mult))
    tgt   = max(min_tgt,   round_to_tick(sl * target_rr))
    trail = max(min_trail, round_to_tick(sl * trail_rr))
    be    = max(min_sl * 0.5, round_to_tick(sl * 0.5))
    return sl, be, trail, tgt, round(atr_val, 2)


# ═════════════════════════════════════════════════════════════════════════════
# Signal functions — date guard removed for historical replay
# ═════════════════════════════════════════════════════════════════════════════

def _ema_ce(c5: list[Candle], c15: list[Candle]) -> bool:
    if len(c5) < 21 or len(c15) < 21:
        return False
    e21 = calc_ema(c5, 20)[-1]; e9 = calc_ema(c5, 9)[-1]
    if None in (e21, e9):
        return False
    e21_15 = calc_ema(c15, 20)[-1]
    if e21_15 is None:
        return False
    return c5[-1].close > e21 and e9 > e21 and c5[-1].close > c5[-2].high and c15[-1].close > e21_15


def _ema_pe(c5: list[Candle], c15: list[Candle]) -> bool:
    if len(c5) < 21 or len(c15) < 21:
        return False
    e21 = calc_ema(c5, 20)[-1]; e9 = calc_ema(c5, 9)[-1]
    if None in (e21, e9):
        return False
    e21_15 = calc_ema(c15, 20)[-1]
    if e21_15 is None:
        return False
    return c5[-1].close < e21 and e9 < e21 and c5[-1].close < c5[-2].low and c15[-1].close < e21_15


def _orb_ce(c5: list[Candle], c15: list[Candle], **_) -> bool:
    """ORB CE: first 09:15 candle sets range, sustain candle (09:20) > orb_high, entry 09:25-09:35."""
    if len(c5) < 3:
        return False
    c0 = c5[-1]
    hhmm = (c0.timestamp.hour, c0.timestamp.minute)
    if not ((9, 25) <= hhmm <= (9, 35)):
        return False
    day = c0.timestamp.date()
    today_c = [c for c in c5 if c.timestamp.date() == day]
    if not today_c:
        return False
    orb_high = today_c[0].high    # first candle of the day (09:15)
    sustain  = next((c for c in today_c if c.timestamp.hour == 9 and c.timestamp.minute == 20), None)
    if sustain is None or sustain.close <= orb_high:
        return False
    return c0.close > orb_high


def _orb_pe(c5: list[Candle], c15: list[Candle], **_) -> bool:
    if len(c5) < 3:
        return False
    c0 = c5[-1]
    hhmm = (c0.timestamp.hour, c0.timestamp.minute)
    if not ((9, 25) <= hhmm <= (9, 35)):
        return False
    day = c0.timestamp.date()
    today_c = [c for c in c5 if c.timestamp.date() == day]
    if not today_c:
        return False
    orb_low  = today_c[0].low
    sustain  = next((c for c in today_c if c.timestamp.hour == 9 and c.timestamp.minute == 20), None)
    if sustain is None or sustain.close >= orb_low:
        return False
    return c0.close < orb_low


def _mom_ce(c5: list[Candle], c15: list[Candle],
            min_body: float = 40.0,
            win_start: time = time(13, 30),
            win_end:   time = time(14, 30)) -> bool:
    if len(c5) < 21 or len(c15) < 21:
        return False
    c0 = c5[-1]
    t  = c0.timestamp.time()
    if not (win_start <= t < win_end):
        return False
    body = c0.close - c0.open
    atr_val = atr_at(c5, 14)
    eff_min = max(min_body, atr_val * 0.5) if atr_val else min_body
    if body < eff_min:
        return False
    e9 = calc_ema(c5, 9)[-1]; e21 = calc_ema(c5, 21)[-1]
    if None in (e9, e21):
        return False
    if c0.close <= e9 or e9 <= e21:
        return False
    e21_15 = calc_ema(c15, 21)[-1]
    if e21_15 is None:
        return False
    return c15[-1].close > e21_15


def _mom_pe(c5: list[Candle], c15: list[Candle],
            min_body: float = 40.0,
            win_start: time = time(13, 30),
            win_end:   time = time(14, 30)) -> bool:
    if len(c5) < 21 or len(c15) < 21:
        return False
    c0 = c5[-1]
    t  = c0.timestamp.time()
    if not (win_start <= t < win_end):
        return False
    body = c0.open - c0.close
    atr_val = atr_at(c5, 14)
    eff_min = max(min_body, atr_val * 0.5) if atr_val else min_body
    if body < eff_min:
        return False
    e9 = calc_ema(c5, 9)[-1]; e21 = calc_ema(c5, 21)[-1]
    if None in (e9, e21):
        return False
    if c0.close >= e9 or e9 >= e21:
        return False
    e21_15 = calc_ema(c15, 21)[-1]
    if e21_15 is None:
        return False
    return c15[-1].close < e21_15


def _trb_ce(c5: list[Candle], c15: list[Candle], **_) -> bool:
    """TRB CE: 09:45 15m anchor high breakout, only after 10:00."""
    c0 = c5[-1]
    hhmm = (c0.timestamp.hour, c0.timestamp.minute)
    if hhmm < (10, 0):
        return False
    day = c0.timestamp.date()
    anchor = next((c for c in c15
                   if c.timestamp.date() == day
                   and c.timestamp.hour == 9 and c.timestamp.minute == 45), None)
    if anchor is None:
        return False
    # fresh crossover: prev close <= anchor.high, current > anchor.high
    if len(c5) < 2:
        return False
    return c5[-2].close <= anchor.high and c0.close > anchor.high


def _trb_pe(c5: list[Candle], c15: list[Candle], **_) -> bool:
    c0 = c5[-1]
    hhmm = (c0.timestamp.hour, c0.timestamp.minute)
    if hhmm < (10, 0):
        return False
    day = c0.timestamp.date()
    anchor = next((c for c in c15
                   if c.timestamp.date() == day
                   and c.timestamp.hour == 9 and c.timestamp.minute == 45), None)
    if anchor is None:
        return False
    if len(c5) < 2:
        return False
    return c5[-2].close >= anchor.low and c0.close < anchor.low


def _vwap_ce(c5: list[Candle], c15: list[Candle],
             vwap_series: dict[str, float] | None = None, **_) -> bool:
    """VWAP CE: retest dip (any prev N closed below VWAP), then close above + prev high."""
    if vwap_series is None or len(c5) < 4:
        return False
    c0 = c5[-1]
    key = c0.timestamp.strftime("%Y-%m-%d")
    vwap = vwap_series.get(key)
    if vwap is None:
        return False
    lookback = c5[-4:-1]     # 3 prior candles
    retest = any(c.close < vwap for c in lookback)
    return retest and c0.close > vwap and c0.close > c5[-2].high


def _vwap_pe(c5: list[Candle], c15: list[Candle],
             vwap_series: dict[str, float] | None = None, **_) -> bool:
    if vwap_series is None or len(c5) < 4:
        return False
    c0 = c5[-1]
    key = c0.timestamp.strftime("%Y-%m-%d")
    vwap = vwap_series.get(key)
    if vwap is None:
        return False
    lookback = c5[-4:-1]
    retest = any(c.close > vwap for c in lookback)
    return retest and c0.close < vwap and c0.close < c5[-2].low


def _pdhl_ce(c5: list[Candle], c15: list[Candle],
             pdhl_series: dict[str, tuple[float | None, float | None]] | None = None, **_) -> bool:
    """PDHL CE: fresh close above previous day high."""
    if pdhl_series is None or len(c5) < 2:
        return False
    c0 = c5[-1]
    day = c0.timestamp.strftime("%Y-%m-%d")
    pdh, _ = pdhl_series.get(day, (None, None))
    if pdh is None:
        return False
    return c5[-2].close <= pdh and c0.close > pdh and c0.close > c5[-2].high


def _pdhl_pe(c5: list[Candle], c15: list[Candle],
             pdhl_series: dict[str, tuple[float | None, float | None]] | None = None, **_) -> bool:
    if pdhl_series is None or len(c5) < 2:
        return False
    c0 = c5[-1]
    day = c0.timestamp.strftime("%Y-%m-%d")
    _, pdl = pdhl_series.get(day, (None, None))
    if pdl is None:
        return False
    return c5[-2].close >= pdl and c0.close < pdl and c0.close < c5[-2].low


def _ob_ce(c5: list[Candle], c15: list[Candle], **_) -> bool:
    """OB CE: close inside a valid (non-breaker) bullish order block."""
    from strategies.ob_strategy import detect_order_blocks
    if len(c5) < 15:
        return False
    zones = detect_order_blocks(c5, swing_length=10, max_atr_mult=3.5,
                                 atr_period=10, max_blocks=3, invalidation="Wick")
    bull_obs = [z for z in zones.get("bull", []) if not z.breaker]
    if not bull_obs:
        return False
    close = c5[-1].close
    return any(ob.bottom <= close <= ob.top for ob in bull_obs)


def _ob_pe(c5: list[Candle], c15: list[Candle], **_) -> bool:
    from strategies.ob_strategy import detect_order_blocks
    if len(c5) < 15:
        return False
    zones = detect_order_blocks(c5, swing_length=10, max_atr_mult=3.5,
                                 atr_period=10, max_blocks=3, invalidation="Wick")
    bear_obs = [z for z in zones.get("bear", []) if not z.breaker]
    if not bear_obs:
        return False
    close = c5[-1].close
    return any(ob.bottom <= close <= ob.top for ob in bear_obs)


# Registry: name → (ce_fn, pe_fn)
STRATEGY_SIGNALS: dict[str, tuple[Callable, Callable]] = {
    "EMA":  (_ema_ce,  _ema_pe),
    "ORB":  (_orb_ce,  _orb_pe),
    "OB":   (_ob_ce,   _ob_pe),
    "MOM":  (_mom_ce,  _mom_pe),
    "TRB":  (_trb_ce,  _trb_pe),
    "VWAP": (_vwap_ce, _vwap_pe),
    "PDHL": (_pdhl_ce, _pdhl_pe),
}


# ═════════════════════════════════════════════════════════════════════════════
# Core engine — runs one strategy in isolation
# ═════════════════════════════════════════════════════════════════════════════

def run_strategy(
    name: str,
    ce_fn: Callable, pe_fn: Callable,
    candles_5m: list[Candle], candles_15m: list[Candle],
    *,
    qty: int,
    atr_period: int, sl_mult: float, target_rr: float, trail_rr: float,
    min_sl: float, min_tgt: float, min_trail: float,
    force_exit_hhmm: tuple[int, int],
    no_entry_hhmm:   tuple[int, int],
    extra_kwargs: dict,
) -> list[Trade]:
    """Replay all candles using one strategy's signal functions. Returns closed trades."""
    buf5  : deque[Candle] = deque(maxlen=200)
    buf15 : deque[Candle] = deque(maxlen=100)
    buf15_lookup: dict[str, list[Candle]] = {}

    # pre-build 15m lookup (chronological slices)
    _buf: list[Candle] = []
    for c in candles_15m:
        _buf.append(c)
        t = c.timestamp.astimezone(IST) if c.timestamp.tzinfo else IST.localize(c.timestamp)
        bm  = (t.hour * 60 + t.minute) // 15 * 15
        key = f"{t.date()} {bm//60:02d}:{bm%60:02d}"
        buf15_lookup[key] = list(_buf)

    def _get_15m(ts: datetime) -> list[Candle]:
        t = ts.astimezone(IST) if ts.tzinfo else IST.localize(ts)
        for delta in range(1, 10):
            bm = (t.hour * 60 + t.minute) - delta * 15
            if bm < 0:
                break
            key = f"{t.date()} {bm//60:02d}:{bm%60:02d}"
            if key in buf15_lookup:
                return buf15_lookup[key]
        return []

    trades: list[Trade] = []
    open_trade: Trade | None = None
    trade_num = 0

    for candle in candles_5m:
        ts    = candle.timestamp
        t_ist = ts.astimezone(IST) if ts.tzinfo else IST.localize(ts)
        hhmm  = (t_ist.hour, t_ist.minute)

        buf5.append(candle)
        c5  = list(buf5)
        c15 = _get_15m(ts)

        # ── manage open position ───────────────────────────────────────────
        if open_trade:
            t   = open_trade
            hi  = candle.high
            lo  = candle.low

            # update highest ltp
            if hi > t.highest_ltp:
                t.highest_ltp = hi

            # target hit?
            if hi >= t.target_ref:
                t.finalise(t.target_ref, ts, "TARGET_HIT", qty)
                trades.append(t); open_trade = None
                continue

            # trailing stop update
            be_trigger = t.entry_price + t.be_pts
            if t.highest_ltp >= be_trigger:
                above_be  = t.highest_ltp - be_trigger
                steps     = int(above_be // t.trail_pts)
                new_stop  = round_to_tick(t.entry_price + steps * t.trail_pts)
                if new_stop > t.current_stop:
                    t.current_stop = new_stop
                    if not t.break_even:
                        t.break_even = True
                    else:
                        t.trail_steps += 1
                        t.target_ref   = round_to_tick(t.target_ref + t.trail_pts)

            # stop hit?
            if lo <= t.current_stop:
                reason = "TRAILING_SL" if t.break_even else "INITIAL_SL"
                t.finalise(t.current_stop, ts, reason, qty)
                trades.append(t); open_trade = None
                continue

        # ── EOD force exit ─────────────────────────────────────────────────
        if hhmm >= force_exit_hhmm:
            if open_trade:
                open_trade.finalise(candle.close, ts, "EOD_EXIT", qty)
                trades.append(open_trade); open_trade = None
            continue

        # ── skip entry conditions ──────────────────────────────────────────
        if open_trade:
            continue
        if hhmm >= no_entry_hhmm:
            continue
        if len(c5) < 22 or len(c15) < 21:
            continue

        # ── evaluate signal ────────────────────────────────────────────────
        direction: str | None = None
        if ce_fn(c5, c15, **extra_kwargs):
            direction = "CE"
        elif pe_fn(c5, c15, **extra_kwargs):
            direction = "PE"

        if direction is None:
            continue

        # ── open trade ─────────────────────────────────────────────────────
        trade_num += 1
        price = candle.close
        sl, be, trail, tgt, atr_val = resolve_risk(
            c5, price,
            atr_period=atr_period, sl_mult=sl_mult, target_rr=target_rr, trail_rr=trail_rr,
            min_sl=min_sl, min_tgt=min_tgt, min_trail=min_trail,
        )
        open_trade = Trade(
            num=trade_num, strategy=name, direction=direction,
            entry_time=ts, entry_price=price, atr_at_entry=atr_val,
            sl_pts=sl, be_pts=be, trail_pts=trail, target_pts=tgt,
            initial_sl=round_to_tick(price - sl),
            current_stop=round_to_tick(price - sl),
            target_ref=round_to_tick(price + tgt),
            highest_ltp=price,
        )

    # end of data: force-close
    if open_trade and candles_5m:
        open_trade.finalise(candles_5m[-1].close, candles_5m[-1].timestamp, "EOD_EXIT", qty)
        trades.append(open_trade)

    return trades


# ═════════════════════════════════════════════════════════════════════════════
# VWAP + PDHL series builders  (pre-compute per-day values from candle data)
# ═════════════════════════════════════════════════════════════════════════════

def build_vwap_series(candles_5m: list[Candle]) -> dict[str, float]:
    """
    Build a map {date_str: daily_vwap} using the classic intraday VWAP
    = sum(typical_price * volume) / sum(volume) for all candles that day.
    Falls back to simple arithmetic mean of close prices when volume = 0.
    """
    from collections import defaultdict
    day_tp_vol: dict[str, tuple[float, float]] = defaultdict(lambda: (0.0, 0.0))
    for c in candles_5m:
        key = c.timestamp.strftime("%Y-%m-%d")
        tp  = (c.high + c.low + c.close) / 3
        vol = c.volume if c.volume > 0 else 1
        old_tp, old_vol = day_tp_vol[key]
        day_tp_vol[key] = (old_tp + tp * vol, old_vol + vol)
    return {k: round(tp / vol, 2) for k, (tp, vol) in day_tp_vol.items()}


def build_pdhl_series(candles_5m: list[Candle]) -> dict[str, tuple[float | None, float | None]]:
    """
    Build a map {date_str: (prev_day_high, prev_day_low)} from intraday data.
    For each trading day, the previous trading day's intraday high/low is used.
    """
    from collections import defaultdict
    day_hl: dict[str, tuple[float, float]] = {}
    for c in candles_5m:
        day = c.timestamp.strftime("%Y-%m-%d")
        if day not in day_hl:
            day_hl[day] = (c.high, c.low)
        else:
            hi, lo = day_hl[day]
            day_hl[day] = (max(hi, c.high), min(lo, c.low))

    sorted_days = sorted(day_hl.keys())
    result: dict[str, tuple[float | None, float | None]] = {}
    for i, day in enumerate(sorted_days):
        if i == 0:
            result[day] = (None, None)
        else:
            result[day] = day_hl[sorted_days[i - 1]]
    return result


# ═════════════════════════════════════════════════════════════════════════════
# Statistics
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class StrategyStats:
    name:          str
    trades:        int   = 0
    winners:       int   = 0
    losers:        int   = 0
    be_trades:     int   = 0
    ce_trades:     int   = 0
    pe_trades:     int   = 0
    initial_sl:    int   = 0
    trailing_sl:   int   = 0
    target_hits:   int   = 0
    eod_exits:     int   = 0
    total_pnl_pts: float = 0.0
    gross_profit:  float = 0.0
    gross_loss:    float = 0.0
    peak_pnl_pts:  float = 0.0
    max_dd_pts:    float = 0.0
    total_dur_mins:int   = 0

    @property
    def win_pct(self) -> float:
        return self.winners / self.trades * 100 if self.trades else 0.0

    @property
    def avg_pnl(self) -> float:
        return self.total_pnl_pts / self.trades if self.trades else 0.0

    @property
    def profit_factor(self) -> float:
        if self.gross_loss == 0:
            return float("inf") if self.gross_profit > 0 else 0.0
        return round(self.gross_profit / abs(self.gross_loss), 2)

    @property
    def avg_dur(self) -> float:
        return self.total_dur_mins / self.trades if self.trades else 0.0

    def pct(self, n: int) -> float:
        return n / self.trades * 100 if self.trades else 0.0


def compute_stats(name: str, trades: list[Trade]) -> StrategyStats:
    s = StrategyStats(name=name, trades=len(trades))
    cum = 0.0; peak = 0.0
    for t in trades:
        cum += t.pnl_pts
        peak = max(peak, cum)
        s.max_dd_pts = min(s.max_dd_pts, cum - peak)
        if t.pnl_pts > 0:
            s.winners     += 1
            s.gross_profit += t.pnl_pts
        elif t.pnl_pts < 0:
            s.losers      += 1
            s.gross_loss  += t.pnl_pts
        else:
            s.be_trades   += 1
        if t.direction == "CE": s.ce_trades += 1
        else:                   s.pe_trades += 1
        if   t.exit_reason == "INITIAL_SL":  s.initial_sl  += 1
        elif t.exit_reason == "TRAILING_SL": s.trailing_sl += 1
        elif t.exit_reason == "TARGET_HIT":  s.target_hits += 1
        else:                                s.eod_exits   += 1
        s.total_pnl_pts  += t.pnl_pts
        s.total_dur_mins += t.duration_mins
    s.total_pnl_pts = round(s.total_pnl_pts, 2)
    s.gross_profit  = round(s.gross_profit,  2)
    s.gross_loss    = round(s.gross_loss,    2)
    s.peak_pnl_pts  = round(peak,            2)
    s.max_dd_pts    = round(s.max_dd_pts,    2)
    return s


# ═════════════════════════════════════════════════════════════════════════════
# Display
# ═════════════════════════════════════════════════════════════════════════════

def _col_pnl(v: float) -> str:
    c = G if v >= 0 else R
    return f"{c}{'+'if v>=0 else ''}{v:.1f}{RST}"

def _col_pct(v: float, good_above: float = 50.0) -> str:
    c = G if v >= good_above else (Y if v >= 40.0 else R)
    return f"{c}{v:.1f}%{RST}"

def _col_pf(v: float) -> str:
    c = G if v >= 1.5 else (Y if v >= 1.0 else R)
    if v == float("inf"):
        return f"{G}∞{RST}"
    return f"{c}{v:.2f}{RST}"


def print_comparison(all_stats: list[StrategyStats]) -> None:
    if not all_stats:
        print("No results.")
        return

    # sort by total P&L descending
    ranked = sorted(all_stats, key=lambda s: s.total_pnl_pts, reverse=True)

    W = 110
    print()
    print("=" * W)
    print(f"  {BOLD}STRATEGY COMPARISON - RANKED BY TOTAL P&L{RST}")
    print("=" * W)

    # header
    hdr = (
        f"  {'Rank':<5} {'Strategy':<8} {'Trades':>7} {'Win%':>7} {'AvgP&L':>8} "
        f"{'TotalP&L':>10} {'PF':>6} {'MaxDD':>8} "
        f"{'InitSL%':>8} {'TrlSL%':>8} {'Target%':>8} {'EOD%':>7} "
        f"{'CE':>5} {'PE':>5} {'AvgDur':>8}"
    )
    sep = "  " + "-" * (W - 2)
    print(hdr)
    print(sep)

    for rank, s in enumerate(ranked, 1):
        if s.trades == 0:
            print(f"  {rank:<5} {s.name:<8} {'No trades':>7}")
            continue
        pnl_str = _col_pnl(s.total_pnl_pts)
        wr_str  = _col_pct(s.win_pct)
        pf_str  = _col_pf(s.profit_factor)
        avg_str = _col_pnl(s.avg_pnl)
        dd_str  = f"{R}{s.max_dd_pts:.1f}{RST}"
        medal   = ["🥇", "🥈", "🥉", "  ", "  ", "  ", "  "][min(rank - 1, 6)]
        print(
            f"  {medal}{rank:<4} {BOLD}{s.name:<8}{RST} "
            f"{s.trades:>7} "
            f"{wr_str:>18} "
            f"{avg_str:>19} "
            f"{pnl_str:>21} "
            f"{pf_str:>17} "
            f"{dd_str:>19} "
            f"{s.pct(s.initial_sl):>7.1f}% "
            f"{s.pct(s.trailing_sl):>7.1f}% "
            f"{s.pct(s.target_hits):>7.1f}% "
            f"{s.pct(s.eod_exits):>6.1f}% "
            f"{s.ce_trades:>5} "
            f"{s.pe_trades:>5} "
            f"{s.avg_dur:>7.0f}m"
        )

    print(sep)

    # ── detailed per-strategy exit breakdown ──────────────────────────────
    print()
    print(f"  {BOLD}EXIT BREAKDOWN PER STRATEGY{RST}")
    print("=" * W)
    exit_hdr = (
        f"  {'Strategy':<8}  "
        f"{'INITIAL_SL':>20}  "
        f"{'TRAILING_SL':>22}  "
        f"{'TARGET_HIT':>22}  "
        f"{'EOD_EXIT':>20}"
    )
    print(exit_hdr)
    print("  " + "-" * (W - 2))

    def _exit_col(count: int, total: int, total_pnl: float) -> str:
        pct  = count / total * 100 if total else 0
        sign = "+" if total_pnl >= 0 else ""
        col  = G if total_pnl >= 0 else R
        return f"{count:>3} ({pct:4.1f}%)  {col}{sign}{total_pnl:>7.1f}pts{RST}"

    for s_orig in all_stats:
        # look up trades for this strategy from ranked list
        s = next((x for x in ranked if x.name == s_orig.name), None)
        if s is None or s.trades == 0:
            continue
        # We need raw trade lists — use stats directly
        print(
            f"  {BOLD}{s.name:<8}{RST}  "
            f"{R}InitSL:  {s.initial_sl:>3} ({s.pct(s.initial_sl):4.1f}%)  avg={_exit_pnl_avg(s, 'initial_sl')}{RST}  "
            f"{Y}TrlSL:   {s.trailing_sl:>3} ({s.pct(s.trailing_sl):4.1f}%)  avg={_exit_pnl_avg(s, 'trailing_sl')}{RST}  "
            f"{G}Target:  {s.target_hits:>3} ({s.pct(s.target_hits):4.1f}%)  avg={_exit_pnl_avg(s, 'target_hits')}{RST}  "
            f"{B}EOD:     {s.eod_exits:>3} ({s.pct(s.eod_exits):4.1f}%){RST}"
        )

    print("=" * W)


# We need average pnl per exit bucket but StrategyStats doesn't store per-exit sums.
# Store them separately via a parallel dict.
_EXIT_PNL: dict[str, dict[str, list[float]]] = {}

def _exit_pnl_avg(s: StrategyStats, bucket: str) -> str:
    vals = _EXIT_PNL.get(s.name, {}).get(bucket, [])
    if not vals:
        return "  —  "
    avg = sum(vals) / len(vals)
    c   = G if avg >= 0 else R
    return f"{c}{'+'if avg>=0 else ''}{avg:.1f}pts{RST}"


def _store_exit_pnl(name: str, trades: list[Trade]) -> None:
    buckets: dict[str, list[float]] = {
        "initial_sl": [], "trailing_sl": [], "target_hits": [], "eod_exits": []
    }
    for t in trades:
        if   t.exit_reason == "INITIAL_SL":  buckets["initial_sl"].append(t.pnl_pts)
        elif t.exit_reason == "TRAILING_SL": buckets["trailing_sl"].append(t.pnl_pts)
        elif t.exit_reason == "TARGET_HIT":  buckets["target_hits"].append(t.pnl_pts)
        else:                                buckets["eod_exits"].append(t.pnl_pts)
    _EXIT_PNL[name] = buckets


# ═════════════════════════════════════════════════════════════════════════════
# Data fetch (shared with backtest_atr.py)
# ═════════════════════════════════════════════════════════════════════════════

def fetch_candles_chunked(days: int, from_str: str | None, to_str: str | None,
                          chunk: int = 58) -> tuple[list[Candle], list[Candle]]:
    from broker.kite_client import get_kite
    from market.historical_data import SENSEX_TOKEN
    kite  = get_kite()
    to_dt = datetime.strptime(to_str, "%Y-%m-%d") if to_str else datetime.now()
    fr_dt = datetime.strptime(from_str, "%Y-%m-%d") if from_str else to_dt - timedelta(days=days)

    print(f"\n  Fetching SENSEX candles: {fr_dt.date()} to {to_dt.date()}  "
          f"({(to_dt - fr_dt).days} calendar days)")

    def _fetch_all(interval: str) -> list[Candle]:
        seen: set[datetime] = set(); out: list[Candle] = []
        cursor = fr_dt; chunk_n = 0
        while cursor < to_dt:
            end = min(cursor + timedelta(days=chunk), to_dt); chunk_n += 1
            sys.stdout.write(f"\r    {interval}: chunk {chunk_n}  {cursor.date()} → {end.date()} ...   ")
            sys.stdout.flush()
            records = kite.historical_data(
                instrument_token=SENSEX_TOKEN,
                from_date=cursor.strftime("%Y-%m-%d 09:00:00"),
                to_date=end.strftime("%Y-%m-%d 15:30:00"),
                interval=interval,
            )
            for r in records:
                ts = IST.localize(r["date"]) if r["date"].tzinfo is None else r["date"]
                if (ts.hour, ts.minute) < (9, 15) or ts in seen:
                    continue
                seen.add(ts)
                out.append(Candle(
                    timestamp=ts, open=float(r["open"]), high=float(r["high"]),
                    low=float(r["low"]),   close=float(r["close"]),
                    volume=int(r.get("volume", 0)),
                ))
            cursor = end + timedelta(days=1)
        print(f"\r    {interval}: {len(out)} candles ({chunk_n} chunks)               ")
        return sorted(out, key=lambda c: c.timestamp)

    return _fetch_all("5minute"), _fetch_all("15minute")


# ═════════════════════════════════════════════════════════════════════════════
# CSV export
# ═════════════════════════════════════════════════════════════════════════════

def save_csv(all_trades: dict[str, list[Trade]], path: str) -> None:
    fields = ["strategy", "num", "direction", "entry_time", "exit_time",
              "entry_price", "exit_price", "initial_sl", "target_ref",
              "atr_at_entry", "sl_pts", "trail_pts", "target_pts",
              "highest_ltp", "break_even", "trail_steps",
              "pnl_pts", "pnl_cash", "duration_mins", "exit_reason"]
    total = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for name, trades in all_trades.items():
            for t in trades:
                w.writerow({
                    "strategy":    t.strategy,
                    "num":         t.num,
                    "direction":   t.direction,
                    "entry_time":  t.entry_time.strftime("%Y-%m-%d %H:%M"),
                    "exit_time":   t.exit_time.strftime("%Y-%m-%d %H:%M") if t.exit_time else "",
                    "entry_price": t.entry_price,
                    "exit_price":  t.exit_price,
                    "initial_sl":  t.initial_sl,
                    "target_ref":  t.target_ref,
                    "atr_at_entry":t.atr_at_entry or "",
                    "sl_pts":      t.sl_pts,
                    "trail_pts":   t.trail_pts,
                    "target_pts":  t.target_pts,
                    "highest_ltp": t.highest_ltp,
                    "break_even":  t.break_even,
                    "trail_steps": t.trail_steps,
                    "pnl_pts":     t.pnl_pts,
                    "pnl_cash":    t.pnl_cash,
                    "duration_mins": t.duration_mins,
                    "exit_reason": t.exit_reason,
                })
                total += 1
    print(f"\n  {G}CSV saved: {path}{RST}  ({total} rows across {len(all_trades)} strategies)")


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    all_names = list(STRATEGY_SIGNALS.keys())

    parser = argparse.ArgumentParser(
        description="SENSEX multi-strategy comparison backtest",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--days",    type=int,   default=180)
    parser.add_argument("--from",    dest="from_date", default=None)
    parser.add_argument("--to",      dest="to_date",   default=None)
    parser.add_argument("--only",    nargs="+",  choices=all_names, default=all_names,
                        help="Run only these strategies (default: all)")

    # Risk — Mode C (SENSEX spot ATR × multiplier)
    parser.add_argument("--atr-period",      type=int,   default=int(getattr(settings, "SPOT_ATR_PERIOD", 5)))
    parser.add_argument("--spot-atr-sl",     type=float,
                        default=float(getattr(settings, "SPOT_ATR_SL_MULT",    2.5)))
    parser.add_argument("--spot-atr-target", type=float,
                        default=float(getattr(settings, "SPOT_ATR_TARGET_RR",  1.2)))
    parser.add_argument("--spot-atr-trail",  type=float,
                        default=float(getattr(settings, "SPOT_ATR_TRAIL_RR",   0.5)))

    # Floors
    parser.add_argument("--min-sl",     type=float, default=20.0)
    parser.add_argument("--min-target", type=float, default=30.0)
    parser.add_argument("--min-trail",  type=float, default=5.0)

    # Session
    parser.add_argument("--qty",      type=int,
                        default=int(getattr(settings, "QUANTITY", 20)))
    parser.add_argument("--exit",     default=str(getattr(settings, "FORCE_EXIT_TIME", "15:15")))
    parser.add_argument("--no-entry", default="15:00")
    parser.add_argument("--mom-body", type=float, default=40.0,
                        help="Momentum min body pts (default 40)")

    # Output
    parser.add_argument("--csv", default=None)

    args = parser.parse_args()

    print()
    print("+-------------------------------------------------------------+")
    print("|   SENSEX Multi-Strategy Comparison Backtest                 |")
    print("+-------------------------------------------------------------+")
    print(f"  Risk: Mode C (SENSEX spot ATR)  SL x{args.spot_atr_sl}  "
          f"Target RR {args.spot_atr_target}  Trail RR {args.spot_atr_trail}")
    print(f"  Strategies: {' | '.join(args.only)}")

    try:
        c5m, c15m = fetch_candles_chunked(args.days, args.from_date, args.to_date)
    except Exception as exc:
        print(f"\n{R}  ERROR: {exc}{RST}")
        print("  Make sure KITE_API_KEY and KITE_ACCESS_TOKEN are set in .env")
        sys.exit(1)

    if len(c5m) < 22:
        print(f"\n{R}  Not enough candles ({len(c5m)}).{RST}")
        sys.exit(1)

    # build auxiliary series (VWAP + PDHL) once, shared by all strategies
    vwap_series = build_vwap_series(c5m)
    pdhl_series = build_pdhl_series(c5m)

    # ── Force exit / no-entry as (hour, min) tuples ───────────────────────
    fe = parse_time_ist(args.exit)
    ne = parse_time_ist(args.no_entry)
    fe_hhmm = (fe.hour, fe.minute)
    ne_hhmm = (ne.hour, ne.minute)

    # ── risk kwargs shared by all strategies ──────────────────────────────
    risk_kwargs = dict(
        qty=args.qty,
        atr_period=args.atr_period,
        sl_mult=args.spot_atr_sl, target_rr=args.spot_atr_target, trail_rr=args.spot_atr_trail,
        min_sl=args.min_sl, min_tgt=args.min_target, min_trail=args.min_trail,
        force_exit_hhmm=fe_hhmm, no_entry_hhmm=ne_hhmm,
    )

    all_trades:  dict[str, list[Trade]]   = {}
    all_stats_l: list[StrategyStats]      = []

    for name in args.only:
        ce_fn, pe_fn = STRATEGY_SIGNALS[name]

        # extra kwargs per strategy
        extra: dict = {}
        if name == "VWAP":
            extra["vwap_series"] = vwap_series
        elif name == "PDHL":
            extra["pdhl_series"] = pdhl_series
        elif name == "MOM":
            extra["min_body"]   = args.mom_body

        sys.stdout.write(f"  Running {name:<6} ... ")
        sys.stdout.flush()
        trades = run_strategy(name, ce_fn, pe_fn, c5m, c15m,
                              extra_kwargs=extra, **risk_kwargs)
        all_trades[name] = trades
        stats = compute_stats(name, trades)
        _store_exit_pnl(name, trades)
        all_stats_l.append(stats)
        print(f"{len(trades):>4} trades  P&L={_col_pnl(stats.total_pnl_pts)}  Win%={stats.win_pct:.1f}%")

    print_comparison(all_stats_l)

    if args.csv:
        save_csv(all_trades, args.csv)


if __name__ == "__main__":
    main()
