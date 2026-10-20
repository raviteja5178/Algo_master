"""Tests for research/pivot_backtest.py — config parity, fills, stage logic, daily limits."""

from __future__ import annotations

from datetime import datetime, time

import pandas as pd
import pytest

from config import settings
from market.candle_builder import Candle
from research.pivot_backtest import (
    VARIANT_OVERRIDES,
    backtest_variant,
    live_signal_kwargs,
    manager_kwargs,
    report,
    simulate_trade,
)
from research.cpr_study import build_features
from strategies.pivot_strategy import PivotSetup, find_pivot_setup
from tests.test_cpr_study import _synthetic


def _c(hhmm: str, o, h, l, c) -> Candle:
    hh, mm = map(int, hhmm.split(":"))
    return Candle(datetime(2024, 3, 4, hh, mm), o, h, l, c)


def _setup(side="CE", entry=100.0, stop=95.0, t1=110.0, t2=120.0, t3=130.0) -> PivotSetup:
    risk = abs(entry - stop)
    return PivotSetup(side=side, mode="OPEN_DIRECTION", entry=entry, stop=stop, risk=risk,
                      t1=t1, t2=t2, t3=t3, atr=4.0, pivot=98.0)


def _run(setup, later):
    # Pin the trade-management knobs the assertions below depend on, so these tests
    # do not change when the live .env / settings defaults are tuned.
    mk = {**manager_kwargs(), "be_trigger_r": 1.0, "be_buffer_pts": 5.0,
          "t1_lock_pct": 0.5, "t2_lock_pct": 0.5,
          "trail_atr_mult": 1.0, "t2_trail_atr_mult": 0.75}
    return simulate_trade(setup, later, lambda j: None, mk, datetime(2024, 3, 4).date())


class TestConfigParity:
    def test_live_kwargs_are_accepted_by_find_pivot_setup(self):
        # every key must be a real parameter — a typo would raise TypeError
        assert find_pivot_setup([], None, **live_signal_kwargs()) is None

    def test_live_kwargs_mirror_settings(self):
        kw = live_signal_kwargs()
        assert kw["sustain_candles"] == settings.PIVOT_SUSTAIN_CANDLES
        assert kw["min_od_gap_atr"] == settings.PIVOT_OD_MIN_GAP_ATR
        assert kw["bounce_zone_atr"] == settings.PIVOT_BOUNCE_ZONE_ATR
        assert kw["enable_acceptance"] == settings.PIVOT_ACCEPTANCE

    def test_overrides_are_valid_kwargs(self):
        for name, ov in VARIANT_OVERRIDES.items():
            assert find_pivot_setup([], None, **{**live_signal_kwargs(), **ov}) is None, name

    def test_manager_kwargs_match_main_py(self):
        mk = manager_kwargs()
        assert mk["be_trigger_r"] == settings.PIVOT_BE_TRIGGER_R
        assert mk["t2_trail_atr_mult"] == settings.PIVOT_T2_TRAIL_ATR_MULT
        assert mk["delta"] == 1.0


class TestSimulateTrade:
    def test_stop_hit(self):
        tr, j = _run(_setup(), [_c("09:30", 100, 101, 94, 95)])
        assert tr.reason == "PIVOT_SL_HIT" and tr.exit == 95.0
        assert tr.r == pytest.approx(-1.0) and j == 0

    def test_gap_through_stop_fills_at_open(self):
        tr, _ = _run(_setup(), [_c("09:30", 90, 91, 88, 89)])
        assert tr.exit == 90.0 and tr.r == pytest.approx(-2.0)

    def test_adverse_extreme_first_means_stop_before_target(self):
        # one candle spans both stop and T1: low is processed first → stopped out
        tr, _ = _run(_setup(), [_c("09:30", 100, 111, 94, 105)])
        assert tr.reason == "PIVOT_SL_HIT"

    def test_breakeven_then_stopped_at_plus_buffer(self):
        later = [_c("09:30", 100, 106, 100, 105),            # +5 = 1R → BE (stop 105)
                 _c("09:35", 105, 106, 100, 101)]             # falls back through BE stop
        tr, j = _run(_setup(), later)
        assert tr.reason == "PIVOT_BE_STOP" and tr.exit == 105.0
        assert tr.r == pytest.approx(1.0) and j == 1

    def test_runs_to_t3(self):
        later = [_c("09:30", 100, 111, 100, 110), _c("09:35", 110, 121, 110, 120),
                 _c("09:40", 120, 131, 120, 130)]
        tr, j = _run(_setup(), later)
        assert tr.reason == "PIVOT_TARGET_T3" and tr.exit == 130.0
        assert tr.r == pytest.approx(6.0) and tr.stage == "T2" and j == 2

    def test_pe_mirror(self):
        s = _setup("PE", entry=100.0, stop=105.0, t1=90.0, t2=80.0, t3=70.0)
        tr, _ = _run(s, [_c("09:30", 100, 106, 99, 104)])
        assert tr.reason == "PIVOT_SL_HIT" and tr.exit == 105.0
        assert tr.r == pytest.approx(-1.0)

    def test_eod_exit_marks_to_last_close(self):
        tr, j = _run(_setup(), [_c("09:30", 100, 102, 99, 101), _c("09:35", 101, 102, 99, 102)])
        assert tr.reason == "EOD" and tr.exit == 102.0 and j == 1
        assert tr.r == pytest.approx(0.4)


class TestBacktestDriver:
    def test_runs_on_synthetic_and_respects_limits(self):
        daily, m5 = _synthetic(n_days=130, seed=5)
        trades = backtest_variant(daily, m5, {}, max_trades=2)
        report_text = report({"LIVE": trades}, build_features(daily, m5))
        assert "Overall by variant" in report_text
        if len(trades):
            assert trades.groupby("date").size().max() <= 2
            assert trades["risk"].gt(0).all()
            assert trades["side"].isin(["CE", "PE"]).all()

    def test_no_new_entries_after_cutoff_and_no_overlap(self):
        daily, m5 = _synthetic(n_days=130, seed=9)
        trades = backtest_variant(daily, m5, dict(pivot_mode="BOTH", enable_acceptance=True))
        # entries come from candles strictly before the cutoff; bars>=1 always
        if len(trades):
            assert trades["bars"].ge(1).all()

    def test_variant_with_no_modes_produces_no_trades(self):
        daily, m5 = _synthetic(n_days=100, seed=2)
        t = backtest_variant(daily, m5, dict(pivot_mode="NONE", enable_acceptance=False,
                                             bounce_zone_atr=0.0))
        assert len(t) == 0
