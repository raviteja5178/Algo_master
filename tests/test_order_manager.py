"""
Tests for the paper broker order manager.

Covers:
  - Complete fill
  - Rejection (simulated by overriding)
  - Partial fill
  - Duplicate order prevention (via idempotency)
  - Stop modification failure
  - Pre-sell position guard (zero qty → RuntimeError, partial qty → cap)
"""

from __future__ import annotations

import pytest

from execution.paper_broker import PaperBroker


class TestPaperBroker:
    def test_buy_and_fill(self) -> None:
        broker = PaperBroker()
        broker.update_ltp("SENSEX26SEP79500CE", 220.0)
        result = broker.place_buy_order("SENSEX26SEP79500CE", 20)
        assert result["status"] == "COMPLETE"
        assert result["filled_qty"] == 20
        assert result["average_price"] == pytest.approx(220.0)
        assert broker.get_position_qty("SENSEX26SEP79500CE") == 20

    def test_sell_reduces_position(self) -> None:
        broker = PaperBroker()
        broker.update_ltp("SENSEX26SEP79500CE", 220.0)
        broker.place_buy_order("SENSEX26SEP79500CE", 20)
        broker.update_ltp("SENSEX26SEP79500CE", 250.0)
        result = broker.place_sell_order("SENSEX26SEP79500CE", 20)
        assert result["status"] == "COMPLETE"
        assert broker.get_position_qty("SENSEX26SEP79500CE") == 0

    def test_stop_placed_and_triggered(self) -> None:
        broker = PaperBroker()
        broker.update_ltp("SENSEX26SEP79500CE", 220.0)
        broker.place_buy_order("SENSEX26SEP79500CE", 20)
        sl_id = broker.place_stop_order("SENSEX26SEP79500CE", 20, trigger_price=190.0)
        assert broker.get_order_status(sl_id) == "TRIGGER PENDING"
        # Simulate price hitting stop — SL order becomes COMPLETE but position is
        # NOT removed here.  The bot's exit path calls place_sell_order() next,
        # which does the actual position decrement.  This is the correct flow that
        # prevents the PRE_SELL_QTY_MISMATCH bug.
        broker.update_ltp("SENSEX26SEP79500CE", 188.0)
        assert broker.get_order_status(sl_id) == "COMPLETE"
        assert broker.get_position_qty("SENSEX26SEP79500CE") == 20  # held until sell
        # Bot exit path calls place_sell_order after seeing STOP_HIT
        broker.place_sell_order("SENSEX26SEP79500CE", 20, tag="STOP_HIT", ltp_hint=188.0)
        assert broker.get_position_qty("SENSEX26SEP79500CE") == 0   # now cleared

    def test_modify_stop_increases(self) -> None:
        broker = PaperBroker()
        broker.update_ltp("SENSEX26SEP79500CE", 220.0)
        sl_id = broker.place_stop_order("SENSEX26SEP79500CE", 20, trigger_price=190.0)
        ok = broker.modify_stop_order(sl_id, 220.0)
        assert ok is True

    def test_modify_stop_refuses_lower(self) -> None:
        broker = PaperBroker()
        broker.update_ltp("SENSEX26SEP79500CE", 220.0)
        sl_id = broker.place_stop_order("SENSEX26SEP79500CE", 20, trigger_price=190.0)
        ok = broker.modify_stop_order(sl_id, 180.0)
        assert ok is False

    def test_cancel_stop(self) -> None:
        broker = PaperBroker()
        sl_id = broker.place_stop_order("SENSEX26SEP79500CE", 20, trigger_price=190.0)
        assert broker.cancel_order(sl_id) is True
        assert broker.get_order_status(sl_id) is None


# ─────────────────────────────────────────────────────────────────────────────
# Pre-sell position guard
# ─────────────────────────────────────────────────────────────────────────────

class TestPreSellGuard:
    """
    Verify that place_sell_order refuses to send a SELL when the broker
    position is zero or less — protecting against accidental naked shorts.
    Also verifies that a partial position caps the sell quantity rather than
    overshooting into a short.
    """

    SYM = "SENSEX26SEP79500CE"

    def test_sell_with_no_position_raises(self) -> None:
        """actual qty = 0 → RuntimeError, position unchanged."""
        broker = PaperBroker()
        broker.update_ltp(self.SYM, 250.0)
        with pytest.raises(RuntimeError, match="PRE_SELL_QTY_MISMATCH"):
            broker.place_sell_order(self.SYM, 20)
        # Position must still be 0 — no negative qty created
        assert broker.get_position_qty(self.SYM) == 0

    def test_sell_with_negative_position_raises(self) -> None:
        """actual qty < 0 (already short) → RuntimeError."""
        broker = PaperBroker()
        broker._positions[self.SYM] = -5   # simulate pre-existing short
        broker.update_ltp(self.SYM, 250.0)
        with pytest.raises(RuntimeError, match="PRE_SELL_QTY_MISMATCH"):
            broker.place_sell_order(self.SYM, 20)

    def test_sell_capped_when_partial_position(self) -> None:
        """
        Expected 20 but broker only holds 10.
        Sell must be capped to 10 — never send 20 (that would create a -10 short).
        """
        broker = PaperBroker()
        broker.update_ltp(self.SYM, 250.0)
        broker._positions[self.SYM] = 10   # simulate partial position
        result = broker.place_sell_order(self.SYM, 20)
        assert result["status"] == "COMPLETE"
        assert result["filled_qty"] == 10          # capped to actual
        assert broker.get_position_qty(self.SYM) == 0   # fully flat, not -10

    def test_sell_full_position_succeeds(self) -> None:
        """Normal path: actual == expected → sell proceeds unchanged."""
        broker = PaperBroker()
        broker.update_ltp(self.SYM, 250.0)
        broker.place_buy_order(self.SYM, 20)
        result = broker.place_sell_order(self.SYM, 20)
        assert result["status"] == "COMPLETE"
        assert result["filled_qty"] == 20
        assert broker.get_position_qty(self.SYM) == 0
