"""
Tests that PAPER / SHADOW mode restart recovery restores the paper position
into the broker's in-memory state WITHOUT calling the real Zerodha API,
preventing the spurious STALE_TRADE_AUTO_CLOSE that was triggered on every
mid-trade restart in SHADOW mode.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from execution.paper_broker import PaperBroker
from execution.position_manager import State, StateMachine
from risk.safety_manager import SafetyManager


# ── Minimal stubs ──────────────────────────────────────────────────────────────

def _active_trade(symbol: str = "SENSEX26O0172600CE", qty: int = 20) -> dict:
    return {
        "trade_id": "TRADE_CE_TEST_001",
        "strategy_type": "CE_VWAP",
        "option_symbol": symbol,
        "instrument_token": 12345,
        "quantity": qty,
        "entry_price": 350.0,
        "stop_order_id": "PAPER_SL_ABCDEF",
        "current_stop": 280.0,
        "highest_ltp": 360.0,
        "target_reference": 472.0,
    }


def _make_ctx() -> MagicMock:
    """Return a minimal BotContext-like mock with a real PaperBroker and StateMachine."""
    ctx = MagicMock()
    ctx.broker = PaperBroker()
    ctx.sm = StateMachine()
    ctx.safety = SafetyManager(ctx.sm)
    return ctx


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestShadowRestartRecovery:
    """
    When TRADING_MODE is PAPER or SHADOW and there is an active trade in the DB,
    recover_from_restart must:
      1. NOT call get_net_position_qty (the real Zerodha API).
      2. Restore the qty into the PaperBroker._positions dict.
      3. NOT close (mark_trade_closed) the active trade.
      4. Leave the state machine in POSITION_OPEN.
    """

    @pytest.mark.parametrize("mode", ["PAPER", "SHADOW"])
    def test_paper_shadow_does_not_call_real_broker(self, mode: str) -> None:
        ctx = _make_ctx()

        with (
            patch("main.settings.TRADING_MODE", mode),
            patch("main.fetch_active_trade", return_value=_active_trade()),
            # get_net_position_qty is used inside SafetyManager (risk module)
            patch("risk.safety_manager.get_net_position_qty") as mock_qty,
            patch("main.mark_trade_closed") as mock_close,
            patch("main.upsert_trade"),
        ):
            from main import recover_from_restart
            recover_from_restart(ctx)

            # Real broker qty check must NOT be called
            mock_qty.assert_not_called()

            # Trade must NOT be auto-closed
            mock_close.assert_not_called()

    @pytest.mark.parametrize("mode", ["PAPER", "SHADOW"])
    def test_paper_shadow_restores_position_in_broker(self, mode: str) -> None:
        ctx = _make_ctx()
        symbol = "SENSEX26O0172600CE"
        qty = 20

        with (
            patch("main.settings.TRADING_MODE", mode),
            patch("main.fetch_active_trade", return_value=_active_trade(symbol, qty)),
            patch("risk.safety_manager.get_net_position_qty"),
            patch("main.mark_trade_closed"),
            patch("main.upsert_trade"),
        ):
            from main import recover_from_restart
            recover_from_restart(ctx)

            # PaperBroker should now hold the restored qty
            assert ctx.broker.get_position_qty(symbol) == qty

    @pytest.mark.parametrize("mode", ["PAPER", "SHADOW"])
    def test_paper_shadow_sets_position_open_state(self, mode: str) -> None:
        ctx = _make_ctx()

        with (
            patch("main.settings.TRADING_MODE", mode),
            patch("main.fetch_active_trade", return_value=_active_trade()),
            patch("risk.safety_manager.get_net_position_qty"),
            patch("main.mark_trade_closed"),
            patch("main.upsert_trade"),
        ):
            from main import recover_from_restart
            recover_from_restart(ctx)

            assert ctx.sm.state == State.POSITION_OPEN

    def test_live_mode_still_calls_real_broker(self) -> None:
        """LIVE mode must still use reconcile_position (real Zerodha API)."""
        ctx = _make_ctx()

        with (
            patch("main.settings.TRADING_MODE", "LIVE"),
            patch("main.fetch_active_trade", return_value=_active_trade()),
            patch("main.mark_trade_closed"),
            patch("main.upsert_trade"),
            # Patch at the source so SafetyManager sees it
            patch("risk.safety_manager.get_net_position_qty", return_value=20) as mock_qty,
        ):
            from main import recover_from_restart
            recover_from_restart(ctx)

            mock_qty.assert_called_once()

    def test_live_mode_auto_closes_stale_trade(self) -> None:
        """If reconcile_position returns False in LIVE mode, the trade is closed."""
        ctx = _make_ctx()

        with (
            patch("main.settings.TRADING_MODE", "LIVE"),
            patch("main.fetch_active_trade", return_value=_active_trade()),
            patch("main.mark_trade_closed") as mock_close,
            patch("main.upsert_trade"),
            patch("main._fetch_broker_orders", return_value=[]),
            # qty=0 triggers mismatch → reconcile_position returns False
            patch("risk.safety_manager.get_net_position_qty", return_value=0),
        ):
            ctx.sm._state = State.POSITION_OPEN  # allow HALTED transition
            from main import recover_from_restart
            recover_from_restart(ctx)

            mock_close.assert_called_once()
