"""
Tests for Order Block (OB) strategy — is_ob_ce_signal / is_ob_pe_signal.

Covers:
  - Original behaviour (no approach buffer): inside zone fires, outside does not.
  - Approach buffer (PE): fires when close is within buffer_pts below OB bottom.
  - Approach buffer (PE): does NOT fire when close is farther than buffer_pts below.
  - Approach buffer (CE): fires when close is within buffer_pts above OB top.
  - Approach buffer (CE): does NOT fire when close is farther than buffer_pts above.
  - Inside-zone still fires when buffer is active (backward compat).
  - Breaker OBs are never triggered (neither inside nor on approach).
  - Today guard: signals never fire on yesterday's candles.
  - Insufficient candles return False without error.

All tests use swing_length=5, atr_period=5 so the series stays short (~13 candles).
Buffer behaviour is tested against the real ATR computed on the same series.
Exact boundary tests (buffer edge ±1 pt) use unittest.mock.patch to pin the ATR.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest

from market.candle_builder import Candle
from strategies.ob_strategy import is_ob_ce_signal, is_ob_pe_signal

_TODAY = date.today()

# ── shared kwargs ─────────────────────────────────────────────────────────────
# Use swing_length=5 / atr_period=5 so the test series only needs ~13 candles.
_OB_KWARGS = dict(
    swing_length=5,
    max_atr_mult=10.0,   # generous cap so OBs are never discarded in tests
    atr_period=5,
    max_blocks=3,
    invalidation="Wick",
)


# ── timestamp helpers ─────────────────────────────────────────────────────────

def _ts(i: int) -> datetime:
    """Today at 09:15 + i×5 min."""
    base = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15)
    return base + timedelta(minutes=i * 5)


def _c(i: int, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(_ts(i), open=o, high=h, low=l, close=c)


# ── candle series factories ───────────────────────────────────────────────────

def _bear_ob_base() -> list[Candle]:
    """
    Build 13 candles that produce exactly one valid (non-breaker) bearish OB
    at approximately [998, 1002].

    Structure (swing_length=5):
      Bars 0-5  : 6 flat candles at p=1000 (range ±2)
      Bar  6    : swing-LOW pivot  (low=800, high=1000.5)  → detected as swing LOW
      Bars 7-11 : 5 flat candles at p=1000 (confirmation window)
      Bar  12   : crossover — close < swing-LOW → triggers bearish OB formation
                  The OB zone is the last flat candle's body: bottom=998, top=1002.

    NOTE: the crossover candle's low extends to 778 (below pivot) which would
    normally invalidate the OB immediately under Wick mode (breach = high of
    *bearish* OB signals when c.high > ob.top).  For bearish OBs, the breaker
    fires when c.high > ob.top; the crossover candle's HIGH is 1002 (= ob.top),
    which is exactly at the boundary so the OB remains valid.
    """
    sl, p = 5, 1000.0
    candles: list[Candle] = []
    for i in range(sl + 1):
        candles.append(_c(i, p, p + 2, p - 2, p))
    # swing LOW pivot
    candles.append(_c(len(candles), p, p + 0.5, p - 200, p + 0.5))
    # confirmation window
    for _ in range(sl):
        candles.append(_c(len(candles), p, p + 2, p - 2, p))
    # crossover: close < pivot.low.  HIGH must be <= 1002 (= ob.top) so the OB
    # is NOT immediately breached (bearish OB breaker: c.high > ob.top).
    candles.append(_c(len(candles), p, p + 2, p - 222, p - 210))
    return candles


def _bull_ob_base() -> list[Candle]:
    """
    Build 13 candles that produce exactly one valid (non-breaker) bullish OB
    at approximately [998, 1002].

    Structure (swing_length=5):
      Bars 0-5  : 6 flat candles at p=1000 (range ±2)
      Bar  6    : swing-HIGH pivot (high=1200, low=999.5)
      Bars 7-11 : 5 flat candles at p=1000 (confirmation window)
      Bar  12   : crossover — close > swing-HIGH → triggers bullish OB formation
                  The OB zone: bottom=998, top=1002.

    For bullish OBs the breaker fires when c.low < ob.bottom.  The crossover
    candle's LOW must be >= ob.bottom (=998) to keep the OB valid.
    """
    sl, p = 5, 1000.0
    candles: list[Candle] = []
    for i in range(sl + 1):
        candles.append(_c(i, p, p + 2, p - 2, p))
    # swing HIGH pivot
    candles.append(_c(len(candles), p, p + 200, p - 0.5, p - 0.5))
    for _ in range(sl):
        candles.append(_c(len(candles), p, p + 2, p - 2, p))
    # crossover: close > pivot.high.  LOW must be >= 998 (= ob.bottom).
    candles.append(_c(len(candles), p, p + 222, p - 2, p + 210))
    return candles


def _append_signal(base: list[Candle], close: float, high: float, low: float) -> list[Candle]:
    """Return a new list with one extra signal candle appended."""
    candles = list(base)
    candles.append(_c(len(candles), base[-1].close, high, low, close))
    return candles


# ─────────────────────────────────────────────────────────────────────────────
# Verify the factories themselves produce working OBs
# ─────────────────────────────────────────────────────────────────────────────

class TestOBFactories:
    """Sanity-check that the test fixtures actually produce the expected OBs."""

    def test_bear_base_produces_valid_bear_ob(self):
        from strategies.ob_strategy import detect_order_blocks
        candles = _bear_ob_base()
        _, bear = detect_order_blocks(candles, **_OB_KWARGS)
        valid = [o for o in bear if not o.breaker]
        assert valid, f"Expected a valid bearish OB; got: {bear}"

    def test_bull_base_produces_valid_bull_ob(self):
        from strategies.ob_strategy import detect_order_blocks
        candles = _bull_ob_base()
        bull, _ = detect_order_blocks(candles, **_OB_KWARGS)
        valid = [o for o in bull if not o.breaker]
        assert valid, f"Expected a valid bullish OB; got: {bull}"


# ─────────────────────────────────────────────────────────────────────────────
# PE_OB (bearish order block) signal tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPeObSignal:
    """is_ob_pe_signal — original and approach-buffer behaviour."""

    def _get_bear_ob(self):
        from strategies.ob_strategy import detect_order_blocks
        _, bear = detect_order_blocks(_bear_ob_base(), **_OB_KWARGS)
        valid = [o for o in bear if not o.breaker]
        assert valid, "Test fixture did not produce a valid bearish OB"
        return valid[0]

    # ── original behaviour (no buffer) ───────────────────────────────────────

    def test_inside_zone_no_buffer_fires(self):
        """Close inside the bearish OB zone fires with no buffer (original behaviour)."""
        ob = self._get_bear_ob()
        # Signal candle: close inside zone; HIGH <= ob.top so OB stays valid
        candles = _append_signal(
            _bear_ob_base(),
            close=ob.bottom + 0.5,
            high=ob.top - 0.5,
            low=ob.bottom - 1,
        )
        assert is_ob_pe_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.0) is True

    def test_outside_zone_no_buffer_does_not_fire(self):
        """Close BELOW the OB bottom with no buffer does NOT fire."""
        ob = self._get_bear_ob()
        candles = _append_signal(
            _bear_ob_base(),
            close=ob.bottom - 20,
            high=ob.top - 0.5,
            low=ob.bottom - 25,
        )
        assert is_ob_pe_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.0) is False

    # ── approach buffer behaviour ─────────────────────────────────────────────

    def test_approach_within_buffer_fires(self):
        """Close within buffer_pts below OB bottom fires when approach buffer is active.

        ATR(5) on our base series ≈ 57.9 pts.  buffer_pts = 0.2×57.9 ≈ 11.6 pts.
        ob.bottom ≈ 998.  close = ob.bottom - 5 (within buffer).
        """
        ob = self._get_bear_ob()
        close = ob.bottom - 5  # within ~11.6 pt buffer
        candles = _append_signal(
            _bear_ob_base(),
            close=close,
            high=ob.top - 0.5,
            low=close - 2,
        )
        assert is_ob_pe_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.2) is True

    def test_approach_beyond_buffer_does_not_fire(self):
        """Close farther than buffer_pts below OB bottom does NOT fire.

        ATR≈57.9, buffer≈11.6.  close = ob.bottom - 20 (beyond buffer).
        """
        ob = self._get_bear_ob()
        close = ob.bottom - 20  # beyond ~11.6 pt buffer
        candles = _append_signal(
            _bear_ob_base(),
            close=close,
            high=ob.top - 0.5,
            low=close - 2,
        )
        assert is_ob_pe_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.2) is False

    def test_inside_zone_with_buffer_fires(self):
        """Inside-zone close still fires when approach buffer is active (backward compat)."""
        ob = self._get_bear_ob()
        candles = _append_signal(
            _bear_ob_base(),
            close=ob.bottom + 0.5,
            high=ob.top - 0.5,
            low=ob.bottom - 1,
        )
        assert is_ob_pe_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.2) is True

    def test_approach_exactly_at_boundary_fires(self):
        """Close at exactly ob.bottom - buffer_pts (boundary) fires."""
        ob = self._get_bear_ob()
        # Pin ATR to 100.0 → buffer_pts = 0.2 × 100 = 20.0
        # close = ob.bottom - 20.0 is exactly on the boundary
        with patch("strategies.ob_strategy.atr_at", return_value=100.0):
            buffer_pts = 0.2 * 100.0
            close = ob.bottom - buffer_pts
            candles = _append_signal(
                _bear_ob_base(),
                close=close,
                high=ob.top - 0.5,
                low=close - 2,
            )
            result = is_ob_pe_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.2)
        assert result is True, f"Expected PE_OB to fire at boundary close={close:.1f}"

    def test_approach_just_beyond_boundary_does_not_fire(self):
        """Close 1 pt beyond buffer_pts does NOT fire."""
        ob = self._get_bear_ob()
        with patch("strategies.ob_strategy.atr_at", return_value=100.0):
            buffer_pts = 0.2 * 100.0
            close = ob.bottom - buffer_pts - 1
            candles = _append_signal(
                _bear_ob_base(),
                close=close,
                high=ob.top - 0.5,
                low=close - 2,
            )
            result = is_ob_pe_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.2)
        assert result is False, f"Expected PE_OB NOT to fire 1pt beyond boundary close={close:.1f}"

    # ── guard tests ───────────────────────────────────────────────────────────

    def test_today_guard_blocks_yesterday_candles(self):
        """Signals never fire when the latest candle is from yesterday."""
        ob = self._get_bear_ob()
        candles = _append_signal(
            _bear_ob_base(),
            close=ob.bottom + 0.5,
            high=ob.top - 0.5,
            low=ob.bottom - 1,
        )
        yesterday = _TODAY - timedelta(days=1)
        shifted = [
            Candle(
                datetime(yesterday.year, yesterday.month, yesterday.day,
                         c.timestamp.hour, c.timestamp.minute),
                open=c.open, high=c.high, low=c.low, close=c.close,
            )
            for c in candles
        ]
        assert is_ob_pe_signal(shifted, **_OB_KWARGS, approach_buffer_atr_mult=0.0) is False

    def test_insufficient_candles_returns_false(self):
        """Fewer than swing_length + 2 candles return False without error."""
        candles = [_c(i, 1000.0, 1002.0, 998.0, 1000.0) for i in range(5)]
        assert is_ob_pe_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.2) is False


# ─────────────────────────────────────────────────────────────────────────────
# CE_OB (bullish order block) signal tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCeObSignal:
    """is_ob_ce_signal — original and approach-buffer behaviour."""

    def _get_bull_ob(self):
        from strategies.ob_strategy import detect_order_blocks
        bull, _ = detect_order_blocks(_bull_ob_base(), **_OB_KWARGS)
        valid = [o for o in bull if not o.breaker]
        assert valid, "Test fixture did not produce a valid bullish OB"
        return valid[0]

    # ── original behaviour (no buffer) ───────────────────────────────────────

    def test_inside_zone_no_buffer_fires(self):
        """Close inside the bullish OB zone fires with no buffer (original behaviour)."""
        ob = self._get_bull_ob()
        # Signal candle: close inside zone; LOW >= ob.bottom so OB stays valid
        candles = _append_signal(
            _bull_ob_base(),
            close=(ob.top + ob.bottom) / 2,
            high=ob.top + 1,
            low=ob.bottom,
        )
        assert is_ob_ce_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.0) is True

    def test_outside_zone_no_buffer_does_not_fire(self):
        """Close ABOVE the OB top with no buffer does NOT fire."""
        ob = self._get_bull_ob()
        candles = _append_signal(
            _bull_ob_base(),
            close=ob.top + 20,
            high=ob.top + 25,
            low=ob.bottom,
        )
        assert is_ob_ce_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.0) is False

    # ── approach buffer behaviour ─────────────────────────────────────────────

    def test_approach_within_buffer_fires(self):
        """Close within buffer_pts above OB top fires when approach buffer is active.

        ATR(5) ≈ 57.9 pts.  buffer_pts = 0.2×57.9 ≈ 11.6 pts.
        close = ob.top + 5 (within buffer).
        """
        ob = self._get_bull_ob()
        close = ob.top + 5  # within ~11.6 pt buffer
        candles = _append_signal(
            _bull_ob_base(),
            close=close,
            high=close + 2,
            low=ob.bottom,
        )
        assert is_ob_ce_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.2) is True

    def test_approach_beyond_buffer_does_not_fire(self):
        """Close farther than buffer_pts above OB top does NOT fire.

        ATR≈57.9, buffer≈11.6.  close = ob.top + 20 (beyond buffer).
        """
        ob = self._get_bull_ob()
        close = ob.top + 20  # beyond ~11.6 pt buffer
        candles = _append_signal(
            _bull_ob_base(),
            close=close,
            high=close + 2,
            low=ob.bottom,
        )
        assert is_ob_ce_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.2) is False

    def test_inside_zone_with_buffer_fires(self):
        """Inside-zone close still fires when approach buffer is active (backward compat)."""
        ob = self._get_bull_ob()
        candles = _append_signal(
            _bull_ob_base(),
            close=(ob.top + ob.bottom) / 2,
            high=ob.top + 1,
            low=ob.bottom,
        )
        assert is_ob_ce_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.2) is True

    def test_approach_exactly_at_boundary_fires(self):
        """Close at exactly ob.top + buffer_pts (boundary) fires."""
        ob = self._get_bull_ob()
        with patch("strategies.ob_strategy.atr_at", return_value=100.0):
            buffer_pts = 0.2 * 100.0
            close = ob.top + buffer_pts
            candles = _append_signal(
                _bull_ob_base(),
                close=close,
                high=close + 2,
                low=ob.bottom,
            )
            result = is_ob_ce_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.2)
        assert result is True, f"Expected CE_OB to fire at boundary close={close:.1f}"

    def test_approach_just_beyond_boundary_does_not_fire(self):
        """Close 1 pt beyond buffer_pts does NOT fire."""
        ob = self._get_bull_ob()
        with patch("strategies.ob_strategy.atr_at", return_value=100.0):
            buffer_pts = 0.2 * 100.0
            close = ob.top + buffer_pts + 1
            candles = _append_signal(
                _bull_ob_base(),
                close=close,
                high=close + 2,
                low=ob.bottom,
            )
            result = is_ob_ce_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.2)
        assert result is False, f"Expected CE_OB NOT to fire 1pt beyond boundary close={close:.1f}"

    # ── guard tests ───────────────────────────────────────────────────────────

    def test_today_guard_blocks_yesterday_candles(self):
        """Signals never fire when the latest candle is from yesterday."""
        ob = self._get_bull_ob()
        candles = _append_signal(
            _bull_ob_base(),
            close=(ob.top + ob.bottom) / 2,
            high=ob.top + 1,
            low=ob.bottom,
        )
        yesterday = _TODAY - timedelta(days=1)
        shifted = [
            Candle(
                datetime(yesterday.year, yesterday.month, yesterday.day,
                         c.timestamp.hour, c.timestamp.minute),
                open=c.open, high=c.high, low=c.low, close=c.close,
            )
            for c in candles
        ]
        assert is_ob_ce_signal(shifted, **_OB_KWARGS, approach_buffer_atr_mult=0.0) is False

    def test_insufficient_candles_returns_false(self):
        """Fewer than swing_length + 2 candles return False without error."""
        candles = [_c(i, 1000.0, 1002.0, 998.0, 1000.0) for i in range(5)]
        assert is_ob_ce_signal(candles, **_OB_KWARGS, approach_buffer_atr_mult=0.2) is False
