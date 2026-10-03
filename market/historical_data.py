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


def fetch_previous_day_hl(instrument_token: int) -> tuple[float | None, float | None]:
    """
    Return (prev_day_high, prev_day_low) for the most recent completed trading day.

    Fetches the last 5 daily candles and returns the HIGH and LOW of the
    most recent day that is strictly before today.  Returns (None, None)
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
        return None, None

    today = _date.today()
    # records are chronological oldest-first; find the last day before today
    prev = None
    for r in records:
        ts = IST.localize(r["date"]) if r["date"].tzinfo is None else r["date"]
        if ts.date() < today:
            prev = r
    if prev is None:
        logger.warning("fetch_previous_day_hl: no prior-day candle found.")
        return None, None

    pdh = float(prev["high"])
    pdl = float(prev["low"])
    log_event(logger, "PREV_DAY_HL_LOADED", pdh=pdh, pdl=pdl, date=str(prev["date"])[:10])
    return pdh, pdl
