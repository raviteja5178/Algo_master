"""
Trailing stop manager — deterministic, testable.

Fixed-step algorithm (entry = 220, initial_sl = 30, break_even = 30, trail_step = 10):

  start:       stop = 190
  LTP 250:     stop = 220  (break-even activated)
  LTP 260:     stop = 230
  LTP 270:     stop = 240
  LTP 300:     stop = 270
  LTP falls:   stop stays at 270 (never moves backward)

ATR-dynamic algorithm (tsl_atr_trail_mult > 0):

  On each tick, the trail distance is recomputed from the latest 5m ATR:
    trail_dist = ATR(period, 5m SENSEX) × tsl_atr_trail_mult × ATM_delta(0.4)
    desired_stop = highest_ltp - trail_dist

  Break-even activation still uses the fixed break_even_trigger_points.
  After BE fires, subsequent stop updates are ATR-driven, not step-driven.

  Example (entry=577, be=101, ATR=147, mult=0.5, delta=0.4):
    trail_dist = 147 × 0.5 × 0.4 = 29.4 pts
    LTP 678 (BE trigger): stop = 577 (entry)
    LTP 710: desired = 710 - 29 = 681 → stop moves to 681 (+104 locked)
    LTP 750: desired = 750 - 29 = 721 → stop moves to 721 (+144 locked)
    LTP 880: desired = 880 - 29 = 851 → stop moves to 851 (+274 locked)
    Price falls: stop stays at last highest value (never moves backward)
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from utils.logging_config import log_event
from utils.price_utils import round_to_tick

if TYPE_CHECKING:
    from market.candle_builder import Candle

logger = logging.getLogger(__name__)

# ATM delta — same constant used in atr_risk.py for option-premium conversion
_ATM_DELTA = 0.4


class TrailingStopManager:
    """
    Trailing stop state machine — supports two modes:

    Fixed-step mode (tsl_atr_trail_mult == 0.0, default):
        Stop ratchets up in discrete trail_step_points increments above
        break-even.  Deterministic and easy to reason about.

    ATR-dynamic mode (tsl_atr_trail_mult > 0.0):
        After break-even fires, the stop floats at:
            highest_ltp − ATR(period) × tsl_atr_trail_mult × ATM_delta(0.4)
        The trail distance adapts to current volatility on every tick.
        Calm market → small ATR → tight trail (locks profit quickly).
        Trending day → large ATR → wide trail (doesn't shake out runners).
        candles_5m must be passed to update() for ATR computation.

    All mutable state is held in instance attributes so it can be persisted
    and restored after a bot restart.
    """

    def __init__(
        self,
        entry_price: float,
        initial_sl_points: float = 30.0,
        break_even_trigger_points: float = 30.0,
        trail_step_points: float = 10.0,
        tsl_atr_trail_mult: float = 0.0,
        tsl_atr_period: int = 5,
    ) -> None:
        self.entry_price = entry_price
        self.initial_sl_points = initial_sl_points
        self.break_even_trigger_points = break_even_trigger_points
        self.trail_step_points = trail_step_points
        self.tsl_atr_trail_mult = tsl_atr_trail_mult
        self.tsl_atr_period = tsl_atr_period

        # Mutable state (persisted to DB)
        self.current_stop: float = round_to_tick(entry_price - initial_sl_points)
        self.highest_ltp: float = entry_price
        self.break_even_activated: bool = False
        self.trail_steps_completed: int = 0

    # ── Public ─────────────────────────────────────────────────────────────────

    def update(
        self,
        ltp: float,
        candles_5m: Sequence[Candle] | None = None,
    ) -> float | None:
        """
        Feed a new LTP.  Returns the new stop price if the stop should be
        modified at the broker, otherwise returns None.

        candles_5m is required when tsl_atr_trail_mult > 0 (ATR-dynamic mode).
        It is ignored in fixed-step mode.

        The caller is responsible for sending the modification order.
        """
        self.highest_ltp = max(self.highest_ltp, ltp)

        new_stop = self._calculate_stop(candles_5m)
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
                    mode="atr_dynamic" if self.tsl_atr_trail_mult > 0 else "fixed_step",
                )
            else:
                self.trail_steps_completed += 1
                log_event(
                    logger, "TRAILING_SL_UPDATED",
                    entry=self.entry_price, ltp=ltp,
                    old_stop=old_stop, new_stop=new_stop,
                    steps=self.trail_steps_completed,
                    mode="atr_dynamic" if self.tsl_atr_trail_mult > 0 else "fixed_step",
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

    def _calculate_stop(
        self,
        candles_5m: Sequence[Candle] | None,
    ) -> float | None:
        """
        Compute the desired stop based on highest_ltp.

        Break-even zone: entry_price + break_even_trigger <= highest_ltp
            -> stop = entry_price  (both modes)

        After break-even, two modes diverge:

        Fixed-step (tsl_atr_trail_mult == 0):
            Each additional trail_step_points above break-even:
            -> stop rises by trail_step_points

        ATR-dynamic (tsl_atr_trail_mult > 0):
            stop = highest_ltp - ATR(period) × mult × ATM_delta
            Recomputed fresh on every tick; trail distance scales with
            current volatility.  Falls back to fixed-step if ATR is
            unavailable (insufficient candles).
        """
        be_trigger = self.entry_price + self.break_even_trigger_points
        if self.highest_ltp < be_trigger:
            return None  # not yet in profit territory

        # ── ATR-dynamic mode ──────────────────────────────────────────────────
        if self.tsl_atr_trail_mult > 0 and self.break_even_activated:
            # Break-even has fired; switch to ATR-based floating trail
            atr_val = self._current_atr(candles_5m)
            if atr_val and atr_val > 0:
                trail_dist = round_to_tick(
                    atr_val * self.tsl_atr_trail_mult * _ATM_DELTA
                )
                desired = round_to_tick(self.highest_ltp - trail_dist)
                # Never let the dynamic stop fall below entry (break-even floor)
                return max(desired, self.entry_price)

            # ATR unavailable (cold start / < period candles) — fall through
            # to fixed-step so we never lose trail protection
            logger.debug(
                "ATR-dynamic TSL: ATR unavailable (candles=%d) — using fixed step",
                len(candles_5m) if candles_5m else 0,
            )

        # ── Fixed-step mode (default + ATR fallback) ──────────────────────────
        above_be = self.highest_ltp - be_trigger
        steps_above = int(above_be // self.trail_step_points)
        return self.entry_price + steps_above * self.trail_step_points

    def _current_atr(
        self,
        candles_5m: Sequence[Candle] | None,
    ) -> float | None:
        """Return the latest ATR value from the 5m candle buffer, or None."""
        if not candles_5m:
            return None
        from market.indicators import atr_at
        return atr_at(candles_5m, period=self.tsl_atr_period)
