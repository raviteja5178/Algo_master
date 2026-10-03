"""
Tests for broker reconciliation / position mismatch detection.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from execution.position_manager import State, StateMachine
from risk.safety_manager import SafetyManager


class TestReconciliation:
    def test_reconcile_match_returns_true(self) -> None:
        sm = StateMachine()
        manager = SafetyManager(sm)
        with patch("risk.safety_manager.get_net_position_qty", return_value=20):
            result = manager.reconcile_position("SENSEX26SEP79500CE", expected_qty=20)
        assert result is True
        assert manager.is_mismatch() is False

    def test_reconcile_mismatch_halts(self) -> None:
        sm = StateMachine()
        manager = SafetyManager(sm)
        # Force into a state that allows HALTED
        sm._state = State.POSITION_OPEN
        with patch("risk.safety_manager.get_net_position_qty", return_value=0):
            result = manager.reconcile_position("SENSEX26SEP79500CE", expected_qty=20)
        assert result is False
        assert manager.is_mismatch() is True
        assert sm.state == State.HALTED

    def test_reconcile_no_symbol_returns_true(self) -> None:
        sm = StateMachine()
        manager = SafetyManager(sm)
        result = manager.reconcile_position(None, 0)
        assert result is True
