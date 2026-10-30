"""
PE entry strategy — SENSEX 5m EMA 9/21 + RSI (copied rule-set).

Macro trend (15m, latest completed candle):
    GLOBAL_TREND = SHORT_ONLY when  15m Close < 15m EMA9  AND  15m EMA9 < 15m EMA21

Trigger (5m, latest completed candle) — any of:
    c) EMA cross : (opt-in, ema_cross=True) EMA9 crosses BELOW EMA21 on this candle
                   (prev EMA9 >= prev EMA21  AND  EMA9 < EMA21)
    a) Crossover : prev 5m close >= prev EMA9  AND  5m close < EMA9
    b) Pullback  : price pulled back from below EMA9 up to EMA21, then
                   the current candle is rejected at EMA21.  All must hold:
                     1. Current close is on/below EMA21:
                           0 <= EMA21 − close <= pullback_tol_pts
                     2. A close below EMA9 within the PULLBACK_TREND_LOOKBACK
                        candles before the current one (was in the downtrend
                        before the bounce — not already crawling on EMA21).
                     3. Prior candle's high reached AT OR ABOVE EMA21
                        (actually touched the level, not just hovered near it).
                     4. Current candle turned back down: red (close < open)
                        and close < prior close.  A candle still rising into
                        EMA21 is the bounce, not the rejection.

Momentum:
    5m RSI(rsi_period) < rsi_max   (default 45)
"""

from __future__ import annotations

from collections.abc import Sequence
from utils.time_utils import today_ist

from market.candle_builder import Candle
from market.indicators import atr_at, ema, rsi

FAST_EMA = 9
SLOW_EMA = 21
# Candles before the current one searched for the pre-bounce close below EMA9.
PULLBACK_TREND_LOOKBACK = 4


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
    ema_cross: bool = False,
    cross_without_15m: bool = False,
    cross_only: bool = False,
    ignore_15m: bool = False,
    require_candle_color: bool = False,
    min_body_atr: float = 0.0,
) -> bool:
    """
    Return True when the 15m trend is SHORT_ONLY and a 5m PE trigger fires.

    Both sequences must be in chronological order (oldest first).
    Minimum required: 21 completed 5m candles and 21 completed 15m candles.
    """
    if len(candles_5m) < SLOW_EMA or (not ignore_15m and len(candles_15m) < SLOW_EMA):
        return False

    latest = candles_5m[-1]
    if latest.timestamp.date() != today_ist():
        return False

    trend_ok = True if ignore_15m else is_global_trend_short(candles_15m)
    if not trend_ok and not ((ema_cross or cross_only) and cross_without_15m):
        return False

    ema9_series = ema(candles_5m, FAST_EMA)
    e9_now, e9_prev = ema9_series[-1], ema9_series[-2]
    e21_now = ema(candles_5m, SLOW_EMA)[-1]
    rsi_now = rsi(candles_5m, rsi_period)[-1]
    if None in (e9_now, e9_prev, e21_now, rsi_now):
        return False

    # require_candle_color: every trigger (crossover / EMA cross / pullback) needs the
    # signal candle itself to be bearish (close < open).
    if require_candle_color and not latest.close < latest.open:
        return False

    # min_body_atr: the signal candle body must be >= min_body_atr x ATR(14).  Fails open
    # while ATR is not computable.
    if min_body_atr > 0:
        _atr = atr_at(candles_5m, period=14)
        if _atr and abs(latest.close - latest.open) < min_body_atr * _atr:
            return False

    crossover = candles_5m[-2].close >= e9_prev and latest.close < e9_now

    # EMA9 x EMA21 cross (opt-in): EMA9 moves from >= EMA21 to < EMA21 on this candle.
    # cross_without_15m: this trigger alone may fire when the 15m trend is not SHORT_ONLY.
    # cross_only: the cross is the ONLY trigger (no close-vs-EMA9 crossover / pullback).
    e21_series = ema(candles_5m, SLOW_EMA)
    cross = bool((ema_cross or cross_only) and e21_series[-2] is not None
                 and e9_prev >= e21_series[-2] and e9_now < e21_now)
    if cross_only or not trend_ok:
        return cross and rsi_now < rsi_max
    if cross:
        crossover = True

    # Pullback to EMA21 — all conditions must hold:
    #   1. Current close sits on or just below EMA21 (within tolerance).
    #      A close above EMA21 would trip the EMA-collapse exit, so the lower
    #      bound is 0 (not negative).
    #   2. A recent candle closed BELOW EMA9 — price was in the downtrend
    #      before the bounce.  Without this, candles crawling along EMA21 for
    #      many bars repeatedly fire a false pullback signal.  (Requiring it of
    #      the prior candle alone made 1+2 describe a candle RISING to EMA21.)
    #   3. Prior candle's high reached AT OR ABOVE EMA21 — the bounce actually
    #      touched the level.  A candle that stayed entirely below EMA21 is not
    #      a pullback; it is just a continuation candle.
    #   4. Current candle is red and closes below the prior close — the
    #      rejection has started.
    e21_prev = ema(candles_5m, SLOW_EMA)[-2]
    prev = candles_5m[-2]
    _recent = range(-PULLBACK_TREND_LOOKBACK - 1, -1)          # candles before the current one
    was_trending = any(
        ema9_series[k] is not None and candles_5m[k].close < ema9_series[k] for k in _recent
    )
    pullback = (
        0 <= e21_now - latest.close <= pullback_tol_pts   # (1) close on/below EMA21
        and was_trending                                   # (2) downtrend before the bounce
        and e21_prev is not None
        and prev.high >= e21_prev                          # (3) prior high bounced to EMA21
        and latest.close < latest.open                     # (4) rejection candle: red
        and latest.close < prev.close                      #     and closing lower
    )

    return (crossover or pullback) and rsi_now < rsi_max
