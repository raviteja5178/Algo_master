"""
Pivot trade manager — SL / break-even / TSL / targets for CE_PIVOT / PE_PIVOT.

All decisions are made on the SENSEX index price (Pivot, R1/R2/R3, S1/S2/S3,
ATR).  The option-side protective SL order at the broker is derived from the
index stop and only ever moves in the profit direction.

Stage machine:

  INITIAL  stop = signal-candle low/high (structure) ± ATR buffer
  BE       price moved >= be_trigger_r × signal_risk in favour
           → stop = entry + be_buffer_pts  (trade can no longer lose)
  T1       R1 / S1 touched
           → stop = entry + t1_lock_pct × (T1 − entry)   (profit locked)
           → chandelier trail: stop = best − trail_atr_mult × ATR
  T2       R2 / S2 touched
           → stop = T1 + t2_lock_pct × (T2 − T1)         (more profit locked)
           → chandelier trail continues (tighter multiplier if t2_trail_atr_mult set)
  EXIT     stop crossed           → reason SL_HIT / BE_STOP / TSL_HIT
           T3 / R3/S3 touched     → reason TARGET_T3

Single-lot design: SENSEX quantity 20 is one lot, so there is no partial
booking — instead the T1/T2 locks + chandelier trail let the whole lot run
toward T3 while protecting gains at each milestone.

TSL ratchet — the stop ONLY moves in the profit direction (never back).

Stop comparison uses a 0.25 pt epsilon guard to suppress floating-point noise.

ATR refresh: callers may call update_atr(new_atr) whenever a new completed
candle is available so the chandelier trail uses current-session volatility.

Delta refresh: callers may call update_delta(new_delta) as the option moves
deeper ITM/OTM so the option stop tracks the actual option premium accurately.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Sequence

from utils.logging_config import log_event
from utils.price_utils import round_to_tick

logger = logging.getLogger(__name__)

_STATE_FILE = Path(__file__).resolve().parent.parent / ".pivot_trade.json"

# Minimum favourable distance (index pts) below the stop before we trigger.
# Prevents floating-point epsilon from causing spurious exits near the stop.
_STOP_EPSILON = 0.25


class PivotTradeManager:
    # Trail-only mode (Pine engine).  Class-level defaults so manager states
    # saved before this mode existed still load (load() restores via __dict__).
    trail_only: bool = False
    trail_act_r: float = 1.0
    trail_mult: float = 3.0
    # ATR-based triggers (0 = off).  A stale swing stop can sit 4-5 ATR away, so
    # "1R" alone would never arm the trail/BE on a 2-ATR move.
    trail_act_atr: float = 0.0
    be_atr: float = 0.0
    be_buf_atr: float = 0.2
    # Pivot-grid floor lock (Pine trades).  Class defaults keep older saved states loadable.
    grid_mode: bool = False
    grid_exit_at: int = 0          # 0 = no hard target exit, ladder floors only
    grid_buffer: float = 0.0
    grid_levels: list = []         # every grid level ahead of entry, nearest first
    # Grid break-even: once price has covered this fraction of the way from entry to T1,
    # move the stop to the entry price (0 = off).  Saved states without it load as off.
    grid_be_pct: float = 0.0

    def __init__(
        self,
        side: str,
        entry_index: float,
        stop_index: float,
        t1: float,
        t2: float,
        t3: float,
        atr: float,
        option_entry: float,
        *,
        delta: float = 0.4,
        be_trigger_r: float = 1.0,
        be_buffer_pts: float = 5.0,
        t1_lock_pct: float = 0.5,
        t2_lock_pct: float = 0.5,
        trail_atr_mult: float = 1.0,
        t2_trail_atr_mult: float = 0.75,
        hard_sl_cushion: float = 1.25,
        max_sl_pct: float = 0.5,
        signal_risk: float | None = None,
        trail_only: bool = False,
        trail_act_r: float = 1.0,
        trail_mult: float = 3.0,
        trail_act_atr: float = 0.0,
        be_atr: float = 0.0,
        be_buf_atr: float = 0.2,
        max_peak_fallback_pts: float = 0.0,
        grid_mode: bool = False,
        grid_exit_at: int = 0,
        grid_buffer: float = 0.0,
        grid_levels: Sequence[float] | None = None,
        grid_be_pct: float = 0.0,
    ) -> None:
        self.grid_be_pct = max(0.0, grid_be_pct)
        self.grid_mode = grid_mode
        self.grid_exit_at = min(3, max(0, int(grid_exit_at)))
        self.grid_buffer = max(0.0, grid_buffer)
        self.grid_levels = [float(x) for x in (grid_levels or ())]
        self.trail_only = trail_only
        self.trail_act_atr = trail_act_atr
        self.be_atr = be_atr
        self.be_buf_atr = be_buf_atr
        self.trail_act_r = trail_act_r
        self.trail_mult = trail_mult
        self.max_peak_fallback_pts = max_peak_fallback_pts
        self.side = side
        self.sign = 1 if side == "CE" else -1
        self.entry_index = entry_index
        self.stop_index = stop_index
        self.t1, self.t2, self.t3 = t1, t2, t3
        self.atr = atr
        self.option_entry = option_entry
        self.delta = delta
        self.be_trigger_r = be_trigger_r
        self.be_buffer_pts = be_buffer_pts
        self.t1_lock_pct = t1_lock_pct
        self.t2_lock_pct = t2_lock_pct
        self.trail_atr_mult = trail_atr_mult
        self.t2_trail_atr_mult = t2_trail_atr_mult
        self.hard_sl_cushion = hard_sl_cushion
        self.max_sl_pct = max_sl_pct

        # risk used for BE threshold: use the signal-candle risk (setup.risk)
        # when provided so that fill-price slippage does not inflate/deflate the
        # BE trigger level.  Falls back to abs(entry - stop) if not supplied.
        self.risk = (signal_risk if (signal_risk is not None and signal_risk > 0)
                     else abs(entry_index - stop_index))
        self.best_index = entry_index
        self.stage = "INITIAL"
        self.option_stop = self._option_stop_for(stop_index)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _fav(self, price: float) -> float:
        """Signed favourable distance from entry (positive = in profit)."""
        return (price - self.entry_index) * self.sign

    def _option_stop_for(self, stop_index: float) -> float:
        """
        Convert an index stop to an option SL trigger.
        Loss side is widened by hard_sl_cushion (index logic exits first; the
        broker order is the disaster backstop).  Profit side is shrunk by the
        same factor so the broker stop never sits above the real lock level.
        """
        dist = self._fav(stop_index) * self.delta
        dist = dist * self.hard_sl_cushion if dist < 0 else dist / self.hard_sl_cushion
        if dist < 0 and self.max_sl_pct > 0:
            dist = max(dist, -self.option_entry * self.max_sl_pct)
        return max(0.05, round_to_tick(self.option_entry + dist))

    def _move_stop(self, new_stop: float, stage: str) -> bool:
        # Compare at stored precision: a sub-paisa difference would otherwise count as
        # a "move" on every tick (same rounded stop, but a broker/DB update + a trail
        # step counted each time).
        new_stop = round(new_stop, 2)
        if self._fav(new_stop) <= self._fav(self.stop_index):
            logger.debug(
                "PIVOT_STOP_NOOP side=%s stage=%s proposed=%.2f current=%.2f",
                self.side, stage, new_stop, self.stop_index,
            )
            return False
        old = self.stop_index
        self.stop_index = round(new_stop, 2)
        self.stage = stage
        self.option_stop = max(self.option_stop, self._option_stop_for(self.stop_index))
        log_event(logger, "PIVOT_STOP_MOVED", side=self.side, stage=stage,
                  old=old, new=self.stop_index, option_stop=self.option_stop,
                  locked_idx_pts=round(self._fav(self.stop_index), 2))
        return True

    # ── live update helpers ────────────────────────────────────────────────────
    def update_atr(self, new_atr: float) -> None:
        """Refresh the ATR used for the chandelier trail.

        Call this whenever a 5m candle completes so the trail reflects the
        current session's volatility rather than the frozen entry-time ATR.
        Only accepts positive values; silently ignores invalid inputs.
        """
        if new_atr and new_atr > 0:
            self.atr = new_atr

    def update_delta(self, new_delta: float) -> None:
        """Refresh the option delta used for broker SL conversion.

        As the option moves ITM/OTM the actual delta changes.  Updating delta
        keeps the option stop aligned with the real premium behaviour.
        Only accepted in (0, 1] range to prevent nonsensical values.
        """
        if 0 < new_delta <= 1.0:
            self.delta = new_delta

    # ── main entry point (call on every SENSEX tick) ─────────────────────────
    def on_index_price(self, price: float) -> tuple[str, object] | None:
        """
        Returns:
          ("EXIT", reason)            — close the position now
          ("STOP_MOVED", option_stop) — modify the broker SL order to option_stop
          None                        — nothing to do

        Stop comparison uses an epsilon guard (_STOP_EPSILON) so that a single
        floating-point tick that is effectively at the stop does not trigger a
        spurious exit.  The exit fires only when price is clearly through the stop.

        Stage machine:
          INITIAL → BE → T1 → T2 → (exit at T3 or TSL)
        """
        # 1. stop hit
        if self._fav(price) < -_STOP_EPSILON + self._fav(self.stop_index):
            reason = {
                "INITIAL": "PIVOT_SL_HIT",
                "BE":      "PIVOT_BE_STOP",
            }.get(self.stage, "PIVOT_TSL_HIT")
            return ("EXIT", reason)

        # Pivot-grid floor lock (Pine trades): the pivot levels ahead of entry form a
        # ladder.  The Pine stop is untouched until the first level prints; every
        # level price then clears flips polarity (resistance -> support for a CE,
        # support -> resistance for a PE) and the stop ratchets to that level
        # -/+ buffer.  A pullback to the floor exits the trade.  With grid_exit_at
        # 1..3 the trade also exits outright when that target prints; 0 = ladder only.
        if self.grid_mode:
            if self._fav(price) > self._fav(self.best_index):
                self.best_index = price
            if self.grid_exit_at:
                exit_level = (self.t1, self.t2, self.t3)[self.grid_exit_at - 1]
                if self._fav(price) >= self._fav(exit_level):
                    return ("EXIT", f"PIVOT_TARGET_T{self.grid_exit_at}")
            fav_best = self._fav(self.best_index)
            ladder = self.grid_levels or [self.t1, self.t2, self.t3]
            cleared = [lv for lv in ladder if fav_best >= self._fav(lv)]
            moved = False
            if cleared:
                moved = self._move_stop(cleared[-1] - self.sign * self.grid_buffer,
                                        "T1" if len(cleared) == 1 else "T2")
            elif (self.grid_be_pct > 0 and self.stage == "INITIAL"
                  and fav_best >= self.grid_be_pct * self._fav(self.t1)):
                moved = self._move_stop(self.entry_index, "BE")
            return ("STOP_MOVED", self.option_stop) if moved else None

        # 1b. peak fallback guard (if price gives back >= max_peak_fallback_pts from high-watermark)
        if self.max_peak_fallback_pts > 0 and self.stage in ("BE", "T1", "T2", "TRAIL"):
            if (self._fav(self.best_index) - self._fav(price)) >= self.max_peak_fallback_pts:
                return ("EXIT", "PIVOT_PEAK_FALLBACK")

        # Trail-only (Pine engine): no fixed target, no break-even, no T1/T2
        # locks.  The initial stop stays until profit reaches trail_act_r x risk,
        # then a wide ATR chandelier ratchets behind the best price.
        if self.trail_only:
            if self._fav(price) > self._fav(self.best_index):
                self.best_index = price
            fav_best = self._fav(self.best_index)
            moved = False
            # Break-even (slightly in profit) once price has run be_atr x ATR.
            if (self.be_atr > 0 and self.stage == "INITIAL"
                    and fav_best >= self.be_atr * self.atr):
                moved |= self._move_stop(
                    self.entry_index + self.sign * self.be_buf_atr * self.atr, "BE")
            # Chandelier trail from the EARLIER of 1R or trail_act_atr x ATR.
            act = self.trail_act_r * self.risk
            if self.trail_act_atr > 0:
                act = min(act, self.trail_act_atr * self.atr)
            if self.trail_mult > 0 and fav_best >= act:
                moved |= self._move_stop(
                    self.best_index - self.sign * self.trail_mult * self.atr, "TRAIL")
            return ("STOP_MOVED", self.option_stop) if moved else None

        # 2. final target T3
        if self._fav(price) >= self._fav(self.t3):
            return ("EXIT", "PIVOT_TARGET_T3")

        if self._fav(price) > self._fav(self.best_index):
            self.best_index = price
        moved = False

        # 3a. T2 reached → lock more profit, tighten trail multiplier.
        #     Evaluated before T1 so we don't double-fire if T2 was just hit.
        if self.stage == "T1" and self._fav(self.best_index) >= self._fav(self.t2):
            lock = (self.t1 + self.sign * self.t2_lock_pct
                    * abs(self._fav(self.t2) - self._fav(self.t1)))
            moved |= self._move_stop(lock, "T2")
            self.stage = "T2"
            return ("STOP_MOVED", self.option_stop) if moved else None

        # 3b. T1 reached → lock profit, start chandelier trail.
        #     Return immediately so the chandelier fires on the NEXT tick once
        #     best_index has been updated, preventing a double-fire this tick.
        if self.stage not in ("T1", "T2") and self._fav(self.best_index) >= self._fav(self.t1):
            lock = self.entry_index + self.sign * self.t1_lock_pct * self._fav(self.t1)
            moved |= self._move_stop(lock, "T1")
            self.stage = "T1"
            return ("STOP_MOVED", self.option_stop) if moved else None

        # 4. break-even after be_trigger_r × risk (only in INITIAL stage)
        if self.stage == "INITIAL" and self._fav(self.best_index) >= self.be_trigger_r * self.risk:
            moved |= self._move_stop(
                self.entry_index + self.sign * self.be_buffer_pts, "BE"
            )

        # 5. chandelier trail after T1 / T2
        if self.stage in ("T1", "T2") and self.trail_atr_mult > 0:
            mult = (self.t2_trail_atr_mult
                    if self.stage == "T2" and self.t2_trail_atr_mult > 0
                    else self.trail_atr_mult)
            moved |= self._move_stop(
                self.best_index - self.sign * mult * self.atr, self.stage
            )

        return ("STOP_MOVED", self.option_stop) if moved else None

    # ── persistence (restart recovery) ────────────────────────────────────────
    def save(self, trade_id: str) -> None:
        try:
            _STATE_FILE.write_text(json.dumps({"trade_id": trade_id, **self.__dict__}))
        except Exception as exc:
            logger.warning("Pivot trade state save failed: %s", exc)

    @classmethod
    def load(cls, trade_id: str) -> "PivotTradeManager | None":
        try:
            d = json.loads(_STATE_FILE.read_text())
        except Exception:
            return None
        if d.pop("trade_id", None) != trade_id:
            return None
        obj = cls.__new__(cls)
        obj.__dict__.update(d)
        return obj

    @staticmethod
    def clear() -> None:
        try:
            _STATE_FILE.unlink(missing_ok=True)
        except Exception:
            pass
