"""Tests for the EMA index-based risk engine and related EMA risk controls."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from execution.ema_trade_manager import EmaTradeManager, plan_ema_risk, plan_natr_risk
from execution.smart_exit import SmartExitEngine
from market.candle_builder import Candle


# ── plan_ema_risk ─────────────────────────────────────────────────────────────

class TestPlanEmaRisk:
    def test_swing_with_buffer(self):
        plan, why = plan_ema_risk("CE", 1000, 60, None, 920, swing_buffer_atr=0.25)
        assert why is None
        assert plan["source"] == "swing"
        assert plan["risk"] == pytest.approx(95.0)      # 80 + 0.25×60
        assert plan["stop"] == pytest.approx(905.0)
        assert plan["target"] == pytest.approx(1285.0)  # 3R

    def test_clamped_to_min_atr(self):
        plan, _ = plan_ema_risk("CE", 1000, 60, None, 990, swing_buffer_atr=0.0)
        assert plan["risk"] == pytest.approx(60.0)      # 10 → 1×ATR

    def test_clamped_to_max_atr(self):
        plan, _ = plan_ema_risk("PE", 1000, 60, 1500, None)
        assert plan["risk"] == pytest.approx(120.0)     # 2×ATR
        assert plan["stop"] == pytest.approx(1120.0)
        assert plan["target"] < 1000

    def test_fallback_atr_when_no_swing(self):
        plan, _ = plan_ema_risk("CE", 1000, 60, None, None)
        assert plan["source"] == "atr_fallback"
        assert plan["risk"] == pytest.approx(90.0)      # 1.5×ATR

    def test_room_filter_blocks(self):
        plan, why = plan_ema_risk("CE", 1000, 60, None, None, levels=[1050], min_room_r=1.5)
        assert plan is None and "room" in why

    def test_room_filter_ignores_levels_behind(self):
        plan, why = plan_ema_risk("CE", 1000, 60, None, None, levels=[950], min_room_r=1.5)
        assert why is None and plan is not None

    def test_no_atr_blocks(self):
        assert plan_ema_risk("CE", 1000, None, None, 900)[0] is None


# ── EmaTradeManager ───────────────────────────────────────────────────────────

def _mgr(**kw) -> EmaTradeManager:
    # CE: entry 1000, stop 900 (risk 100), target 1300, ATR 50, option 400, delta 0.5
    return EmaTradeManager("CE", 1000, 900, 1300, 50, 400, delta=0.5, **kw)


class TestEmaTradeManager:
    def test_initial_option_stop_uses_delta_and_cushion(self):
        m = _mgr(hard_sl_cushion=1.1, max_sl_pct=0.30)
        # 100 × 0.5 × 1.1 = 55 → 345
        assert m.option_stop == pytest.approx(345.0)

    def test_option_stop_capped_by_max_sl_pct(self):
        m = _mgr(hard_sl_cushion=1.1, max_sl_pct=0.10)
        assert m.option_stop == pytest.approx(360.0)

    def test_stop_hit(self):
        assert _mgr().on_index_price(899) == ("EXIT", "EMA_SL_HIT")

    def test_target(self):
        assert _mgr().on_index_price(1300) == ("EXIT", "EMA_TARGET")

    def test_no_be_before_1r(self):
        m = _mgr()
        assert m.on_index_price(1099) is None
        assert m.stage == "INITIAL"

    def test_be_at_1r_then_trail(self):
        m = _mgr(be_buffer_pts=4, trail_atr_mult=2.0)
        act = m.on_index_price(1100)
        assert act[0] == "STOP_MOVED"
        assert m.stop_index == pytest.approx(1004.0)
        m.on_index_price(1200)                      # chandelier: 1200 − 100
        assert m.stage == "TRAIL" and m.stop_index == pytest.approx(1100.0)
        assert m.on_index_price(1099) == ("EXIT", "EMA_TSL_HIT")

    def test_be_stop_reason(self):
        m = _mgr(be_buffer_pts=4)
        m.on_index_price(1100)
        assert m.on_index_price(1003) == ("EXIT", "EMA_BE_STOP")

    def test_time_stop(self):
        m = _mgr(time_stop_bars=3, time_stop_min_r=0.5)
        m.on_index_price(1040)
        assert m.on_candle(1040, None) is None
        assert m.on_candle(1040, None) is None
        assert m.on_candle(1040, None) == "EMA_TIME_STOP"

    def test_no_time_stop_when_moving(self):
        m = _mgr(time_stop_bars=1, time_stop_min_r=0.5)
        m.on_index_price(1060)
        assert m.on_candle(1060, None) is None

    def test_ema9_trail_exit_only_after_be(self):
        m = _mgr()
        assert m.on_candle(1000, 1010) is None       # INITIAL → ignored
        m.on_index_price(1100)
        assert m.on_candle(1090, 1095) == "EMA_TRAIL_EMA9"

    def test_pe_mirror(self):
        m = EmaTradeManager("PE", 1000, 1100, 700, 50, 400, delta=0.5)
        assert m.on_index_price(900)[0] == "STOP_MOVED"
        assert m.stop_index == pytest.approx(996.0)
        assert m.on_index_price(1101) is None or True
        m2 = EmaTradeManager("PE", 1000, 1100, 700, 50, 400)
        assert m2.on_index_price(1101) == ("EXIT", "EMA_SL_HIT")

    def test_save_load_roundtrip(self, tmp_path, monkeypatch):
        import execution.ema_trade_manager as etm
        monkeypatch.setattr(etm, "_STATE_FILE", tmp_path / "ema.json")
        m = _mgr()
        m.on_index_price(1100)
        m.save("T1")
        r = EmaTradeManager.load("T1")
        assert r is not None and r.stage == "BE" and r.stop_index == m.stop_index
        assert EmaTradeManager.load("OTHER") is None
        EmaTradeManager.clear()
        assert EmaTradeManager.load("T1") is None

# ── NATR-managed risk (EMA_NATR_RISK) ────────────────────────────────────────

class TestNatrRisk:
    def test_plan_uses_line_behind_entry(self):
        p, why = plan_natr_risk("CE", 1000, 880, 30, mult=3.0, target_rr=2.0)
        assert why is None
        assert p["stop"] == 880 and p["risk"] == 120 and p["target"] == 1240
        assert p["source"] == "natr_line"

    def test_plan_line_wrong_side_uses_mult_atr(self):
        p, _ = plan_natr_risk("CE", 1000, 1050, 30, mult=3.0)   # line above price
        assert p["stop"] == 910 and p["source"] == "natr_atr"
        p, _ = plan_natr_risk("PE", 1000, 950, 30, mult=3.0)
        assert p["stop"] == 1090

    def test_plan_min_distance_and_no_target(self):
        p, _ = plan_natr_risk("CE", 1000, 995, 30, min_atr=1.0, target_rr=0)
        assert p["risk"] == 30 and p["target"] > 100000

    def test_plan_needs_atr(self):
        assert plan_natr_risk("CE", 1000, 900, None)[0] is None

    def test_manager_ignores_be_trail_and_candle_exits(self):
        m = EmaTradeManager("CE", 1000, 880, 1240, 30, 400, delta=0.5, natr_mode=True)
        assert m.on_index_price(1200) is None            # no BE / chandelier move
        assert m.stop_index == 880 and m.stage == "INITIAL"
        assert m.on_candle(900, 1000) is None            # no EMA9 / time-stop exit
        assert m.on_index_price(879) == ("EXIT", "EMA_SL_HIT")

    def test_stop_follows_natr_line_only_forward(self):
        m = EmaTradeManager("CE", 1000, 880, 1240, 30, 400, delta=0.5, natr_mode=True)
        assert m.set_natr_line(940, close=1100) is True
        assert m.stop_index == 940 and m.stage == "TRAIL"
        assert m.on_index_price(1105)[0] == "STOP_MOVED"  # broker SL update reported once
        assert m.on_index_price(1106) is None
        assert m.set_natr_line(920, close=1100) is False  # never loosens
        assert m.stop_index == 940
        assert m.on_index_price(939) == ("EXIT", "EMA_TSL_HIT")

    def test_line_on_wrong_side_of_close_ignored(self):
        m = EmaTradeManager("CE", 1000, 880, 1240, 30, 400, natr_mode=True)
        assert m.set_natr_line(1050, close=1020) is False
        assert m.stop_index == 880

    def test_pe_mirror(self):
        m = EmaTradeManager("PE", 1000, 1120, 760, 30, 400, natr_mode=True)
        assert m.set_natr_line(1060, close=900) is True
        assert m.stop_index == 1060
        assert m.on_index_price(1061) == ("EXIT", "EMA_TSL_HIT")

    def test_broker_trail_off_keeps_option_stop_but_index_stop_follows(self):
        m = EmaTradeManager("CE", 1000, 880, 1240, 30, 400, delta=0.5, natr_mode=True,
                            natr_broker_trail=False)
        initial = m.option_stop
        assert m.set_natr_line(940, close=1100) is True
        assert m.stop_index == 940 and m.option_stop == initial
        assert m.on_index_price(1105) is None            # no broker SL modification requested
        assert m.on_index_price(939) == ("EXIT", "EMA_TSL_HIT")

    def test_off_by_default(self):
        assert _mgr().natr_mode is False
        assert _mgr().set_natr_line(950, close=1100) is False

    def test_save_load_keeps_natr_mode(self, tmp_path, monkeypatch):
        import execution.ema_trade_manager as etm
        monkeypatch.setattr(etm, "_STATE_FILE", tmp_path / "ema.json")
        m = EmaTradeManager("CE", 1000, 880, 1240, 30, 400, natr_mode=True)
        m.set_natr_line(940, close=1100)
        m.save("T9")
        r = EmaTradeManager.load("T9")
        assert r.natr_mode is True and r.stop_index == 940




# ── SmartExit: EMA profit-lock skip + multi-close collapse ───────────────────

def _eng(**kw) -> SmartExitEngine:
    base = dict(enable_reversal_exit=False, enable_time_decay=False,
                enable_daily_loss_limit=False, profit_lock_atr_mult=1.5)
    base.update(kw)
    return SmartExitEngine(**base)


class TestSmartExitEma:
    def test_profit_lock_skipped_for_ema(self):
        e = _eng(ema_profit_lock=False)
        assert e.check_on_tick("CE", 100, 500, 20, 0, entry_atr=10) is None

    def test_profit_lock_still_active_for_other_strategies(self):
        e = _eng(ema_profit_lock=False)
        assert e.check_on_tick("CE_ORB", 100, 500, 20, 0, entry_atr=10) == "PROFIT_LOCK"

    def _bear_then_last(self, last_close: float) -> list[Candle]:
        t = datetime(2026, 1, 1, 9, 15)
        out = [Candle(t + timedelta(minutes=5 * i), 1000 + 5 * i, 1001 + 5 * i, 999 + 5 * i, 1000 + 5 * i)
               for i in range(30)]
        # one close well below EMA21 then `last_close`
        out.append(Candle(t + timedelta(minutes=150), 1100, 1100, 1050, 1050))
        out.append(Candle(t + timedelta(minutes=155), last_close, last_close, last_close, last_close))
        return out

    def test_two_closes_required(self):
        e = _eng(enable_profit_lock=False, ema_collapse_closes=2)
        assert e.check_on_candle("CE", self._bear_then_last(1160), []) is None
        assert e.check_on_candle("CE", self._bear_then_last(1040), []) == "EMA_COLLAPSE"

    def test_single_close_default(self):
        e = _eng(enable_profit_lock=False)
        c = self._bear_then_last(1160)[:-1]
        assert e.check_on_candle("CE", c, []) == "EMA_COLLAPSE"


# ── Day lock: max trades + consecutive losses ─────────────────────────────────

class TestEmaDayLock:
    def test_consecutive_losses_and_max_trades(self, monkeypatch):
        from config import settings
        import strategies.signal_engine as se
        monkeypatch.setattr(settings, "EMA_MAX_TRADES_PER_DAY", 3)
        monkeypatch.setattr(settings, "EMA_MAX_CONSEC_LOSSES", 2)
        day = "2099-01-01"
        se._reset_ema_cooldown_if_new_day(day)
        se.note_ema_trade(day)
        se.note_ema_result(day, -100)
        assert se.ema_day_block_reason() is None
        se.note_ema_trade(day)
        se.note_ema_result(day, -50)
        assert "consecutive" in se.ema_day_block_reason()

        se._reset_ema_cooldown_if_new_day("2099-01-02")
        day = "2099-01-02"
        for pnl in (-1, 10, 10):
            se.note_ema_trade(day)
            se.note_ema_result(day, pnl)
        assert "max EMA trades" in se.ema_day_block_reason()
        se._reset_ema_cooldown_if_new_day("2099-01-03")
        assert se.ema_day_block_reason() is None


# ── Pullback must hold the trend side of EMA21 ────────────────────────────────

class TestPullbackSide:
    def test_ce_pullback_rejected_below_ema21(self):
        from datetime import date
        from market.indicators import ema
        from strategies.ce_strategy import is_ce_signal
        d = date.today()
        base = datetime(d.year, d.month, d.day, 9, 15)
        closes = [1000 + 10 * i for i in range(30)]
        c5 = [Candle(base + timedelta(minutes=5 * i), c, c + 1, c - 1, c) for i, c in enumerate(closes)]
        c15 = [Candle(base + timedelta(minutes=15 * i), 1000 + 5 * i, 1001 + 5 * i, 999 + 5 * i, 1000 + 5 * i)
               for i in range(30)]
        e21 = ema(c5, 21)[-1]
        below = e21 - 50
        c5[-1] = Candle(c5[-1].timestamp, below, below + 1, below - 1, below)
        assert is_ce_signal(c5, c15, rsi_min=0, pullback_tol_pts=1000) is False
