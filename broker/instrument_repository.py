"""
Instrument master: load, cache, and query the Zerodha instrument list.

Instruments are cached in memory for the session and optionally on disk to
avoid re-downloading on restart within the same trading day.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timedelta
from typing import Literal

from broker.kite_client import get_kite
from config import settings
from utils.logging_config import log_event

logger = logging.getLogger(__name__)

# In-memory cache: list of instrument dicts
_instruments: list[dict] = []
_loaded_date: date | None = None


def load_instruments(force: bool = False) -> list[dict]:
    """Download and cache the full instrument master from Zerodha."""
    global _instruments, _loaded_date

    today = date.today()
    if _instruments and _loaded_date == today and not force:
        return _instruments

    kite = get_kite()
    log_event(logger, "INSTRUMENT_MASTER_LOAD", date=today)
    data = kite.instruments()  # returns list[dict]
    _instruments = data
    _loaded_date = today
    logger.info("Loaded %d instruments from Zerodha", len(_instruments))
    return _instruments


def get_sensex_options(
    expiry: date,
    option_type: Literal["CE", "PE"],
) -> list[dict]:
    """
    Filter to SENSEX option contracts for a given expiry and type.
    Returns list of instrument dicts sorted by strike.
    """
    instruments = load_instruments()
    result = [
        i for i in instruments
        if (
            i.get("name") == settings.UNDERLYING         # e.g. "SENSEX"
            and i.get("instrument_type") == option_type  # "CE" or "PE"
            and i.get("segment") in ("BFO", "BFO-OPT")  # BSE Futures & Options
            and _parse_expiry(i.get("expiry")) == expiry
        )
    ]
    result.sort(key=lambda x: float(x.get("strike", 0)))
    return result


def get_near_month_future(
    underlying: str | None = None,
    min_days_to_expiry: int = 0,
) -> dict | None:
    """
    Nearest-expiry futures contract for *underlying* that is at least
    *min_days_to_expiry* days from expiry (skips a contract whose liquidity is
    already rolling to the next month).  Returns None when none is listed.
    """
    name = underlying or settings.UNDERLYING
    earliest = date.today() + timedelta(days=max(0, min_days_to_expiry))
    candidates = []
    for i in load_instruments():
        if i.get("name") != name or i.get("instrument_type") != "FUT":
            continue
        exp = _parse_expiry(i.get("expiry"))
        if exp is not None and exp >= earliest:
            candidates.append((exp, i))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _parse_expiry(raw) -> date | None:
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def resolve_expiry() -> date:
    """
    Return the configured or nearest weekly expiry date.
    """
    if settings.EXPIRY_MODE == "CONFIGURED":
        if not settings.CONFIGURED_EXPIRY:
            raise ValueError("CONFIGURED_EXPIRY must be set.")
        return datetime.strptime(settings.CONFIGURED_EXPIRY, "%Y-%m-%d").date()

    # AUTO mode: find nearest weekly expiry for SENSEX options
    instruments = load_instruments()
    today = date.today()
    expiries = sorted(
        {
            _parse_expiry(i["expiry"])
            for i in instruments
            if i.get("name") == settings.UNDERLYING and i.get("segment") in ("BFO", "BFO-OPT")
            and _parse_expiry(i["expiry"]) is not None
            and _parse_expiry(i["expiry"]) >= today  # type: ignore[operator]
        }
    )
    if not expiries:
        raise ValueError("No upcoming SENSEX option expiries found in instrument master.")

    # Expiry-day rollover: on the expiry day itself, after EXPIRY_DAY_ROLLOVER_TIME,
    # new entries use the next expiry to avoid near-zero-theta contracts.
    if expiries[0] == today and len(expiries) > 1 and settings.EXPIRY_DAY_ROLLOVER_TIME:
        from utils.time_utils import is_after_or_equal, now_ist, parse_time_ist
        try:
            if is_after_or_equal(now_ist().time(), parse_time_ist(settings.EXPIRY_DAY_ROLLOVER_TIME)):
                log_event(logger, "EXPIRY_ROLLOVER", today=today, next_expiry=expiries[1])
                return expiries[1]
        except ValueError:
            pass   # bad config — keep nearest expiry
    return expiries[0]


def is_expiry_day() -> bool:
    """True when today is a SENSEX option expiry date (fails safe to False)."""
    try:
        today = date.today()
        return any(
            _parse_expiry(i.get("expiry")) == today
            for i in load_instruments()
            if i.get("name") == settings.UNDERLYING and i.get("segment") in ("BFO", "BFO-OPT")
        )
    except Exception:
        return False


def find_instrument(tradingsymbol: str) -> dict | None:
    """Exact lookup by trading symbol."""
    instruments = load_instruments()
    for i in instruments:
        if i.get("tradingsymbol") == tradingsymbol:
            return i
    return None
