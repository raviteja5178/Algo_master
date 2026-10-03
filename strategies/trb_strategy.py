"""
Time Range Breakout (TRB) Strategy — 9:45-10:00 AM 15m breakout (5m timeframe triggers).

This strategy identifies the HIGH and LOW of the 15-minute completed candle
starting at 09:45 AM (spanning 09:45 to 10:00).
Once the 10:00 AM window completes, it monitors 5-minute candle closes for breakouts:
    CE_TRB: 5m close crosses ABOVE the 15m high boundary.
    PE_TRB: 5m close crosses BELOW the 15m low boundary.

Optional filters (opt-in):
    - Body ratio: breakout candle body / range >= min_body_ratio.
    - Buffer: close must exceed level by ATR(14) * mult.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date

from market.candle_builder import Candle
from market.indicators import atr_at

logger = logging.getLogger(__name__)


def get_trb_range(candles_15m: Sequence[Candle]) -> tuple[float | None, float | None]:
    """
    Find the HIGH and LOW of the 15-minute anchor candle starting at 09:45 AM today.
    Returns (trb_high, trb_low) or (None, None) if the candle is not yet complete.
    """
    if not candles_15m:
        return None, None

    latest_date = candles_15m[-1].timestamp.date()

    # Search for the 15-minute candle starting exactly at 09:45 AM today
    today_15m = [
        c for c in candles_15m
        if c.timestamp.date() == latest_date
        and c.timestamp.hour == 9
        and c.timestamp.minute == 45
    ]

    if not today_15m:
        return None, None

    # The 09:45 AM candle spans 09:45 to 10:00. It is fully completed at 10:00 AM.
    anchor = today_15m[0]
    return anchor.high, anchor.low


# ── Internal filter helpers ───────────────────────────────────────────────────

def _passes_body_filter(c0: Candle, min_body_ratio: float) -> bool:
    """
    True when the breakout candle's body is at least min_body_ratio of its range.
    A min_body_ratio of 0.0 disables the filter.
    """
    if min_body_ratio <= 0.0:
        return True
    candle_range = max(c0.high - c0.low, 1.0)
    body = abs(c0.close - c0.open)
    passes = (body / candle_range) >= min_body_ratio
    if not passes:
        logger.debug(
            "TRB body filter REJECTED  body=%.1f  range=%.1f  ratio=%.2f  min=%.2f",
            body, candle_range, body / candle_range, min_body_ratio,
        )
    return passes


def _passes_buffer_filter(
    c0: Candle,
    candles_5m: Sequence[Candle],
    level: float,
    direction: int,          # +1 for CE (above), -1 for PE (below)
    buffer_atr_mult: float,
) -> bool:
    """
    True when the close exceeds the TRB boundary by at least ATR(14)*mult.
    """
    if buffer_atr_mult <= 0.0:
        return True
    atr_val = atr_at(candles_5m, period=14)
    if not atr_val:
        return True   # no ATR data — skip filter
    buffer = atr_val * buffer_atr_mult
    if direction == 1:
        passes = c0.close >= level + buffer
    else:
        passes = c0.close <= level - buffer
    if not passes:
        logger.debug(
            "TRB buffer filter REJECTED  close=%.2f  level=%.2f  buffer=%.2f  (ATR=%.2f x %.2f)",
            c0.close, level, buffer, atr_val, buffer_atr_mult,
        )
    return passes


# ── Public signal functions ───────────────────────────────────────────────────

def is_trb_ce_signal(
    candles_5m: Sequence[Candle],
    candles_15m: Sequence[Candle],
    *,
    min_body_ratio: float = 0.0,
    buffer_atr_mult: float = 0.0,
) -> bool:
    """
    Return True if the 5m close crosses ABOVE the 9:45 AM 15m candle high.
    """
    if len(candles_5m) < 2:
        return False

    c0 = candles_5m[-1]
    c1 = candles_5m[-2]

    # ── Date guard ─────────────────────────────────────────────────────────────
    if c0.timestamp.date() != date.today():
        return False

    # ── Time guard: No trades before or during the 09:45–10:00 anchor candle itself ──
    # The 09:45 15m candle is fully complete at 10:00:00.
    # Therefore, the first 5m candle that can breakout is the 10:00–10:05 candle,
    # which has a timestamp of 10:00 (representing start) or completed close at 10:05.
    ts = (c0.timestamp.hour, c0.timestamp.minute)
    if ts < (10, 0):
        return False

    trb_high, _ = get_trb_range(candles_15m)
    if trb_high is None:
        return False

    # ── Crossover check ────────────────────────────────────────────────────────
    if not (c1.close <= trb_high and c0.close > trb_high):
        return False

    # ── False-breakout filters ─────────────────────────────────────────────────
    if not _passes_body_filter(c0, min_body_ratio):
        return False

    if not _passes_buffer_filter(c0, candles_5m, trb_high, +1, buffer_atr_mult):
        return False

    return True


def is_trb_pe_signal(
    candles_5m: Sequence[Candle],
    candles_15m: Sequence[Candle],
    *,
    min_body_ratio: float = 0.0,
    buffer_atr_mult: float = 0.0,
) -> bool:
    """
    Return True if the 5m close crosses BELOW the 9:45 AM 15m candle low.
    """
    if len(candles_5m) < 2:
        return False

    c0 = candles_5m[-1]
    c1 = candles_5m[-2]

    # ── Date guard ─────────────────────────────────────────────────────────────
    if c0.timestamp.date() != date.today():
        return False

    # ── Time guard: No trades before or during the 09:45–10:00 anchor candle itself ──
    ts = (c0.timestamp.hour, c0.timestamp.minute)
    if ts < (10, 0):
        return False

    _, trb_low = get_trb_range(candles_15m)
    if trb_low is None:
        return False

    # ── Crossover check ────────────────────────────────────────────────────────
    if not (c1.close >= trb_low and c0.close < trb_low):
        return False

    # ── False-breakout filters ─────────────────────────────────────────────────
    if not _passes_body_filter(c0, min_body_ratio):
        return False

    if not _passes_buffer_filter(c0, candles_5m, trb_low, -1, buffer_atr_mult):
        return False

    return True
