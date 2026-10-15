"""
PE entry strategy — SENSEX 5m EMA 9/21 + RSI (copied rule-set).

Macro trend (15m, latest completed candle):
    GLOBAL_TREND = SHORT_ONLY when  15m Close < 15m EMA9  AND  15m EMA9 < 15m EMA21

Trigger (5m, latest completed candle) — either:
    a) Crossover : prev 5m close >= prev EMA9  AND  5m close < EMA9
    b) Pullback  : price pulled back from below EMA9 up to EMA21, then
                   the current candle closes back ON or BELOW EMA21 (within
                   pullback_tol_pts).  Three conditions must ALL hold:
                     1. Current close is on/below EMA21:
                           0 <= EMA21 − close <= pullback_tol_pts
                     2. Prior candle closed BELOW EMA9 (was in the downtrend
                        before the bounce — not already crawling on EMA21).
                     3. Prior candle's high reached AT OR ABOVE EMA21
                        (actually touched the level, not just hovered near it).

Momentum:
    5m RSI(rsi_period) < rsi_max   (default 45)
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from market.candle_builder import Candle
from market.indicators import ema, rsi

FAST_EMA = 9
SLOW_EMA = 21


def is_global_trend_short(candles_15m: Sequence[Candle]) -> bool:
    """15m Close < EMA9 < EMA21 → SHORT_ONLY."""
    if len(candles_15m) < SLOW_EMA:
        return False
    e9 = ema(candles_15m, FAST_EMA)[-1]
    e21 = ema(candles_15m, SLOW_EMA)[-1]
    if e9 is None or e21 is None:
        return False
    return candles_15m[-1].close < e9 and e9 < e21


def is_pe_signal(
    candles_5m: Sequence[Candle],
    candles_15m: Sequence[Candle],
    *,
    rsi_period: int = 14,
    rsi_max: float = 45.0,
    pullback_tol_pts: float = 10.0,
) -> bool:
    """
    Return True when the 15m trend is SHORT_ONLY and a 5m PE trigger fires.

    Both sequences must be in chronological order (oldest first).
    Minimum required: 21 completed 5m candles and 21 completed 15m candles.
    """
    if len(candles_5m) < SLOW_EMA or len(candles_15m) < SLOW_EMA:
        return False

    latest = candles_5m[-1]
    if latest.timestamp.date() != date.today():
        return False

    if not is_global_trend_short(candles_15m):
        return False

    ema9_series = ema(candles_5m, FAST_EMA)
    e9_now, e9_prev = ema9_series[-1], ema9_series[-2]
    e21_now = ema(candles_5m, SLOW_EMA)[-1]
    rsi_now = rsi(candles_5m, rsi_period)[-1]
    if None in (e9_now, e9_prev, e21_now, rsi_now):
        return False

    crossover = candles_5m[-2].close >= e9_prev and latest.close < e9_now

    # Pullback to EMA21 — three conditions must ALL hold:
    #   1. Current close sits on or just below EMA21 (within tolerance).
    #      A close above EMA21 would trip the EMA-collapse exit, so the lower
    #      bound is 0 (not negative).
    #   2. Prior candle closed BELOW EMA9 — confirms price was in the downtrend
    #      before the bounce.  Without this, candles that have been crawling
    #      along EMA21 for multiple bars repeatedly fire a false pullback signal.
    #   3. Prior candle's high reached AT OR ABOVE EMA21 — confirms the bounce
    #      actually touched the level.  A candle that stayed entirely below
    #      EMA21 is not a pullback; it is just a continuation candle.
    e21_prev = ema(candles_5m, SLOW_EMA)[-2]
    prev = candles_5m[-2]
    pullback = (
        0 <= e21_now - latest.close <= pullback_tol_pts   # (1) close on/below EMA21
        and prev.close < e9_prev                           # (2) prior candle was below EMA9
        and e21_prev is not None
        and prev.high >= e21_prev                          # (3) prior high bounced to EMA21
    )

    return (crossover or pullback) and rsi_now < rsi_max
