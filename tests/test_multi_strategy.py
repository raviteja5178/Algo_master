"""
Every strategy trades independently: each owns a slot with its own position
check, holds its trade to completion, and is never blocked by (or closes)
another strategy's position — even on the same option symbol.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from execution.position_manager import State

SYM = "SENSEX26O2281000CE"


@pytest.fixture()
def bot(monkeypatch, tmp_path):
    """Real BotContext (PAPER, tmp DB) with deterministic option selection."""
    import main
    from config import settings as st
    from execution import ema_trade_manager as etm
    from execution import pivot_trade_manager as ptm
    from persistence import models

    monkeypatch.setattr(models.settings, "DB_PATH", str(tmp_path / "t.db"))
    models.init_db()
    for key, val in {
        "TRADING_MODE": "PAPER", "MIN_RR": 0.0, "QUANTITY": 20,
        "MIN_OPTION_ENTRY_PRICE": 0.0, "NATR_MIN_OPTION_ENTRY_PRICE": 0.0,
        "USE_SWING_SL": False, "USE_SPOT_ATR_RISK": False,
        "INITIAL_SL_POINTS": 30.0, "INITIAL_TARGET_OFFSET_POINTS": 90.0,
        "ENABLE_SMART_EXIT": False, "GENERIC_INDEX_EXITS": False,
        "MAX_RISK_RUPEES_PER_TRADE": 0.0, "NO_NEW_ENTRY_AFTER": "23:59",
    }.items():
        monkeypatch.setattr(st, key, val)
    monkeypatch.setattr(ptm, "_STATE_FILE", tmp_path / "p.json")
    monkeypatch.setattr(etm, "_STATE_FILE", tmp_path / "e.json")
    monkeypatch.setattr(etm, "_IDX_STATE_FILE", tmp_path / "i.json")
    monkeypatch.setattr(main, "notify", MagicMock())
    monkeypatch.setattr(main, "_write_state", lambda ctx: None)
    monkeypatch.setattr(main, "_write_ltp", lambda ctx: None)
    monkeypatch.setattr(main, "select_atm_candidates", lambda ltp, ot: [
        {"tradingsymbol": SYM, "strike": 81000, "instrument_token": 11}])
    ctx = main.BotContext()
    ctx.sensex_ltp = 81000.0
    return main, ctx


def _candle():
    from datetime import datetime
    from market.candle_builder import Candle
    return Candle(timestamp=datetime(2026, 10, 20, 10, 0), open=81000.0, high=81010.0,
                  low=80990.0, close=81000.0, volume=100)


def _enter(main, ctx, signal: str) -> object:
    slot = ctx.slot_for(main.strategy_key(signal))
    main.execute_entry(slot, signal, 81000.0)
    return slot


class TestIndependentSlots:
    def test_two_strategies_hold_the_same_symbol_at_once(self, bot) -> None:
        main, ctx = bot
        orb = _enter(main, ctx, "CE_ORB")
        vwap = _enter(main, ctx, "CE_VWAP")           # same side, same option symbol
        assert orb.sm.state == State.POSITION_OPEN
        assert vwap.sm.state == State.POSITION_OPEN
        assert orb.tradingsymbol == vwap.tradingsymbol == SYM
        assert orb.trade_id != vwap.trade_id
        assert orb.stop_order_id != vwap.stop_order_id
        assert ctx.broker.get_position_qty(SYM) == 40   # both lots held

    def test_each_strategy_has_its_own_position_check(self, bot) -> None:
        main, ctx = bot
        orb = _enter(main, ctx, "CE_ORB")
        first_id = orb.trade_id
        _enter(main, ctx, "PE_ORB")                   # ORB already holds a trade
        assert orb.trade_id == first_id               # held to completion, no 2nd entry
        assert ctx.broker.get_position_qty(SYM) == 20
        assert _enter(main, ctx, "CE_NATR").sm.state == State.POSITION_OPEN

    def test_exit_of_one_strategy_leaves_the_others_open(self, bot) -> None:
        main, ctx = bot
        orb = _enter(main, ctx, "CE_ORB")
        vwap = _enter(main, ctx, "CE_VWAP")
        with patch.object(main, "mark_trade_closed_with_reason"):
            main.execute_exit(orb, reason="TARGET_HIT", exit_ltp=81100.0)
        assert orb.sm.state == State.IDLE and orb.trade_id is None
        assert vwap.sm.state == State.POSITION_OPEN and vwap.trade_id
        assert ctx.broker.get_position_qty(SYM) == 20
        assert not ctx.is_halted()

    def test_strategy_can_trade_again_after_its_own_exit(self, bot) -> None:
        main, ctx = bot
        orb = _enter(main, ctx, "CE_ORB")
        with patch.object(main, "mark_trade_closed_with_reason"):
            main.execute_exit(orb, reason="TARGET_HIT", exit_ltp=81100.0)
        assert orb.can_create_entry("CE_ORB")

    def test_db_guard_is_per_strategy(self, bot) -> None:
        from persistence.trade_store import fetch_active_trade, fetch_active_trades
        main, ctx = bot
        _enter(main, ctx, "CE_ORB")
        _enter(main, ctx, "PE_VWAP")
        _enter(main, ctx, "CE_NATR")
        assert fetch_active_trade("ORB")["strategy_type"] == "CE_ORB"
        assert fetch_active_trade("NATR")["strategy_type"] == "CE_NATR"
        assert fetch_active_trade("EMA") is None
        assert len(fetch_active_trades()) == 3


class TestTickRouting:
    def test_sl_hit_closes_only_its_own_trade(self, bot, monkeypatch) -> None:
        main, ctx = bot
        monkeypatch.setattr(main, "mark_trade_closed_with_reason", MagicMock())
        monkeypatch.setattr(main, "_live_event", MagicMock())
        monkeypatch.setattr(main, "now_ist", main.now_ist)
        ce = _enter(main, ctx, "CE_ORB")
        pe = _enter(main, ctx, "PE_VWAP")
        # PAPER prices the option off the index; a drop hurts the CE only.
        ce_sl = ctx.broker._open_orders[ce.stop_order_id]["trigger_price"]
        main.on_option_ltp(ce, ce_sl - 1)
        assert ce.sm.state == State.IDLE
        assert pe.sm.state == State.POSITION_OPEN


class TestSignalRouting:
    def test_candle_handler_enters_every_signalled_strategy(self, bot) -> None:
        main, ctx = bot
        ctx.agg_5m = MagicMock(get_completed=MagicMock(return_value=[MagicMock()] * 20))
        ctx.agg_15m = MagicMock(get_completed=MagicMock(return_value=[MagicMock()] * 20))
        entered = []
        with (
            patch.object(main, "_refresh_intraday_regime"),
            patch.object(main, "market_open", return_value=True),
            patch.object(main, "atr_at", return_value=50.0),
            patch.object(main, "evaluate_all_signals",
                         return_value=["CE_ORB", "PE_VWAP", "CE_NATR"]),
            patch.object(main, "execute_entry",
                         side_effect=lambda slot, sig, *a, **k: entered.append((slot.key, sig))),
        ):
            main._make_candle_handler_5m(ctx)(_candle())
        assert entered == [("ORB", "CE_ORB"), ("VWAP", "PE_VWAP"), ("NATR", "CE_NATR")]

    def test_busy_strategy_is_skipped_but_others_enter(self, bot) -> None:
        main, ctx = bot
        orb = ctx.slot_for("ORB")
        orb.sm._state = State.POSITION_OPEN            # ORB holds a trade
        ctx.agg_5m = MagicMock(get_completed=MagicMock(return_value=[MagicMock()] * 20))
        ctx.agg_15m = MagicMock(get_completed=MagicMock(return_value=[MagicMock()] * 20))
        entered = []
        with (
            patch.object(main, "_refresh_intraday_regime"),
            patch.object(main, "market_open", return_value=True),
            patch.object(main, "atr_at", return_value=50.0),
            patch.object(main, "evaluate_all_signals", return_value=["CE_ORB", "CE_VWAP"]),
            patch.object(main, "execute_entry",
                         side_effect=lambda slot, sig, *a, **k: entered.append(sig)),
        ):
            main._make_candle_handler_5m(ctx)(_candle())
        assert entered == ["CE_VWAP"]

    def test_halted_slot_blocks_all_new_entries(self, bot) -> None:
        main, ctx = bot
        ctx.slot_for("ORB").sm.force_halt("test")
        ctx.agg_5m = MagicMock(get_completed=MagicMock(return_value=[MagicMock()] * 20))
        ctx.agg_15m = MagicMock(get_completed=MagicMock(return_value=[MagicMock()] * 20))
        with (
            patch.object(main, "_refresh_intraday_regime"),
            patch.object(main, "market_open", return_value=True),
            patch.object(main, "atr_at", return_value=50.0),
            patch.object(main, "evaluate_all_signals", return_value=["CE_VWAP"]) as ev,
            patch.object(main, "execute_entry") as entry,
        ):
            main._make_candle_handler_5m(ctx)(_candle())
        ev.assert_not_called()
        entry.assert_not_called()


class TestEodAndRecovery:
    def test_eod_squares_off_every_open_slot(self, bot, monkeypatch) -> None:
        main, ctx = bot
        monkeypatch.setattr(main, "mark_trade_closed_with_reason", MagicMock())
        monkeypatch.setattr(main.EODManager, "run_eod_exit", MagicMock(return_value=True))
        a = _enter(main, ctx, "CE_ORB")
        b = _enter(main, ctx, "PE_VWAP")
        main._run_eod_exit(ctx)
        assert a.sm.state == State.IDLE and b.sm.state == State.IDLE
        assert main.EODManager.run_eod_exit.call_count == 2

    def test_restart_rebuilds_one_slot_per_open_trade(self, bot) -> None:
        main, ctx = bot
        _enter(main, ctx, "CE_ORB")
        _enter(main, ctx, "PE_VWAP")
        fresh = main.BotContext()
        main.recover_from_restart(fresh)
        assert set(fresh.slots) == {"ORB", "VWAP"}
        assert all(s.sm.state == State.POSITION_OPEN for s in fresh.slots.values())
        assert fresh.broker.get_position_qty(SYM) == 40
        assert fresh.overall_state() == State.POSITION_OPEN


class TestWebsocketToken:
    def test_shared_option_token_is_kept_until_last_slot_closes(self, bot, monkeypatch) -> None:
        main, ctx = bot
        monkeypatch.setattr(main, "mark_trade_closed_with_reason", MagicMock())
        a = _enter(main, ctx, "CE_ORB")
        b = _enter(main, ctx, "CE_VWAP")
        ctx.ws = MagicMock()
        main.execute_exit(a, reason="TARGET_HIT", exit_ltp=81100.0)
        ctx.ws.remove_token.assert_not_called()
        main.execute_exit(b, reason="TARGET_HIT", exit_ltp=81100.0)
        ctx.ws.remove_token.assert_called_once_with(11)


class TestPerStrategyCooldown:
    def test_loss_in_one_strategy_does_not_block_another(self) -> None:
        from strategies.smart_entry import SmartEntryFilter
        flt = SmartEntryFilter(cooldown_candles=3)
        flt.on_trade_closed(-50.0, strategy="ORB")
        assert flt.cooldown_remaining_for("ORB") == 3
        assert flt.cooldown_remaining_for("VWAP") == 0
        assert flt.cooldown_remaining_for("EMA") == 0


class TestEvaluateAllSignals:
    def test_returns_signals_from_several_strategies(self, monkeypatch) -> None:
        from strategies import signal_engine as se
        calls = []
        monkeypatch.setattr(se, "_evaluate_core",
                            lambda *a, collect=False, **k: calls.append(collect) or ["CE_ORB", "PE_VWAP"])
        assert se.evaluate_all_signals([], []) == ["CE_ORB", "PE_VWAP"]
        assert se.evaluate_signals([], []) == "CE_ORB"
        assert calls == [True, False]


class TestTradeStateFiles:
    def test_two_trades_share_one_state_file(self, tmp_path, monkeypatch) -> None:
        import execution.ema_trade_manager as etm
        monkeypatch.setattr(etm, "_IDX_STATE_FILE", tmp_path / "idx.json")
        mk = lambda: etm.IndexTradeManager("CE", 81000.0, 80900.0, 81220.0, 60.0, 300.0,  # noqa: E731
                                           delta=0.5, be_trigger_r=1.0, be_buffer_pts=12.0,
                                           trail_atr_mult=2.0, hard_sl_cushion=1.5)
        mk().save("T1")
        mk().save("T2")
        assert etm.IndexTradeManager.load("T1") is not None
        etm.IndexTradeManager.clear("T1")
        assert etm.IndexTradeManager.load("T1") is None
        assert etm.IndexTradeManager.load("T2") is not None   # untouched
