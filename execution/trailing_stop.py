"""
Trailing stop manager — deterministic, testable.

Algorithm (entry = 220, initial_sl = 30, break_even = 30, trail_step = 10):

  start:       stop = 190
  LTP 250:     stop = 220  (break-even activated)
  LTP 260:     stop = 230
  LTP 270:     stop = 240
  LTP 300:     stop = 270
  LTP falls:   stop stays at 270 (never moves backward)
"""

from __future__ import annotations

import logging

from utils.logging_config import log_event
from utils.price_utils import round_to_tick

logger = logging.getLogger(__name__)


class TrailingStopManager:
    """
    Pure-Python trailing stop state machine.

    All state is held in instance attributes so it can be persisted and
    restored after a restart.
    """

    def __init__(
        self,
        entry_price: float,
        initial_sl_points: float = 30.0,
        break_even_trigger_points: float = 30.0,
        trail_step_points: float = 10.0,
    ) -> None:
        self.entry_price = entry_price
        self.initial_sl_points = initial_sl_points
        self.break_even_trigger_points = break_even_trigger_points
        self.trail_step_points = trail_step_points

        # Mutable state (persisted to DB)
        self.current_stop: float = round_to_tick(entry_price - initial_sl_points)
        self.highest_ltp: float = entry_price
        self.break_even_activated: bool = False
        self.trail_steps_completed: int = 0

    # ── Public ─────────────────────────────────────────────────────────────────

    def update(self, ltp: float) -> float | None:
        """
        Feed a new LTP.  Returns the new stop price if the stop should be
        modified at the broker, otherwise returns None.

        The caller is responsible for sending the modification order.
        """
        self.highest_ltp = max(self.highest_ltp, ltp)

        new_stop = self._calculate_stop()
        if new_stop is None:
            return None

        # Enforce: stop must never move backward
        new_stop = max(new_stop, self.current_stop)
        new_stop = round_to_tick(new_stop)

        if new_stop > self.current_stop:
            old_stop = self.current_stop
            self.current_stop = new_stop
            if not self.break_even_activated:
                self.break_even_activated = True
                log_event(
                    logger, "BREAK_EVEN_ACTIVATED",
                    entry=self.entry_price, ltp=ltp, new_stop=new_stop,
                )
            else:
                self.trail_steps_completed += 1
                log_event(
                    logger, "TRAILING_SL_UPDATED",
                    entry=self.entry_price, ltp=ltp,
                    old_stop=old_stop, new_stop=new_stop,
                    steps=self.trail_steps_completed,
                )
            return new_stop

        return None

    def is_stop_hit(self, ltp: float) -> bool:
        """Return True if LTP has breached the current stop (exit trigger)."""
        return ltp <= self.current_stop

    def to_dict(self) -> dict:
        return {
            "entry_price": self.entry_price,
            "current_stop": self.current_stop,
            "highest_ltp": self.highest_ltp,
            "break_even_activated": int(self.break_even_activated),
            "trail_steps_completed": self.trail_steps_completed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TrailingStopManager":
        obj = cls(
            entry_price=d["entry_price"],
            initial_sl_points=d.get("initial_sl_points", 30.0),
            break_even_trigger_points=d.get("break_even_trigger_points", 30.0),
            trail_step_points=d.get("trail_step_points", 10.0),
        )
        obj.current_stop = d["current_stop"]
        obj.highest_ltp = d["highest_ltp"]
        obj.break_even_activated = bool(d["break_even_activated"])
        obj.trail_steps_completed = d["trail_steps_completed"]
        return obj

    # ── Private ────────────────────────────────────────────────────────────────

    def _calculate_stop(self) -> float | None:
        """
        Compute the desired stop based on highest_ltp.

        Break-even zone: entry_price + break_even_trigger <= highest_ltp
            -> stop = entry_price

        Each additional trail_step_points above break-even:
            -> stop rises by trail_step_points
        """
        be_trigger = self.entry_price + self.break_even_trigger_points
        if self.highest_ltp < be_trigger:
            return None  # not yet in profit territory

        # How many trail steps above break-even have been completed?
        # First step: moves stop to entry_price (break-even)
        above_be = self.highest_ltp - be_trigger
        steps_above = int(above_be // self.trail_step_points)

        desired_stop = self.entry_price + steps_above * self.trail_step_points
        return desired_stop
