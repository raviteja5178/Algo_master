"""get_near_month_future: contract selection and roll-over."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from broker import instrument_repository as repo


def _fut(sym, exp, name="SENSEX"):
    return {"tradingsymbol": sym, "name": name, "instrument_type": "FUT", "expiry": exp, "instrument_token": hash(sym) & 0xFFFF}


def _patched(instruments):
    return patch.object(repo, "load_instruments", return_value=instruments)


def test_picks_nearest_expiry():
    today = date.today()
    ins = [_fut("DEC", today + timedelta(days=70)), _fut("OCT", today + timedelta(days=10)),
           _fut("NOV", today + timedelta(days=40))]
    with _patched(ins):
        assert repo.get_near_month_future("SENSEX")["tradingsymbol"] == "OCT"


def test_rolls_to_next_month_inside_min_days():
    today = date.today()
    ins = [_fut("OCT", today + timedelta(days=2)), _fut("NOV", today + timedelta(days=30))]
    with _patched(ins):
        assert repo.get_near_month_future("SENSEX", min_days_to_expiry=3)["tradingsymbol"] == "NOV"
        assert repo.get_near_month_future("SENSEX", min_days_to_expiry=0)["tradingsymbol"] == "OCT"


def test_ignores_other_underlyings_options_and_expired():
    today = date.today()
    ins = [_fut("NIFTYFUT", today + timedelta(days=5), name="NIFTY"),
           _fut("OLD", today - timedelta(days=1)),
           {"tradingsymbol": "OPT", "name": "SENSEX", "instrument_type": "CE", "expiry": today + timedelta(days=1)},
           _fut("OCT", today + timedelta(days=9))]
    with _patched(ins):
        assert repo.get_near_month_future("SENSEX")["tradingsymbol"] == "OCT"


def test_accepts_string_expiry_and_returns_none_when_empty():
    today = date.today()
    with _patched([_fut("OCT", (today + timedelta(days=4)).isoformat())]):
        assert repo.get_near_month_future("SENSEX")["tradingsymbol"] == "OCT"
    with _patched([]):
        assert repo.get_near_month_future("SENSEX") is None
