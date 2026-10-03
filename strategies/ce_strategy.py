"""
CE entry strategy — SENSEX 5M CE Intraday V1.

All four conditions must be true on the most-recent completed candles:

    1. 5m  Close(0)        > 5m  EMA(close, 20, 0)   ← price above trend
    2. 5m  EMA(close, 9,0) > 5m  EMA(close, 20, 0)   ← short EMA above long EMA
    3. 5m  Close(0)        > 5m  High(1)              ← breakout above previous candle high
    4. 15m Close(0)        > 15m EMA(close, 20, 0)    ← higher-TF trend confirmed
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from market.candle_builder import Candle
from market.indicators import ema


def is_ce_signal(
    candles_5m: Sequence[Candle],
    candles_15m: Sequence[Candle],
) -> bool:
    """
    Return True when all four CE entry conditions are satisfied.

    Both sequences must be in chronological order (oldest first).
    Minimum required: 21 completed 5m candles and 21 completed 15m candles.
    """
    if len(candles_5m) < 21 or len(candles_15m) < 21:
        return False

    latest = candles_5m[-1]

    # ── Today-only guard ───────────────────────────────────────────────────────
    if latest.timestamp.date() != date.today():
        return False

    # ── 5-minute EMA values ────────────────────────────────────────────────────
    ema21_5m_series = ema(candles_5m, 20)
    ema9_5m_series  = ema(candles_5m, 9)

    ema21_0_5m = ema21_5m_series[-1]
    ema9_0_5m  = ema9_5m_series[-1]

    if None in (ema21_0_5m, ema9_0_5m):
        return False

    # ── 15-minute trend values ─────────────────────────────────────────────────
    close_0_15m = candles_15m[-1].close
    ema21_0_15m = ema(candles_15m, 20)[-1]

    if ema21_0_15m is None:
        return False

    # ── Four core conditions ───────────────────────────────────────────────────
    return (
        latest.close  > ema21_0_5m        # 1. price above 5m EMA21
        and ema9_0_5m > ema21_0_5m        # 2. EMA9 above EMA21
        and latest.close > candles_5m[-2].high  # 3. close above prev candle high
        and close_0_15m  > ema21_0_15m    # 4. 15m trend confirmed
    )
