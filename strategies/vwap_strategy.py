"""
VWAP Retest Strategy.

Logic:
──────
Institutions use VWAP as a benchmark — large orders cluster around it.
When price pulls back to VWAP after a directional move and a 5m candle
closes back on the right side, it signals resumption of that move.

CE_VWAP signal (bullish retest):
    1. At least one of the previous N candles closed BELOW VWAP
       (price touched / dipped into VWAP — the "retest").
    2. The current candle closes ABOVE VWAP (price reclaimed VWAP).
    3. The current candle close > previous candle high (momentum confirmation).
    4. VWAP itself is rising (or flat) — not in a downtrend.

PE_VWAP signal (bearish retest):
    Mirror of the above — dip above VWAP then close back below.

Config knobs (all in settings.py):
    ENABLE_VWAP_STRATEGY      bool   (default False — opt-in)
    VWAP_RETEST_LOOKBACK      int    candles to look back for the retest (default 3)
    VWAP_MIN_BOUNCE_PTS       float  minimum distance close must be above/below VWAP (default 0)
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date

from market.candle_builder import Candle

logger = logging.getLogger(__name__)


def is_vwap_ce_signal(
    candles_5m: Sequence[Candle],
    vwap: float | None,
    *,
    retest_lookback: int = 3,
    min_bounce_pts: float = 0.0,
) -> bool:
    """
    Return True when:
      1. VWAP is available and valid.
      2. Within the last *retest_lookback* completed candles, at least one
         closed BELOW VWAP (the retest dip).
      3. The current (latest) candle closes ABOVE VWAP.
      4. Current close > previous candle high (momentum confirmation).
      5. Close is at least min_bounce_pts above VWAP.
    """
    if vwap is None or vwap <= 0:
        return False
    if len(candles_5m) < retest_lookback + 1:
        return False

    c0 = candles_5m[-1]
    c1 = candles_5m[-2]

    if c0.timestamp.date() != date.today():
        return False

    # Current candle must close above VWAP
    if c0.close <= vwap:
        return False

    # Momentum: close must break above previous candle high
    if c0.close <= c1.high:
        return False

    # Minimum bounce distance above VWAP
    if min_bounce_pts > 0 and (c0.close - vwap) < min_bounce_pts:
        return False

    # At least one candle in the lookback window must have closed below VWAP
    lookback = candles_5m[-(retest_lookback + 1):-1]  # exclude current
    if not any(c.close < vwap for c in lookback):
        logger.debug(
            "VWAP CE: no retest — none of last %d candles closed below VWAP %.2f",
            retest_lookback, vwap,
        )
        return False

    return True


def is_vwap_pe_signal(
    candles_5m: Sequence[Candle],
    vwap: float | None,
    *,
    retest_lookback: int = 3,
    min_bounce_pts: float = 0.0,
) -> bool:
    """
    Return True when:
      1. VWAP is available and valid.
      2. Within the last *retest_lookback* completed candles, at least one
         closed ABOVE VWAP (the retest pop).
      3. The current (latest) candle closes BELOW VWAP.
      4. Current close < previous candle low (momentum confirmation).
      5. Close is at least min_bounce_pts below VWAP.
    """
    if vwap is None or vwap <= 0:
        return False
    if len(candles_5m) < retest_lookback + 1:
        return False

    c0 = candles_5m[-1]
    c1 = candles_5m[-2]

    if c0.timestamp.date() != date.today():
        return False

    # Current candle must close below VWAP
    if c0.close >= vwap:
        return False

    # Momentum: close must break below previous candle low
    if c0.close >= c1.low:
        return False

    # Minimum bounce distance below VWAP
    if min_bounce_pts > 0 and (vwap - c0.close) < min_bounce_pts:
        return False

    # At least one candle in the lookback window must have closed above VWAP
    lookback = candles_5m[-(retest_lookback + 1):-1]  # exclude current
    if not any(c.close > vwap for c in lookback):
        logger.debug(
            "VWAP PE: no retest — none of last %d candles closed above VWAP %.2f",
            retest_lookback, vwap,
        )
        return False

    return True
