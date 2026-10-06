"""
Comprehensive tests for the TrailingStopManager.

Verifies:
  - Initial SL placement
  - Break-even activation at exactly entry + 30
  - Each 10-point trailing step
  - Gap moves (skipping multiple steps)
  - Price retracement (stop must NOT move backward)
  - Stop-hit detection
"""

from __future__ import annotations

import pytest

from execution.trailing_stop import TrailingStopManager


class TestTrailingStop:
    """
    All examples use entry=220, initial_sl=30, break_even=30, trail=10
    as specified in PROJECT.md Section 23.
    """

    def _mgr(self) -> TrailingStopManager:
        return TrailingStopManager(
            entry_price=220,
            initial_sl_points=30,
            break_even_trigger_points=30,
            trail_step_points=10,
        )

    # ── Initial state ──────────────────────────────────────────────────────────

    def test_initial_stop(self) -> None:
        m = self._mgr()
        assert m.current_stop == pytest.approx(190.0)
        assert m.break_even_activated is False
        assert m.trail_steps_completed == 0

    # ── No movement below break-even ───────────────────────────────────────────

    def test_no_change_before_break_even(self) -> None:
        m = self._mgr()
        result = m.update(230)
        assert result is None
        assert m.current_stop == pytest.approx(190.0)

    def test_no_change_at_249(self) -> None:
        m = self._mgr()
        assert m.update(249) is None
        assert m.current_stop == pytest.approx(190.0)

    # ── Break-even activation at LTP 250 ──────────────────────────────────────

    def test_break_even_at_250(self) -> None:
        m = self._mgr()
        new_stop = m.update(250)
        assert new_stop == pytest.approx(220.0)
        assert m.current_stop == pytest.approx(220.0)
        assert m.break_even_activated is True

    # ── Trailing steps ────────────────────────────────────────────────────────

    def test_trail_to_230_at_260(self) -> None:
        m = self._mgr()
        m.update(250)
        new_stop = m.update(260)
        assert new_stop == pytest.approx(230.0)
        assert m.current_stop == pytest.approx(230.0)

    def test_trail_to_240_at_270(self) -> None:
        m = self._mgr()
        m.update(250)
        m.update(260)
        new_stop = m.update(270)
        assert new_stop == pytest.approx(240.0)

    def test_trail_to_250_at_280(self) -> None:
        m = self._mgr()
        m.update(250)
        m.update(260)
        m.update(270)
        new_stop = m.update(280)
        assert new_stop == pytest.approx(250.0)

    def test_trail_to_270_at_300(self) -> None:
        m = self._mgr()
        for ltp in (250, 260, 270, 280, 290, 300):
            m.update(ltp)
        assert m.current_stop == pytest.approx(270.0)

    # ── Gap moves ────────────────────────────────────────────────────────────

    def test_gap_move_to_300(self) -> None:
        """Price jumps directly from 220 to 300 — stop should land at 270."""
        m = self._mgr()
        new_stop = m.update(300)
        assert new_stop == pytest.approx(270.0)
        assert m.current_stop == pytest.approx(270.0)

    # ── Retracement — stop never moves backward ───────────────────────────────

    def test_stop_never_decreases_on_retracement(self) -> None:
        m = self._mgr()
        m.update(300)
        assert m.current_stop == pytest.approx(270.0)
        # Price falls
        result = m.update(240)
        assert result is None           # no modification needed
        assert m.current_stop == pytest.approx(270.0)  # unchanged

    def test_stop_unchanged_on_oscillation(self) -> None:
        m = self._mgr()
        m.update(260)
        stop_after = m.current_stop
        m.update(255)
        m.update(258)
        assert m.current_stop == pytest.approx(stop_after)

    # ── Stop-hit detection ────────────────────────────────────────────────────

    def test_stop_hit_below_initial(self) -> None:
        m = self._mgr()
        assert m.is_stop_hit(189) is True
        assert m.is_stop_hit(190) is True   # at stop = hit

    def test_stop_not_hit_above(self) -> None:
        m = self._mgr()
        assert m.is_stop_hit(191) is False

    def test_trailing_stop_hit_after_move(self) -> None:
        m = self._mgr()
        m.update(300)
        assert m.current_stop == pytest.approx(270.0)
        assert m.is_stop_hit(269) is True
        assert m.is_stop_hit(271) is False


# ── ATR-dynamic TSL tests ─────────────────────────────────────────────────────

from datetime import datetime, timedelta

from market.candle_builder import Candle


def _flat_candles(n: int, base: float = 72000.0, atr_spread: float = 147.0) -> list[Candle]:
    """
    Build *n* candles whose Wilder ATR converges to atr_spread.
    Each candle: high=base+atr_spread, low=base-atr_spread, close=base.
    True range is constant = 2×atr_spread; Wilder ATR → atr_spread after warm-up.
    """
    ts = datetime(2026, 10, 5, 9, 15)
    candles = []
    for i in range(n):
        candles.append(Candle(
            timestamp=ts + timedelta(minutes=5 * i),
            open=base,
            high=base + atr_spread,
            low=base - atr_spread,
            close=base,
        ))
    return candles


def _mgr_atr(
    entry: float = 577.45,
    be: float = 101.05,
    trail_step: float = 101.05,
    mult: float = 0.5,
    period: int = 5,
) -> "TrailingStopManager":
    return TrailingStopManager(
        entry_price=entry,
        initial_sl_points=202.1,
        break_even_trigger_points=be,
        trail_step_points=trail_step,
        tsl_atr_trail_mult=mult,
        tsl_atr_period=period,
    )


class TestAtrDynamicTrail:
    """
    ATR-dynamic mode: after BE fires, stop floats at highest_ltp - ATR × mult × 0.4.

    Reference numbers (Oct 5 first trade):
        entry=577.45, be=101.05, ATR≈147, mult=0.5, delta=0.4
        trail_dist = 147 × 0.5 × 0.4 = 29.4 pts
    """

    # ── fixed-step unchanged when mult=0 ──────────────────────────────────────

    def test_fixed_step_unaffected_when_mult_zero(self) -> None:
        """mult=0 → legacy behaviour exactly preserved."""
        m = TrailingStopManager(
            entry_price=220,
            initial_sl_points=30,
            break_even_trigger_points=30,
            trail_step_points=10,
            tsl_atr_trail_mult=0.0,
        )
        m.update(250)
        new_stop = m.update(260)
        assert new_stop == pytest.approx(230.0)

    # ── BE phase still uses fixed trigger ─────────────────────────────────────

    def test_be_not_fired_before_trigger(self) -> None:
        candles = _flat_candles(30)
        m = _mgr_atr()
        result = m.update(640.0, candles)   # below be_trigger 578.5
        assert result is None
        assert m.break_even_activated is False

    def test_be_fires_at_trigger(self) -> None:
        candles = _flat_candles(30)
        m = _mgr_atr()
        result = m.update(678.5, candles)   # entry(577.45) + be(101.05) = 678.5
        assert result == pytest.approx(577.45)
        assert m.break_even_activated is True

    # ── ATR-dynamic trail after BE ────────────────────────────────────────────

    def test_atr_dynamic_trail_after_be(self) -> None:
        """After BE fires, stop = highest_ltp - ATR×mult×delta, floored at entry."""
        candles = _flat_candles(30, atr_spread=147.0)
        m = _mgr_atr(mult=0.5, period=5)
        # Fire BE
        m.update(678.5, candles)
        assert m.break_even_activated is True

        # Now LTP rises to 710
        new_stop = m.update(710.0, candles)
        # Candle true range = high-low = 2×atr_spread = 294 → Wilder ATR converges to 294.
        # trail_dist = 294 × 0.5 × 0.4 = 58.8 → desired = 710 - 58.8 = 651.2
        assert new_stop is not None
        assert new_stop > m.entry_price          # above entry (profit locked)
        assert new_stop == pytest.approx(710.0 - 294.0 * 0.5 * 0.4, abs=0.6)

    def test_stop_never_moves_backward_on_retracement(self) -> None:
        candles = _flat_candles(30, atr_spread=147.0)
        m = _mgr_atr(mult=0.5, period=5)
        m.update(678.5, candles)   # BE
        m.update(750.0, candles)   # ATR trail kicks in
        stop_after_rally = m.current_stop

        # Price falls — stop must NOT move backward
        result = m.update(680.0, candles)
        assert result is None
        assert m.current_stop == pytest.approx(stop_after_rally)

    def test_stop_rises_with_rally(self) -> None:
        candles = _flat_candles(30, atr_spread=147.0)
        m = _mgr_atr(mult=0.5, period=5)
        m.update(678.5, candles)

        stops = []
        for ltp in (700, 750, 800, 880):
            s = m.update(float(ltp), candles)
            if s is not None:
                stops.append(s)

        # Each new high should push the stop higher
        assert stops == sorted(stops), "stops should be strictly non-decreasing"
        # Final stop at peak 880: desired = 880 - 29.4 ≈ 850.6
        assert m.current_stop > 800.0

    def test_entry_floor_prevents_stop_below_entry(self) -> None:
        """Even if ATR is huge, stop must not fall below entry after BE fires."""
        # Huge ATR (500) → trail_dist = 500 × 0.5 × 0.4 = 100
        candles = _flat_candles(30, atr_spread=500.0)
        m = _mgr_atr(entry=577.45, be=101.05, mult=0.5, period=5)
        m.update(678.5, candles)   # BE fires → stop = entry

        # With huge ATR trail, desired = highest - 100 = 678.5 - 100 = 578.5 > entry ✓
        new_stop = m.update(679.0, candles)
        assert new_stop is None or new_stop >= m.entry_price

    # ── Fallback to fixed-step when candles unavailable ───────────────────────

    def test_falls_back_to_fixed_step_when_no_candles(self) -> None:
        """ATR unavailable → falls back to fixed-step trail (never drops protection)."""
        m = _mgr_atr(
            entry=220, be=30, trail_step=10, mult=0.5, period=5
        )
        # Fixed-step BE fires at 250
        m.update(250, None)
        assert m.break_even_activated is True
        # ATR-dynamic would need candles; with None it falls back
        new_stop = m.update(260, None)
        assert new_stop == pytest.approx(230.0)   # fixed-step behaviour

    def test_falls_back_to_fixed_step_when_too_few_candles(self) -> None:
        """Only 3 candles → ATR unavailable → fixed step used."""
        candles = _flat_candles(3, atr_spread=147.0)   # too few for ATR(5)
        m = _mgr_atr(entry=220, be=30, trail_step=10, mult=0.5, period=5)
        m.update(250, candles)   # BE
        new_stop = m.update(260, candles)
        assert new_stop == pytest.approx(230.0)   # fixed-step

    # ── Oct 5 scenario — the trade that motivated this feature ────────────────

    def test_oct5_scenario(self) -> None:
        """
        Oct 5: entry=577.45, BE=101.05, ATR=147, mult=0.5
        Peak=678.75 — with ATR-dynamic, must lock profit above entry.
        Original fixed-step exited at entry (zero profit).
        """
        candles = _flat_candles(30, atr_spread=147.0)
        m = _mgr_atr(entry=577.45, be=101.05, trail_step=101.05, mult=0.5, period=5)

        m.update(678.75, candles)    # BE fires, stop = entry
        assert m.break_even_activated is True
        assert m.current_stop == pytest.approx(577.45)

        # Next tick slightly above — ATR trail kicks in
        # trail_dist = 147 × 0.5 × 0.4 = 29.4
        # desired = 678.75 - 29.4 = 649.35 > entry → stop moves up
        result = m.update(679.0, candles)
        # With ATR trail: stop should be above entry
        assert result is not None
        assert m.current_stop > 577.45
