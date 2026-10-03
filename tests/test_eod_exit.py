"""
Tests for EOD forced exit.

Key invariant: the broker position is the truth.
If get_position_qty() != 0 after a COMPLETE fill, the trade must NOT be
marked closed and run_eod_exit must return False.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from execution.eod_manager import EODManager


class FakeStore:
    def __init__(self) -> None:
        self.closed: dict | None = None

    def mark_trade_closed(self, trade_id, exit_price, exit_time, pnl) -> None:
        self.closed = {"trade_id": trade_id, "exit_price": exit_price, "pnl": pnl}


class TestEODExit:
    def _broker(self, fill_price: float = 250.0) -> MagicMock:
        b = MagicMock()
        b.place_sell_order.return_value = {
            "order_id": "TEST_SELL_001",
            "status": "COMPLETE",
            "filled_qty": 20,
            "average_price": fill_price,
        }
        b.get_position_qty.return_value = 0
        b.cancel_order.return_value = True
        return b

    def test_successful_eod_exit(self) -> None:
        store = FakeStore()
        broker = self._broker(250.0)
        mgr = EODManager(broker, store)
        ok = mgr.run_eod_exit(
            tradingsymbol="SENSEX26SEP79500CE",
            quantity=20,
            trade_id="TRADE_001",
            stop_order_id="SL_001",
            entry_price=220.0,
        )
        assert ok is True
        assert store.closed is not None
        assert store.closed["exit_price"] == pytest.approx(250.0)
        # P&L = (250 - 220) * 20 = 600
        assert store.closed["pnl"] == pytest.approx(600.0)

    def test_eod_cancels_stop_before_exit(self) -> None:
        store = FakeStore()
        broker = self._broker()
        mgr = EODManager(broker, store)
        mgr.run_eod_exit("SENSEX26SEP79500CE", 20, "T1", "SL_001", 220.0)
        broker.cancel_order.assert_called_once_with("SL_001")

    def test_eod_not_duplicated(self) -> None:
        store = FakeStore()
        broker = self._broker()
        mgr = EODManager(broker, store)
        mgr.run_eod_exit("SENSEX26SEP79500CE", 20, "T1", None, 220.0)
        mgr.run_eod_exit("SENSEX26SEP79500CE", 20, "T1", None, 220.0)
        # place_sell_order called only once
        assert broker.place_sell_order.call_count == 1

    def test_eod_retries_on_failure(self) -> None:
        store = FakeStore()
        broker = MagicMock()
        # Fail first attempt, succeed on second
        broker.place_sell_order.side_effect = [
            Exception("network error"),
            {"order_id": "X", "status": "COMPLETE", "filled_qty": 20, "average_price": 240.0},
        ]
        broker.get_position_qty.return_value = 0
        broker.cancel_order.return_value = True
        mgr = EODManager(broker, store)
        ok = mgr.run_eod_exit("SENSEX26SEP79500CE", 20, "T1", None, 220.0)
        assert ok is True
        assert broker.place_sell_order.call_count == 2

    def test_eod_not_closed_when_broker_position_remains(self) -> None:
        """
        If broker still reports qty != 0 after a COMPLETE fill, the trade must
        NOT be marked closed and the method must return False so the caller
        can transition to EXIT_PENDING / HALTED and reconcile.
        """
        store = FakeStore()
        broker = self._broker(fill_price=250.0)
        # Broker says position is still open despite COMPLETE status
        broker.get_position_qty.return_value = 20
        mgr = EODManager(broker, store)
        ok = mgr.run_eod_exit(
            tradingsymbol="SENSEX26SEP79500CE",
            quantity=20,
            trade_id="TRADE_REMAIN",
            stop_order_id=None,
            entry_price=220.0,
        )
        assert ok is False
        # Trade must NOT have been persisted as closed
        assert store.closed is None
        # _executed_today must remain False so a retry is possible
        assert mgr._executed_today is False
