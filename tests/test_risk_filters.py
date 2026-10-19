"""Tests for ATM_DELTA sizing, swing-SL ATR floor and the pre-entry margin check."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from config import settings
from execution.atr_risk import compute_risk_params
from execution.order_manager import OrderManager
from market.candle_builder import Candle

_TS = datetime(2026, 1, 1, 9, 15)


def _candles(n=20, base=80000.0, spread=50.0):
    return [Candle(timestamp=_TS, open=base, high=base + spread, low=base - spread, close=base)
            for _ in range(n)]


def _risk(delta, swing_low, min_mult=0.0):
    return compute_risk_params(
        _candles(), fixed_sl=30, fixed_target=60, fixed_trail=10,
        min_sl_pts=5, min_target_pts=5, min_trail_pts=2, entry_price=500.0,
        use_spot_atr=True, spot_atr_period=5, spot_sl_mult=3.0,
        target_rr=2.0, trail_rr=0.5,
        use_swing_sl=True, option_type="CE", sensex_ltp=80000.0,
        swing_high=None, swing_low=swing_low,
        swing_sl_min_atr_mult=min_mult, max_sl_pct=0.9, atm_delta=delta,
    )


def test_default_delta_is_half():
    assert settings.ATM_DELTA == 0.5


def test_higher_delta_widens_option_sl():
    r4 = _risk(0.4, swing_low=79900.0)   # 100 index pts
    r5 = _risk(0.5, swing_low=79900.0)
    assert r4.sl_mode == r5.sl_mode == "swing_sl"
    assert r4.initial_sl_points == pytest.approx(40.0, abs=0.1)
    assert r5.initial_sl_points == pytest.approx(50.0, abs=0.1)
    assert r5.initial_target_points > r4.initial_target_points


def test_swing_floor_rejects_tight_swing_and_falls_to_atr():
    # ATR(5) = 100 index pts; swing 70 pts away → 70 < 100×0.8 → Mode C
    tight = _risk(0.5, swing_low=79930.0, min_mult=0.8)
    assert tight.sl_mode == "spot_atr"
    # Same swing passes a looser floor (70 >= 100×0.6)
    assert _risk(0.5, swing_low=79930.0, min_mult=0.6).sl_mode == "swing_sl"


def _om(order_margins=None, margins=None):
    om = OrderManager.__new__(OrderManager)
    om._kite = MagicMock()
    om._kite.TRANSACTION_TYPE_BUY = "BUY"
    if order_margins is not None:
        om._kite.order_margins.return_value = order_margins
    if margins is not None:
        om._kite.margins.return_value = margins
    return om


def test_margin_shortfall_detected():
    om = _om([{"total": 21619.0}], {"available": {"live_balance": 14664.6}})
    assert om._margin_shortfall("SENSEX26O2274500CE", 20, "BFO", 500.0) == (21619.0, 14664.6)


def test_margin_sufficient_returns_none():
    om = _om([{"total": 10000.0}], {"available": {"live_balance": 14664.6}})
    assert om._margin_shortfall("X", 20, "BFO", 500.0) is None


def test_margin_api_error_fails_open():
    om = _om()
    om._kite.order_margins.side_effect = RuntimeError("boom")
    assert om._margin_shortfall("X", 20, "BFO", 500.0) is None


def test_place_buy_order_blocked_without_sending_order():
    om = _om([{"total": 21619.0}], {"available": {"live_balance": 14664.6}})
    with patch.object(settings, "ENTRY_MARGIN_CHECK", True):
        res = om.place_buy_order("SENSEX26O2274500CE", 20, ltp_hint=500.0)
    assert res["status"] == "REJECTED" and res["filled_qty"] == 0
    assert "PRE_ENTRY_MARGIN_CHECK" in res["reason"]
    om._kite.place_order.assert_not_called()


def test_place_buy_order_sends_when_check_disabled():
    om = _om()
    om._kite.place_order.return_value = "OID1"
    om._wait_for_fill = MagicMock(return_value={"status": "COMPLETE"})
    with patch.object(settings, "ENTRY_MARGIN_CHECK", False):
        res = om.place_buy_order("X", 20, ltp_hint=500.0)
    assert res["status"] == "COMPLETE"
    om._kite.order_margins.assert_not_called()
