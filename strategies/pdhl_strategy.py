"""
Previous Day High / Low (PDHL) Breakout Strategy.

Logic:
──────
The previous day's HIGH and LOW are widely watched levels — institutional
orders cluster around them. A clean breakout and close beyond these levels,
especially early in the session, often has strong follow-through.

CE_PDHL signal (previous day high breakout):
    1. Previous day high (PDH) is available.
    2. Previous candle closed AT or BELOW PDH (not already above).
    3. Current candle closes ABOVE PDH (clean breakout).
    4. Current candle close > previous candle high (momentum confirmation).

PE_PDHL signal (previous day low breakout):
    Mirror — current close breaks below previous day low.

Also exposes get_previous_day_hl() which main.py calls at startup to
fetch and store the PDH/PDL from historical data.

Config knobs (all in settings.py):
    ENABLE_PDHL_STRATEGY     bool   (default False — opt-in)
    PDHL_BUFFER_PTS          float  close must exceed PDH/PDL by this many pts (default 0)
                                    prevents 1-tick noise breakouts
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date

from market.candle_builder import Candle

logger = logging.getLogger(__name__)


def is_pdhl_ce_signal(
    candles_5m: Sequence[Candle],
    prev_day_high: float | None,
    *,
    buffer_pts: float = 0.0,
) -> bool:
    """
    Return True when the latest 5m candle closes above the previous day high.

    Conditions:
      1. prev_day_high is available.
      2. Previous candle closed at or below PDH (fresh crossover, not continuation).
      3. Current candle closes above PDH + buffer_pts.
      4. Current close > previous candle high (momentum confirmation).
    """
    if prev_day_high is None or prev_day_high <= 0:
        return False
    if len(candles_5m) < 2:
        return False

    c0 = candles_5m[-1]
    c1 = candles_5m[-2]

    if c0.timestamp.date() != date.today():
        return False

    level = prev_day_high + buffer_pts

    # Fresh crossover: previous candle was at or below PDH
    if c1.close > prev_day_high:
        logger.debug(
            "PDHL CE: not a fresh crossover — prev close %.2f already above PDH %.2f",
            c1.close, prev_day_high,
        )
        return False

    # Current close must clear the level
    if c0.close <= level:
        return False

    # Momentum: close must also be above previous candle high
    if c0.close <= c1.high:
        return False

    return True


def is_pdhl_pe_signal(
    candles_5m: Sequence[Candle],
    prev_day_low: float | None,
    *,
    buffer_pts: float = 0.0,
) -> bool:
    """
    Return True when the latest 5m candle closes below the previous day low.

    Conditions:
      1. prev_day_low is available.
      2. Previous candle closed at or above PDL (fresh crossover, not continuation).
      3. Current candle closes below PDL - buffer_pts.
      4. Current close < previous candle low (momentum confirmation).
    """
    if prev_day_low is None or prev_day_low <= 0:
        return False
    if len(candles_5m) < 2:
        return False

    c0 = candles_5m[-1]
    c1 = candles_5m[-2]

    if c0.timestamp.date() != date.today():
        return False

    level = prev_day_low - buffer_pts

    # Fresh crossover: previous candle was at or above PDL
    if c1.close < prev_day_low:
        logger.debug(
            "PDHL PE: not a fresh crossover — prev close %.2f already below PDL %.2f",
            c1.close, prev_day_low,
        )
        return False

    # Current close must break below the level
    if c0.close >= level:
        return False

    # Momentum: close must also be below previous candle low
    if c0.close >= c1.low:
        return False

    return True
