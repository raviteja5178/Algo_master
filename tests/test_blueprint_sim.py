"""Tests for research/blueprint_sim.py — signal rule, target pick, fills, pipeline."""

from __future__ import annotations

from datetime import datetime, time

import pandas as pd
import pytest

from market.historical_data import compute_pivot_levels
from research.blueprint_sim import (
    DEFAULT_EMA,
    VARIANTS,
    blueprint_signal,
    fib_levels,
    filter_levels,
    pick_target,
    report,
    run_simulation,
    simulate_day,
)
from research.cpr_study import build_features
from tests.test_cpr_study import _synthetic

LV = {"P": 95.0, "BC": 94.0, "TC": 96.0,
      "R1": 106.0, "R2": 120.0, "R3": 140.0,
      "S1": 80.0, "S2": 70.0, "S3": 50.0}


def _row(hhmm: str, o, h, l, c, ema=100.0):
    hh, mm = map(int, hhmm.split(":"))
    return {"timestamp": datetime(2024, 3, 4, hh, mm), "open": o, "high": h,
            "low": l, "close": c, "ema": ema}


class TestDefaults:
    def test_default_ema_is_21(self):
        assert DEFAULT_EMA == 21


class TestFibLevels:
    def test_matches_live_formula(self):
        live = compute_pivot_levels(110.0, 90.0, 105.0, formula="FIBONACCI")
        mine = fib_levels(110.0, 90.0, 105.0)
        for k in ("r1", "r2", "r3", "s1", "s2", "s3"):
            assert mine[k.upper()] == pytest.approx(getattr(live, k), abs=0.01)
        assert mine["P"] == pytest.approx(live.pivot, abs=0.01)


class TestSignal:
    def test_long_cross(self):
        assert blueprint_signal(99, 100, 99, 102, 100, None, None) == "CE"

    def test_no_signal_without_cross(self):
        # already above EMA on the previous candle → not a fresh cross
        assert blueprint_signal(101, 100, 101, 103, 100, None, None) is None

    def test_red_candle_cannot_be_long(self):
        assert blueprint_signal(99, 100, 103, 102, 100, None, None) is None

    def test_short_cross(self):
        assert blueprint_signal(101, 100, 101, 98, 100, None, None) == "PE"

    def test_pivot_filter_blocks(self):
        assert blueprint_signal(99, 100, 99, 102, 100, 103.0, None) is None
        assert blueprint_signal(101, 100, 101, 98, 100, None, 97.0) is None

    def test_filter_levels(self):
        assert filter_levels("NONE", LV) == (None, None)
        assert filter_levels("LINE", LV) == (95.0, 95.0)
        assert filter_levels("BAND", LV) == (96.0, 94.0)


class TestTargetPick:
    def test_nearest_level_with_enough_room(self):
        assert pick_target("CE", 102.0, 4.0, LV, 1.0) == 106.0      # room 4 >= 4
        assert pick_target("CE", 102.0, 5.0, LV, 1.0) == 120.0      # R1 too close
        assert pick_target("PE", 85.0, 4.0, LV, 1.0) == 80.0

    def test_none_when_no_level(self):
        assert pick_target("CE", 139.0, 5.0, LV, 1.0) is None


class TestSimulate:
    def _base(self, third):
        return [
            _row("09:15", 100, 100, 98, 99),                 # below EMA
            _row("09:20", 99, 102.5, 98, 102),               # green cross, low 98 → risk 4
            third,
        ]

    def test_target_hit(self):
        rows = self._base(_row("09:25", 102, 107, 101, 106))
        tr = simulate_day(rows + [_row("09:30", 106, 107, 105, 106)], LV, "NONE", "CANDLE")
        assert len(tr) == 1
        assert tr[0].reason == "TARGET" and tr[0].target == 106.0
        assert tr[0].r == pytest.approx(1.0)

    def test_stop_hit(self):
        rows = self._base(_row("09:25", 102, 103, 97, 98))
        tr = simulate_day(rows + [_row("09:30", 98, 99, 97, 98)], LV, "NONE", "CANDLE")
        assert tr[0].reason == "STOP" and tr[0].r == pytest.approx(-1.0)

    def test_stop_wins_when_both_touched_in_one_candle(self):
        rows = self._base(_row("09:25", 102, 107, 97, 100))
        tr = simulate_day(rows + [_row("09:30", 100, 101, 99, 100)], LV, "NONE", "CANDLE")
        assert tr[0].reason == "STOP"

    def test_eod_exit(self):
        rows = self._base(_row("09:25", 102, 103, 101, 103))
        tr = simulate_day(rows + [_row("09:30", 103, 104, 102, 104)], LV, "NONE", "CANDLE")
        assert tr[0].reason == "EOD" and tr[0].exit == 104

    def test_line_filter_blocks_long_below_p(self):
        lv = {**LV, "P": 103.0, "TC": 104.0, "BC": 102.0}
        rows = self._base(_row("09:25", 102, 107, 101, 106)) + [_row("09:30", 106, 107, 105, 106)]
        assert simulate_day(rows, lv, "LINE", "CANDLE") == []

    def test_level_stop_uses_pivot(self):
        # LINE/LEVEL: stop at P=95 → risk 7 from entry 102, R1 (106) room 4 < 7 → R2
        rows = self._base(_row("09:25", 102, 121, 101, 120)) + [_row("09:30", 120, 121, 119, 120)]
        tr = simulate_day(rows, LV, "LINE", "LEVEL")
        assert tr[0].stop == 95.0 and tr[0].target == 120.0

    def test_scan_window(self):
        rows = [_row("09:15", 100, 100, 98, 99), _row("09:20", 99, 102.5, 98, 102),
                _row("09:25", 102, 107, 101, 106), _row("09:30", 106, 107, 105, 106)]
        assert simulate_day(rows, LV, "NONE", "CANDLE", scan_start=time(10, 0)) == []

    def test_short_mirror(self):
        rows = [_row("09:15", 100, 102, 100, 101),
                _row("09:20", 101, 102, 97.5, 98),           # red cross, high 102 → risk 4
                _row("09:25", 98, 99, 93, 94),               # entry 98, S1 not near; use LV below
                _row("09:30", 94, 95, 93, 94)]
        lv = {**LV, "S1": 94.0, "P": 105.0, "TC": 106.0, "BC": 104.0}
        tr = simulate_day(rows, lv, "LINE", "CANDLE")
        assert tr[0].side == "PE" and tr[0].reason == "TARGET"
        assert tr[0].r == pytest.approx(1.0)


class TestPipeline:
    def test_runs_and_reports(self):
        daily, m5 = _synthetic(n_days=120, seed=11)
        trades = run_simulation(daily, m5)
        assert set(trades["variant"]).issubset({f"{a}/{b}" for a, b in VARIANTS})
        assert trades["reason"].isin(["TARGET", "STOP", "EOD"]).all()
        # the control variant takes at least as many signals as any filtered one
        counts = trades["variant"].value_counts()
        assert counts["NONE/CANDLE"] >= counts.get("LINE/CANDLE", 0)
        text = report(trades, build_features(daily, m5))
        assert "Overall by variant" in text and "Stability" in text
