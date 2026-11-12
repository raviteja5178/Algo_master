"""
Estimate an option's real delta from its traded premium (Black-Scholes).

The implied volatility is solved from the premium, then delta is read off at
that volatility.  Used to convert index-point targets to option-premium points
with the delta the contract actually has (a deep ITM strike is ~0.7, not 0.5).
Returns None whenever the inputs cannot support a sensible estimate so callers
fall back to their configured delta.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time as dtime

from utils.time_utils import IST

RISK_FREE = 0.065
_MIN_VOL, _MAX_VOL = 0.01, 5.0


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _d1(spot: float, strike: float, years: float, vol: float, r: float) -> float:
    return (math.log(spot / strike) + (r + 0.5 * vol * vol) * years) / (vol * math.sqrt(years))


def bs_price(spot: float, strike: float, years: float, vol: float, opt: str, r: float = RISK_FREE) -> float:
    d1 = _d1(spot, strike, years, vol, r)
    d2 = d1 - vol * math.sqrt(years)
    disc = math.exp(-r * years)
    if opt == "CE":
        return spot * _ncdf(d1) - strike * disc * _ncdf(d2)
    return strike * disc * _ncdf(-d2) - spot * _ncdf(-d1)


def bs_delta(spot: float, strike: float, years: float, vol: float, opt: str, r: float = RISK_FREE) -> float:
    """Absolute delta (0..1) — positive for both CE and PE."""
    d1 = _d1(spot, strike, years, vol, r)
    return _ncdf(d1) if opt == "CE" else _ncdf(-d1)


def implied_vol(price: float, spot: float, strike: float, years: float, opt: str,
                r: float = RISK_FREE) -> float | None:
    """Bisection IV solve; None when the premium is outside the model's range."""
    if min(price, spot, strike, years) <= 0:
        return None
    lo, hi = _MIN_VOL, _MAX_VOL
    if not (bs_price(spot, strike, years, lo, opt, r) <= price <= bs_price(spot, strike, years, hi, opt, r)):
        return None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if bs_price(spot, strike, years, mid, opt, r) < price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def option_delta_from_premium(spot: float, strike: float, expiry: date, opt: str, premium: float,
                              now: datetime, r: float = RISK_FREE) -> float | None:
    """Absolute delta implied by `premium`, or None if it cannot be estimated."""
    if isinstance(expiry, datetime):
        expiry = expiry.date()
    expiry_dt = datetime.combine(expiry, dtime(15, 30), tzinfo=IST) if now.tzinfo else \
        datetime.combine(expiry, dtime(15, 30))
    years = (expiry_dt - now).total_seconds() / (365.0 * 24 * 3600)
    if years <= 0:
        return None
    vol = implied_vol(premium, spot, strike, years, opt, r)
    if vol is None:
        return None
    return round(bs_delta(spot, strike, years, vol, opt, r), 3)
