"""
Opening Range Breakout (ORB) Strategy (5-minute timeframe).

Opening range:
    The HIGH and LOW of the FIRST completed 5m candle (09:15–09:20).

Entry logic (3-step):

  Step 1 — Sustain confirmation (09:20–09:25 candle)
    The candle IMMEDIATELY after the ORB candle must close on the correct side:
      CE: 09:20–09:25 close > ORB High  (price sustained above the range)
      PE: 09:20–09:25 close < ORB Low   (price sustained below the range)
    If the 09:20–09:25 candle closes inside the range, ORB is skipped for
    the day — no further ORB signals fire.

  Step 2 — Entry window (09:25–09:40)
    If sustain is confirmed, the entry fires on whichever candle in the
    09:25–09:35 window crosses the ORB level (standard crossover check).
    After 09:40 ORB is disabled entirely (handled by ORB_ACTIVE_UNTIL=09:40
    in settings; here the window guard provides a tighter internal check).

  Step 3 — Crossover (same as before)
    CE: prev close <= ORB High AND current close > ORB High
    PE: prev close >= ORB Low  AND current close < ORB Low

False-breakout filters (opt-in via keyword args):

    1. Body ratio  (ORB_MIN_BODY_RATIO > 0)
    2. Breakout buffer  (ORB_BUFFER_ATR_MULT > 0)
    3. 15-minute trend confirmation  (ORB_REQUIRE_15M_TREND = true)
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date

from market.candle_builder import Candle
from market.indicators import atr_at, ema

logger = logging.getLogger(__name__)

# Opening range = first completed 5m candle only (09:15–09:20)
ORB_CANDLES: int = 1

# The candle immediately after ORB that must confirm sustain (09:20–09:25)
_SUSTAIN_CANDLE_HOUR  = 9
_SUSTAIN_CANDLE_MIN   = 20

# Entry is only allowed on candles whose timestamp falls in this window.
# Candle timestamps mark the START of the 5m bar:
#   09:25 candle → fires at 09:30 close
#   09:30 candle → fires at 09:35 close
#   09:35 candle → fires at 09:40 close  ← last allowed
_ENTRY_WINDOW_START = (9, 25)
_ENTRY_WINDOW_END   = (9, 35)   # inclusive


def get_orb_range(candles_5m: Sequence[Candle]) -> tuple[float | None, float | None]:
    """
    Find the HIGH and LOW of the opening range for the current trading day.
    Opening range = the first ORB_CANDLES completed 5m candles (09:15–09:20).
    Returns (orb_high, orb_low) or (None, None) if not enough candles.
    """
    if not candles_5m:
        return None, None

    latest_date = candles_5m[-1].timestamp.date()

    today_candles = [
        c for c in candles_5m
        if c.timestamp.date() == latest_date
        and (c.timestamp.hour, c.timestamp.minute) >= (9, 15)
    ]

    if len(today_candles) < ORB_CANDLES:
        return None, None

    orb = today_candles[:ORB_CANDLES]
    orb_high = max(c.high for c in orb)
    orb_low  = min(c.low  for c in orb)
    return orb_high, orb_low


# ---------------------------------------------------------------------------
# Sustain + entry-window helpers
# ---------------------------------------------------------------------------

def _get_sustain_candle(candles_5m: Sequence[Candle]) -> Candle | None:
    """
    Return the 09:20–09:25 candle for today, or None if not yet available.
    This is the candle that must confirm the ORB is sustained.
    """
    latest_date = candles_5m[-1].timestamp.date()
    for c in candles_5m:
        if (
            c.timestamp.date() == latest_date
            and c.timestamp.hour == _SUSTAIN_CANDLE_HOUR
            and c.timestamp.minute == _SUSTAIN_CANDLE_MIN
        ):
            return c
    return None


def _in_entry_window(c0: Candle) -> bool:
    """True when the signal candle's timestamp falls in [09:25, 09:35]."""
    ts = (c0.timestamp.hour, c0.timestamp.minute)
    return _ENTRY_WINDOW_START <= ts <= _ENTRY_WINDOW_END


# ---------------------------------------------------------------------------
# Internal filter helpers
# ---------------------------------------------------------------------------

def _passes_body_filter(c0: Candle, min_body_ratio: float) -> bool:
    """
    True when the breakout candle's body is at least min_body_ratio of its range.
    A min_body_ratio of 0.0 disables the filter entirely.
    """
    if min_body_ratio <= 0.0:
        return True
    candle_range = max(c0.high - c0.low, 1.0)   # floor at 1 to avoid div/0
    body = abs(c0.close - c0.open)
    passes = (body / candle_range) >= min_body_ratio
    if not passes:
        logger.debug(
            "ORB body filter REJECTED  body=%.1f  range=%.1f  ratio=%.2f  min=%.2f",
            body, candle_range, body / candle_range, min_body_ratio,
        )
    return passes


def _passes_buffer_filter(
    c0: Candle,
    candles_5m: Sequence[Candle],
    orb_level: float,
    direction: int,          # +1 for CE (above), -1 for PE (below)
    buffer_atr_mult: float,
) -> bool:
    """
    True when the close exceeds the ORB level by at least ATR(14)*mult.
    direction=+1  → close must be > orb_level + buffer
    direction=-1  → close must be < orb_level - buffer
    A buffer_atr_mult of 0.0 disables the filter.
    When ATR is unavailable the filter is skipped (fail-open).
    """
    if buffer_atr_mult <= 0.0:
        return True
    atr_val = atr_at(candles_5m, period=14)
    if not atr_val:
        return True   # no ATR data — skip filter
    buffer = atr_val * buffer_atr_mult
    if direction == 1:
        passes = c0.close >= orb_level + buffer
    else:
        passes = c0.close <= orb_level - buffer
    if not passes:
        logger.debug(
            "ORB buffer filter REJECTED  close=%.2f  orb=%.2f  buffer=%.2f  (ATR=%.2f x %.2f)",
            c0.close, orb_level, buffer, atr_val, buffer_atr_mult,
        )
    return passes


def _passes_trend_filter(
    candles_15m: Sequence[Candle] | None,
    direction: int,          # +1 CE, -1 PE
) -> bool:
    """
    True when the 15m trend aligns with direction.
    CE (+1): 15m close > 15m EMA21
    PE (-1): 15m close < 15m EMA21
    Skipped when candles_15m is None/empty or EMA is unavailable.
    """
    if not candles_15m:
        return True
    ema21 = ema(candles_15m, 21)[-1]
    if ema21 is None:
        return True
    close_15m = candles_15m[-1].close
    if direction == 1:
        passes = close_15m > ema21
    else:
        passes = close_15m < ema21
    if not passes:
        logger.debug(
            "ORB 15m trend filter REJECTED  15m_close=%.2f  ema21=%.2f  direction=%d",
            close_15m, ema21, direction,
        )
    return passes


# ---------------------------------------------------------------------------
# Public signal functions
# ---------------------------------------------------------------------------

def is_orb_ce_signal(
    candles_5m: Sequence[Candle],
    candles_15m: Sequence[Candle] | None = None,
    *,
    min_body_ratio: float = 0.0,
    buffer_atr_mult: float = 0.0,
    require_15m_trend: bool = False,
) -> bool:
    """
    Return True if:
      1. The 09:20–09:25 (sustain) candle closed ABOVE the ORB High.
      2. The current signal candle is within the 09:25–09:35 entry window.
      3. The 5m close crosses ABOVE the ORB High.
      4. All enabled false-breakout filters pass.
    """
    if len(candles_5m) < ORB_CANDLES + 1:
        return False

    c0 = candles_5m[-1]
    c1 = candles_5m[-2]

    # ── Date guard ─────────────────────────────────────────────────────────────
    if c0.timestamp.date() != date.today():
        return False

    # ── Entry window: only 09:25, 09:30, 09:35 candles ───────────────────────
    if not _in_entry_window(c0):
        return False

    orb_high, _ = get_orb_range(candles_5m)
    if orb_high is None:
        return False

    # ── Sustain confirmation: 09:20–09:25 candle must close > ORB High ────────
    sustain = _get_sustain_candle(candles_5m)
    if sustain is None:
        logger.debug("ORB CE skipped — sustain candle (09:20) not yet available")
        return False
    if sustain.close <= orb_high:
        logger.debug(
            "ORB CE rejected — sustain candle close %.2f <= ORB High %.2f (no sustain)",
            sustain.close, orb_high,
        )
        return False

    # ── Breakout check: signal candle must close above ORB High ───────────────
    # The sustain candle (09:20) already confirmed the move is above the range.
    # On the entry candle we just require close > ORB High (price holding above).
    if c0.close <= orb_high:
        return False

    # ── False-breakout filters ─────────────────────────────────────────────────
    if not _passes_body_filter(c0, min_body_ratio):
        return False

    if not _passes_buffer_filter(c0, candles_5m, orb_high, +1, buffer_atr_mult):
        return False

    if require_15m_trend and not _passes_trend_filter(candles_15m, +1):
        return False

    return True


def is_orb_pe_signal(
    candles_5m: Sequence[Candle],
    candles_15m: Sequence[Candle] | None = None,
    *,
    min_body_ratio: float = 0.0,
    buffer_atr_mult: float = 0.0,
    require_15m_trend: bool = False,
) -> bool:
    """
    Return True if:
      1. The 09:20–09:25 (sustain) candle closed BELOW the ORB Low.
      2. The current signal candle is within the 09:25–09:35 entry window.
      3. The 5m close crosses BELOW the ORB Low.
      4. All enabled false-breakout filters pass.
    """
    if len(candles_5m) < ORB_CANDLES + 1:
        return False

    c0 = candles_5m[-1]
    c1 = candles_5m[-2]

    # ── Date guard ─────────────────────────────────────────────────────────────
    if c0.timestamp.date() != date.today():
        return False

    # ── Entry window: only 09:25, 09:30, 09:35 candles ───────────────────────
    if not _in_entry_window(c0):
        return False

    _, orb_low = get_orb_range(candles_5m)
    if orb_low is None:
        return False

    # ── Sustain confirmation: 09:20–09:25 candle must close < ORB Low ─────────
    sustain = _get_sustain_candle(candles_5m)
    if sustain is None:
        logger.debug("ORB PE skipped — sustain candle (09:20) not yet available")
        return False
    if sustain.close >= orb_low:
        logger.debug(
            "ORB PE rejected — sustain candle close %.2f >= ORB Low %.2f (no sustain)",
            sustain.close, orb_low,
        )
        return False

    # ── Breakout check: signal candle must close below ORB Low ────────────────
    # The sustain candle (09:20) already confirmed the move is below the range.
    # On the entry candle we just require close < ORB Low (price holding below).
    if c0.close >= orb_low:
        return False

    # ── False-breakout filters ─────────────────────────────────────────────────
    if not _passes_body_filter(c0, min_body_ratio):
        return False

    if not _passes_buffer_filter(c0, candles_5m, orb_low, -1, buffer_atr_mult):
        return False

    if require_15m_trend and not _passes_trend_filter(candles_15m, -1):
        return False

    return True
