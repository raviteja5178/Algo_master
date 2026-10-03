"""
NATR Trailing Stop Strategy  (ATR 5 Min Index Study).

Logic
-----
Normalised ATR (NATR) is used to build a dynamic trailing stop line that
flips direction when price crosses it.  A Buy (CE) signal fires the first
time price closes above the stop after it was below; a Sell (PE) signal
fires the first time price closes below the stop after it was above.

NOTE: This is a completely separate strategy from ATR Copilot (band breakout).
      ATR Copilot  = EMA21 ± ATR5×3.0 static symmetric bands — fires on band breakout.
      NATR         = ratcheting trailing stop — fires on stop crossover.

Calculation (mirrors the TradingView "ATR 5 Min Index Study"):

    ATR     = Wilder ATR(natr_period) on 5m candles
    NATR    = ATR / Close * 100                       (normalised %)
    loss    = natr_mult * NATR * Close / 100
            = natr_mult * ATR                         (simplifies to ATR mult)

    ATR Trailing Stop update rule (per new completed candle):
        if close > prev_stop:
            stop = max(prev_stop, close - loss)   # ratchet up in uptrend
        elif close < prev_stop:
            stop = min(prev_stop, close + loss)   # ratchet down in downtrend
        else:
            stop = close - loss                   # first candle seed

    CE signal: prev_close <= prev_stop  AND  close > stop  (cross above)
    PE signal: prev_close >= prev_stop  AND  close < stop  (cross below)

Config knobs (settings.py):
    ENABLE_NATR_STRATEGY   bool   (default False)
    NATR_PERIOD            int    ATR period  (default 21)
    NATR_MULT              float  ATR multiplier (default 3.0)

The stop line and direction state is STATELESS — recomputed from scratch on
every candle using the full candle buffer.  This is intentional: it means
the signal is deterministic and reproducible from historical data.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date

from market.candle_builder import Candle
from market.indicators import atr as calc_atr

logger = logging.getLogger(__name__)

# Minimum candles needed: natr_period + 1 for ATR seed + 1 prev candle for cross
_MIN_CANDLES = 25


def _compute_natr_stop(
    candles: Sequence[Candle],
    natr_period: int,
    natr_mult: float,
) -> list[float | None]:
    """
    Compute the ATR trailing stop line for the full candle series.

    Returns a list parallel to *candles*.  Positions where ATR is not yet
    available are None.  The stop starts as soon as ATR is computable.
    """
    n = len(candles)
    atr_series = calc_atr(candles, natr_period)
    result: list[float | None] = [None] * n

    prev_stop: float | None = None

    for i in range(1, n):
        atr_val = atr_series[i]
        if atr_val is None:
            prev_stop = None
            continue

        close = candles[i].close
        loss  = natr_mult * atr_val   # natr_mult * ATR  (NATR simplifies)

        if prev_stop is None:
            # First computable candle — seed the stop below price
            new_stop = close - loss
        elif close > prev_stop:
            new_stop = max(prev_stop, close - loss)   # ratchet up
        elif close < prev_stop:
            new_stop = min(prev_stop, close + loss)   # ratchet down
        else:
            new_stop = prev_stop

        result[i] = new_stop
        prev_stop = new_stop

    return result


def is_natr_ce_signal(
    candles_5m: Sequence[Candle],
    *,
    natr_period: int = 21,
    natr_mult: float = 3.0,
) -> bool:
    """
    Return True when the 5m close crosses ABOVE the NATR trailing stop
    on the most-recent completed candle (bullish flip — CE entry).

    Conditions:
      1. Latest candle is from today.
      2. Previous candle close was AT OR BELOW the stop (price was below stop).
      3. Current candle close is ABOVE the stop (price crossed above).
    """
    if len(candles_5m) < max(_MIN_CANDLES, natr_period + 3):
        return False

    if candles_5m[-1].timestamp.date() != date.today():
        return False

    stops = _compute_natr_stop(candles_5m, natr_period, natr_mult)

    stop_curr = stops[-1]
    stop_prev = stops[-2]
    if stop_curr is None or stop_prev is None:
        return False

    close_curr = candles_5m[-1].close
    close_prev = candles_5m[-2].close

    # Cross above: previous close was at/below stop, current close is above stop
    crossed_above = (close_prev <= stop_prev) and (close_curr > stop_curr)
    if not crossed_above:
        return False

    logger.debug(
        "NATR CE signal: close %.2f > stop %.2f  (prev close %.2f <= prev stop %.2f)",
        close_curr, stop_curr, close_prev, stop_prev,
    )
    return True


def is_natr_pe_signal(
    candles_5m: Sequence[Candle],
    *,
    natr_period: int = 21,
    natr_mult: float = 3.0,
) -> bool:
    """
    Return True when the 5m close crosses BELOW the NATR trailing stop
    on the most-recent completed candle (bearish flip — PE entry).

    Conditions:
      1. Latest candle is from today.
      2. Previous candle close was AT OR ABOVE the stop (price was above stop).
      3. Current candle close is BELOW the stop (price crossed below).
    """
    if len(candles_5m) < max(_MIN_CANDLES, natr_period + 3):
        return False

    if candles_5m[-1].timestamp.date() != date.today():
        return False

    stops = _compute_natr_stop(candles_5m, natr_period, natr_mult)

    stop_curr = stops[-1]
    stop_prev = stops[-2]
    if stop_curr is None or stop_prev is None:
        return False

    close_curr = candles_5m[-1].close
    close_prev = candles_5m[-2].close

    # Cross below: previous close was at/above stop, current close is below stop
    crossed_below = (close_prev >= stop_prev) and (close_curr < stop_curr)
    if not crossed_below:
        return False

    logger.debug(
        "NATR PE signal: close %.2f < stop %.2f  (prev close %.2f >= prev stop %.2f)",
        close_curr, stop_curr, close_prev, stop_prev,
    )
    return True
