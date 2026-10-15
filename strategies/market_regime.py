"""
Intraday market-regime classifier (rule-based, no AI, no network).

Answers "is the market trending, choppy or volatile RIGHT NOW?" on every closed
5m candle, using plain arithmetic on candles the bot already holds:

    ER   Kaufman Efficiency Ratio over the last N same-day candles
         |close[now] - close[N ago]| / sum(|close change|)   (1 = straight line, 0 = noise)
    ADX  Wilder ADX(14) with +DI / -DI  (trend strength + direction)
    VOL  current ATR(14) / mean ATR(14) of the recent history (volatility vs normal)

Rules (all thresholds are settings.INTRADAY_REGIME_*):
    TRENDING : ER >= ER_TRENDING  and  ADX >= ADX_TRENDING
    CHOPPY   : ER <= ER_CHOPPY      (ER reacts faster than ADX, so ADX is not required)
    MIXED    : anything in between
    WARMUP   : not enough same-day candles yet (first ~hour)
    volatile : VOL >= VOL_RATIO     (independent overlay — a market can be
                                     "trending and volatile" or "choppy and volatile")

Observational only: nothing in the entry/exit path reads this. It is shown on the
dashboard and snapshotted into trades.smart_entry_flags for later analysis.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass

from market.candle_builder import Candle
from market.indicators import atr

# Candles of ATR history used as the "normal volatility" baseline.
_ATR_BASELINE_CANDLES = 150
_ATR_BASELINE_MIN = 30


@dataclass(frozen=True)
class RegimeSnapshot:
    regime: str                 # TRENDING | CHOPPY | MIXED | WARMUP
    direction: str | None       # "UP" | "DOWN" | None  (from +DI vs -DI)
    volatile: bool
    er: float | None
    adx: float | None
    plus_di: float | None
    minus_di: float | None
    vol_ratio: float | None
    candle_ts: str | None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def label(self) -> str:
        """Human-readable one-liner, e.g. 'TRENDING DOWN · VOLATILE'."""
        text = self.regime
        if self.regime == "TRENDING" and self.direction:
            text += f" {self.direction}"
        if self.volatile:
            text += " · VOLATILE"
        return text


def efficiency_ratio(closes: Sequence[float], period: int) -> float | None:
    """Kaufman ER over the last *period* changes, or None if not enough data."""
    if period < 1 or len(closes) < period + 1:
        return None
    window = list(closes[-(period + 1):])
    path = sum(abs(window[i] - window[i - 1]) for i in range(1, len(window)))
    if path <= 0:
        return 0.0
    return abs(window[-1] - window[0]) / path


def adx_latest(
    candles: Sequence[Candle], period: int = 14
) -> tuple[float, float, float] | None:
    """
    Wilder ADX for the latest candle, returned as (adx, +DI, -DI).
    Needs at least 2*period + 1 candles; otherwise None.
    """
    n = len(candles)
    if period < 1 or n < 2 * period + 1:
        return None

    tr: list[float] = []
    pdm: list[float] = []
    mdm: list[float] = []
    for i in range(1, n):
        c, p = candles[i], candles[i - 1]
        up = c.high - p.high
        down = p.low - c.low
        pdm.append(up if (up > down and up > 0) else 0.0)
        mdm.append(down if (down > up and down > 0) else 0.0)
        tr.append(max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close)))

    s_tr = sum(tr[:period])
    s_p = sum(pdm[:period])
    s_m = sum(mdm[:period])

    def _di_dx(st: float, sp: float, sm: float) -> tuple[float, float, float]:
        if st <= 0:
            return 0.0, 0.0, 0.0
        pdi = 100.0 * sp / st
        mdi = 100.0 * sm / st
        denom = pdi + mdi
        dx = 100.0 * abs(pdi - mdi) / denom if denom > 0 else 0.0
        return pdi, mdi, dx

    pdi, mdi, dx = _di_dx(s_tr, s_p, s_m)
    dxs = [dx]
    adx_val: float | None = None
    for i in range(period, len(tr)):
        s_tr = s_tr - s_tr / period + tr[i]
        s_p = s_p - s_p / period + pdm[i]
        s_m = s_m - s_m / period + mdm[i]
        pdi, mdi, dx = _di_dx(s_tr, s_p, s_m)
        if adx_val is None:
            dxs.append(dx)
            if len(dxs) == period:
                adx_val = sum(dxs) / period
        else:
            adx_val = (adx_val * (period - 1) + dx) / period

    if adx_val is None:
        return None
    return adx_val, pdi, mdi


def volatility_ratio(candles: Sequence[Candle], period: int = 14) -> float | None:
    """Current ATR / mean ATR of the recent history; None if the baseline is too short."""
    series = [v for v in atr(candles, period)[-_ATR_BASELINE_CANDLES:] if v is not None]
    if len(series) < _ATR_BASELINE_MIN:
        return None
    baseline = sum(series) / len(series)
    if baseline <= 0:
        return None
    return series[-1] / baseline


def classify_intraday(
    candles_5m: Sequence[Candle],
    *,
    er_period: int = 12,
    adx_period: int = 14,
    er_trending: float = 0.5,
    er_choppy: float = 0.3,
    adx_trending: float = 25.0,
    vol_ratio_threshold: float = 1.5,
) -> RegimeSnapshot:
    """
    Classify the market from completed 5m candles (oldest first).

    ER uses only the latest trading day (an overnight gap would distort it), so
    the regime reads WARMUP until ``er_period + 1`` candles exist for that day.
    ADX and the ATR baseline use the whole series, like the bot's other ATR use.
    """
    if not candles_5m:
        return RegimeSnapshot("WARMUP", None, False, None, None, None, None, None, None)

    last = candles_5m[-1]
    day = last.timestamp.date()
    today = [c for c in candles_5m if c.timestamp.date() == day]

    er = efficiency_ratio([c.close for c in today], er_period)
    adx_res = adx_latest(candles_5m, adx_period)
    vol = volatility_ratio(candles_5m)
    volatile = vol is not None and vol >= vol_ratio_threshold

    adx_val = pdi = mdi = None
    direction: str | None = None
    if adx_res is not None:
        adx_val, pdi, mdi = adx_res
        direction = "UP" if pdi > mdi else "DOWN" if mdi > pdi else None

    if er is None:
        regime = "WARMUP"
    elif er >= er_trending and adx_val is not None and adx_val >= adx_trending:
        regime = "TRENDING"
    elif er <= er_choppy:
        regime = "CHOPPY"
    else:
        regime = "MIXED"

    def _r(x: float | None, nd: int = 2) -> float | None:
        return None if x is None else round(x, nd)

    return RegimeSnapshot(
        regime=regime,
        direction=direction,
        volatile=volatile,
        er=_r(er, 3),
        adx=_r(adx_val, 1),
        plus_di=_r(pdi, 1),
        minus_di=_r(mdi, 1),
        vol_ratio=_r(vol, 2),
        candle_ts=last.timestamp.isoformat(),
    )
