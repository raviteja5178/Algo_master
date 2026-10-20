"""Feature maths for the order-flow study (pure functions, no network)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.orderflow_study import attach_features, orderflow_features


def _fut(n=30, vol=100, spike_at=None, spike=1000):
    ts = pd.date_range("2026-10-01 09:15", periods=n, freq="5min")
    v = np.full(n, vol, dtype=float)
    if spike_at is not None:
        v[spike_at] = spike
    return pd.DataFrame({
        "timestamp": ts, "open": 100.0, "high": 101.0, "low": 99.0,
        "close": np.linspace(100, 90, n), "volume": v,
        "oi": np.linspace(1000, 1000 + 10 * n, n),
    })


def test_rel_vol_uses_only_previous_candles():
    f = orderflow_features(_fut(spike_at=25))
    spike = f.iloc[25]["rel_vol"]
    assert spike == 10.0                       # 1000 / median(100...) -- spike not in its own baseline
    assert f.iloc[26]["rel_vol"] == 1.0        # median of prior 20 is still 100 (one spike)


def test_rel_vol_nan_until_enough_history():
    f = orderflow_features(_fut())
    assert f["rel_vol"].iloc[:5].isna().all()
    assert not np.isnan(f["rel_vol"].iloc[10])


def test_oi_change_is_lookback_difference():
    fut = _fut()
    f = orderflow_features(fut, oi_lookback=3)
    assert f["oi_chg"].iloc[2] != f["oi_chg"].iloc[2]          # NaN (not enough history)
    assert f["oi_chg"].iloc[10] == fut["oi"].iloc[10] - fut["oi"].iloc[7]


def test_signed_volume_follows_candle_direction():
    fut = _fut()
    fut["open"] = fut["close"] + 1.0          # every candle closes below its open -> bearish
    f = orderflow_features(fut, oi_lookback=3)
    assert f["signed_vol_sum"].iloc[10] == -300.0


def test_features_do_not_look_ahead():
    base = _fut(spike_at=25)
    changed = base.copy()
    changed.loc[26:, "volume"] = 99999.0       # future candles must not alter earlier rows
    a, b = orderflow_features(base), orderflow_features(changed)
    pd.testing.assert_frame_equal(a.iloc[:26], b.iloc[:26])


def test_attach_uses_candle_before_entry_and_signs_by_side():
    feats = orderflow_features(_fut())
    sig = feats.iloc[20]["timestamp"]
    entry = sig + pd.Timedelta(minutes=5)
    trades = pd.DataFrame({
        "date": [entry.date()], "entry_time": [entry.strftime("%H:%M")], "side": ["PE"], "r": [1.0],
    })
    out = attach_features(trades, feats)
    assert out.loc[0, "rel_vol"] == feats.iloc[20]["rel_vol"]
    assert out.loc[0, "flow_align"] == -feats.iloc[20]["signed_vol_sum"]   # PE flips the sign


def test_attach_handles_empty():
    out = attach_features(pd.DataFrame(), orderflow_features(_fut()))
    assert out.empty
