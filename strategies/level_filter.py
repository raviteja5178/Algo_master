"""
Support / resistance room filter for VWAP retest entries.

A CE entry is blocked when the nearest resistance above the signal close is
closer than ``min_room_atr`` x ATR; a PE entry is blocked when the nearest
support below the close is that close.  Levels considered:

  * previous-day high / low
  * Fibonacci/Traditional pivot levels (P, R1-R3, S1-S3)
  * today's high / low so far, excluding the last ``exclude_last`` candles
    (so the move that produced the signal does not count as its own level)

Pure functions, no I/O — safe to call from the signal engine and from replays.
"""

from __future__ import annotations

from collections.abc import Sequence

from market.candle_builder import Candle


def collect_levels(
    candles_5m: Sequence[Candle],
    *,
    prev_day_high: float | None = None,
    prev_day_low: float | None = None,
    pivot_levels=None,
    use_pivots: bool = True,
    use_day_extremes: bool = True,
    exclude_last: int = 3,
) -> list[float]:
    """Return every candidate S/R level as a flat list of index prices."""
    levels: list[float] = []
    if prev_day_high:
        levels.append(float(prev_day_high))
    if prev_day_low:
        levels.append(float(prev_day_low))
    if use_pivots and pivot_levels is not None:
        for name in ("pivot", "r1", "r2", "r3", "s1", "s2", "s3"):
            v = getattr(pivot_levels, name, None)
            if v:
                levels.append(float(v))
    if use_day_extremes and candles_5m:
        today = candles_5m[-1].timestamp.date()
        todays = [c for c in candles_5m if c.timestamp.date() == today]
        older = todays[:-exclude_last] if exclude_last > 0 else todays
        if older:
            levels.append(max(c.high for c in older))
            levels.append(min(c.low for c in older))
    return levels


def level_room_blocked(
    side: str,
    close: float,
    atr: float | None,
    levels: Sequence[float],
    min_room_atr: float,
) -> tuple[bool, float | None, float | None]:
    """
    Decide whether a *side* ("CE"/"PE") entry at *close* lacks room to run.

    Returns ``(blocked, nearest_level, room_pts)``.  Fails open (not blocked)
    when the filter is disabled, ATR is unavailable, or no level lies ahead.
    """
    if min_room_atr <= 0 or not atr or atr <= 0:
        return False, None, None
    if side == "CE":
        ahead = [lv for lv in levels if lv > close]
        if not ahead:
            return False, None, None
        nearest = min(ahead)
        room = nearest - close
    else:
        ahead = [lv for lv in levels if lv < close]
        if not ahead:
            return False, None, None
        nearest = max(ahead)
        room = close - nearest
    return room < min_room_atr * atr, nearest, room
