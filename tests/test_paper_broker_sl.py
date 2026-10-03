"""
Tests for PaperBroker stop-loss behaviour.

Regression coverage for the PRE_SELL_QTY_MISMATCH bug:
  _check_stops() previously removed the position from _positions when the SL
  order triggered, so the subsequent place_sell_order() call saw qty=0 and
  raised PRE_SELL_QTY_MISMATCH — leaving the logical position un-exited and
  reporting a wrong PnL (entry price used as exit price).

After the fix, _check_stops() marks the SL order COMPLETE but does NOT touch
_positions.  The bot's exit path calls place_sell_order(), which decrements the
position correctly.
"""

from __future__ import annotations

import pytest
from execution.paper_broker import PaperBroker


# ── helpers ──────────────────────────────────────────────────────────────────

def _open_trade(broker: PaperBroker, symbol: str, qty: int, entry: float) -> str:
    """Buy and place an SL order.  Returns the SL order_id."""
    broker.place_buy_order(symbol, qty, ltp_hint=entry)
    sl_id = broker.place_stop_order(symbol, qty, trigger_price=entry * 0.80)
    return sl_id


# ── core regression ───────────────────────────────────────────────────────────

class TestSlDoesNotRemovePosition:
    """_check_stops must NOT remove the position — place_sell_order does that."""

    def test_position_still_present_after_sl_triggers(self):
        broker = PaperBroker()
        symbol = "TEST26O01CE"
        broker.place_buy_order(symbol, 20, ltp_hint=300.0)
        broker.place_stop_order(symbol, 20, trigger_price=240.0)

        # Push price below SL
        broker.update_ltp(symbol, 235.0)

        # Position must still be 20 — not yet sold
        assert broker.get_position_qty(symbol) == 20

    def test_place_sell_order_succeeds_after_sl_triggers(self):
        broker = PaperBroker()
        symbol = "TEST26O01CE"
        broker.place_buy_order(symbol, 20, ltp_hint=300.0)
        sl_id = broker.place_stop_order(symbol, 20, trigger_price=240.0)

        broker.update_ltp(symbol, 235.0)  # trigger SL

        # SL order should be COMPLETE
        assert broker.get_order_status(sl_id) == "COMPLETE"

        # Sell must succeed (no RuntimeError)
        result = broker.place_sell_order(symbol, 20, tag="STOP_HIT", ltp_hint=235.0)
        assert result["status"] == "COMPLETE"
        assert result["filled_qty"] == 20
        assert result["average_price"] == pytest.approx(235.0)

    def test_position_zero_after_sell_following_sl(self):
        broker = PaperBroker()
        symbol = "TEST26O01CE"
        broker.place_buy_order(symbol, 20, ltp_hint=300.0)
        broker.place_stop_order(symbol, 20, trigger_price=240.0)

        broker.update_ltp(symbol, 235.0)
        broker.place_sell_order(symbol, 20, tag="STOP_HIT", ltp_hint=235.0)

        assert broker.get_position_qty(symbol) == 0

    def test_no_presell_error_regression(self):
        """Directly reproduce the original bug sequence that caused BOT_HALTED."""
        broker = PaperBroker()
        symbol = "SENSEX26O0172700CE"
        # Entry at ₹300
        broker.place_buy_order(symbol, 20, ltp_hint=300.0)
        sl_id = broker.place_stop_order(symbol, 20, trigger_price=240.0)

        # Trailing SL moved to BE (300) after ltp=332
        broker.modify_stop_order(sl_id, 300.0)

        # Trailing SL moved to 315 after ltp=345
        broker.modify_stop_order(sl_id, 315.0)

        # Price drops to 314 — SL triggers
        broker.update_ltp(symbol, 314.0)

        # Before the fix this raised:
        #   RuntimeError: PRE_SELL_QTY_MISMATCH: expected 20 but paper broker reports 0
        result = broker.place_sell_order(symbol, 20, tag="STOP_HIT", ltp_hint=314.0)
        assert result["status"] == "COMPLETE"
        assert result["average_price"] == pytest.approx(314.0)
        assert broker.get_position_qty(symbol) == 0


# ── SL order state ────────────────────────────────────────────────────────────

class TestSlOrderState:
    def test_sl_order_becomes_complete_on_trigger(self):
        broker = PaperBroker()
        sl_id = _open_trade(broker, "SYM", 20, 300.0)
        broker.update_ltp("SYM", 230.0)
        assert broker.get_order_status(sl_id) == "COMPLETE"

    def test_sl_order_not_triggered_above_price(self):
        broker = PaperBroker()
        sl_id = _open_trade(broker, "SYM", 20, 300.0)
        broker.update_ltp("SYM", 250.0)  # above SL of 240
        assert broker.get_order_status(sl_id) == "TRIGGER PENDING"

    def test_cancel_complete_sl_is_noop(self):
        broker = PaperBroker()
        sl_id = _open_trade(broker, "SYM", 20, 300.0)
        broker.update_ltp("SYM", 230.0)  # trigger
        result = broker.cancel_order(sl_id)
        assert result is False  # already COMPLETE, not cancelled

    def test_modify_sl_rejects_lower_price(self):
        broker = PaperBroker()
        sl_id = _open_trade(broker, "SYM", 20, 300.0)
        result = broker.modify_stop_order(sl_id, 200.0)  # lower than 240
        assert result is False


# ── Multiple SL on different symbols don't interfere ─────────────────────────

class TestMultipleSymbols:
    def test_sl_on_one_symbol_does_not_affect_other(self):
        broker = PaperBroker()
        _open_trade(broker, "CE_SYM", 20, 400.0)
        _open_trade(broker, "PE_SYM", 20, 350.0)

        # Trigger CE SL (SL = 320)
        broker.update_ltp("CE_SYM", 310.0)
        # PE SL (SL = 280) not triggered
        broker.update_ltp("PE_SYM", 290.0)

        assert broker.get_position_qty("CE_SYM") == 20  # still held, sell not called
        assert broker.get_position_qty("PE_SYM") == 20  # untouched

    def test_sell_after_sl_of_one_symbol_clears_only_that_symbol(self):
        broker = PaperBroker()
        _open_trade(broker, "CE_SYM", 20, 400.0)
        _open_trade(broker, "PE_SYM", 20, 350.0)

        broker.update_ltp("CE_SYM", 310.0)  # trigger CE SL
        broker.place_sell_order("CE_SYM", 20, tag="STOP_HIT", ltp_hint=310.0)

        assert broker.get_position_qty("CE_SYM") == 0
        assert broker.get_position_qty("PE_SYM") == 20  # untouched
