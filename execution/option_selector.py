"""
ATM option selector.

Finds the nearest-ATM SENSEX CE or PE option instrument for a given
underlying price and expiry.  Never hard-codes a strike.

ITM fallback
------------
When called with ``itm_fallback=True`` (the default), the function returns
a *list* of candidate instruments ordered from most-preferred to least:

  CE: [ATM, ATM−100, ATM−200]   (lower strike = more ITM for a call)
  PE: [ATM, ATM+100, ATM+200]   (higher strike = more ITM for a put)

The caller (main.py) fetches the LTP for each candidate in order and uses
the first one whose premium is at or above the configured minimum.  This
prevents the common failure mode where the nearest-ATM strike is OTM and
priced below the minimum, blocking a valid directional trade.

Pass ``itm_fallback=False`` to get the old single-instrument behaviour.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal, TypedDict

from broker.instrument_repository import get_sensex_options, resolve_expiry
from utils.logging_config import log_event

logger = logging.getLogger(__name__)

# How many additional ITM strikes to include in the candidate list.
_ITM_FALLBACK_STEPS = 2

# Strike increment for SENSEX options (BSE weekly series uses 100-pt steps).
SENSEX_STRIKE_STEP = 100


class OptionInstrument(TypedDict):
    tradingsymbol: str
    instrument_token: int
    strike: float
    expiry: date
    exchange: str
    lot_size: int


def _make_instrument(row: dict, expiry: date) -> OptionInstrument:
    return {
        "tradingsymbol": row["tradingsymbol"],
        "instrument_token": int(row["instrument_token"]),
        "strike": float(row["strike"]),
        "expiry": expiry,
        "exchange": row.get("exchange", "BFO"),
        "lot_size": int(row.get("lot_size", 1)),
    }


def select_atm_option(
    underlying_price: float,
    option_type: Literal["CE", "PE"],
    expiry: date | None = None,
    itm_fallback: bool = True,
) -> OptionInstrument:
    """
    Return the ATM instrument nearest to *underlying_price*.

    When *itm_fallback* is True (default), first tries the ATM strike.
    If you need to check premium before committing, use
    ``select_atm_candidates()`` to get an ordered list.

    Raises ValueError if no valid instrument is found.
    """
    candidates = select_atm_candidates(underlying_price, option_type, expiry,
                                       steps=1 if not itm_fallback else 1)
    instrument = candidates[0]
    log_event(
        logger,
        "ATM_OPTION_SELECTED",
        type=option_type,
        underlying=underlying_price,
        strike=instrument["strike"],
        symbol=instrument["tradingsymbol"],
        expiry=instrument["expiry"],
    )
    return instrument


def select_atm_candidates(
    underlying_price: float,
    option_type: Literal["CE", "PE"],
    expiry: date | None = None,
    steps: int = _ITM_FALLBACK_STEPS,
) -> list[OptionInstrument]:
    """
    Return an ordered list of candidate instruments for the given direction.

    The first element is always the nearest-ATM strike.  Subsequent elements
    are one step deeper ITM each time:
      CE: strike − 100, strike − 200, …
      PE: strike + 100, strike + 200, …

    Only strikes that exist in the instrument master are included.
    The list always contains at least one element (the ATM strike).

    Use this when you want to try progressively more ITM options until one
    meets the minimum premium threshold.

    Raises ValueError if no SENSEX options are available for *expiry*.
    """
    if expiry is None:
        expiry = resolve_expiry()

    options = get_sensex_options(expiry, option_type)
    if not options:
        raise ValueError(
            f"No SENSEX {option_type} options found for expiry {expiry}. "
            "Check instrument master and CONFIGURED_EXPIRY."
        )

    # Build a quick lookup: strike → instrument row
    strike_map: dict[float, dict] = {float(o["strike"]): o for o in options}

    # ATM: nearest strike by absolute distance
    atm_strike = min(strike_map, key=lambda s: abs(s - underlying_price))

    candidates: list[OptionInstrument] = [_make_instrument(strike_map[atm_strike], expiry)]

    # Walk ITM: for PE higher strikes are ITM; for CE lower strikes are ITM.
    direction = +SENSEX_STRIKE_STEP if option_type == "PE" else -SENSEX_STRIKE_STEP
    candidate_strike = atm_strike
    for _ in range(steps):
        candidate_strike += direction
        if candidate_strike in strike_map:
            candidates.append(_make_instrument(strike_map[candidate_strike], expiry))

    return candidates
