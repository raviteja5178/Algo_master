"""
Tests for the CE and PE entry strategy rules.

CE covers:
  - CE positive case (all 4 conditions true)
  - CE: each individual condition false
  - CE today-only guard

PE covers:
  - PE positive case (all 4 conditions true)
  - PE: each individual condition false
  - PE today-only guard
"""

from __future__ import annotations

from datetime import datetime, date, timedelta

import pytest

from market.candle_builder import Candle
from strategies.ce_strategy import is_ce_signal
from strategies.pe_strategy import is_pe_signal

# Use today's date so the today-only guard passes in all tests
_TODAY = date.today()
BASE_TIME = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15)


def make_candles(count: int, close: float = 100.0, high: float = 101.0, low: float = 99.0) -> list[Candle]:
    """Create *count* identical candles (oldest first), all dated today."""
    candles = []
    for i in range(count):
        ts = BASE_TIME + timedelta(minutes=5 * i)
        candles.append(Candle(timestamp=ts, open=close, high=high, low=low, close=close))
    return candles


def make_candles_with_overrides(count: int, overrides: dict[int, dict]) -> list[Candle]:
    candles = make_candles(count)
    as_list = list(candles)
    for idx, fields in overrides.items():
        c = as_list[idx]
        as_list[idx] = Candle(
            timestamp=c.timestamp,
            open=fields.get("open", c.open),
            high=fields.get("high", c.high),
            low=fields.get("low", c.low),
            close=fields.get("close", c.close),
        )
    return as_list


# ─────────────────────────────────────────────────────────────────────────────
# CE STRATEGY
# ─────────────────────────────────────────────────────────────────────────────

class TestCEStrategy:
    """
    Setup:
      - 21 five-minute candles. 20 neutral seeds so EMA21 is populated,
        then a strong bullish candle: close > EMA21 and > prev candle high.
      - 21 fifteen-minute candles. Last close=115 > EMA21 (~100).
    """

    def _build_bullish_5m(self) -> list[Candle]:
        candles = []
        for i in range(20):
            ts = BASE_TIME + timedelta(minutes=5 * i)
            candles.append(Candle(timestamp=ts, open=100, high=101, low=99, close=100))
        # newest candle: close > EMA21 (~100) and > prev high (101)
        ts = BASE_TIME + timedelta(minutes=5 * 20)
        candles.append(Candle(timestamp=ts, open=110, high=120, low=109, close=115))
        return candles

    def _build_bullish_15m(self) -> list[Candle]:
        candles = make_candles(20, close=100.0, high=101.0)
        ts = BASE_TIME + timedelta(minutes=15 * 20)
        candles.append(Candle(timestamp=ts, open=110, high=116, low=109, close=115))
        return candles

    def test_ce_positive(self) -> None:
        """All 4 conditions true → signal fires."""
        assert is_ce_signal(self._build_bullish_5m(), self._build_bullish_15m()) is True

    def test_ce_false_when_5m_close_below_ema21(self) -> None:
        candles_5m = self._build_bullish_5m()
        c = candles_5m[-1]
        candles_5m[-1] = Candle(c.timestamp, open=95, high=96, low=94, close=95)
        assert is_ce_signal(candles_5m, self._build_bullish_15m()) is False

    def test_ce_false_when_ema9_below_ema21(self) -> None:
        candles = make_candles(11, close=100.0, high=101.0)
        for i in range(9):
            ts = BASE_TIME + timedelta(minutes=5 * (11 + i))
            candles.append(Candle(timestamp=ts, open=80, high=82, low=78, close=80))
        ts = BASE_TIME + timedelta(minutes=5 * 20)
        candles.append(Candle(timestamp=ts, open=102, high=103, low=101, close=102))
        assert is_ce_signal(candles, self._build_bullish_15m()) is False

    def test_ce_false_when_close_not_above_prev_high(self) -> None:
        candles_5m = self._build_bullish_5m()
        prev_high = candles_5m[-2].high
        c = candles_5m[-1]
        candles_5m[-1] = Candle(c.timestamp, open=100, high=102, low=99, close=prev_high)
        assert is_ce_signal(candles_5m, self._build_bullish_15m()) is False

    def test_ce_false_when_15m_close_below_ema21_rule4(self) -> None:
        candles_15m = make_candles(20, close=100.0)
        ts = BASE_TIME + timedelta(minutes=15 * 20)
        candles_15m.append(Candle(timestamp=ts, open=90, high=92, low=88, close=90))
        assert is_ce_signal(self._build_bullish_5m(), candles_15m) is False

    def test_ce_insufficient_candles(self) -> None:
        assert is_ce_signal(make_candles(10), make_candles(10)) is False

    def test_ce_false_on_yesterday_candle(self) -> None:
        """Today-only guard: latest candle is from yesterday → rejected."""
        candles_5m = self._build_bullish_5m()
        yesterday = _TODAY - timedelta(days=1)
        c = candles_5m[-1]
        candles_5m[-1] = Candle(
            timestamp=datetime(yesterday.year, yesterday.month, yesterday.day, 10, 0),
            open=c.open, high=c.high, low=c.low, close=c.close,
        )
        assert is_ce_signal(candles_5m, self._build_bullish_15m()) is False


# ─────────────────────────────────────────────────────────────────────────────
# PE STRATEGY
# ─────────────────────────────────────────────────────────────────────────────

class TestPEStrategy:
    """
    Setup:
      - 21 five-minute candles. 20 neutral seeds so EMA21 is populated,
        then a strong bearish candle: close < EMA21 and < prev candle low.
      - 21 fifteen-minute candles. Last close=85 < EMA21 (~100).
    """

    def _build_bearish_5m(self) -> list[Candle]:
        candles = []
        for i in range(20):
            ts = BASE_TIME + timedelta(minutes=5 * i)
            candles.append(Candle(timestamp=ts, open=100, high=101, low=99, close=100))
        # newest candle: close < EMA21 (~100) and < prev low (99)
        ts = BASE_TIME + timedelta(minutes=5 * 20)
        candles.append(Candle(timestamp=ts, open=90, high=91, low=81, close=85))
        return candles

    def _build_bearish_15m(self) -> list[Candle]:
        candles = make_candles(20, close=100.0)
        ts = BASE_TIME + timedelta(minutes=15 * 20)
        candles.append(Candle(timestamp=ts, open=92, high=93, low=84, close=85))
        return candles

    def test_pe_positive(self) -> None:
        """All 4 conditions true → signal fires."""
        assert is_pe_signal(self._build_bearish_5m(), self._build_bearish_15m()) is True

    def test_pe_false_when_5m_close_above_ema21(self) -> None:
        candles_5m = self._build_bearish_5m()
        c = candles_5m[-1]
        candles_5m[-1] = Candle(c.timestamp, open=110, high=112, low=109, close=111)
        assert is_pe_signal(candles_5m, self._build_bearish_15m()) is False

    def test_pe_false_when_ema9_above_ema21(self) -> None:
        candles = make_candles(11, close=100.0)
        for i in range(9):
            ts = BASE_TIME + timedelta(minutes=5 * (11 + i))
            candles.append(Candle(timestamp=ts, open=120, high=122, low=118, close=120))
        ts = BASE_TIME + timedelta(minutes=5 * 20)
        candles.append(Candle(timestamp=ts, open=88, high=90, low=86, close=88))
        assert is_pe_signal(candles, self._build_bearish_15m()) is False

    def test_pe_false_when_close_not_below_prev_low(self) -> None:
        candles_5m = self._build_bearish_5m()
        prev_low = candles_5m[-2].low
        c = candles_5m[-1]
        candles_5m[-1] = Candle(c.timestamp, open=98, high=99, low=98, close=prev_low)
        assert is_pe_signal(candles_5m, self._build_bearish_15m()) is False

    def test_pe_false_when_15m_close_above_ema21(self) -> None:
        candles_15m = make_candles(20, close=100.0)
        ts = BASE_TIME + timedelta(minutes=15 * 20)
        candles_15m.append(Candle(timestamp=ts, open=110, high=112, low=108, close=111))
        assert is_pe_signal(self._build_bearish_5m(), candles_15m) is False

    def test_pe_insufficient_candles(self) -> None:
        assert is_pe_signal(make_candles(20), make_candles(20)) is False

    def test_pe_false_on_yesterday_candle(self) -> None:
        """Today-only guard: latest candle not today → rejected."""
        candles_5m = self._build_bearish_5m()
        yesterday = _TODAY - timedelta(days=1)
        c = candles_5m[-1]
        candles_5m[-1] = Candle(
            timestamp=datetime(yesterday.year, yesterday.month, yesterday.day, 10, 0),
            open=c.open, high=c.high, low=c.low, close=c.close,
        )
        assert is_pe_signal(candles_5m, self._build_bearish_15m()) is False
