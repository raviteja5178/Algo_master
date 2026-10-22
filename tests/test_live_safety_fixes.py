"""
Regression tests for six bugs that could leave a live position unprotected,
crash the bot, or let anyone on the network switch it to LIVE trading:

1. Entry TIMEOUT went back to IDLE without cancelling the live order.
2. PRICE_UNCONFIRMED / CANCELLED-with-fills entries were treated as rejected,
   leaving an open position with no SL.
3. A failed exit sell left the position naked (stop already cancelled).
4. EOD square-off did POSITION_OPEN -> CLOSED, which raises ValueError.
5. The 5m candle handler returned on is_entry_blocked() before the pivot
   ATR refresh / AI exit / reversal smart-exit ever ran in a position.
6. The Flask dashboard listened on 0.0.0.0 with unauthenticated POSTs.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from execution.position_manager import State, StateMachine


SYM = "SENSEX26OCT81000CE"


def _sm(state: State) -> StateMachine:
    sm = StateMachine()
    sm._state = state  # noqa: SLF001
    return sm


# ─────────────────────────────────────────────────────────────────────────────
# OrderManager — cancel-and-confirm + limit price on buy fills
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def order_manager():
    with patch("execution.order_manager.get_kite") as gk:
        from execution.order_manager import OrderManager
        om = OrderManager()
        yield om, gk.return_value


class TestCancelUnfilledOrder:
    def test_returns_confirmed_partial_fill(self, order_manager) -> None:
        om, kite = order_manager
        kite.orders.return_value = [{"order_id": "B1", "status": "CANCELLED",
                                     "filled_quantity": 10, "average_price": 301.5}]
        res = om.cancel_unfilled_order("B1", SYM, 20)
        kite.cancel_order.assert_called_once()
        assert res == {"order_id": "B1", "status": "CANCELLED",
                       "filled_qty": 10, "average_price": 301.5}

    def test_unconfirmed_when_order_stays_open(self, order_manager) -> None:
        om, kite = order_manager
        kite.orders.return_value = [{"order_id": "B1", "status": "OPEN",
                                     "filled_quantity": 0, "average_price": 0.0}]
        with patch("execution.order_manager.time.sleep"):
            res = om.cancel_unfilled_order("B1", SYM, 20, max_polls=3)
        assert res["status"] == "UNCONFIRMED"

    def test_buy_result_carries_limit_price(self, order_manager) -> None:
        om, kite = order_manager
        kite.place_order.return_value = "B1"
        with (
            patch("execution.order_manager.settings") as ms,
            patch.object(om, "_wait_for_fill",
                         return_value={"order_id": "B1", "status": "TIMEOUT",
                                       "filled_qty": 0, "average_price": 0.0}),
        ):
            ms.ENTRY_MARGIN_CHECK = False
            res = om.place_buy_order(SYM, 20, ltp_hint=300.0)
        assert res["limit_price"] == pytest.approx(301.5)


# ─────────────────────────────────────────────────────────────────────────────
# Bugs 1 + 2 — entry fill resolution
# ─────────────────────────────────────────────────────────────────────────────

def _entry_ctx() -> SimpleNamespace:
    return SimpleNamespace(sm=_sm(State.ENTRY_PENDING), broker=MagicMock(),
                           tradingsymbol=SYM, quantity=20, trade_id="TRADE_T")


def _resolve(ctx, fill, hint=300.0):
    from main import _resolve_entry_fill
    with patch("main.notify"), patch("main._live_event"):
        return _resolve_entry_fill(ctx, fill, hint)


class TestResolveEntryFill:
    def test_timeout_is_cancelled_and_released_when_nothing_filled(self) -> None:
        ctx = _entry_ctx()
        ctx.broker.cancel_unfilled_order.return_value = {
            "order_id": "B1", "status": "CANCELLED", "filled_qty": 0, "average_price": 0.0}
        outcome, _ = _resolve(ctx, {"order_id": "B1", "status": "TIMEOUT",
                                    "filled_qty": 0, "average_price": 0.0})
        ctx.broker.cancel_unfilled_order.assert_called_once_with("B1", SYM, 20)
        assert outcome == "NO_FILL"

    def test_timeout_partial_fill_is_protected_not_released(self) -> None:
        ctx = _entry_ctx()
        ctx.broker.cancel_unfilled_order.return_value = {
            "order_id": "B1", "status": "CANCELLED", "filled_qty": 10, "average_price": 0.0}
        outcome, fill = _resolve(ctx, {"order_id": "B1", "status": "TIMEOUT", "filled_qty": 0,
                                       "average_price": 0.0, "limit_price": 301.5})
        assert outcome == "FILLED"
        assert fill["status"] == "COMPLETE"
        assert fill["filled_qty"] == 10
        assert fill["average_price"] == pytest.approx(301.5)   # limit-price estimate

    def test_timeout_with_unconfirmed_cancel_halts(self) -> None:
        ctx = _entry_ctx()
        ctx.broker.cancel_unfilled_order.return_value = {
            "order_id": "B1", "status": "UNCONFIRMED", "filled_qty": 0, "average_price": 0.0}
        outcome, _ = _resolve(ctx, {"order_id": "B1", "status": "TIMEOUT",
                                    "filled_qty": 0, "average_price": 0.0})
        assert outcome == "HALTED"
        assert ctx.sm.state == State.HALTED

    def test_price_unconfirmed_uses_limit_price_estimate(self) -> None:
        ctx = _entry_ctx()
        outcome, fill = _resolve(ctx, {"order_id": "B1", "status": "PRICE_UNCONFIRMED",
                                       "filled_qty": 20, "average_price": 0.0,
                                       "limit_price": 301.5})
        assert outcome == "FILLED"
        assert fill["average_price"] == pytest.approx(301.5)
        ctx.broker.cancel_unfilled_order.assert_not_called()

    def test_cancelled_with_fills_is_an_open_position(self) -> None:
        ctx = _entry_ctx()
        outcome, fill = _resolve(ctx, {"order_id": "B1", "status": "CANCELLED",
                                       "filled_qty": 5, "average_price": 299.0})
        assert outcome == "FILLED"
        assert (fill["filled_qty"], fill["average_price"]) == (5, 299.0)

    def test_rejected_is_no_fill(self) -> None:
        ctx = _entry_ctx()
        outcome, _ = _resolve(ctx, {"order_id": "B1", "status": "REJECTED",
                                    "filled_qty": 0, "average_price": 0.0})
        assert outcome == "NO_FILL"


# ─────────────────────────────────────────────────────────────────────────────
# Bug 3 — failed exit sell must not leave the position naked
# ─────────────────────────────────────────────────────────────────────────────

def _exit_ctx() -> SimpleNamespace:
    from strategies.smart_entry import SmartEntryFilter
    broker = MagicMock()
    broker.cancel_order.return_value = True
    broker.place_stop_order.return_value = "SL_NEW"
    broker.get_position_qty.return_value = 20
    return SimpleNamespace(
        sm=_sm(State.POSITION_OPEN), broker=broker, trade_id="TRADE_T",
        tradingsymbol=SYM, instrument_token=1, quantity=20, entry_price=300.0,
        stop_order_id="SL_OLD", strategy_type="CE_ORB", sensex_ltp=81000.0,
        trailing=SimpleNamespace(current_stop=280.0, highest_ltp=310.0,
                                 break_even_activated=False, trail_steps_completed=0),
        target=MagicMock(), smart_entry=SmartEntryFilter(), pivot_mgr=None, ws=None,
    )


def _run_exit(ctx):
    from main import execute_exit
    with (
        patch("main.mark_trade_closed_with_reason") as mock_close,
        patch("main.upsert_trade"),
        patch("main.notify"),
        patch("main.add_live_order_event"),
        patch("main.settings") as ms,
    ):
        ms.TRADING_MODE = "LIVE"
        execute_exit(ctx, reason="TRAILING_STOP_HIT")
    return mock_close


_TIMEOUT = {"order_id": "S1", "status": "TIMEOUT", "filled_qty": 0, "average_price": 0.0}


class TestExecuteExitRecovery:
    def test_timeout_is_cancelled_and_retried(self) -> None:
        ctx = _exit_ctx()
        ctx.broker.place_sell_order.side_effect = [
            _TIMEOUT,
            {"order_id": "S2", "status": "COMPLETE", "filled_qty": 20, "average_price": 240.0},
        ]
        ctx.broker.cancel_unfilled_order.return_value = {
            "order_id": "S1", "status": "CANCELLED", "filled_qty": 0, "average_price": 0.0}
        mock_close = _run_exit(ctx)
        ctx.broker.cancel_unfilled_order.assert_called_once_with("S1", SYM, 20)
        assert ctx.sm.state == State.IDLE
        assert mock_close.call_args[0][1] == pytest.approx(240.0)

    def test_partial_fill_then_retry_uses_weighted_price(self) -> None:
        ctx = _exit_ctx()
        ctx.broker.place_sell_order.side_effect = [
            _TIMEOUT,
            {"order_id": "S2", "status": "COMPLETE", "filled_qty": 12, "average_price": 240.0},
        ]
        ctx.broker.cancel_unfilled_order.return_value = {
            "order_id": "S1", "status": "CANCELLED", "filled_qty": 8, "average_price": 250.0}
        ctx.broker.get_position_qty.return_value = 12
        mock_close = _run_exit(ctx)
        assert ctx.broker.place_sell_order.call_args_list[1][0][:2] == (SYM, 12)
        assert ctx.sm.state == State.IDLE
        assert mock_close.call_args[0][1] == pytest.approx(244.0)   # (8*250 + 12*240) / 20

    def test_retry_failure_replaces_stop_and_halts(self) -> None:
        ctx = _exit_ctx()
        rejected = {"order_id": "S1", "status": "REJECTED", "filled_qty": 0, "average_price": 0.0}
        ctx.broker.place_sell_order.side_effect = [rejected, dict(rejected, order_id="S2")]
        mock_close = _run_exit(ctx)
        ctx.broker.place_stop_order.assert_called_once_with(SYM, 20, 280.0)
        assert ctx.stop_order_id == "SL_NEW"
        assert ctx.sm.state == State.HALTED
        mock_close.assert_not_called()

    def test_unconfirmed_cancel_halts_without_new_orders(self) -> None:
        ctx = _exit_ctx()
        ctx.broker.place_sell_order.return_value = _TIMEOUT
        ctx.broker.cancel_unfilled_order.return_value = {
            "order_id": "S1", "status": "UNCONFIRMED", "filled_qty": 0, "average_price": 0.0}
        _run_exit(ctx)
        assert ctx.broker.place_sell_order.call_count == 1
        ctx.broker.place_stop_order.assert_not_called()
        assert ctx.sm.state == State.HALTED

    def test_sell_exception_replaces_stop_before_halting(self) -> None:
        ctx = _exit_ctx()
        ctx.broker.place_sell_order.side_effect = ConnectionError("network down")
        _run_exit(ctx)
        ctx.broker.place_stop_order.assert_called_once_with(SYM, 20, 280.0)
        assert ctx.sm.state == State.HALTED


# ─────────────────────────────────────────────────────────────────────────────
# Bug 4 — EOD square-off state transitions
# ─────────────────────────────────────────────────────────────────────────────

class TestEodExit:
    def _ctx(self, eod_ok: bool) -> SimpleNamespace:
        eod = MagicMock()
        eod.run_eod_exit.return_value = eod_ok
        return SimpleNamespace(
            sm=_sm(State.POSITION_OPEN), eod=eod, trade_id="TRADE_T", tradingsymbol=SYM,
            instrument_token=1, quantity=20, stop_order_id="SL1", entry_price=300.0,
            trailing=MagicMock(), target=MagicMock(), pivot_mgr=None, ws=None,
            strategy_type="CE_ORB",
        )

    def test_successful_eod_reaches_idle_without_crashing(self) -> None:
        from main import _run_eod_exit
        ctx = self._ctx(eod_ok=True)
        _run_eod_exit(ctx)
        assert ctx.sm.state == State.IDLE
        assert ctx.trade_id is None and ctx.tradingsymbol is None
        assert ctx.instrument_token is None and ctx.stop_order_id is None

    def test_failed_eod_halts(self) -> None:
        from main import _run_eod_exit
        ctx = self._ctx(eod_ok=False)
        with patch("main.notify"):
            _run_eod_exit(ctx)
        assert ctx.sm.state == State.HALTED


# ─────────────────────────────────────────────────────────────────────────────
# Bug 5 — 5m candle handler must run exit logic while a position is open
# ─────────────────────────────────────────────────────────────────────────────

def _candle_ctx(state: State, pivot_mgr=None) -> SimpleNamespace:
    smart_exit = MagicMock()
    smart_exit.check_on_candle.return_value = None
    smart_exit.check_on_tick.return_value = "REVERSAL_SIGNAL"
    agg = MagicMock()
    agg.get_completed.return_value = [MagicMock() for _ in range(20)]
    return SimpleNamespace(
        sm=_sm(state), agg_5m=agg, agg_15m=MagicMock(), vwap=MagicMock(),
        smart_entry=MagicMock(), ws=None, pivot_mgr=pivot_mgr, smart_exit=smart_exit,
        ai_confirmation=None, sensex_ltp=81000.0, strategy_type="CE_ORB",
        entry_price=300.0, quantity=20, entry_atr=50.0, tradingsymbol=SYM,
        trade_id="TRADE_T", prev_day_high=None, prev_day_low=None, pivot_levels=None,
        ai_regime=None, intraday_regime=None, orb_fired_today=False,
        orb_direction_today=None, daily_trend=None,
    )


def _run_candle(ctx, signal):
    from main import _make_candle_handler_5m
    with (
        patch("main._refresh_intraday_regime"),
        patch("main._write_state"),
        patch("main.tick_ema_cooldown"),
        patch("main.tick_mom_cooldown"),
        patch("main.market_open", return_value=True),
        patch("main.atr_at", return_value=55.0),
        patch("main.fetch_today_realised_pnl", return_value=0.0),
        patch("main.evaluate_all_signals", return_value=[signal] if signal else []) as mock_eval,
        patch("main.execute_exit") as mock_exit,
        patch("main.execute_entry") as mock_entry,
    ):
        _make_candle_handler_5m(ctx)(MagicMock(close=81000.0))
    return mock_eval, mock_exit, mock_entry


class TestCandleHandlerInPosition:
    def test_reversal_smart_exit_fires_while_position_open(self) -> None:
        ctx = _candle_ctx(State.POSITION_OPEN)
        _, mock_exit, mock_entry = _run_candle(ctx, "PE_ORB")   # opposite side, same strategy
        mock_exit.assert_called_once_with(ctx, reason="REVERSAL_SIGNAL")
        mock_entry.assert_not_called()

    def test_other_strategys_opposite_signal_does_not_close_position(self) -> None:
        ctx = _candle_ctx(State.POSITION_OPEN)              # holds CE_ORB
        _, mock_exit, _ = _run_candle(ctx, "PE_VWAP")
        mock_exit.assert_not_called()

    def test_pivot_atr_and_delta_refreshed_while_position_open(self) -> None:
        pivot = MagicMock()
        pivot._fav.return_value = 50.0          # SENSEX at T1 → delta 0.5
        ctx = _candle_ctx(State.POSITION_OPEN, pivot_mgr=pivot)
        with patch("main.settings.TRADING_MODE", "SHADOW"), \
             patch("main.settings.PIVOT_OPTION_DELTA", 0.4):
            _, mock_exit, mock_entry = _run_candle(ctx, None)
        pivot.update_atr.assert_called_once_with(55.0)
        pivot.update_delta.assert_called_once_with(0.5)
        mock_entry.assert_not_called()

    def test_open_position_never_triggers_a_new_entry(self) -> None:
        ctx = _candle_ctx(State.POSITION_OPEN)
        ctx.smart_exit.check_on_tick.return_value = None
        _, mock_exit, mock_entry = _run_candle(ctx, "CE")
        mock_exit.assert_not_called()
        mock_entry.assert_not_called()

    def test_halted_bot_skips_signal_evaluation(self) -> None:
        ctx = _candle_ctx(State.HALTED)
        mock_eval, _, mock_entry = _run_candle(ctx, "CE")
        mock_eval.assert_not_called()
        mock_entry.assert_not_called()

    def test_idle_bot_still_enters(self) -> None:
        ctx = _candle_ctx(State.IDLE)
        _, _, mock_entry = _run_candle(ctx, "CE")
        mock_entry.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# execute_entry end-to-end (PAPER): MIN_RR gate + emergency exit
#   - the MIN_RR gate used to run AFTER the fill and return to IDLE, leaving
#     the filled position with no SL;
#   - the emergency exit after an SL placement failure did
#     ENTRY_PENDING -> EXIT_PENDING (invalid), so it halted without selling.
# ─────────────────────────────────────────────────────────────────────────────

def _risk(sl: float, target: float):
    from execution.atr_risk import RiskParams
    return RiskParams(initial_sl_points=sl, break_even_trigger_points=sl / 2,
                      trail_step_points=10.0, initial_target_points=target,
                      atr_value=None, sl_mode="fixed")


@pytest.fixture()
def entry_env(monkeypatch):
    import main
    from config import settings as st
    for key, val in {
        "TRADING_MODE": "PAPER", "MIN_RR": 2.0, "QUANTITY": 20,
        "MIN_OPTION_ENTRY_PRICE": 0.0, "NATR_MIN_OPTION_ENTRY_PRICE": 0.0,
        "USE_SWING_SL": False, "USE_SPOT_ATR_RISK": False,
        "INITIAL_SL_POINTS": 30.0, "INITIAL_TARGET_OFFSET_POINTS": 30.0,   # R:R 1.0
    }.items():
        monkeypatch.setattr(st, key, val)
    store = {name: MagicMock() for name in (
        "notify", "record_action", "upsert_trade", "release_entry_slot",
        "mark_trade_closed", "note_side_trade", "LatencyTracker")}
    for name, mock in store.items():
        monkeypatch.setattr(main, name, mock)
    monkeypatch.setattr(main, "has_action", lambda _id: False)
    monkeypatch.setattr(main, "fetch_active_trade", lambda strategy_key=None: None)
    monkeypatch.setattr(main, "claim_entry_slot_atomic", MagicMock(return_value=True))
    monkeypatch.setattr(main, "select_atm_candidates", lambda ltp, ot: [
        {"tradingsymbol": SYM, "strike": 81000, "instrument_token": 1}])

    broker = MagicMock()
    broker.place_buy_order.return_value = {"order_id": "B1", "status": "COMPLETE",
                                           "filled_qty": 20, "average_price": 300.0}
    broker.place_stop_order.return_value = "SL1"
    sm = _sm(State.IDLE)
    ctx = SimpleNamespace(
        sm=sm, broker=broker, quantity=20, sensex_ltp=81000.0,
        agg_5m=MagicMock(get_completed=MagicMock(return_value=[])),
        smart_entry=MagicMock(), smart_exit=None, pivot_mgr=None, ws=None,
        intraday_regime=None, trade_id=None, tradingsymbol=None, instrument_token=None,
        stop_order_id=None, trailing=None, target=None, latency=None,
        can_create_entry=lambda signal_type="": sm.can_enter(),
        entry_block_reason=lambda signal_type="": "",
    )
    return main, ctx, store


class TestEntryMinRR:
    def test_low_rr_is_blocked_before_any_order(self, entry_env) -> None:
        main, ctx, _ = entry_env
        main.execute_entry(ctx, "CE_ORB", 81000.0)
        ctx.broker.place_buy_order.assert_not_called()
        main.claim_entry_slot_atomic.assert_not_called()
        assert ctx.sm.state == State.IDLE

    def test_rr_miss_after_fill_keeps_and_protects_position(self, entry_env, monkeypatch) -> None:
        main, ctx, _ = entry_env
        # The LTP estimate passes (R:R 3); the real 300.0 fill fails (R:R 1).
        monkeypatch.setattr(
            main, "compute_risk_params",
            lambda *a, entry_price=0.0, **kw: _risk(30, 30) if entry_price == 300.0 else _risk(30, 90))
        main.execute_entry(ctx, "CE_ORB", 81000.0)
        ctx.broker.place_buy_order.assert_called_once()
        ctx.broker.place_stop_order.assert_called_once()
        assert ctx.sm.state == State.POSITION_OPEN
        assert ctx.stop_order_id == "SL1"


class TestMaxRiskPerTrade:
    """A setup whose SL would lose more than MAX_RISK_RUPEES_PER_TRADE is skipped
    before any order (fixed fallback here: SL 30 pts × qty 20 = ₹600)."""

    def test_over_cap_is_skipped_before_order(self, entry_env, monkeypatch) -> None:
        main, ctx, _ = entry_env
        from config import settings as st
        monkeypatch.setattr(st, "MIN_RR", 0.0)
        monkeypatch.setattr(st, "MAX_RISK_RUPEES_PER_TRADE", 500.0)
        main.execute_entry(ctx, "CE_ORB", 81000.0)
        ctx.broker.place_buy_order.assert_not_called()
        main.claim_entry_slot_atomic.assert_not_called()
        assert ctx.sm.state == State.IDLE

    def test_under_cap_trades(self, entry_env, monkeypatch) -> None:
        main, ctx, _ = entry_env
        from config import settings as st
        monkeypatch.setattr(st, "MIN_RR", 0.0)
        monkeypatch.setattr(st, "MAX_RISK_RUPEES_PER_TRADE", 700.0)
        main.execute_entry(ctx, "CE_ORB", 81000.0)
        ctx.broker.place_buy_order.assert_called_once()
        assert ctx.sm.state == State.POSITION_OPEN

    def test_pivot_uses_setup_risk_and_does_not_consume_it(self, entry_env, monkeypatch) -> None:
        main, ctx, _ = entry_env
        from config import settings as st
        from strategies import signal_engine as se
        monkeypatch.setattr(st, "MIN_RR", 0.0)
        monkeypatch.setattr(st, "PIVOT_OPTION_DELTA", 0.4)
        monkeypatch.setattr(st, "MAX_RISK_RUPEES_PER_TRADE", 700.0)
        setup = MagicMock(risk=100.0, side="CE")            # 100 × 0.4 × 20 = ₹800
        monkeypatch.setattr(se, "_last_pivot_setup", setup)
        main.execute_entry(ctx, "CE_PIVOT", 81000.0)
        ctx.broker.place_buy_order.assert_not_called()
        assert se.peek_pivot_setup() is setup

    def test_pivot_rupee_risk_uses_option_delta_even_in_paper(self, entry_env, monkeypatch) -> None:
        """PAPER prices the index itself, but the capped loss is an option loss:
        ₹800 at delta 0.4 must pass a ₹1500 cap (delta 1.0 would wrongly say ₹2000)."""
        main, ctx, _ = entry_env
        from config import settings as st
        monkeypatch.setattr(st, "MIN_RR", 0.0)
        monkeypatch.setattr(st, "PIVOT_OPTION_DELTA", 0.4)
        monkeypatch.setattr(st, "MAX_RISK_RUPEES_PER_TRADE", 1500.0)
        blocked = []
        monkeypatch.setattr(main, "log_event",
                            lambda lg, ev, **f: blocked.append(ev) if ev == "ENTRY_BLOCKED_MAX_RISK" else None)
        from strategies import signal_engine as se
        monkeypatch.setattr(se, "_last_pivot_setup", MagicMock(risk=100.0, side="CE"))
        try:
            main.execute_entry(ctx, "CE_PIVOT", 81000.0)
        except TypeError:
            pass   # MagicMock setup can't drive the trade manager past the cap check
        assert blocked == []


class TestGenericIndexExits:
    """GENERIC_INDEX_EXITS: VWAP/ORB/... trades get the index-anchored engine."""

    def _enable(self, monkeypatch, main, sl_mode="spot_atr"):
        from config import settings as st
        from execution.atr_risk import RiskParams
        monkeypatch.setattr(st, "MIN_RR", 0.0)
        monkeypatch.setattr(st, "GENERIC_INDEX_EXITS", True)
        monkeypatch.setattr(st, "ATM_DELTA", 0.5)
        monkeypatch.setattr(st, "BE_TRIGGER_RR", 1.0)
        monkeypatch.setattr(main, "compute_risk_params", lambda *a, **k: RiskParams(
            initial_sl_points=50.0, break_even_trigger_points=25.0, trail_step_points=15.0,
            initial_target_points=110.0, atr_value=80.0, sl_mode=sl_mode))

    def test_atr_risk_trade_is_index_managed(self, entry_env, monkeypatch, tmp_path) -> None:
        import execution.ema_trade_manager as etm
        main, ctx, _ = entry_env
        monkeypatch.setattr(etm, "_IDX_STATE_FILE", tmp_path / "idx.json")
        self._enable(monkeypatch, main)
        main.execute_entry(ctx, "CE_VWAP", 81000.0)
        mgr = ctx.pivot_mgr
        assert isinstance(mgr, etm.IndexTradeManager)
        assert mgr.stop_index == pytest.approx(81000.0 - 50.0 / 0.5)      # option SL → index
        assert mgr.t3 == pytest.approx(81000.0 + 110.0 / 0.5)
        assert mgr.trail_ema9_exit is False and mgr.time_stop_bars == 0
        ctx.broker.place_stop_order.assert_called_once()                  # broker backstop placed
        assert ctx.sm.state == State.POSITION_OPEN
        assert (tmp_path / "idx.json").exists()                            # state saved for restart

    def test_fixed_fallback_keeps_option_tsl(self, entry_env, monkeypatch) -> None:
        main, ctx, _ = entry_env
        self._enable(monkeypatch, main, sl_mode="fixed")
        main.execute_entry(ctx, "CE_VWAP", 81000.0)
        assert ctx.pivot_mgr is None and ctx.sm.state == State.POSITION_OPEN

    def test_flag_off_is_unchanged(self, entry_env, monkeypatch) -> None:
        main, ctx, _ = entry_env
        self._enable(monkeypatch, main)
        from config import settings as st
        monkeypatch.setattr(st, "GENERIC_INDEX_EXITS", False)
        main.execute_entry(ctx, "CE_VWAP", 81000.0)
        assert ctx.pivot_mgr is None


class TestIndexTradeManager:
    def _mgr(self):
        from execution.ema_trade_manager import IndexTradeManager
        return IndexTradeManager("CE", 81000.0, 80900.0, 81220.0, 60.0, 300.0,
                                 delta=0.5, be_trigger_r=1.0, be_buffer_pts=12.0,
                                 trail_atr_mult=2.0, hard_sl_cushion=1.5)

    def test_exit_reasons_are_idx(self) -> None:
        m = self._mgr()
        assert m.on_index_price(80895.0) == ("EXIT", "IDX_SL_HIT")
        assert self._mgr().on_index_price(81225.0) == ("EXIT", "IDX_TARGET")

    def test_break_even_then_trail(self) -> None:
        m = self._mgr()
        assert m.on_index_price(81100.0)[0] == "STOP_MOVED"                # +1R → BE + buffer
        assert m.stage in ("BE", "TRAIL") and m.stop_index >= 81012.0
        assert m.on_index_price(81011.0) == ("EXIT", m.EXIT_REASONS[m.stage])

    def test_backstop_is_wider_than_index_stop(self) -> None:
        m = self._mgr()                       # index risk 100 × 0.5 = 50 option pts, × 1.5 cushion
        assert m.option_stop == pytest.approx(300.0 - 75.0)

    def test_no_ema_specific_exits(self) -> None:
        m = self._mgr()
        m.stage = "BE"
        assert m.on_candle(80950.0, 81100.0) is None                       # close < EMA9 ignored
        m.stage, m.bars = "INITIAL", 50
        assert m.on_candle(81001.0, None) is None                          # no time stop

    def test_state_file_is_separate_from_ema(self, monkeypatch, tmp_path) -> None:
        import execution.ema_trade_manager as etm
        monkeypatch.setattr(etm, "_STATE_FILE", tmp_path / "ema.json")
        monkeypatch.setattr(etm, "_IDX_STATE_FILE", tmp_path / "idx.json")
        m = self._mgr()
        m.save("T1")
        assert (tmp_path / "idx.json").exists() and not (tmp_path / "ema.json").exists()
        assert etm.IndexTradeManager.load("T1").stop_index == m.stop_index
        assert etm.EmaTradeManager.load("T1") is None
        etm.IndexTradeManager.clear()
        assert not (tmp_path / "idx.json").exists()


class TestEntryRiskWiring:
    """Strategy-review fixes: execute_entry must pass the configured BE multiple,
    delta and target mode through to the trade's managers."""

    def test_entry_uses_configured_be_delta_and_fixed_target(self, entry_env, monkeypatch) -> None:
        main, ctx, _ = entry_env
        from config import settings as st
        monkeypatch.setattr(st, "MIN_RR", 0.0)
        monkeypatch.setattr(st, "BE_TRIGGER_RR", 1.4)
        monkeypatch.setattr(st, "ATM_DELTA", 0.5)
        monkeypatch.setattr(st, "TARGET_TRAIL_WITH_STOP", False)
        main.execute_entry(ctx, "CE_ORB", 81000.0)
        assert ctx.sm.state == State.POSITION_OPEN
        assert ctx.trailing.break_even_trigger_points == pytest.approx(42.0)   # 30 × 1.4
        assert ctx.trailing.atm_delta == pytest.approx(0.5)
        assert ctx.target.ratchet_with_stop is False
        assert ctx.target.target_reference == pytest.approx(300.0 + 30.0)


class TestEntryEmergencyExit:
    def test_sl_failure_sells_the_position(self, entry_env, monkeypatch) -> None:
        main, ctx, store = entry_env
        from config import settings as st
        monkeypatch.setattr(st, "MIN_RR", 0.0)
        ctx.broker.place_stop_order.side_effect = RuntimeError("SL rejected")
        ctx.broker.place_sell_order.return_value = {"order_id": "S1", "status": "COMPLETE",
                                                    "filled_qty": 20, "average_price": 295.0}
        main.execute_entry(ctx, "CE_ORB", 81000.0)
        ctx.broker.place_sell_order.assert_called_once()
        store["mark_trade_closed"].assert_called_once()
        assert ctx.sm.state == State.IDLE

    def test_failed_emergency_sell_halts(self, entry_env, monkeypatch) -> None:
        main, ctx, _ = entry_env
        from config import settings as st
        monkeypatch.setattr(st, "MIN_RR", 0.0)
        ctx.broker.place_stop_order.side_effect = RuntimeError("SL rejected")
        ctx.broker.place_sell_order.return_value = {"order_id": "S1", "status": "REJECTED",
                                                    "filled_qty": 0, "average_price": 0.0}
        main.execute_entry(ctx, "CE_ORB", 81000.0)
        ctx.broker.place_sell_order.assert_called_once()
        assert ctx.sm.state == State.HALTED


# ─────────────────────────────────────────────────────────────────────────────
# Bug 6 — dashboard bound to loopback, mutating endpoints need the token
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def dash(tmp_path, monkeypatch):
    ui_app = importlib.import_module("ui.app")
    env_file = tmp_path / ".env"
    env_file.write_text("TRADING_MODE=PAPER\n", encoding="utf-8")
    monkeypatch.setattr(ui_app, "ENV_FILE", env_file)
    ui_app.app.config["TESTING"] = True
    return ui_app, ui_app.app.test_client(), env_file


class TestDashboardAuth:
    def test_default_bind_is_loopback(self, dash) -> None:
        ui_app, _, _ = dash
        assert ui_app.DASHBOARD_HOST == "127.0.0.1"

    @pytest.mark.parametrize("path", ["/api/env", "/api/bot/start", "/api/zerodha/import"])
    def test_mutating_endpoints_reject_missing_token(self, dash, path) -> None:
        _, client, env_file = dash
        resp = client.post(path, json={"TRADING_MODE": "LIVE", "ENABLE_LIVE_TRADING": "true"})
        assert resp.status_code == 403
        assert "LIVE" not in env_file.read_text(encoding="utf-8")

    def test_wrong_token_rejected(self, dash) -> None:
        _, client, env_file = dash
        resp = client.post("/api/env", json={"TRADING_MODE": "LIVE"},
                           headers={"X-Dashboard-Token": "guess"})
        assert resp.status_code == 403
        assert "LIVE" not in env_file.read_text(encoding="utf-8")

    def test_valid_token_accepted(self, dash, monkeypatch) -> None:
        ui_app, client, env_file = dash
        import os
        import config.settings as cs
        # The endpoint writes os.environ and settings — restore both afterwards.
        monkeypatch.setattr(cs, "QUANTITY", cs.QUANTITY)
        for key in ("QUANTITY", "TRADING_MODE"):
            monkeypatch.setenv(key, os.environ.get(key, ""))
        resp = client.post("/api/env", json={"QUANTITY": "20"},
                           headers={"X-Dashboard-Token": ui_app.DASHBOARD_TOKEN})
        assert resp.status_code == 200
        assert "QUANTITY" in env_file.read_text(encoding="utf-8")

    def test_foreign_host_rejected(self, dash) -> None:
        _, client, _ = dash
        resp = client.get("/api/env", headers={"Host": "evil.example:5000"})
        assert resp.status_code == 403

    def test_page_embeds_token_for_same_origin_fetch(self, dash) -> None:
        ui_app, client, _ = dash
        html = client.get("/strategies").get_data(as_text=True)
        assert ui_app.DASHBOARD_TOKEN in html
        assert "X-Dashboard-Token" in html
