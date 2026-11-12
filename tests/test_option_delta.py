from datetime import date, datetime

import pytest

from utils import option_delta as od
from utils.time_utils import IST

NOW = IST.localize(datetime(2026, 11, 11, 12, 30))
EXPIRY = date(2026, 11, 17)


def test_roundtrip_delta_matches_model_delta():
    years = (datetime(2026, 11, 17, 15, 30) - datetime(2026, 11, 11, 12, 30)).total_seconds() / (365 * 24 * 3600)
    prem = od.bs_price(25300.0, 25400.0, years, 0.14, "PE")
    d = od.option_delta_from_premium(25300.0, 25400.0, EXPIRY, "PE", prem, NOW)
    assert d == pytest.approx(od.bs_delta(25300.0, 25400.0, years, 0.14, "PE"), abs=0.01)


def test_itm_put_delta_is_above_half():
    years = 6.1 / 365
    prem = od.bs_price(25300.0, 25400.0, years, 0.14, "PE")
    d = od.option_delta_from_premium(25300.0, 25400.0, EXPIRY, "PE", prem, NOW)
    assert d is not None and d > 0.5


def test_ce_and_pe_deltas_are_positive_and_sum_near_one():
    years = 3 / 365
    ce = od.bs_delta(25000.0, 25000.0, years, 0.15, "CE")
    pe = od.bs_delta(25000.0, 25000.0, years, 0.15, "PE")
    assert 0 < ce < 1 and 0 < pe < 1
    assert ce + pe == pytest.approx(1.0, abs=0.01)


@pytest.mark.parametrize("premium", [0.0, -5.0, 1e9])
def test_unusable_premium_returns_none(premium):
    assert od.option_delta_from_premium(25300.0, 25400.0, EXPIRY, "PE", premium, NOW) is None


def test_expired_contract_returns_none():
    assert od.option_delta_from_premium(25300.0, 25400.0, date(2026, 11, 10), "PE", 100.0, NOW) is None


def test_trail_does_not_report_repeated_identical_stop_moves():
    from execution.ema_trade_manager import EmaTradeManager

    m = EmaTradeManager('PE', 25305.95, 25359.54, 25145.18, 30.0, 272.1)
    m.on_index_price(25290)
    m.best_index = 25162.8
    m.atr = 32.0
    reported = sum(1 for p in (25162.8, 25163.0, 25164.0, 25165.0) * 50 if m.on_index_price(p))
    assert reported <= 1

