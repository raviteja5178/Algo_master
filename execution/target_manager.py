"""
Dynamic target reference manager.

The target reference is a bot-side tracking value.
It does NOT automatically place a live limit sell order (USE_LIVE_TARGET_ORDER=false default).

Initial reference = entry_price + INITIAL_TARGET_OFFSET_POINTS
After each trailing step: reference += TARGET_TRAIL_STEP_POINTS
"""

from __future__ import annotations

import logging

from utils.logging_config import log_event

logger = logging.getLogger(__name__)


class DynamicTargetManager:
    def __init__(
        self,
        entry_price: float,
        initial_offset_points: float = 50.0,
        trail_step_points: float = 10.0,
    ) -> None:
        self.entry_price = entry_price
        self.trail_step_points = trail_step_points
        self.target_reference: float = entry_price + initial_offset_points
        self._last_trail_steps: int = 0

    def sync_trail_steps(self, trail_steps_completed: int) -> None:
        """
        Called after the trailing stop manager updates its step count.
        Advances the target reference by one trail_step for each new step.
        """
        new_steps = trail_steps_completed - self._last_trail_steps
        if new_steps > 0:
            old_ref = self.target_reference
            self.target_reference += new_steps * self.trail_step_points
            self._last_trail_steps = trail_steps_completed
            log_event(
                logger, "TARGET_REFERENCE_UPDATED",
                old=old_ref, new=self.target_reference, steps=trail_steps_completed,
            )

    def is_target_hit(self, current_price: float) -> bool:
        """Return True if current price has reached or exceeded target reference."""
        return current_price >= self.target_reference

    def to_dict(self) -> dict:
        return {
            "target_reference": self.target_reference,
            "last_trail_steps": self._last_trail_steps,
        }
