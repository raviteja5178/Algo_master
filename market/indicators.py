"""
Technical indicator calculations.

All functions operate on plain lists/sequences of floats (close prices or
Candle objects).  They do NOT use external TA libraries so they are
deterministic and easy to unit-test.

EMA convention:
    ema[0] = most-recent value  (i.e. the latest completed candle EMA)
    The seed value for EMA is the simple mean of the first `period` elements.

ATR convention:
    True Range = max(high-low, abs(high-prev_close), abs(low-prev_close))
    ATR(n) = Wilder-smoothed (RMA) average of last n true ranges.
    Returns a list parallel to the input; early values where TR cannot be
    computed are None.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from market.candle_builder import Candle


def _closes(candles: Sequence[Union[Candle, float]]) -> list[float]:
    if candles and isinstance(candles[0], Candle):
        return [c.close for c in candles]  # type: ignore[union-attr]
    return list(candles)  # type: ignore[arg-type]


def ema(values: Sequence[Union[Candle, float]], period: int) -> list[float]:
    """
    Return a list of EMA values in the same order as *values*.

    values[0] is the OLDEST item (chronological order for calculation).
    The returned list has the same length as values; early items that cannot
    have a full seed window are None.
    """
    closes = _closes(values)
    n = len(closes)
    if n < period:
        return [None] * n  # type: ignore[list-item]

    result: list[float | None] = [None] * n
    k = 2.0 / (period + 1)

    # seed: SMA of first `period` closes
    seed = sum(closes[:period]) / period
    result[period - 1] = seed

    for i in range(period, n):
        result[i] = closes[i] * k + result[i - 1] * (1.0 - k)  # type: ignore[operator]

    return result  # type: ignore[return-value]


def ema_at(values: Sequence[Union[Candle, float]], period: int, index: int = -1) -> float | None:
    """
    Return the EMA value at a specific position.
    index=-1 means the most-recent candle (chronological last).
    """
    result = ema(values, period)
    return result[index] if result else None


def atr(candles: Sequence[Candle], period: int = 14) -> list[float | None]:
    """
    Average True Range using Wilder's smoothing (RMA).

    Requires Candle objects (needs high, low, close).
    Returns a list the same length as *candles*; positions where ATR cannot
    yet be computed are None.

    Wilder smoothing: ATR[i] = (ATR[i-1] * (period-1) + TR[i]) / period
    Seed: simple mean of the first *period* true ranges.
    """
    n = len(candles)
    if n < period + 1:
        return [None] * n  # type: ignore[list-item]

    # Compute true ranges (index 1 … n-1; index 0 has no prev close)
    tr: list[float] = []
    for i in range(1, n):
        high  = candles[i].high
        low   = candles[i].low
        prev_close = candles[i - 1].close
        true_range = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr.append(true_range)

    result: list[float | None] = [None] * n

    # Seed = SMA of first `period` true ranges (indices 1…period in original)
    if len(tr) < period:
        return result  # type: ignore[return-value]

    seed = sum(tr[:period]) / period
    result[period] = seed  # ATR[period] corresponds to candles[period]

    for i in range(period + 1, n):
        result[i] = (result[i - 1] * (period - 1) + tr[i - 1]) / period  # type: ignore[operator]

    return result  # type: ignore[return-value]


def atr_at(candles: Sequence[Candle], period: int = 14, index: int = -1) -> float | None:
    """Return ATR at a specific position (-1 = most-recent)."""
    result = atr(candles, period)
    if not result:
        return None
    val = result[index]
    return float(val) if val is not None else None

def swing_levels(
    candles: Sequence[Candle],
    length: int = 10,
    reference_price: float | None = None,
) -> tuple[float | None, float | None]:
    """
    Return the nearest confirmed swing HIGH above and swing LOW below the
    reference price from *candles*.

    Uses TradingView-compatible pivot detection (``ta.pivothigh`` / ``ta.pivotlow``):

      A candle at index ``i - length`` is a swing HIGH if its high is strictly
      greater than the highest high in candles[i-length+1 … i].

      A candle at index ``i - length`` is a swing LOW if its low is strictly
      less than the lowest low in candles[i-length+1 … i].

    When ``reference_price`` is provided (e.g. current SENSEX LTP):
      - swing_high = the **nearest** confirmed pivot high that is ABOVE reference_price
      - swing_low  = the **nearest** confirmed pivot low  that is BELOW reference_price

    When ``reference_price`` is None, returns the most-recent pivot high and low
    regardless of their position relative to price (legacy behaviour).

    Parameters
    ----------
    candles         : sequence of Candle objects (chronological, oldest first)
    length          : pivot look-back window (default 10)
    reference_price : current SENSEX spot price; filters pivots to valid SL sides

    Returns
    -------
    (swing_high, swing_low) — either value is None if not detected / no valid pivot.
    """
    n = len(candles)
    if n < length + 2:
        return None, None

    # Collect all confirmed pivot highs and lows (most-recent last)
    pivot_highs: list[float] = []
    pivot_lows:  list[float] = []

    for i in range(length, n):
        window = candles[i - length + 1: i + 1]
        upper  = max(c.high for c in window)
        lower  = min(c.low  for c in window)
        pivot  = candles[i - length]

        if pivot.high > upper:
            pivot_highs.append(pivot.high)
        if pivot.low < lower:
            pivot_lows.append(pivot.low)

    if reference_price is None:
        # Legacy: return the most-recent pivot of each type
        return (pivot_highs[-1] if pivot_highs else None,
                pivot_lows[-1]  if pivot_lows  else None)

    # Structure-first: nearest pivot HIGH above price, nearest pivot LOW below price
    # "nearest" = smallest distance to reference_price → take the minimum/maximum
    highs_above = [h for h in pivot_highs if h > reference_price]
    lows_below  = [l for l in pivot_lows  if l < reference_price]

    swing_high = min(highs_above) if highs_above else None   # closest high above
    swing_low  = max(lows_below)  if lows_below  else None   # closest low below

    return swing_high, swing_low

