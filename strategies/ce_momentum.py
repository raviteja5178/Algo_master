"""
CE Momentum entry strategy — Phase 2 (acceleration / continuation).

Fires during the afternoon breakout window (default 13:30–14:30 IST) when
the market is already in a confirmed uptrend and produces a large-body candle,
even if the close does NOT exceed the previous candle high.

Rules (all must be true on the most-recent COMPLETED 5m candle):

    1. 5m candle body  >= MOMENTUM_MIN_BODY_PTS   ← strong bull candle
    2. 5m close        > 5m EMA9[0]               ← price above short EMA
    3. 5m EMA9[0]      > 5m EMA21[0]              ← short EMA above medium EMA
    4. 15mins close[0]   > 15mins EMA21[0]            ← higher-TF trend confirmed
    5. candle time     in [MOMENTUM_WINDOW_START, MOMENTUM_WINDOW_END)

Body = abs(close - open).  This filters out doji / indecision candles and
only catches genuine acceleration moves like the 13:55 and 14:00 candles today.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import time

from market.candle_builder import Candle
from market.indicators import ema


def is_ce_momentum_signal(
    candles_5m: Sequence[Candle],
    candles_15m: Sequence[Candle],
    min_body_pts: float = 40.0,
    window_start: time = time(13, 30),
    window_end: time = time(14, 30),
    atr_body_ratio: float = 0.5,   # body must be >= 50% of ATR(14) when ATR is available
) -> bool:
    """
    Return True when the momentum CE conditions are all satisfied.

    Both sequences must be in chronological order (oldest first).
    Minimum required: 21 completed 5m candles and 21 completed 15m candles.

    The body threshold adapts to current volatility when ATR is available:
        effective_min_body = max(min_body_pts, ATR(14) * atr_body_ratio)
    This prevents firing on weak candles on low-volatility days and raises
    the bar automatically on high-volatility days.
    """
    if len(candles_5m) < 21 or len(candles_15m) < 21:
        return False

    latest = candles_5m[-1]

    # ── Rule 5: time window ────────────────────────────────────────────────────
    candle_time = latest.timestamp.time()
    if not (window_start <= candle_time < window_end):
        return False

    # ── Rule 1: strong bull body (ATR-adaptive) ────────────────────────────────
    body = latest.close - latest.open   # positive = bullish candle
    from market.indicators import atr_at
    atr_val = atr_at(candles_5m, period=14)
    effective_min = max(min_body_pts, atr_val * atr_body_ratio) if atr_val else min_body_pts
    if body < effective_min:
        return False

    # ── 5-minute EMA values ────────────────────────────────────────────────────
    ema9_5m  = ema(candles_5m, 9)
    ema21_5m = ema(candles_5m, 21)

    ema9_0  = ema9_5m[-1]
    ema21_0 = ema21_5m[-1]

    if None in (ema9_0, ema21_0):
        return False

    # ── Rule 2: close > EMA9 ──────────────────────────────────────────────────
    if latest.close <= ema9_0:
        return False

    # ── Rule 3: EMA9 > EMA21 ──────────────────────────────────────────────────
    if ema9_0 <= ema21_0:
        return False

    # ── Rule 4: 15mins trend ───────────────────────────────────────────────────
    ema21_15m   = ema(candles_15m, 21)
    ema21_0_15m = ema21_15m[-1]
    if ema21_0_15m is None:
        return False

    return candles_15m[-1].close > ema21_0_15m
