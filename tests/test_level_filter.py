"""Tests for the VWAP support/resistance room filter."""

from __future__ import annotations

from datetime import datetime, timedelta

from market.candle_builder import Candle
from market.historical_data import compute_pivot_levels
from strategies.level_filter import collect_levels, level_room_blocked


def _candles(n: int, high: float = 100.0, low: float = 90.0) -> list[Candle]:
    t0 = datetime(2026, 10, 16, 9, 15)
    return [
        Candle(t0 + timedelta(minutes=5 * i), 95.0, high, low, 95.0)
        for i in range(n)
    ]


def test_ce_blocked_when_resistance_too_close():
    blocked, level, room = level_room_blocked("CE", 100.0, 20.0, [110.0, 150.0], 1.0)
    assert blocked is True
    assert level == 110.0
    assert room == 10.0


def test_ce_allowed_when_room_sufficient():
    blocked, level, room = level_room_blocked("CE", 100.0, 20.0, [130.0], 1.0)
    assert blocked is False
    assert level == 130.0 and room == 30.0


def test_pe_uses_support_below_close():
    blocked, level, room = level_room_blocked("PE", 100.0, 20.0, [90.0, 50.0, 120.0], 1.0)
    assert blocked is True
    assert level == 90.0 and room == 10.0


def test_levels_behind_price_are_ignored():
    # CE only cares about levels above the close
    blocked, level, _ = level_room_blocked("CE", 100.0, 20.0, [95.0, 99.0], 1.0)
    assert blocked is False and level is None


def test_fails_open_without_atr_or_when_disabled():
    assert level_room_blocked("CE", 100.0, None, [101.0], 1.0)[0] is False
    assert level_room_blocked("CE", 100.0, 0.0, [101.0], 1.0)[0] is False
    assert level_room_blocked("CE", 100.0, 20.0, [101.0], 0.0)[0] is False


def test_collect_levels_includes_pdhl_pivots_and_day_extremes():
    pl = compute_pivot_levels(120.0, 80.0, 100.0, formula="FIBONACCI")
    candles = _candles(10, high=100.0, low=90.0)
    levels = collect_levels(candles, prev_day_high=120.0, prev_day_low=80.0, pivot_levels=pl)
    assert 120.0 in levels and 80.0 in levels
    assert pl.pivot in levels and pl.r1 in levels and pl.s3 in levels
    assert 100.0 in levels and 90.0 in levels  # day high/low


def test_day_extremes_exclude_last_candles():
    candles = _candles(10)
    # Spike only inside the last 3 candles must not become a level
    spike = Candle(candles[-1].timestamp, 95.0, 500.0, 90.0, 95.0)
    candles = candles[:-1] + [spike]
    levels = collect_levels(candles, exclude_last=3)
    assert 500.0 not in levels


def test_pivot_and_day_toggles():
    pl = compute_pivot_levels(120.0, 80.0, 100.0, formula="FIBONACCI")
    candles = _candles(10)
    only_pdhl = collect_levels(
        candles, prev_day_high=120.0, prev_day_low=80.0, pivot_levels=pl,
        use_pivots=False, use_day_extremes=False,
    )
    assert sorted(only_pdhl) == [80.0, 120.0]
