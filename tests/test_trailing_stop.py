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
