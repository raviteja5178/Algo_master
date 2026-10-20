"""Tests for the offline CPR study (research/cpr_study.py) — pure functions + synthetic pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.cpr_study import (
    band_sides,
    build_features,
    classify_day,
    count_side_flips,
    cpr_levels,
    cpr_relation,
    early_state,
    open_position,
    report,
)


class TestCprLevels:
    def test_formula(self):
        bc, p, tc = cpr_levels(110.0, 90.0, 105.0)
        assert p == pytest.approx(305 / 3)
        assert bc == pytest.approx(100.0)           # (H+L)/2
        assert tc == pytest.approx(2 * 305 / 3 - 100.0)

    def test_bc_never_above_tc(self):
        bc, _, tc = cpr_levels(110.0, 90.0, 92.0)   # close in lower half → TC < mid
        assert bc <= tc

    def test_width_depends_on_close_position_only(self):
        # close exactly mid-range → zero-width CPR
        bc, _, tc = cpr_levels(110.0, 90.0, 100.0)
        assert tc - bc == pytest.approx(0.0)
        # width = |2C - H - L| / 3
        bc, _, tc = cpr_levels(110.0, 90.0, 108.0)
        assert tc - bc == pytest.approx(abs(2 * 108 - 110 - 90) / 3)


class TestRelations:
    def test_cpr_relation(self):
        assert cpr_relation(120, 125, 100, 110) == "HIGHER"
        assert cpr_relation(80, 90, 100, 110) == "LOWER"
        assert cpr_relation(105, 120, 100, 110) == "OVERLAP_UP"
        assert cpr_relation(95, 105, 100, 110) == "OVERLAP_DOWN"

    def test_open_position(self):
        assert open_position(111, 100, 110) == "ABOVE_TC"
        assert open_position(99, 100, 110) == "BELOW_BC"
        assert open_position(105, 100, 110) == "INSIDE"
        assert open_position(110, 100, 110) == "INSIDE"   # boundary is inside

    def test_early_state(self):
        assert early_state([111, 112, 113], 100, 110) == "ABOVE"
        assert early_state([99, 98, 97], 100, 110) == "BELOW"
        assert early_state([111, 105, 113], 100, 110) == "MIXED"
        assert early_state([111, 112], 100, 110) == "NA"


class TestSides:
    def test_band_sides(self):
        assert band_sides([111, 105, 99], 100, 110) == [1, 0, -1]

    def test_flips_ignore_inside(self):
        assert count_side_flips([1, 0, 0, -1, 0, 1]) == 2
        assert count_side_flips([1, 1, 0, 1]) == 0
        assert count_side_flips([0, 0]) == 0


class TestClassify:
    @pytest.mark.parametrize("eff,rng,expected", [
        (0.7, 1.5, ("TREND", "HIGH")),
        (0.1, 0.5, ("RANGE", "LOW")),
        (0.35, 1.0, ("MIXED", "NORMAL")),
        (0.5, 0.8, ("TREND", "NORMAL")),     # boundaries: eff>=0.5, rng>=0.8
        (0.25, 1.2, ("MIXED", "HIGH")),
    ])
    def test_thresholds(self, eff, rng, expected):
        assert classify_day(eff, rng) == expected


def _synthetic(n_days: int = 90, seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Weekday daily bars plus 5m bars (09:15-15:25) generated as a random walk."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=n_days)
    price = 70000.0
    daily_rows, m5_rows = [], []
    for d in dates:
        ts = pd.date_range(d + pd.Timedelta(hours=9, minutes=15),
                           d + pd.Timedelta(hours=15, minutes=25), freq="5min")
        steps = rng.normal(0, 25, len(ts))
        closes = price + np.cumsum(steps)
        opens = np.concatenate([[price], closes[:-1]])
        highs = np.maximum(opens, closes) + rng.uniform(0, 8, len(ts))
        lows = np.minimum(opens, closes) - rng.uniform(0, 8, len(ts))
        for t, o, h, l, c in zip(ts, opens, highs, lows, closes):
            m5_rows.append({"timestamp": t, "open": o, "high": h, "low": l, "close": c})
        daily_rows.append({"date": d, "open": opens[0], "high": highs.max(),
                           "low": lows.min(), "close": closes[-1]})
        price = closes[-1]
    return pd.DataFrame(daily_rows), pd.DataFrame(m5_rows)


class TestPipeline:
    def test_features_have_no_lookahead_and_valid_ranges(self):
        daily, m5 = _synthetic()
        feats = build_features(daily, m5)
        assert len(feats) > 40
        assert feats["efficiency"].between(0, 1).all()
        assert (feats["range_atr"] > 0).all()
        assert (feats["bc"] <= feats["tc"]).all()
        assert feats["open_pos"].isin(["ABOVE_TC", "INSIDE", "BELOW_BC"]).all()

        # CPR for a day must come from the PREVIOUS day only.
        first = feats.iloc[0]
        d = pd.Timestamp(first["date"])
        idx = daily.index[daily["date"] == d][0]
        prev = daily.iloc[idx - 1]
        bc, _, tc = cpr_levels(prev["high"], prev["low"], prev["close"])
        assert first["bc"] == pytest.approx(bc, abs=0.01)
        assert first["tc"] == pytest.approx(tc, abs=0.01)

    def test_report_runs(self):
        daily, m5 = _synthetic()
        text = report(build_features(daily, m5))
        assert "By CPR width bucket" in text
        assert "Stability" in text
