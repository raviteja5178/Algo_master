"""
ORB Session Qualifier
=====================
Tracks whether the day's Opening Range Breakout is "sustained" by 10:00 IST.

Definition of "sustained":
  After the ORB entry window closes (09:40), the qualifier inspects the FIRST
  completed 5m candle whose timestamp is >= 10:00 IST:
    - CE direction (ORB fired long): that candle's close must still be ABOVE
      the ORB High.
    - PE direction (ORB fired short): that candle's close must still be BELOW
      the ORB Low.
    - If ORB did NOT fire at all by 09:40: the qualifier also checks whether
      price has closed OUTSIDE the ORB range by 10:00, because a strong day
      will have already broken out even without a formal ORB entry.

Consequence when ORB fails:
  A session-lock flag is set.  All NON-ORB, NON-MOMENTUM strategies
  (EMA, VWAP, TRB, PDHL, OB) are blocked from firing between
  10:00 and the MOMENTUM_WINDOW_START (default 13:30).
  The Momentum window is intentionally EXEMPT so the afternoon engine
  still fires on trending days that have a slow morning.

The state is fully per-day: it resets automatically at the first candle
of each new trading day.

Usage in signal_engine.py:
    from strategies.session_qualifier import SessionQualifier
    _sq = SessionQualifier()

    # Call once per candle BEFORE evaluating signals:
    _sq.update(candles_5m, orb_fired_today, orb_direction)

    # Gate non-momentum strategies:
    if _sq.is_blocked(candle_ts):
        return None
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, time

from market.candle_builder import Candle
from strategies.orb_strategy import get_orb_range
from utils.logging_config import log_event

logger = logging.getLogger(__name__)

# The candle at which the qualifier verdict is locked in.
_VERDICT_TIME = time(10, 0)   # 10:00 IST


class SessionQualifier:
    """
    One instance lives for the entire bot session.
    Call update() on every new completed 5m candle.
    Call is_blocked() before each signal evaluation.
    """

    def __init__(self, unblock_time: str = "13:30") -> None:
        """
        Parameters
        ----------
        unblock_time : str
            HH:MM at which the block is lifted (ORB_QUALIFIER_UNBLOCK_TIME).
            Strategies are re-enabled from this time even on failed ORB days.
            Default "13:30" matches the Momentum afternoon window.
        """
        h, m = unblock_time.split(":")
        self._unblock: time = time(int(h), int(m))

        # ── per-day state (reset on date change) ──────────────────────────────
        self._trade_date:    date | None = None   # date this state belongs to
        self._verdict_set:   bool        = False  # True once the 10:00 check ran
        self._orb_sustained: bool        = True   # guilty until proven innocent
        self._logged:        bool        = False  # avoid repeat log lines

    # ── internal reset ───────────────────────────────────────────────────────

    def _reset_for_day(self, today: date) -> None:
        self._trade_date    = today
        self._verdict_set   = False
        self._orb_sustained = True    # default: allow everything
        self._logged        = False

    # ── public API ───────────────────────────────────────────────────────────

    def update(
        self,
        candles_5m: Sequence[Candle],
        *,
        orb_fired: bool = False,
        orb_direction: str | None = None,   # "CE" | "PE" | None
    ) -> None:
        """
        Must be called once per completed 5m candle, BEFORE evaluate_signals().

        Parameters
        ----------
        candles_5m     : full 5m candle buffer (same slice passed to the engine)
        orb_fired      : True if an ORB trade was entered earlier today
        orb_direction  : "CE" or "PE" — direction of the ORB trade (if any)
        """
        if not candles_5m:
            return

        c0 = candles_5m[-1]
        today = c0.timestamp.date()

        # ── day boundary ──────────────────────────────────────────────────────
        if self._trade_date != today:
            self._reset_for_day(today)

        # ── only run the verdict ONCE, at the first candle >= 10:00 ──────────
        if self._verdict_set:
            return

        ts_time = (c0.timestamp.hour, c0.timestamp.minute)
        if ts_time < (10, 0):
            return  # too early — 09:15–09:55 candles, skip

        # ── verdict time reached ──────────────────────────────────────────────
        self._verdict_set = True

        orb_high, orb_low = get_orb_range(candles_5m)
        if orb_high is None or orb_low is None:
            # No ORB range available — can't assess, allow everything
            self._orb_sustained = True
            return

        close = c0.close

        if orb_fired:
            # ORB trade was taken — check if price still respects the break
            if orb_direction == "CE":
                self._orb_sustained = close > orb_high
            elif orb_direction == "PE":
                self._orb_sustained = close < orb_low
            else:
                self._orb_sustained = True
        else:
            # No ORB trade fired (sustain candle failed or ORB disabled).
            # Price outside range counts as an organic breakout — still trending.
            # Price inside range = day is starting choppy → block mid-morning.
            self._orb_sustained = (close > orb_high) or (close < orb_low)

        if not self._orb_sustained and not self._logged:
            self._logged = True
            log_event(
                logger,
                "ORB_QUALIFIER_BLOCKED",
                candle=c0.timestamp.isoformat(),
                close=round(close, 2),
                orb_high=round(orb_high, 2),
                orb_low=round(orb_low, 2),
                orb_fired=orb_fired,
                msg=(
                    "Price closed back inside ORB range at 10:00 — "
                    "EMA/VWAP/TRB/PDHL/OB signals blocked until "
                    f"{self._unblock.strftime('%H:%M')}."
                ),
            )
        elif self._orb_sustained:
            log_event(
                logger,
                "ORB_QUALIFIER_SUSTAINED",
                candle=c0.timestamp.isoformat(),
                close=round(close, 2),
                orb_high=round(orb_high, 2),
                orb_low=round(orb_low, 2),
                orb_fired=orb_fired,
                msg="ORB sustained at 10:00 — all strategies unblocked.",
            )

    def is_blocked(self, candle_ts: "datetime") -> bool:  # noqa: F821
        """
        Returns True when the signal engine should skip non-momentum strategies.

        Blocked when ALL of:
          1. Verdict has been set (10:00 has passed)
          2. ORB was NOT sustained
          3. Current candle is BEFORE the Momentum window start
        """
        if not self._verdict_set:
            return False
        if self._orb_sustained:
            return False
        # After MOM window start — unblock again (afternoon engine can fire)
        candle_time = (candle_ts.hour, candle_ts.minute)
        mom_time    = (self._unblock.hour, self._unblock.minute)
        if candle_time >= mom_time:
            return False
        return True

    @property
    def sustained(self) -> bool:
        """True when the ORB was sustained (or verdict not yet set)."""
        return self._orb_sustained

    @property
    def verdict_set(self) -> bool:
        """True after the 10:00 candle has been evaluated."""
        return self._verdict_set
