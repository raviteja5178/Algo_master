"""
CE entry strategy — SENSEX 5m EMA 9/21 + RSI (copied rule-set).

Macro trend (15m, latest completed candle):
    GLOBAL_TREND = LONG_ONLY  when  15m Close > 15m EMA9  AND  15m EMA9 > 15m EMA21

Trigger (5m, latest completed candle) — either:
    a) Crossover : prev 5m close <= prev EMA9  AND  5m close > EMA9
    b) Pullback  : price pulled back from above EMA9 down to EMA21, then
                   the current candle bounces off EMA21.  All must hold:
                     1. Current close is on/above EMA21:
                           0 <= close − EMA21 <= pullback_tol_pts
                     2. A close above EMA9 within the PULLBACK_TREND_LOOKBACK
                        candles before the current one (was trending before the
                        dip — not already crawling on EMA21).
                     3. Prior candle's low dipped AT OR BELOW EMA21
                        (actually touched the level, not just hovered near it).
                     4. Current candle turned back up: green (close > open)
                        and close > prior close.  A candle still falling into
                        EMA21 is the dip, not the bounce.

Momentum:
    5m RSI(rsi_period) > rsi_min   (default 55)
"""

from __future__ import annotations

from collections.abc import Sequence
from utils.time_utils import today_ist

from market.candle_builder import Candle
from market.indicators import ema, rsi

FAST_EMA = 9
SLOW_EMA = 21
# Candles before the current one searched for the pre-dip close above EMA9.
PULLBACK_TREND_LOOKBACK = 4


def is_global_trend_long(candles_15m: Sequence[Candle]) -> bool:
    """15m Close > EMA9 > EMA21 → LONG_ONLY."""
    if len(candles_15m) < SLOW_EMA:
        return False
    e9 = ema(candles_15m, FAST_EMA)[-1]
    e21 = ema(candles_15m, SLOW_EMA)[-1]
    if e9 is None or e21 is None:
        return False
    return candles_15m[-1].close > e9 and e9 > e21


def is_ce_signal(
    candles_5m: Sequence[Candle],
    candles_15m: Sequence[Candle],
    *,
    rsi_period: int = 14,
    rsi_min: float = 55.0,
    pullback_tol_pts: float = 10.0,
) -> bool:
    """
    Return True when the 15m trend is LONG_ONLY and a 5m CE trigger fires.

    Both sequences must be in chronological order (oldest first).
    Minimum required: 21 completed 5m candles and 21 completed 15m candles.
    """
    if len(candles_5m) < SLOW_EMA or len(candles_15m) < SLOW_EMA:
        return False

    latest = candles_5m[-1]
    if latest.timestamp.date() != today_ist():
        return False

    if not is_global_trend_long(candles_15m):
        return False

    ema9_series = ema(candles_5m, FAST_EMA)
    e9_now, e9_prev = ema9_series[-1], ema9_series[-2]
    e21_now = ema(candles_5m, SLOW_EMA)[-1]
    rsi_now = rsi(candles_5m, rsi_period)[-1]
    if None in (e9_now, e9_prev, e21_now, rsi_now):
        return False

    crossover = candles_5m[-2].close <= e9_prev and latest.close > e9_now

    # Pullback to EMA21 — all conditions must hold:
    #   1. Current close sits on or just above EMA21 (within tolerance).
    #      A close below EMA21 would trip the EMA-collapse exit, so the lower
    #      bound is 0 (not negative).
    #   2. A recent candle closed ABOVE EMA9 — price was trending before the
    #      dip.  Without this, candles crawling along EMA21 for many bars
    #      repeatedly fire a false pullback signal.  (Requiring it of the prior
    #      candle alone made 1+2 describe a candle FALLING from EMA9 to EMA21.)
    #   3. Prior candle's low reached AT OR BELOW EMA21 — the dip actually
    #      touched the level.  A candle that stayed entirely above EMA21 is
    #      not a pullback; it is just a continuation candle.
    #   4. Current candle is green and closes above the prior close — the
    #      bounce has started.
    e21_prev = ema(candles_5m, SLOW_EMA)[-2]
    prev = candles_5m[-2]
    _recent = range(-PULLBACK_TREND_LOOKBACK - 1, -1)          # candles before the current one
    was_trending = any(
        ema9_series[k] is not None and candles_5m[k].close > ema9_series[k] for k in _recent
    )
    pullback = (
        0 <= latest.close - e21_now <= pullback_tol_pts   # (1) close on/above EMA21
        and was_trending                                   # (2) trend before the dip
        and e21_prev is not None
        and prev.low <= e21_prev                           # (3) prior low dipped to EMA21
        and latest.close > latest.open                     # (4) bounce candle: green
        and latest.close > prev.close                      #     and closing higher
    )

    return (crossover or pullback) and rsi_now > rsi_min
