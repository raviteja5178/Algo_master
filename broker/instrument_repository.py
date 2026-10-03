"""
Instrument master: load, cache, and query the Zerodha instrument list.

Instruments are cached in memory for the session and optionally on disk to
avoid re-downloading on restart within the same trading day.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime
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
    return expiries[0]


def find_instrument(tradingsymbol: str) -> dict | None:
    """Exact lookup by trading symbol."""
    instruments = load_instruments()
    for i in instruments:
        if i.get("tradingsymbol") == tradingsymbol:
            return i
    return None
