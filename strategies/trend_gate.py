"""
Higher-timeframe trend gate — keeps trend-following strategies on the right
side of the market.

  15m : last completed 15m close beyond its EMA21 AND EMA21 sloping the same
        way (CE: close > EMA21 and EMA21 rising; PE mirrored).
  Daily: previous session's close beyond the 20-day EMA of daily closes.

Evidence (270-day replay of production signals, BE 1R + 2xATR trail, ~12 idx-pt
costs): VWAP all signals −0.02R/trade → with both gates +0.11R (both halves
positive); EMA before 12:00 with both gates +0.45R; TRB +0.25R.  Pivot is the
opposite — its best trades are counter-VWAP/counter-trend level entries
(aligned +0.26R vs not-aligned +1.17R over 138 trades) — so Pivot is never
gated here.

Both helpers fail OPEN (return True / "UNKNOWN") when there is not enough
data, so a data gap degrades to "no gate" instead of "no trading".
"""

from __future__ import annotations

from collections.abc import Sequence

from market.candle_builder import Candle
from market.indicators import ema

TREND_EMA_15M = 21


def trend_15m_ok(side: str, candles_15m: Sequence[Candle]) -> bool:
    """True when the completed 15m trend agrees with *side* ("CE"/"PE"),
    or when there is not enough 15m history to judge."""
    if len(candles_15m) < TREND_EMA_15M + 1:
        return True
    e21 = ema(candles_15m, TREND_EMA_15M)
    now, prev = e21[-1], e21[-2]
    if now is None or prev is None:
        return True
    sign = 1 if side == "CE" else -1
    return (candles_15m[-1].close - now) * sign > 0 and (now - prev) * sign > 0


def daily_trend_from_closes(closes: Sequence[float], period: int = 20) -> str:
    """'UP' / 'DOWN' from the last close vs the EMA(period) of *closes*
    (oldest first, completed sessions only); 'UNKNOWN' when too short."""
    if len(closes) < period:
        return "UNKNOWN"
    e = ema(list(closes), period)[-1]
    if e is None or closes[-1] == e:
        return "UNKNOWN"
    return "UP" if closes[-1] > e else "DOWN"


def daily_trend_ok(side: str, daily_trend: str | None) -> bool:
    """True when the daily trend agrees with *side*, or is unknown."""
    if daily_trend not in ("UP", "DOWN"):
        return True
    return (daily_trend == "UP") == (side == "CE")


def strategy_key(sig: str) -> str:
    """'CE_VWAP' -> 'VWAP', 'PE_PIVOT' -> 'PIVOT', 'CE'/'PE' (EMA) -> 'EMA'."""
    return sig.split("_", 1)[1] if "_" in sig else "EMA"
