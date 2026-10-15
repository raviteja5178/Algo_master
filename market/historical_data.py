"""
Historical candle bootstrap.

Fetches enough SENSEX 1-minute candles from Zerodha's historical API
to warm up EMA9 and EMA21 before the live session begins.
At least 21 completed candles for each timeframe are required.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from broker.kite_client import get_kite
from market.candle_builder import Candle
from utils.logging_config import log_event
from utils.time_utils import IST

logger = logging.getLogger(__name__)

# SENSEX BSE index token (spot)
SENSEX_TOKEN = 265  # BSE SENSEX — instrument_token for historical API


# Market session: only candles at or after 09:15 IST are valid trading data.
_SESSION_START_HOUR = 9
_SESSION_START_MINUTE = 15


def fetch_historical_candles(
    instrument_token: int,
    interval: str,  # "minute", "5minute", "15minute"
    days_back: int = 5,
) -> list[Candle]:
    """
    Fetch historical candles from Zerodha and return in chronological order.
    *days_back* determines how far back to go.  5 trading days is sufficient
    to warm up EMA21 on 5-minute and 15-minute timeframes.

    Pre-market candles (before 09:15 IST) are filtered out — Zerodha can
    return pre-open auction data which must not seed the EMA indicators.
    """
    kite = get_kite()
    to_date = datetime.now(IST).replace(tzinfo=None)
    from_date = to_date - timedelta(days=days_back)

    try:
        records = kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date.strftime("%Y-%m-%d %H:%M:%S"),
            to_date=to_date.strftime("%Y-%m-%d %H:%M:%S"),
            interval=interval,
        )
    except Exception as exc:
        exc_str = str(exc).lower()
        is_auth = any(k in exc_str for k in (
            "tokenexception", "invalid token", "token is invalid",
            "session expired", "unauthorised", "unauthorized", "403",
        ))
        if is_auth:
            logger.error(
                "Kite session expired — cannot load historical data. "
                "Re-authenticate via the dashboard Login button."
            )
        else:
            logger.error("Failed to fetch historical data for token %d: %s", instrument_token, exc)
        raise

    candles = []
    skipped = 0
    for r in records:
        ts = IST.localize(r["date"]) if r["date"].tzinfo is None else r["date"]
        # Drop any candle whose timestamp is before market open (09:15 IST).
        if (ts.hour, ts.minute) < (_SESSION_START_HOUR, _SESSION_START_MINUTE):
            skipped += 1
            continue
        candles.append(Candle(
            timestamp=ts,
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=int(r.get("volume", 0)),
        ))

    if skipped:
        logger.info(
            "Filtered %d pre-market candles (before 09:15) from historical data.", skipped,
        )
    log_event(logger, "HISTORICAL_CANDLES_LOADED", interval=interval, count=len(candles))
    return candles


def fetch_previous_day_hl(instrument_token: int) -> tuple[float | None, float | None, float | None]:
    """
    Return (prev_day_high, prev_day_low, prev_day_close) for the most recent completed trading day.

    Fetches the last 7 calendar days of daily candles and returns the HIGH, LOW and CLOSE of the
    most recent day that is strictly before today.  Returns (None, None, None)
    on any error or if no prior-day data is available.
    """
    from datetime import date as _date
    kite = get_kite()
    to_date   = datetime.now(IST).replace(tzinfo=None)
    from_date = to_date - timedelta(days=7)   # 7 calendar days covers weekends
    try:
        records = kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date.strftime("%Y-%m-%d %H:%M:%S"),
            to_date=to_date.strftime("%Y-%m-%d %H:%M:%S"),
            interval="day",
        )
    except Exception as exc:
        logger.error("fetch_previous_day_hl failed: %s", exc)
        return None, None, None

    today = _date.today()
    # records are chronological oldest-first; find the last day before today
    prev = None
    for r in records:
        ts = IST.localize(r["date"]) if r["date"].tzinfo is None else r["date"]
        if ts.date() < today:
            prev = r
    if prev is None:
        logger.warning("fetch_previous_day_hl: no prior-day candle found.")
        return None, None, None

    pdh = float(prev["high"])
    pdl = float(prev["low"])
    pdc = float(prev["close"])
    log_event(logger, "PREV_DAY_HL_LOADED", pdh=pdh, pdl=pdl, pdc=pdc, date=str(prev["date"])[:10])
    return pdh, pdl, pdc


# ── Pivot-level dataclass ─────────────────────────────────────────────────────

from dataclasses import dataclass


@dataclass(frozen=True)
class PivotLevels:
    """Pivot levels computed from the previous day's OHLC.
    Supports Fibonacci and Traditional floor formulas.
    """
    pivot: float
    r1: float
    r2: float
    r3: float
    s1: float
    s2: float
    s3: float
    prev_high: float
    prev_low:  float
    prev_close: float


def compute_pivot_levels(
    high: float,
    low: float,
    close: float,
    formula: str | None = None,
) -> PivotLevels:
    """
    Compute pivot levels from high, low, close using either FIBONACCI (default)
    or TRADITIONAL floor pivot formula.

    Fibonacci formula:
        Range = H - L
        P  = (H + L + C) / 3
        R1 = P + 0.382 * Range
        R2 = P + 0.618 * Range
        R3 = P + 1.000 * Range
        S1 = P - 0.382 * Range
        S2 = P - 0.618 * Range
        S3 = P - 1.000 * Range

    Traditional formula:
        P  = (H + L + C) / 3
        R1 = 2P - L
        R2 = P + (H - L)
        R3 = H + 2*(P - L)
        S1 = 2P - H
        S2 = P - (H - L)
        S3 = L - 2*(H - P)
    """
    from config import settings
    formula_mode = (formula or getattr(settings, "PIVOT_FORMULA", "FIBONACCI")).upper()

    H = float(high)
    L = float(low)
    C = float(close)
    P = (H + L + C) / 3.0
    rng = H - L

    if formula_mode == "TRADITIONAL":
        r1 = 2 * P - L
        r2 = P + rng
        r3 = H + 2 * (P - L)
        s1 = 2 * P - H
        s2 = P - rng
        s3 = L - 2 * (H - P)
    else:  # FIBONACCI
        r1 = P + 0.382 * rng
        r2 = P + 0.618 * rng
        r3 = P + 1.000 * rng
        s1 = P - 0.382 * rng
        s2 = P - 0.618 * rng
        s3 = P - 1.000 * rng

    return PivotLevels(
        pivot      = round(P, 2),
        r1         = round(r1, 2),
        r2         = round(r2, 2),
        r3         = round(r3, 2),
        s1         = round(s1, 2),
        s2         = round(s2, 2),
        s3         = round(s3, 2),
        prev_high  = H,
        prev_low   = L,
        prev_close = C,
    )


def fetch_pivot_levels(instrument_token: int, formula: str | None = None) -> PivotLevels | None:
    """
    Compute pivot levels from the previous completed trading day.

    Returns None on any error or if no prior-day data is available.
    """
    from datetime import date as _date
    kite      = get_kite()
    to_date   = datetime.now(IST).replace(tzinfo=None)
    from_date = to_date - timedelta(days=7)
    try:
        records = kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date.strftime("%Y-%m-%d %H:%M:%S"),
            to_date=to_date.strftime("%Y-%m-%d %H:%M:%S"),
            interval="day",
        )
    except Exception as exc:
        logger.error("fetch_pivot_levels failed: %s", exc)
        return None

    today = _date.today()
    prev  = None
    for r in records:
        ts = IST.localize(r["date"]) if r["date"].tzinfo is None else r["date"]
        if ts.date() < today:
            prev = r
    if prev is None:
        logger.warning("fetch_pivot_levels: no prior-day candle found.")
        return None

    levels = compute_pivot_levels(
        float(prev["high"]),
        float(prev["low"]),
        float(prev["close"]),
        formula=formula,
    )
    log_event(
        logger, "PIVOT_LEVELS_LOADED",
        date=str(prev["date"])[:10],
        P=levels.pivot, R1=levels.r1, R2=levels.r2, R3=levels.r3,
        S1=levels.s1,  S2=levels.s2,  S3=levels.s3,
    )
    return levels
