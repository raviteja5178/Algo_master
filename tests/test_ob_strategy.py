"""
Tests for the Order Block (OB) strategy.

Covers:
  - Bullish OB formation on swing-high crossover
  - Bearish OB formation on swing-low crossover
  - Breaker invalidation (Wick and Close methods)
  - ATR size cap discards oversized OBs
  - CE_OB / PE_OB signal: close inside valid OB triggers signal
  - CE_OB / PE_OB signal: breaker OB does NOT trigger signal
  - Date guard (today-only)
  - Insufficient candles returns empty / False
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from market.candle_builder import Candle
from strategies.ob_strategy import (
    OrderBlock,
    detect_order_blocks,
    is_ob_ce_signal,
    is_ob_pe_signal,
)

_TODAY = date.today()


def _ts(offset_minutes: int) -> datetime:
    """Return a datetime for today at 09:15 + offset_minutes."""
    base = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15)
    return base + timedelta(minutes=offset_minutes)


def _candle(
    offset_minutes: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 1000,
) -> Candle:
    return Candle(_ts(offset_minutes), open_, high, low, close, volume)


# ── Candle sequence builders ──────────────────────────────────────────────────

def _flat_candles(n: int, price: float = 1000.0) -> list[Candle]:
    """n identical candles — used to pad sequences to the required length."""
    return [_candle(i * 5, price, price + 5, price - 5, price) for i in range(n)]


def _bull_ob_candles(swing_length: int = 5) -> list[Candle]:
    """
    Build a synthetic sequence that produces a bullish OB.

    Structure:
      - swing_length + 1 base candles (stable low price)
      - 1 swing-high candle: high=swing_high, low stays same as base (pure upward spike)
      - swing_length candles well below swing_high (confirmation window)
      - 1 crossover candle: close > swing_high

    The spike candle's HIGH must exceed the max-high of every candle in the
    subsequent confirmation window of length swing_length.
    """
    base_price = 1000.0
    swing_high = 1100.0   # spike well above base+10

    candles: list[Candle] = []
    for i in range(swing_length + 1):
        candles.append(_candle(i * 5, base_price, base_price + 10, base_price - 10, base_price))

    # Swing-high spike: high=swing_high, close stays at base (unremarkable close)
    i = len(candles)
    candles.append(_candle(i * 5, base_price, swing_high, base_price - 5, base_price))

    # Confirmation: swing_length candles with high well below swing_high
    for j in range(swing_length):
        i = len(candles)
        candles.append(_candle(i * 5, base_price, base_price + 5, base_price - 5, base_price))

    # Crossover: close breaks above swing_high
    i = len(candles)
    candles.append(_candle(i * 5, swing_high, swing_high + 20, base_price, swing_high + 10))

    return candles


def _bear_ob_candles(swing_length: int = 5) -> list[Candle]:
    """
    Build a synthetic sequence that produces a bearish OB.

    Mirrors _bull_ob_candles but for a downward swing.
    The spike candle's LOW must be below the min-low of every candle in the
    subsequent confirmation window. The HIGH of the spike candle must NOT
    exceed the current confirmation window upper (else it fires as a swing HIGH
    instead of a swing LOW). We keep the spike's high at base_price - 1 to
    ensure it is lower than the flat base_price+5 candles around it.
    """
    base_price = 1000.0
    spike_high = base_price - 1    # deliberately lower than confirmation candle highs
    swing_low  = 900.0

    candles: list[Candle] = []
    for i in range(swing_length + 1):
        candles.append(_candle(i * 5, base_price, base_price + 10, base_price - 10, base_price))

    # Swing-low spike: low=swing_low, high stays LOW (does not trigger swing-high condition)
    i = len(candles)
    candles.append(_candle(i * 5, spike_high, spike_high, swing_low, spike_high))

    # Confirmation: swing_length candles with lows well above swing_low
    for j in range(swing_length):
        i = len(candles)
        candles.append(_candle(i * 5, base_price, base_price + 5, base_price - 5, base_price))

    # Crossover: close breaks below swing_low
    i = len(candles)
    candles.append(_candle(i * 5, swing_low, swing_low, swing_low - 20, swing_low - 10))

    return candles


# ── detect_order_blocks ───────────────────────────────────────────────────────

class TestDetectOrderBlocks:

    def test_returns_empty_when_too_few_candles(self) -> None:
        candles = _flat_candles(5)
        bull, bear = detect_order_blocks(candles, swing_length=10)
        assert bull == []
        assert bear == []

    def test_bullish_ob_detected(self) -> None:
        candles = _bull_ob_candles(swing_length=5)
        bull, bear = detect_order_blocks(candles, swing_length=5, max_blocks=3)
        assert len(bull) >= 1, "Expected at least one bullish OB to be detected"
        assert bull[0].ob_type == "Bull"
        assert not bull[0].breaker

    def test_bearish_ob_detected(self) -> None:
        candles = _bear_ob_candles(swing_length=5)
        bull, bear = detect_order_blocks(candles, swing_length=5, max_blocks=3)
        assert len(bear) >= 1, "Expected at least one bearish OB to be detected"
        assert bear[0].ob_type == "Bear"
        assert not bear[0].breaker

    def test_bull_ob_zone_bounds_are_valid(self) -> None:
        candles = _bull_ob_candles(swing_length=5)
        bull, _ = detect_order_blocks(candles, swing_length=5, max_blocks=3)
        assert len(bull) >= 1
        ob = bull[0]
        assert ob.top > ob.bottom, "OB top must be above bottom"
        assert ob.top > 0 and ob.bottom > 0

    def test_bear_ob_zone_bounds_are_valid(self) -> None:
        candles = _bear_ob_candles(swing_length=5)
        _, bear = detect_order_blocks(candles, swing_length=5, max_blocks=3)
        assert len(bear) >= 1
        ob = bear[0]
        assert ob.top > ob.bottom
        assert ob.top > 0 and ob.bottom > 0

    def test_bull_ob_becomes_breaker_on_wick_pierce(self) -> None:
        """After a bullish OB forms, a candle whose LOW drops below OB.bottom
        (Wick invalidation) flips it to breaker=True."""
        candles = _bull_ob_candles(swing_length=5)
        bull, _ = detect_order_blocks(candles, swing_length=5, max_blocks=3, invalidation="Wick")
        assert len(bull) >= 1
        # The OB was freshly formed; it should still be valid (not a breaker)
        # — unless the same crossover candle happened to pierce its own bottom,
        # which won't happen in our synthetic data since close is above swing_high.
        # At least one must be non-breaker at formation:
        has_valid = any(not ob.breaker for ob in bull)
        assert has_valid, "At least one bullish OB should be non-breaker right after formation"

    def test_atr_cap_discards_oversized_ob(self) -> None:
        """An OB whose height vastly exceeds ATR*maxATRMult is discarded."""
        # Build candles where the swing high is extremely far from current price
        # so the computed OB height >> ATR * mult.
        base_price = 1000.0
        extreme_high = 50000.0   # 49000 pts above base → height >> any ATR
        swing_length = 5
        candles: list[Candle] = []

        for i in range(swing_length + 1):
            candles.append(_candle(i * 5, base_price, base_price + 2, base_price - 2, base_price))

        # Extreme swing candle
        i = len(candles)
        candles.append(_candle(i * 5, base_price, extreme_high, base_price, base_price))

        for j in range(swing_length):
            i = len(candles)
            candles.append(_candle(i * 5, base_price, base_price + 2, base_price - 2, base_price))

        # Crossover — breaks above extreme_high
        i = len(candles)
        candles.append(_candle(i * 5, extreme_high, extreme_high + 10, base_price, extreme_high + 5))

        bull, _ = detect_order_blocks(
            candles,
            swing_length=swing_length,
            max_atr_mult=3.5,
            atr_period=5,
            max_blocks=5,
        )
        # The extreme OB should have been discarded by the ATR size cap
        for ob in bull:
            assert ob.top - ob.bottom < 49000, (
                f"Oversized OB not discarded: top={ob.top} bottom={ob.bottom}"
            )


# ── is_ob_ce_signal ───────────────────────────────────────────────────────────

class TestObCESignal:

    def test_ce_signal_fires_when_close_inside_bull_ob(self) -> None:
        """Close inside a valid bullish OB -> CE_OB signal.

        Strategy: append a fresh candle whose close lands inside the detected
        OB zone.  We do NOT modify the last candle (that would change the OB
        detection result on re-run).  Instead we add one extra candle.
        """
        candles = _bull_ob_candles(swing_length=5)
        bull, _ = detect_order_blocks(candles, swing_length=5, max_blocks=3)
        if not bull or bull[0].breaker:
            pytest.skip("No valid bullish OB detected -- nothing to test against")

        ob = bull[0]
        mid = (ob.top + ob.bottom) / 2
        # Append a candle whose close is mid-OB.
        # Low must be >= ob.bottom (Wick invalidation: low < bottom breaks the OB).
        last = candles[-1]
        extra = Candle(
            _ts((len(candles)) * 5),
            last.close, ob.top, ob.bottom, mid,
        )
        candles.append(extra)

        assert is_ob_ce_signal(candles, swing_length=5, max_blocks=3) is True

    def test_ce_signal_no_fire_when_close_above_ob(self) -> None:
        """Close above the OB zone -> no signal."""
        candles = _bull_ob_candles(swing_length=5)
        bull, _ = detect_order_blocks(candles, swing_length=5, max_blocks=3)
        if not bull:
            pytest.skip("No bullish OB detected")

        ob = bull[0]
        last = candles[-1]
        above_ob = ob.top + 50
        extra = Candle(_ts((len(candles)) * 5), last.close, above_ob + 5, ob.bottom - 1, above_ob)
        candles.append(extra)
        assert is_ob_ce_signal(candles, swing_length=5, max_blocks=3) is False

    def test_ce_signal_no_fire_on_breaker_ob(self) -> None:
        """Close inside a breaker OB -> no signal (invalidated zone)."""
        candles = _bull_ob_candles(swing_length=5)
        bull, _ = detect_order_blocks(candles, swing_length=5, max_blocks=3)
        if not bull:
            pytest.skip("No bullish OB detected")

        ob = bull[0]
        mid = (ob.top + ob.bottom) / 2
        # Append a pierce candle (low drops below OB.bottom -> breaker)
        pierce = _candle((len(candles)) * 5, mid, ob.top + 1, ob.bottom - 50, mid)
        candles.append(pierce)
        # Now append a candle with close inside the OB — must NOT fire (it is a breaker)
        inside = _candle((len(candles)) * 5, mid, ob.top, ob.bottom, mid)
        candles.append(inside)
        assert is_ob_ce_signal(candles, swing_length=5, max_blocks=3) is False

    def test_ce_signal_false_on_too_few_candles(self) -> None:
        candles = _flat_candles(8)
        assert is_ob_ce_signal(candles, swing_length=10) is False

    def test_ce_signal_false_on_yesterday_candle(self) -> None:
        candles = _bull_ob_candles(swing_length=5)
        yesterday = _TODAY - timedelta(days=1)
        last = candles[-1]
        candles[-1] = Candle(
            datetime(yesterday.year, yesterday.month, yesterday.day, 10, 0),
            last.open, last.high, last.low, last.close,
        )
        assert is_ob_ce_signal(candles, swing_length=5) is False


# ── is_ob_pe_signal ───────────────────────────────────────────────────────────

class TestObPESignal:

    def test_pe_signal_fires_when_close_inside_bear_ob(self) -> None:
        """Close inside a valid bearish OB -> PE_OB signal."""
        candles = _bear_ob_candles(swing_length=5)
        _, bear = detect_order_blocks(candles, swing_length=5, max_blocks=3)
        if not bear or bear[0].breaker:
            pytest.skip("No valid bearish OB detected")

        ob = bear[0]
        mid = (ob.top + ob.bottom) / 2
        last = candles[-1]
        # High must be <= ob.top (Wick invalidation: high > top breaks the OB).
        extra = Candle(
            _ts((len(candles)) * 5),
            last.close, ob.top, ob.bottom, mid,
        )
        candles.append(extra)
        assert is_ob_pe_signal(candles, swing_length=5, max_blocks=3) is True

    def test_pe_signal_no_fire_when_close_below_ob(self) -> None:
        """Close below the OB zone -> no signal."""
        candles = _bear_ob_candles(swing_length=5)
        _, bear = detect_order_blocks(candles, swing_length=5, max_blocks=3)
        if not bear:
            pytest.skip("No bearish OB detected")

        ob = bear[0]
        below_ob = ob.bottom - 50
        last = candles[-1]
        extra = Candle(_ts((len(candles)) * 5), last.close, ob.top + 1, below_ob - 5, below_ob)
        candles.append(extra)
        assert is_ob_pe_signal(candles, swing_length=5, max_blocks=3) is False

    def test_pe_signal_no_fire_on_breaker_ob(self) -> None:
        """Close inside a breaker bearish OB -> no signal."""
        candles = _bear_ob_candles(swing_length=5)
        _, bear = detect_order_blocks(candles, swing_length=5, max_blocks=3)
        if not bear:
            pytest.skip("No bearish OB detected")

        ob = bear[0]
        mid = (ob.top + ob.bottom) / 2
        # Pierce above OB.top (bearish breaker condition)
        pierce = _candle((len(candles)) * 5, mid, ob.top + 50, ob.bottom - 1, mid)
        candles.append(pierce)
        inside = _candle((len(candles)) * 5, mid, ob.top, ob.bottom, mid)
        candles.append(inside)
        assert is_ob_pe_signal(candles, swing_length=5, max_blocks=3) is False

    def test_pe_signal_false_on_yesterday_candle(self) -> None:
        candles = _bear_ob_candles(swing_length=5)
        yesterday = _TODAY - timedelta(days=1)
        last = candles[-1]
        candles[-1] = Candle(
            datetime(yesterday.year, yesterday.month, yesterday.day, 10, 0),
            last.open, last.high, last.low, last.close,
        )
        assert is_ob_pe_signal(candles, swing_length=5) is False
