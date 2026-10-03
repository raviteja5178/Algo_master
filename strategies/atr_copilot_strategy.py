"""
ATR Copilot Strategy  (CE_ATR / PE_ATR).

Logic
-----
Based on the TradingView "ATR 5 Min Index Study".  Rather than building a
ratchet trailing stop (NATR strategy), this strategy constructs *static*
upper and lower bands around an EMA and fires when price closes outside the
noise zone for the first time — i.e. the previous candle was INSIDE the band
and the current candle closes OUTSIDE it.

Band calculation:
    EMA  = EMA(ema_period) of 5m close prices
    ATR  = Wilder ATR(atr_period) on 5m candles
    Upper band = EMA + ATR * band_mult
    Lower band = EMA - ATR * band_mult

CE_ATR signal (bullish breakout):
    1. Previous 5m candle closed BELOW or AT the upper band (was inside the noise zone).
    2. Current 5m candle closes ABOVE the upper band BY AT LEAST breakout_buffer_atr_mult × ATR
       (filters marginal / false breakouts caused by a single wick tick).
    3. R:R >= ATR_COPILOT_LONG_MIN_RR  (CE setups are held to a stricter gate).

PE_ATR signal (bearish breakout):
    1. Previous 5m candle closed ABOVE or AT the lower band (was inside the noise zone).
    2. Current 5m candle closes BELOW the lower band BY AT LEAST breakout_buffer_atr_mult × ATR.
    3. R:R >= ATR_COPILOT_MIN_RR.

Config knobs (settings.py):
    ENABLE_ATR_COPILOT_STRATEGY      bool   (default False — opt-in)
    ATR_COPILOT_PERIOD               int    ATR look-back period  (default 5)
    ATR_COPILOT_EMA_PERIOD           int    EMA look-back period  (default 21)
    ATR_COPILOT_BAND_MULT            float  ATR multiplier for band width  (default 3.0)
    ATR_COPILOT_MIN_RR               float  Minimum R:R for PE entries  (default 1.2)
    ATR_COPILOT_LONG_MIN_RR          float  Minimum R:R for CE entries  (default 2.0)
    ATR_COPILOT_BREAKOUT_BUFFER      float  Minimum extra clearance past the band as a
                                            fraction of ATR.  Rejects marginal breakouts
                                            where close is only a few points past the band.
                                            0.0 = disabled / raw band touch fires (default).
                                            0.2 = close must exceed band by at least 0.2×ATR.
                                            Read from .env — no hardcoded constant in code.

The strategy is fully STATELESS — bands are recomputed from scratch on every
call using the full candle buffer.  This makes back-testing reproducible and
avoids any state management across candle events.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date

from market.candle_builder import Candle
from market.indicators import atr as calc_atr, ema as calc_ema

logger = logging.getLogger(__name__)

# Minimum candles needed: ema_period candles to seed EMA + 1 prev candle for
# the "inside-band" check.  We enforce ema_period + atr_period + 2 as a safe
# lower bound so both indicators are fully warm.
_MIN_EXTRA = 2


def _compute_bands(
    candles: Sequence[Candle],
    atr_period: int,
    ema_period: int,
    band_mult: float,
) -> tuple[list[float | None], list[float | None]]:
    """
    Compute upper and lower ATR bands for the full candle series.

    Returns (upper_bands, lower_bands) — both parallel to *candles*.
    Positions where either indicator is not yet available are None.
    """
    n = len(candles)
    ema_series = calc_ema(candles, ema_period)   # list[float], same length
    atr_series = calc_atr(candles, atr_period)   # list[float | None], same length

    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n

    for i in range(n):
        atr_val = atr_series[i]
        ema_val = ema_series[i]
        if atr_val is None or ema_val is None:
            continue
        band = band_mult * atr_val
        upper[i] = ema_val + band
        lower[i] = ema_val - band

    return upper, lower


def is_atr_copilot_ce_signal(
    candles_5m: Sequence[Candle],
    *,
    atr_period: int = 5,
    ema_period: int = 21,
    band_mult: float = 3.0,
    breakout_buffer: float | None = None,
) -> bool:
    """
    Return True when the current 5m candle closes ABOVE the upper ATR band
    by at least breakout_buffer × ATR, and the previous candle was BELOW or
    AT the upper band (first-bar breakout — no continuation entries).

    Conditions:
      1. Latest candle is from today.
      2. Enough candles to warm both EMA and ATR.
      3. Previous close <= upper_band[-2]  (was inside the noise zone).
      4. Current close > upper_band[-1] + breakout_buffer × ATR[-1]
         (genuine breakout, not a marginal tick past the band).

    breakout_buffer=0.0 disables the buffer and reverts to raw band-touch behaviour.
    breakout_buffer=None (default) reads from settings.ATR_COPILOT_BREAKOUT_BUFFER so the
    value is always driven by the .env property — no hardcoded constant anywhere.
    """
    if breakout_buffer is None:
        from config import settings as _s
        breakout_buffer = _s.ATR_COPILOT_BREAKOUT_BUFFER
    min_candles = ema_period + atr_period + _MIN_EXTRA
    if len(candles_5m) < min_candles:
        return False

    if candles_5m[-1].timestamp.date() != date.today():
        return False

    upper, _ = _compute_bands(candles_5m, atr_period, ema_period, band_mult)

    ub_curr = upper[-1]
    ub_prev = upper[-2]
    if ub_curr is None or ub_prev is None:
        return False

    close_curr = candles_5m[-1].close
    close_prev = candles_5m[-2].close

    # Previous candle must have been inside (at or below upper band)
    if close_prev > ub_prev:
        logger.debug(
            "ATR Copilot CE: no fresh breakout — prev close %.2f already above upper band %.2f",
            close_prev, ub_prev,
        )
        return False

    # Compute the minimum clearance required above the band
    required_clearance = 0.0
    if breakout_buffer > 0.0:
        from market.indicators import atr as _calc_atr
        atr_series = _calc_atr(candles_5m, atr_period)
        atr_curr = atr_series[-1]
        if atr_curr is not None:
            required_clearance = breakout_buffer * atr_curr

    # Current close must exceed the band by the required clearance
    if close_curr <= ub_curr + required_clearance:
        if close_curr > ub_curr:
            logger.debug(
                "ATR Copilot CE: breakout filtered — close %.2f only %.2f pts above band %.2f "
                "(required %.2f pts = %.1f x ATR)",
                close_curr, close_curr - ub_curr, ub_curr,
                required_clearance, breakout_buffer,
            )
        return False

    logger.debug(
        "ATR Copilot CE: close %.2f > upper band %.2f + buffer %.2f  (prev close %.2f <= %.2f)",
        close_curr, ub_curr, required_clearance, close_prev, ub_prev,
    )
    return True


def is_atr_copilot_pe_signal(
    candles_5m: Sequence[Candle],
    *,
    atr_period: int = 5,
    ema_period: int = 21,
    band_mult: float = 3.0,
    breakout_buffer: float | None = None,
) -> bool:
    """
    Return True when the current 5m candle closes BELOW the lower ATR band
    by at least breakout_buffer × ATR, and the previous candle was ABOVE or
    AT the lower band (first-bar breakout — no continuation entries).

    Conditions:
      1. Latest candle is from today.
      2. Enough candles to warm both EMA and ATR.
      3. Previous close >= lower_band[-2]  (was inside the noise zone).
      4. Current close < lower_band[-1] - breakout_buffer × ATR[-1]
         (genuine breakout, not a marginal tick past the band).

    breakout_buffer=0.0 disables the buffer and reverts to raw band-touch behaviour.
    breakout_buffer=None (default) reads from settings.ATR_COPILOT_BREAKOUT_BUFFER so the
    value is always driven by the .env property — no hardcoded constant anywhere.
    """
    if breakout_buffer is None:
        from config import settings as _s
        breakout_buffer = _s.ATR_COPILOT_BREAKOUT_BUFFER
    min_candles = ema_period + atr_period + _MIN_EXTRA
    if len(candles_5m) < min_candles:
        return False

    if candles_5m[-1].timestamp.date() != date.today():
        return False

    _, lower = _compute_bands(candles_5m, atr_period, ema_period, band_mult)

    lb_curr = lower[-1]
    lb_prev = lower[-2]
    if lb_curr is None or lb_prev is None:
        return False

    close_curr = candles_5m[-1].close
    close_prev = candles_5m[-2].close

    # Previous candle must have been inside (at or above lower band)
    if close_prev < lb_prev:
        logger.debug(
            "ATR Copilot PE: no fresh breakout — prev close %.2f already below lower band %.2f",
            close_prev, lb_prev,
        )
        return False

    # Compute the minimum clearance required below the band
    required_clearance = 0.0
    if breakout_buffer > 0.0:
        from market.indicators import atr as _calc_atr
        atr_series = _calc_atr(candles_5m, atr_period)
        atr_curr = atr_series[-1]
        if atr_curr is not None:
            required_clearance = breakout_buffer * atr_curr

    # Current close must be below the band by the required clearance
    if close_curr >= lb_curr - required_clearance:
        if close_curr < lb_curr:
            logger.debug(
                "ATR Copilot PE: breakout filtered — close %.2f only %.2f pts below band %.2f "
                "(required %.2f pts = %.1f x ATR)",
                close_curr, lb_curr - close_curr, lb_curr,
                required_clearance, breakout_buffer,
            )
        return False

    logger.debug(
        "ATR Copilot PE: close %.2f < lower band %.2f - buffer %.2f  (prev close %.2f >= %.2f)",
        close_curr, lb_curr, required_clearance, close_prev, lb_prev,
    )
    return True
