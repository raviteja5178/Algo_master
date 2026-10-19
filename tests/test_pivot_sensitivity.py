"""Tests for research/pivot_sensitivity.py — case grid validity, summary, flags, sweep plumbing."""

from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from execution.pivot_trade_manager import PivotTradeManager
from research.pivot_backtest import backtest_variant, live_signal_kwargs, manager_kwargs
from research.pivot_sensitivity import (
    build_cases,
    flag,
    format_report,
    run_sweep,
    summarise,
)
from strategies.pivot_strategy import find_pivot_setup
from tests.test_cpr_study import _synthetic


class TestCases:
    def test_baseline_first_and_labels_unique(self):
        cases = build_cases()
        assert cases[0][0] == "LIVE"
        labels = [c[0] for c in cases]
        assert len(labels) == len(set(labels))

    def test_live_value_never_duplicated_as_a_case(self):
        # a case equal to the live setting would just re-run the baseline
        live = live_signal_kwargs() | manager_kwargs()
        for label, _g, kind, payload in build_cases()[1:]:
            if kind in ("sig", "mgr"):
                (k, v), = payload.items()
                assert live.get(k) != v, label

    def test_every_payload_key_is_a_real_parameter(self):
        sig_params = set(inspect.signature(find_pivot_setup).parameters)
        mgr_params = set(inspect.signature(PivotTradeManager.__init__).parameters)
        top_params = set(inspect.signature(backtest_variant).parameters)
        for label, _g, kind, payload in build_cases():
            for k in payload:
                target = {"sig": sig_params, "mgr": mgr_params, "top": top_params}[kind]
                assert k in target, f"{label}: {k} not a parameter of the {kind} target"


class TestSummaryAndFlags:
    def _trades(self):
        return pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10).date,
            "r": [1, -1, 2, -1, 3, -1, -1, 1, 2, -1],
            "pts": [10, -10, 20, -10, 30, -10, -10, 10, 20, -10],
        })

    def test_summarise(self):
        s = summarise(self._trades())
        assert s["n"] == 10 and s["totPts"] == 40 and s["avgPts"] == 4.0
        assert s["win"] == 50.0
        assert s["exTop5Pts"] == pytest.approx(-10.0)
        assert s["H1Pts"] == pytest.approx(8.0) and s["H2Pts"] == pytest.approx(0.0)

    def test_summarise_empty(self):
        s = summarise(pd.DataFrame(columns=["date", "r", "pts"]))
        assert s["n"] == 0 and s["totPts"] == 0.0

    def test_flag_big_change_and_sign_flip(self):
        row = dict(n=10, totPts=100, H1Pts=5, H2Pts=5)
        assert flag(row, 100) == ""
        assert flag(row, 200) == "!"                       # -50 %
        assert flag(dict(n=10, totPts=-20, H1Pts=5, H2Pts=5), 100) == "!"

    def test_flag_negative_half(self):
        assert flag(dict(n=10, totPts=100, H1Pts=-1, H2Pts=5), 100) == "~"
        assert flag(dict(n=10, totPts=300, H1Pts=-1, H2Pts=5), 100) == "!~"


class TestSweep:
    def test_small_sweep_runs_and_reports(self):
        daily, m5 = _synthetic(n_days=110, seed=4)
        cases = [c for c in build_cases() if c[0] in ("LIVE", "trail_atr_mult=2.0", "max_trades=1")]
        assert len(cases) == 3
        df = run_sweep(daily, m5, cases, workers=1)
        assert list(df["case"]) == ["LIVE", "trail_atr_mult=2.0", "max_trades=1"]
        assert df.loc[df["case"] == "LIVE", "dTot%"].iloc[0] == 0 or np.isnan(
            df.loc[df["case"] == "LIVE", "dTot%"].iloc[0])
        assert "Sensitivity" in format_report(df)
        # max_trades=1 can never take more trades than the baseline
        n = dict(zip(df["case"], df["n"]))
        assert n["max_trades=1"] <= n["LIVE"]
