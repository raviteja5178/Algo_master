"""Tests for the rule-based intraday market regime classifier (no AI)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from market.candle_builder import Candle
from strategies.market_regime import (
    adx_latest,
    classify_intraday,
    efficiency_ratio,
    volatility_ratio,
)

_DAY = datetime(2026, 10, 14, 9, 15)


def _candles(closes, spread=10.0, start=_DAY):
    """Build 5m candles whose range is `spread` around each close."""
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        hi = max(prev, c) + spread / 2
        lo = min(prev, c) - spread / 2
        out.append(Candle(start + timedelta(minutes=5 * i), open=prev, high=hi, low=lo, close=c, volume=100))
        prev = c
    return out


def _straight(n=60, step=20.0, base=73000.0):
    return [base + i * step for i in range(n)]


def _zigzag(n=60, amp=15.0, base=73000.0):
    return [base + (amp if i % 2 else -amp) for i in range(n)]


class TestEfficiencyRatio:
    def test_straight_line_is_one(self):
        assert efficiency_ratio(_straight(20), 12) == pytest.approx(1.0)

    def test_zigzag_is_near_zero(self):
        assert efficiency_ratio(_zigzag(20), 12) < 0.1

    def test_known_value(self):
        # net move 10, path 10 + 10 + 10 = 30 -> ER = 1/3  (up 20, down 10, up 0... see below)
        closes = [0, 20, 10, 10, 10]   # |10-0| / (20 + 10 + 0 + 0) = 1/3
        assert efficiency_ratio(closes, 4) == pytest.approx(1 / 3)

    def test_not_enough_data(self):
        assert efficiency_ratio([1, 2, 3], 12) is None

    def test_flat_series_is_zero(self):
        assert efficiency_ratio([5.0] * 20, 12) == 0.0


class TestADX:
    def test_not_enough_candles(self):
        assert adx_latest(_candles(_straight(20)), 14) is None

    def test_strong_trend_high_adx_and_plus_di_dominates(self):
        adx, pdi, mdi = adx_latest(_candles(_straight(80)), 14)
        assert adx > 40
        assert pdi > mdi

    def test_downtrend_minus_di_dominates(self):
        adx, pdi, mdi = adx_latest(_candles(list(reversed(_straight(80)))), 14)
        assert adx > 40
        assert mdi > pdi

    def test_choppy_low_adx(self):
        # Mean-reverting noise around a fixed level (a perfect zig-zag is
        # degenerate: identical highs/lows make DX read 100 after one bar).
        import random
        rnd = random.Random(7)
        closes = [73000 + rnd.uniform(-25, 25) for _ in range(120)]
        candles = [
            Candle(_DAY + timedelta(minutes=5 * i), open=c, high=c + rnd.uniform(3, 12),
                   low=c - rnd.uniform(3, 12), close=c, volume=100)
            for i, c in enumerate(closes)
        ]
        adx, _, _ = adx_latest(candles, 14)
        assert adx < 25


class TestVolatilityRatio:
    def test_constant_range_is_one(self):
        r = volatility_ratio(_candles(_zigzag(120), spread=10))
        assert r == pytest.approx(1.0, abs=0.15)

    def test_spike_in_range_raises_ratio(self):
        calm = _candles(_zigzag(100, amp=5), spread=10)
        wild = _candles(
            [73000 + (80 if i % 2 else -80) for i in range(100, 130)],
            spread=100,
            start=calm[-1].timestamp + timedelta(minutes=5),
        )
        assert volatility_ratio(calm + wild) > 1.5

    def test_short_history_returns_none(self):
        assert volatility_ratio(_candles(_zigzag(25))) is None


class TestClassifyIntraday:
    def test_empty_is_warmup(self):
        assert classify_intraday([]).regime == "WARMUP"

    def test_too_few_same_day_candles_is_warmup(self):
        assert classify_intraday(_candles(_straight(8))).regime == "WARMUP"

    def test_trending_up(self):
        snap = classify_intraday(_candles(_straight(70)))
        assert snap.regime == "TRENDING"
        assert snap.direction == "UP"
        assert snap.label.startswith("TRENDING UP")

    def test_trending_down(self):
        snap = classify_intraday(_candles(list(reversed(_straight(70)))))
        assert snap.regime == "TRENDING"
        assert snap.direction == "DOWN"

    def test_choppy(self):
        snap = classify_intraday(_candles(_zigzag(70)))
        assert snap.regime == "CHOPPY"

    def test_mixed_between_thresholds(self):
        # Two steps up, one step down: net/path = 1/3 over 12 candles... use a
        # drift that lands ER between 0.3 and 0.5.
        closes = []
        v = 73000.0
        for i in range(70):
            v += 30 if i % 3 else -30      # +30,+30,-30 repeating -> ER ~ 0.33
            closes.append(v)
        snap = classify_intraday(_candles(closes))
        assert snap.er is not None and 0.3 < snap.er < 0.5
        assert snap.regime == "MIXED"

    def test_er_uses_only_latest_day(self):
        yesterday = _candles(_straight(40), start=_DAY - timedelta(days=1))
        today = _candles(_zigzag(8), start=_DAY)   # 8 candles today < er_period+1
        snap = classify_intraday(yesterday + today)
        assert snap.regime == "WARMUP"

    def test_volatile_overlay_independent_of_regime(self):
        calm = _candles(_zigzag(100, amp=5), spread=10)
        wild = _candles(
            [73000 + (90 if i % 2 else -90) for i in range(30)],
            spread=120,
            start=calm[-1].timestamp + timedelta(minutes=5),
        )
        snap = classify_intraday(calm + wild)
        assert snap.volatile is True
        assert snap.regime == "CHOPPY"
        assert snap.label.endswith("VOLATILE")

    def test_to_dict_is_json_serialisable(self):
        import json
        d = classify_intraday(_candles(_straight(70))).to_dict()
        json.dumps(d)
        assert set(d) >= {"regime", "direction", "volatile", "er", "adx", "vol_ratio"}

    def test_thresholds_are_configurable(self):
        snap = classify_intraday(_candles(_straight(70)), adx_trending=999)
        assert snap.regime != "TRENDING"
