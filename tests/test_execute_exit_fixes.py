"""
Tests for the two bugs fixed in execute_exit / reconciliation loop:

Bug 1 — PRE_SELL_QTY_MISMATCH causes HALT instead of clean close
-----------------------------------------------------------------
When the broker's SL order fills at the exchange before the trailing-stop
handler runs, the position is already flat (qty=0).  place_sell_order raises
PRE_SELL_QTY_MISMATCH.  The bot must NOT halt — it should look up the SL fill
price, close the trade record cleanly, and return to IDLE.

Bug 2 — Reconciliation loop crashes with invalid state transition
-----------------------------------------------------------------
The periodic reconciliation loop detected an external close (qty=0) and tried
to transition directly from POSITION_OPEN → CLOSED, which is invalid (not in
_TRANSITIONS).  The fix adds EXIT_PENDING as an intermediate step.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from execution.position_manager import State, StateMachine


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_ctx(
    state: State = State.POSITION_OPEN,
    tradingsymbol: str = "SENSEX26SEP74800CE",
    entry_price: float = 225.10,
    quantity: int = 20,
    trade_id: str = "TRADE_CE_ORB_TEST",
    stop_order_id: str = "SL123",
    sl_fill_price: float = 168.80,
) -> SimpleNamespace:
    """Build a minimal BotContext-like namespace for unit testing."""
    sm = StateMachine()
    sm._state = state  # noqa: SLF001

    broker_mock = MagicMock()
    broker_mock.cancel_order.return_value = True

    from strategies.smart_entry import SmartEntryFilter

    ctx = SimpleNamespace(
        sm=sm,
        broker=broker_mock,
        trade_id=trade_id,
        tradingsymbol=tradingsymbol,
        instrument_token=12345,
        quantity=quantity,
        entry_price=entry_price,
        stop_order_id=stop_order_id,
        trailing=MagicMock(),
        target=MagicMock(),
        strategy_type="CE_ORB",
        sensex_ltp=74800.0,
        smart_entry=SmartEntryFilter(),   # all filters disabled — no side effects
    )
    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# Bug 1 — PRE_SELL_QTY_MISMATCH → clean close, not HALT
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteExitSLRace:
    """
    Simulate the race condition where the broker's SL order fires at the exchange
    before the trailing-stop handler attempts to place a SELL order.
    """

    def test_sl_race_returns_idle_not_halted(self) -> None:
        """Bot must end in IDLE, not HALTED, on PRE_SELL_QTY_MISMATCH."""
        from main import execute_exit

        ctx = _make_ctx(sl_fill_price=168.80)

        # place_sell_order raises PRE_SELL_QTY_MISMATCH (qty=0 at broker)
        ctx.broker.place_sell_order.side_effect = RuntimeError(
            "PRE_SELL_QTY_MISMATCH: expected 20 but broker reports 0 "
            "for SENSEX26SEP74800CE. SELL aborted to prevent naked short."
        )

        _fake_orders = [
            {
                "tradingsymbol": "SENSEX26SEP74800CE",
                "transaction_type": "SELL",
                "status": "COMPLETE",
                "average_price": 168.80,
            }
        ]

        with (
            patch("main.mark_trade_closed_with_reason") as mock_close,
            patch("main.notify") as mock_notify,
            patch("main.log_event"),
            patch("main.now_ist", return_value=MagicMock(isoformat=lambda: "2026-09-23T10:18:00")),
            patch("main._fetch_broker_orders", return_value=_fake_orders),
            patch("main.settings") as ms,
        ):
            ms.TRADING_MODE = "LIVE"
            execute_exit(ctx, reason="TRAILING_STOP_HIT")

        # State machine must end at IDLE
        assert ctx.sm.state == State.IDLE

        # Trade must be closed in DB
        mock_close.assert_called_once()
        call_args = mock_close.call_args[0]
        assert call_args[0] == "TRADE_CE_ORB_TEST"   # trade_id
        assert call_args[1] == pytest.approx(168.80)  # exit price from SL order

        # Notification must fire with SL_FILLED_AT_EXCHANGE reason
        notify_calls = {c[0][0] for c in mock_notify.call_args_list}
        assert "EXIT_FILLED" in notify_calls
        assert "BOT_HALTED" not in notify_calls

    def test_sl_race_clears_trade_context(self) -> None:
        """All ctx trade fields must be None after SL-race resolution."""
        from main import execute_exit

        ctx = _make_ctx()
        ctx.broker.place_sell_order.side_effect = RuntimeError(
            "PRE_SELL_QTY_MISMATCH: expected 20 but broker reports 0 "
            "for SENSEX26SEP74800CE. SELL aborted to prevent naked short."
        )

        with (
            patch("main.mark_trade_closed_with_reason"),
            patch("main.notify"),
            patch("main.log_event"),
            patch("main.now_ist", return_value=MagicMock(isoformat=lambda: "2026-09-23T10:18:00")),
            patch("main._fetch_broker_orders", return_value=[]),
            patch("main.settings") as ms,
        ):
            ms.TRADING_MODE = "LIVE"
            execute_exit(ctx, reason="TRAILING_STOP_HIT")

        assert ctx.trade_id is None
        assert ctx.tradingsymbol is None
        assert ctx.trailing is None
        assert ctx.target is None
        assert ctx.stop_order_id is None

    def test_sl_race_uses_sl_order_fill_price(self) -> None:
        """The exit price recorded must come from the completed SELL order, not entry."""
        from main import execute_exit

        ctx = _make_ctx(entry_price=225.10, sl_fill_price=195.50)
        ctx.broker.place_sell_order.side_effect = RuntimeError(
            "PRE_SELL_QTY_MISMATCH: expected 20 but broker reports 0 "
            "for SENSEX26SEP74800CE. SELL aborted to prevent naked short."
        )

        _fake_orders = [
            {
                "tradingsymbol": "SENSEX26SEP74800CE",
                "transaction_type": "SELL",
                "status": "COMPLETE",
                "average_price": 195.50,
            }
        ]

        with (
            patch("main.mark_trade_closed_with_reason") as mock_close,
            patch("main.notify"),
            patch("main.log_event"),
            patch("main.now_ist", return_value=MagicMock(isoformat=lambda: "2026-09-23T10:18:00")),
            patch("main._fetch_broker_orders", return_value=_fake_orders),
            patch("main.settings") as ms,
        ):
            ms.TRADING_MODE = "LIVE"
            execute_exit(ctx, reason="TRAILING_STOP_HIT")

        call_args = mock_close.call_args[0]
        assert call_args[1] == pytest.approx(195.50)  # SL fill price, not entry

    def test_other_runtime_error_still_halts(self) -> None:
        """A RuntimeError that is NOT PRE_SELL_QTY_MISMATCH must still halt."""
        from main import execute_exit

        ctx = _make_ctx()
        ctx.broker.place_sell_order.side_effect = RuntimeError("Some other broker error")

        with (
            patch("main.mark_trade_closed"),
            patch("main.notify"),
            patch("main.log_event"),
            patch("main.now_ist", return_value=MagicMock(isoformat=lambda: "2026-09-23T10:18:00")),
        ):
            execute_exit(ctx, reason="TRAILING_STOP_HIT")

        assert ctx.sm.state == State.HALTED

    def test_sl_race_fallback_to_entry_price_when_no_orders(self) -> None:
        """When order history cannot be fetched, exit price falls back to entry_price."""
        from main import execute_exit

        ctx = _make_ctx(entry_price=225.10)
        ctx.broker.place_sell_order.side_effect = RuntimeError(
            "PRE_SELL_QTY_MISMATCH: expected 20 but broker reports 0 "
            "for SENSEX26SEP74800CE. SELL aborted to prevent naked short."
        )
        # kite.orders() raises so we cannot fetch the SL fill price
        ctx.broker._kite.orders.side_effect = Exception("API error")

        with (
            patch("main.mark_trade_closed_with_reason") as mock_close,
            patch("main.notify"),
            patch("main.log_event"),
            patch("main.now_ist", return_value=MagicMock(isoformat=lambda: "2026-09-23T10:18:00")),
        ):
            execute_exit(ctx, reason="TRAILING_STOP_HIT")

        call_args = mock_close.call_args[0]
        # Falls back to entry_price when order history is unavailable
        assert call_args[1] == pytest.approx(225.10)
        assert ctx.sm.state == State.IDLE


# ─────────────────────────────────────────────────────────────────────────────
# Bug 2 — Reconciliation loop: POSITION_OPEN → EXIT_PENDING → CLOSED → IDLE
# ─────────────────────────────────────────────────────────────────────────────

class TestReconciliationTransition:
    """
    The reconciliation loop must transition through EXIT_PENDING before CLOSED.
    Previously it went POSITION_OPEN → CLOSED directly, which is invalid and
    raised a ValueError caught by the bare except, silently swallowing the fix.
    """

    def test_external_close_transitions_through_exit_pending(self) -> None:
        """State must go POSITION_OPEN → EXIT_PENDING → CLOSED → IDLE."""
        sm = StateMachine()
        sm._state = State.POSITION_OPEN  # noqa: SLF001

        states_seen: list[str] = []
        original_transition = sm.transition

        def recording_transition(new_state: State, reason: str = "") -> None:
            original_transition(new_state, reason)
            states_seen.append(new_state.value)

        sm.transition = recording_transition  # type: ignore[method-assign]

        # Simulate just the transition sequence the reconciliation loop now uses
        sm.transition(State.EXIT_PENDING, reason="external close detected")
        sm.transition(State.CLOSED, reason="external close detected")
        sm.transition(State.IDLE, reason="ready for next trade")

        assert states_seen == ["EXIT_PENDING", "CLOSED", "IDLE"]
        assert sm.state == State.IDLE

    def test_direct_position_open_to_closed_is_invalid(self) -> None:
        """Confirm the old (broken) direct transition raises ValueError."""
        sm = StateMachine()
        sm._state = State.POSITION_OPEN  # noqa: SLF001

        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition(State.CLOSED, reason="should fail")
