"""
Regression tests for bugs found in the Oct 2026 strategy review:

1. Target ratchet: DynamicTargetManager raised the target by a full trail step
   on every trailing-stop update, so it ran away from price and TARGET_HIT
   could never fire (0 target exits in 43 trades).
2. BE_TRIGGER_RR was in .env but never read — break-even was hard-coded at
   0.5R in atr_risk.compute_risk_params.
3. TrailingStopManager hard-coded delta 0.4 while the SL was sized with
   settings.ATM_DELTA (0.5), so trail and SL described different distances.
4. Restart recovery rebuilt the trailing stop from global fixed points instead
   of the trade's stored sl/be/tsl/target snapshot, and lost break-even state.
5. VWAP strategy documented "VWAP rising (or flat)" but never checked it.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from execution.atr_risk import compute_risk_params
from execution.target_manager import DynamicTargetManager
from execution.trailing_stop import TrailingStopManager
from market.candle_builder import Candle
from strategies.vwap_strategy import is_vwap_ce_signal, is_vwap_pe_signal, vwap_slope_ok

_TODAY = date.today()


def _c(i: int, o: float, h: float, lo: float, c: float) -> Candle:
    ts = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9 + (15 + 5 * i) // 60, (15 + 5 * i) % 60)
    return Candle(ts, open=o, high=h, low=lo, close=c, volume=0)


# ── 1. Target ratchet ─────────────────────────────────────────────────────────

class TestTargetRatchet:
    def test_target_stays_fixed_by_default(self) -> None:
        tgt = DynamicTargetManager(400.0, 120.0, 30.0)
        for steps in range(1, 40):           # ATR mode: one "step" per stop update
            tgt.sync_trail_steps(steps)
        assert tgt.target_reference == pytest.approx(520.0)
        assert tgt.is_target_hit(520.0)

    def test_ratchet_is_opt_in(self) -> None:
        tgt = DynamicTargetManager(400.0, 120.0, 30.0, ratchet_with_stop=True)
        tgt.sync_trail_steps(3)
        assert tgt.target_reference == pytest.approx(610.0)

    def test_target_reachable_through_a_real_trailing_run(self) -> None:
        """Price climbing steadily to entry + target must trigger the target."""
        trail = TrailingStopManager(400.0, 100.0, 50.0, 30.0)
        tgt = DynamicTargetManager(400.0, 220.0, 30.0)
        hit = False
        for ltp in range(400, 640, 5):
            trail.update(float(ltp))
            tgt.sync_trail_steps(trail.trail_steps_completed)
            if tgt.is_target_hit(float(ltp)):
                hit = True
                break
        assert hit and trail.trail_steps_completed > 0


# ── 2. BE_TRIGGER_RR ──────────────────────────────────────────────────────────

class TestBreakEvenTrigger:
    def test_default_stays_half_r(self) -> None:
        p = compute_risk_params([], fixed_sl=40.0, fixed_target=80.0, fixed_trail=10.0)
        assert p.break_even_trigger_points == pytest.approx(20.0)

    def test_be_trigger_rr_scales_break_even(self) -> None:
        p = compute_risk_params([], fixed_sl=40.0, fixed_target=80.0, fixed_trail=10.0,
                                be_trigger_rr=1.4)
        assert p.break_even_trigger_points == pytest.approx(56.0)

    def test_setting_exists_and_is_read_from_env(self, monkeypatch) -> None:
        import importlib
        import config.settings as st
        # settings re-reads .env with override=True on reload — keep the real
        # .env out of this test so only the variable set here is seen.
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
        monkeypatch.setenv("BE_TRIGGER_RR", "1.4")
        try:
            assert importlib.reload(st).BE_TRIGGER_RR == pytest.approx(1.4)
        finally:
            monkeypatch.delenv("BE_TRIGGER_RR")
            importlib.reload(st)


# ── 3. Trailing-stop delta ────────────────────────────────────────────────────

class TestTrailingDelta:
    def test_atr_trail_uses_configured_delta(self) -> None:
        trail = TrailingStopManager(500.0, 100.0, 50.0, 30.0,
                                    tsl_atr_trail_mult=1.0, atm_delta=0.5)
        with patch("market.indicators.atr_at", return_value=100.0):
            trail.update(560.0, candles_5m=[MagicMock()])          # BE fires
            new_stop = trail.update(700.0, candles_5m=[MagicMock()])
        assert new_stop == pytest.approx(650.0)                     # 700 − 100×1×0.5

    def test_default_delta_unchanged(self) -> None:
        assert TrailingStopManager(500.0).atm_delta == pytest.approx(0.4)


# ── 4. Restart recovery uses the trade's own risk snapshot ────────────────────

def _active(**extra) -> dict:
    row = {
        "trade_id": "TRADE_CE_VWAP_T", "strategy_type": "CE_VWAP",
        "option_symbol": "SENSEX26O2274000CE", "instrument_token": 1, "quantity": 20,
        "entry_price": 400.0, "stop_order_id": "PAPER_SL_X", "current_stop": 405.0,
        "highest_ltp": 470.0, "target_reference": 9999.0,     # ratcheted by old code
    }
    row.update(extra)
    return row


def _recover(active: dict):
    from execution.paper_broker import PaperBroker
    from execution.position_manager import StateMachine
    from risk.safety_manager import SafetyManager
    from main import recover_from_restart
    ctx = MagicMock()
    ctx.broker = PaperBroker()
    ctx.sm = StateMachine()
    ctx.safety = SafetyManager(ctx.sm)
    ctx.pivot_mgr = None                 # a fresh BotContext has no trade engine
    with (
        patch("main.settings.TRADING_MODE", "SHADOW"),
        patch("main.settings.TARGET_TRAIL_WITH_STOP", False),
        patch("main.settings.ATM_DELTA", 0.5),
        patch("main.fetch_active_trade", return_value=active),
        patch("main.mark_trade_closed"),
        patch("main.upsert_trade"),
    ):
        recover_from_restart(ctx)
    return ctx


class TestRestartRecoverySnapshot:
    def test_uses_stored_risk_points(self) -> None:
        ctx = _recover(_active(sl_points=90.0, be_points=126.0, tsl_points=27.0,
                               target_points=198.0))
        assert ctx.trailing.initial_sl_points == 90.0
        assert ctx.trailing.break_even_trigger_points == 126.0
        assert ctx.trailing.trail_step_points == 27.0
        assert ctx.trailing.atm_delta == 0.5
        assert ctx.target.target_reference == pytest.approx(598.0)   # not the stale 9999

    def test_break_even_state_restored(self) -> None:
        ctx = _recover(_active(sl_points=90.0, be_points=126.0, tsl_points=27.0,
                               target_points=198.0))
        assert ctx.trailing.break_even_activated is True              # stop 405 ≥ entry 400

    def test_index_managed_trade_restores_its_engine(self, monkeypatch, tmp_path) -> None:
        import execution.ema_trade_manager as etm
        monkeypatch.setattr(etm, "_IDX_STATE_FILE", tmp_path / "idx.json")
        etm.IndexTradeManager("CE", 74000.0, 73900.0, 74220.0, 60.0, 400.0,
                              delta=0.5).save("TRADE_CE_VWAP_T")
        ctx = _recover(_active(sl_points=90.0, be_points=126.0, tsl_points=27.0, target_points=198.0))
        assert isinstance(ctx.pivot_mgr, etm.IndexTradeManager)
        assert ctx.pivot_mgr.stop_index == 73900.0

    def test_old_rows_without_snapshot_fall_back(self) -> None:
        ctx = _recover(_active(current_stop=350.0))
        assert ctx.trailing.break_even_activated is False
        assert ctx.target.target_reference == pytest.approx(9999.0)


# ── 6. EMA pullback needs a real bounce / rejection candle ────────────────────

def _pullback_series(sign: int, *, bounce_against: bool = False) -> list[Candle]:
    """Trend (sign=+1 up / −1 down), one candle back to EMA21 tagging it,
    then a candle turning away from EMA21 — or, with bounce_against=True,
    one that keeps going (CE: red, PE: green)."""
    from datetime import timedelta
    from market.indicators import ema
    base = [_c(i, 1000 + sign * 10 * i, 1001 + sign * 10 * i, 999 + sign * 10 * i, 1000 + sign * 10 * i)
            for i in range(27)]
    # _c packs 27 candles into one morning; re-time them 5 min apart
    t0 = base[0].timestamp
    base = [Candle(t0 + timedelta(minutes=5 * i), open=c.open, high=c.high, low=c.low, close=c.close, volume=0)
            for i, c in enumerate(base)]
    e21 = ema(base, 21)[-1]
    t = t0 + timedelta(minutes=5 * 27)
    prev_close, dclose = base[-1].close, e21 + sign * 4
    hi, lo = max(prev_close, dclose) + 1, min(prev_close, dclose) - 1
    dip = Candle(t, open=prev_close, high=hi if sign > 0 else e21 + 8,
                 low=e21 - 8 if sign > 0 else lo, close=dclose, volume=0)
    c5 = base + [dip]
    bclose = ema(c5, 21)[-1] + sign * 7
    bopen = dclose if not bounce_against else bclose + sign * 3
    c5.append(Candle(t + timedelta(minutes=5), open=bopen, high=max(bopen, bclose) + 1,
                     low=min(bopen, bclose) - 1, close=bclose, volume=0))
    return c5


def _trend_15m(sign: int) -> list[Candle]:
    from datetime import timedelta
    t0 = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15)
    return [Candle(t0 + timedelta(minutes=15 * i), open=1000 + sign * 5 * i, high=1001 + sign * 5 * i,
                   low=999 + sign * 5 * i, close=1000 + sign * 5 * i, volume=0) for i in range(30)]


class TestEmaPullbackConfirmation:
    def test_ce_bounce_off_ema21_fires(self) -> None:
        from strategies.ce_strategy import is_ce_signal
        c5 = _pullback_series(+1)
        assert c5[-1].close > c5[-1].open and c5[-1].close > c5[-2].close
        assert is_ce_signal(c5, _trend_15m(+1)) is True

    def test_ce_red_candle_at_ema21_does_not_fire(self) -> None:
        from strategies.ce_strategy import is_ce_signal
        c5 = _pullback_series(+1, bounce_against=True)
        assert c5[-1].close < c5[-1].open
        assert is_ce_signal(c5, _trend_15m(+1)) is False

    def test_ce_needs_trend_before_the_dip(self) -> None:
        import strategies.ce_strategy as ce
        with patch.object(ce, "PULLBACK_TREND_LOOKBACK", 0):    # no candles searched
            assert ce.is_ce_signal(_pullback_series(+1), _trend_15m(+1)) is False

    def test_pe_rejection_at_ema21_fires(self) -> None:
        from strategies.pe_strategy import is_pe_signal
        c5 = _pullback_series(-1)
        assert c5[-1].close < c5[-1].open and c5[-1].close < c5[-2].close
        assert is_pe_signal(c5, _trend_15m(-1)) is True

    def test_pe_green_candle_at_ema21_does_not_fire(self) -> None:
        from strategies.pe_strategy import is_pe_signal
        c5 = _pullback_series(-1, bounce_against=True)
        assert c5[-1].close > c5[-1].open
        assert is_pe_signal(c5, _trend_15m(-1)) is False

    def test_pe_needs_trend_before_the_bounce(self) -> None:
        import strategies.pe_strategy as pe
        with patch.object(pe, "PULLBACK_TREND_LOOKBACK", 0):
            assert pe.is_pe_signal(_pullback_series(-1), _trend_15m(-1)) is False


# ── 7. TRB: first breakout per side per day + window end ─────────────────────

def _trb_15m() -> list[Candle]:
    t = lambda h, m: datetime(_TODAY.year, _TODAY.month, _TODAY.day, h, m)  # noqa: E731
    return [Candle(t(9, 15), open=74700, high=74750, low=74650, close=74700, volume=0),
            Candle(t(9, 30), open=74700, high=74800, low=74650, close=74750, volume=0),
            Candle(t(9, 45), open=74750, high=75000, low=74800, close=74900, volume=0)]


def _trb_5m(closes: list[tuple[int, int, float]]) -> list[Candle]:
    return [Candle(datetime(_TODAY.year, _TODAY.month, _TODAY.day, h, m),
                   open=c - 5, high=c + 10, low=c - 10, close=c, volume=0) for h, m, c in closes]


class TestTrbFirstBreakout:
    def test_first_breakout_fires(self) -> None:
        from strategies.trb_strategy import is_trb_ce_signal
        c5 = _trb_5m([(10, 0, 74950), (10, 5, 74980), (10, 10, 75040)])
        assert is_trb_ce_signal(c5, _trb_15m()) is True

    def test_re_cross_after_failed_breakout_is_ignored(self) -> None:
        from strategies.trb_strategy import is_trb_ce_signal
        # 10:05 broke out, 10:10 fell back inside, 10:15 re-crosses — whipsaw.
        c5 = _trb_5m([(10, 0, 74950), (10, 5, 75030), (10, 10, 74960), (10, 15, 75040)])
        assert is_trb_ce_signal(c5, _trb_15m()) is False
        assert is_trb_ce_signal(c5, _trb_15m(), first_breakout_only=False) is True

    def test_pe_re_cross_is_ignored(self) -> None:
        from strategies.trb_strategy import is_trb_pe_signal
        c5 = _trb_5m([(10, 0, 74850), (10, 5, 74770), (10, 10, 74840), (10, 15, 74760)])
        assert is_trb_pe_signal(c5, _trb_15m()) is False

    def test_window_end_blocks_late_breakout(self) -> None:
        from datetime import time as dtime
        from strategies.trb_strategy import is_trb_ce_signal
        c5 = _trb_5m([(11, 25, 74950), (11, 30, 75040)])
        assert is_trb_ce_signal(c5, _trb_15m(), window_end=dtime(11, 30)) is False
        assert is_trb_ce_signal(c5, _trb_15m(), window_end=dtime(11, 35)) is True

    def test_engine_passes_trb_settings(self) -> None:
        import inspect
        from strategies import signal_engine
        src = inspect.getsource(signal_engine)
        assert "first_breakout_only=settings.TRB_FIRST_BREAKOUT_ONLY" in src
        assert "settings.TRB_WINDOW_END" in src


# ── 8. VWAP entry cut-off ─────────────────────────────────────────────────────

class TestVwapEntryCutoff:
    def _run(self, cutoff: str):
        from strategies.signal_engine import evaluate_signals
        # A valid CE_VWAP setup (3 closes below VWAP 73600, then a reclaim) at 12:00–12:15.
        t = lambda m: datetime(_TODAY.year, _TODAY.month, _TODAY.day, 12, m)  # noqa: E731
        c5 = [Candle(t(0), open=73580, high=73590, low=73570, close=73580, volume=100),
              Candle(t(5), open=73580, high=73595, low=73575, close=73590, volume=100),
              Candle(t(10), open=73590, high=73600, low=73580, close=73595, volume=100),
              Candle(t(15), open=73600, high=73660, low=73598, close=73650, volume=100)]
        c15 = [Candle(t(0), open=73580, high=73660, low=73570, close=73650, volume=100)]
        with patch("strategies.signal_engine.settings") as ms, \
             patch("strategies.signal_engine.has_processed_signal", return_value=False), \
             patch("strategies.signal_engine.claim_signal_atomic", return_value=True), \
             patch("strategies.signal_engine.record_processed_signal"):
            for k in ("ENABLE_OB_STRATEGY", "ENABLE_ORB_STRATEGY", "ENABLE_PIVOT_STRATEGY",
                      "ENABLE_PDHL_STRATEGY", "ENABLE_NATR_STRATEGY", "ENABLE_ATR_COPILOT_STRATEGY",
                      "ENABLE_TRB_STRATEGY", "ENABLE_EMA_STRATEGY", "ENABLE_MOMENTUM_PHASE",
                      "ENABLE_VWAP_LEVEL_FILTER", "ORB_SESSION_QUALIFIER"):
                setattr(ms, k, False)
            ms.ENABLE_VWAP_STRATEGY = ms.ENABLE_CE_VWAP = ms.ENABLE_PE_VWAP = True
            ms.MAX_TRADES_PER_SIDE = 0
            ms.VWAP_RETEST_LOOKBACK, ms.VWAP_MIN_BOUNCE_PTS = 3, 0.0
            ms.VWAP_MAX_SUBMERGED_CANDLES, ms.VWAP_SLOPE_LOOKBACK = 3, 0
            ms.VWAP_NO_NEW_ENTRY_AFTER = cutoff
            return evaluate_signals(c5, c15, vwap=73600.0)

    def test_signal_before_cutoff_or_without_cutoff(self) -> None:
        assert self._run("") == "CE_VWAP"
        assert self._run("13:30") == "CE_VWAP"

    def test_signal_after_cutoff_is_skipped(self) -> None:
        assert self._run("12:00") is None


# ── 10. Higher-timeframe trend gate ───────────────────────────────────────────

def _c15(direction: int, n: int = 30) -> list[Candle]:
    from datetime import timedelta
    t0 = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15) - timedelta(days=1)
    return [Candle(t0 + timedelta(minutes=15 * i), open=73000 + direction * 20 * i,
                   high=73010 + direction * 20 * i, low=72990 + direction * 20 * i,
                   close=73000 + direction * 20 * i, volume=0) for i in range(n)]


class TestTrendGateHelpers:
    def test_15m_trend(self) -> None:
        from strategies.trend_gate import trend_15m_ok
        assert trend_15m_ok("CE", _c15(+1)) and not trend_15m_ok("PE", _c15(+1))
        assert trend_15m_ok("PE", _c15(-1)) and not trend_15m_ok("CE", _c15(-1))

    def test_15m_fails_open_without_history(self) -> None:
        from strategies.trend_gate import trend_15m_ok
        assert trend_15m_ok("CE", _c15(-1, n=10)) and trend_15m_ok("PE", [])

    def test_daily_trend(self) -> None:
        from strategies.trend_gate import daily_trend_from_closes, daily_trend_ok
        assert daily_trend_from_closes([70000 + 100 * i for i in range(30)]) == "UP"
        assert daily_trend_from_closes([80000 - 100 * i for i in range(30)]) == "DOWN"
        assert daily_trend_from_closes([70000.0] * 5) == "UNKNOWN"
        assert daily_trend_ok("CE", "UP") and not daily_trend_ok("PE", "UP")
        assert daily_trend_ok("PE", "UNKNOWN") and daily_trend_ok("CE", None)

    def test_strategy_keys_and_pivot_never_gated_by_default(self) -> None:
        from config import settings
        from strategies.trend_gate import strategy_key
        assert [strategy_key(s) for s in ("CE", "PE_VWAP", "CE_PIVOT", "PE_TRB")] == ["EMA", "VWAP", "PIVOT", "TRB"]
        assert "PIVOT" not in settings.TREND_GATE_STRATEGIES


class TestTrendGateInEngine:
    def _run(self, c15, *, gate_15m=False, gate_daily=False, daily_trend=None):
        from strategies.signal_engine import evaluate_signals
        t = lambda m: datetime(_TODAY.year, _TODAY.month, _TODAY.day, 10, m)  # noqa: E731
        c5 = [Candle(t(0), open=73580, high=73590, low=73570, close=73580, volume=100),
              Candle(t(5), open=73580, high=73595, low=73575, close=73590, volume=100),
              Candle(t(10), open=73590, high=73600, low=73580, close=73595, volume=100),
              Candle(t(15), open=73600, high=73660, low=73598, close=73650, volume=100)]
        with patch("strategies.signal_engine.settings") as ms, \
             patch("strategies.signal_engine.has_processed_signal", return_value=False), \
             patch("strategies.signal_engine.claim_signal_atomic", return_value=True), \
             patch("strategies.signal_engine.record_processed_signal"):
            for k in ("ENABLE_OB_STRATEGY", "ENABLE_ORB_STRATEGY", "ENABLE_PIVOT_STRATEGY",
                      "ENABLE_PDHL_STRATEGY", "ENABLE_NATR_STRATEGY", "ENABLE_ATR_COPILOT_STRATEGY",
                      "ENABLE_TRB_STRATEGY", "ENABLE_EMA_STRATEGY", "ENABLE_MOMENTUM_PHASE",
                      "ENABLE_VWAP_LEVEL_FILTER", "ORB_SESSION_QUALIFIER", "ENABLE_PE_VWAP"):
                setattr(ms, k, False)
            ms.ENABLE_VWAP_STRATEGY = ms.ENABLE_CE_VWAP = True
            ms.MAX_TRADES_PER_SIDE = 0
            ms.VWAP_RETEST_LOOKBACK, ms.VWAP_MIN_BOUNCE_PTS = 3, 0.0
            ms.VWAP_MAX_SUBMERGED_CANDLES, ms.VWAP_SLOPE_LOOKBACK = 3, 0
            ms.VWAP_NO_NEW_ENTRY_AFTER = ""
            ms.TREND_GATE_15M, ms.TREND_GATE_DAILY = gate_15m, gate_daily
            ms.TREND_GATE_STRATEGIES = frozenset({"EMA", "VWAP", "TRB", "NATR"})
            return evaluate_signals(c5, c15, vwap=73600.0, daily_trend=daily_trend)

    def test_gate_off_keeps_old_behaviour(self) -> None:
        assert self._run(_c15(-1)) == "CE_VWAP"

    def test_ce_against_15m_downtrend_is_blocked(self) -> None:
        assert self._run(_c15(-1), gate_15m=True) is None
        assert self._run(_c15(+1), gate_15m=True) == "CE_VWAP"

    def test_ce_against_daily_downtrend_is_blocked(self) -> None:
        assert self._run(_c15(+1), gate_daily=True, daily_trend="DOWN") is None
        assert self._run(_c15(+1), gate_daily=True, daily_trend="UP") == "CE_VWAP"
        assert self._run(_c15(+1), gate_daily=True, daily_trend="UNKNOWN") == "CE_VWAP"


# ── 9. Strategy date guards use the IST trading date ─────────────────────────

class TestTodayIst:
    def test_strategies_use_today_ist_not_pc_date(self) -> None:
        import importlib
        import inspect
        for name in ("atr_copilot_strategy", "ce_strategy", "natr_strategy", "ob_strategy",
                     "orb_strategy", "pdhl_strategy", "pe_strategy", "smart_entry",
                     "trb_strategy", "vwap_strategy", "signal_engine"):
            src = inspect.getsource(importlib.import_module(f"strategies.{name}"))
            assert "date.today()" not in src, name
            assert "today_ist()" in src, name

    def test_guard_follows_ist_clock(self) -> None:
        from strategies.ce_strategy import is_ce_signal
        c5 = _pullback_series(+1)
        with patch("strategies.ce_strategy.today_ist", return_value=date(2000, 1, 1)):
            assert is_ce_signal(c5, _trend_15m(+1)) is False     # candles are not "today"
        assert is_ce_signal(c5, _trend_15m(+1)) is True


# ── 5. VWAP slope guard ───────────────────────────────────────────────────────

def _falling_day_then_ce_reclaim() -> list[Candle]:
    """Day drifts down (VWAP falling), dips below 73600, then reclaims above it."""
    cs = [_c(i, 74000 - 50 * i, 74010 - 50 * i, 73940 - 50 * i, 73950 - 50 * i) for i in range(8)]
    cs.append(_c(8, 73600, 73605, 73580, 73590))          # retest: closed below VWAP
    cs.append(_c(9, 73595, 73660, 73590, 73650))          # reclaim, close > prev high
    return cs


def _rising_day_then_pe_break() -> list[Candle]:
    cs = [_c(i, 73200 + 50 * i, 73260 + 50 * i, 73190 + 50 * i, 73250 + 50 * i) for i in range(8)]
    cs.append(_c(8, 73600, 73620, 73595, 73610))          # pop above VWAP
    cs.append(_c(9, 73605, 73608, 73540, 73550))          # break below, close < prev low
    return cs


class TestVwapSlope:
    def test_ce_blocked_when_vwap_falling(self) -> None:
        cs = _falling_day_then_ce_reclaim()
        assert is_vwap_ce_signal(cs, 73600.0, slope_lookback=0) is True     # old behaviour
        assert is_vwap_ce_signal(cs, 73600.0, slope_lookback=3) is False

    def test_pe_blocked_when_vwap_rising(self) -> None:
        cs = _rising_day_then_pe_break()
        assert is_vwap_pe_signal(cs, 73600.0, slope_lookback=0) is True
        assert is_vwap_pe_signal(cs, 73600.0, slope_lookback=3) is False

    def test_with_trend_signals_pass(self) -> None:
        assert vwap_slope_ok(_rising_day_then_pe_break(), "CE", 3) is True
        assert vwap_slope_ok(_falling_day_then_ce_reclaim(), "PE", 3) is True

    def test_too_few_candles_does_not_block(self) -> None:
        assert vwap_slope_ok(_falling_day_then_ce_reclaim()[:3], "CE", 3) is True

    def test_engine_passes_configured_lookback(self) -> None:
        import inspect
        from strategies import signal_engine
        assert "slope_lookback=settings.VWAP_SLOPE_LOOKBACK" in inspect.getsource(signal_engine)
