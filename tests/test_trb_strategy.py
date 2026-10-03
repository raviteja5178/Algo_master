"""
Tests for the 15-minute Time Range Breakout (TRB) strategy.

Anchor range = HIGH/LOW of the 15m candle starting at 09:45 AM (completed at 10:00 AM).
Breakout is monitored on 5m completed candles strictly after 10:00 AM.
"""

from __future__ import annotations

from datetime import datetime, date, timedelta
import pytest

from market.candle_builder import Candle
from strategies.trb_strategy import (
    get_trb_range,
    is_trb_ce_signal,
    is_trb_pe_signal,
)

_TODAY = date.today()


def _ts(h: int, m: int) -> datetime:
    return datetime(_TODAY.year, _TODAY.month, _TODAY.day, h, m)


def make_15m_candles(
    anchor_high: float = 75000.0,
    anchor_low: float = 74800.0,
    has_anchor: bool = True,
) -> list[Candle]:
    """
    Build a minimal list of 15m candles including the 09:45 anchor candle.
    The anchor candle starts at 09:45 and ends at 10:00.
    """
    candles = [
        Candle(_ts(9, 15), open=74700.0, high=74750.0, low=74650.0, close=74700.0),
        Candle(_ts(9, 30), open=74700.0, high=74800.0, low=74650.0, close=74750.0),
    ]
    if has_anchor:
        candles.append(
            Candle(_ts(9, 45), open=74750.0, high=anchor_high, low=anchor_low, close=74900.0)
        )
    return candles


def make_5m_candles(
    h: int,
    m: int,
    prev_close: float,
    latest_close: float,
    latest_open: float | None = None,
    latest_high: float | None = None,
    latest_low: float | None = None,
) -> list[Candle]:
    """
    Build a minimal list of 5m candles containing:
      - 1 reference candle before breakout
      - 1 crossover/breakout candle at the specified time (h:m)
    """
    lopen  = latest_open  if latest_open  is not None else prev_close
    lhigh  = latest_high  if latest_high  is not None else max(latest_close, prev_close) + 2
    llow   = latest_low   if latest_low   is not None else min(latest_close, prev_close) - 2

    # A simple sequence of 2 candles
    # Candle 1: starts 5 minutes before (h:m)
    ts1 = _ts(h, m) - timedelta(minutes=5)
    # Candle 2: starts exactly at (h:m)
    ts2 = _ts(h, m)

    return [
        Candle(ts1, open=prev_close, high=prev_close + 5, low=prev_close - 5, close=prev_close),
        Candle(ts2, open=lopen, high=lhigh, low=llow, close=latest_close),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTRBRange:

    def test_get_trb_range_success(self) -> None:
        candles = make_15m_candles(anchor_high=75100.0, anchor_low=74900.0)
        high, low = get_trb_range(candles)
        assert high == 75100.0
        assert low == 74900.0

    def test_get_trb_range_missing_anchor(self) -> None:
        # Build 15m candles without the 09:45 anchor
        candles = make_15m_candles(has_anchor=False)
        high, low = get_trb_range(candles)
        assert high is None
        assert low is None


class TestTRBCEBreakout:

    def test_trb_ce_signal_success(self) -> None:
        # Anchor high = 75000.0
        c15m = make_15m_candles(anchor_high=75000.0, anchor_low=74800.0)
        # Prev close <= 75000.0, Current close > 75000.0
        # Evaluated strictly after 10:00 (e.g., at 10:05 AM)
        c5m = make_5m_candles(10, 5, prev_close=74990.0, latest_close=75010.0)

        assert is_trb_ce_signal(c5m, c15m) is True

    def test_trb_ce_signal_no_crossover(self) -> None:
        c15m = make_15m_candles(anchor_high=75000.0, anchor_low=74800.0)
        # Prev close was already above the high, so not a crossover
        c5m = make_5m_candles(10, 5, prev_close=75005.0, latest_close=75010.0)

        assert is_trb_ce_signal(c5m, c15m) is False

    def test_trb_ce_signal_time_guard(self) -> None:
        c15m = make_15m_candles(anchor_high=75000.0, anchor_low=74800.0)
        # Close exceeds high, but evaluated BEFORE 10:00 AM (e.g. at 09:55 AM)
        c5m = make_5m_candles(9, 55, prev_close=74990.0, latest_close=75010.0)

        assert is_trb_ce_signal(c5m, c15m) is False


class TestTRBPEBreakout:

    def test_trb_pe_signal_success(self) -> None:
        # Anchor low = 74800.0
        c15m = make_15m_candles(anchor_high=75000.0, anchor_low=74800.0)
        # Prev close >= 74800.0, Current close < 74800.0
        # Evaluated strictly after 10:00 (e.g., at 10:10 AM)
        c5m = make_5m_candles(10, 10, prev_close=74810.0, latest_close=74790.0)

        assert is_trb_pe_signal(c5m, c15m) is True

    def test_trb_pe_signal_no_crossover(self) -> None:
        c15m = make_15m_candles(anchor_high=75000.0, anchor_low=74800.0)
        # Prev close was already below, so not a crossover
        c5m = make_5m_candles(10, 10, prev_close=74795.0, latest_close=74790.0)

        assert is_trb_pe_signal(c5m, c15m) is False

    def test_trb_pe_signal_time_guard(self) -> None:
        c15m = make_15m_candles(anchor_high=75000.0, anchor_low=74800.0)
        # Close drops below, but evaluated BEFORE 10:00 AM (e.g. at 09:50 AM)
        c5m = make_5m_candles(9, 50, prev_close=74810.0, latest_close=74790.0)

        assert is_trb_pe_signal(c5m, c15m) is False


class TestTRBFilters:

    def test_body_ratio_filter_ce(self) -> None:
        c15m = make_15m_candles(anchor_high=75000.0, anchor_low=74800.0)
        # Breakout candle range = 75020 - 74980 = 40.0
        # Close = 75010, Open = 75005. Body = 5.0 (Ratio = 5/40 = 0.125)
        c5m = make_5m_candles(
            10, 5,
            prev_close=74990.0, latest_close=75010.0,
            latest_open=75005.0, latest_high=75020.0, latest_low=74980.0,
        )

        # Passes with default 0.0 (disabled)
        assert is_trb_ce_signal(c5m, c15m, min_body_ratio=0.0) is True

        # Fails when body ratio required is 0.40
        assert is_trb_ce_signal(c5m, c15m, min_body_ratio=0.40) is False

    def test_body_ratio_filter_pe(self) -> None:
        c15m = make_15m_candles(anchor_high=75000.0, anchor_low=74800.0)
        # Breakout candle range = 74810 - 74770 = 40.0
        # Close = 74790, Open = 74795. Body = 5.0 (Ratio = 5/40 = 0.125)
        c5m = make_5m_candles(
            10, 10,
            prev_close=74810.0, latest_close=74790.0,
            latest_open=74795.0, latest_high=74810.0, latest_low=74770.0,
        )

        # Passes with default 0.0 (disabled)
        assert is_trb_pe_signal(c5m, c15m, min_body_ratio=0.0) is True

        # Fails when body ratio required is 0.40
        assert is_trb_pe_signal(c5m, c15m, min_body_ratio=0.40) is False
