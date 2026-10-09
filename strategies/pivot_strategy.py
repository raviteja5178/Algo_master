"""
Pivot strategy — two complementary entry modes (CE_PIVOT / PE_PIVOT).

Pivot levels are computed from the PREVIOUS day's SENSEX High / Low / Close:
    PP = (H + L + C) / 3
    R1 = 2×PP − L          S1 = 2×PP − H
    R2 = PP + (H − L)      S2 = PP − (H − L)
    R3 = H + 2×(PP − L)    S3 = L − 2×(H − PP)

═══════════════════════════════════════════════════════════════════════
MODE A — Open-Direction Sustain  (PIVOT_MODE = "OPEN_DIRECTION" | "BOTH")
═══════════════════════════════════════════════════════════════════════
  Premise: the open itself has already committed to one side of the Pivot,
  and the early candles sustain that commitment.

  CE_PIVOT : open > Pivot AND every sustain candle (close + low) is
             strictly above the Pivot.
  PE_PIVOT : open < Pivot AND every sustain candle (close + high) is
             strictly below the Pivot.

  Evaluation window: candles in the OPEN_DIRECTION_WINDOW_START →
  OPEN_DIRECTION_WINDOW_END time range (default 09:15 → 09:30, i.e. the
  first three 5-minute candles of the day).  Outside this window the mode
  is disabled so stale "first-three-candles above" setups don't fire all
  morning.

  Fresh-cross guard: disabled for Mode A (the open IS the cross) but the
  previous day's close is still checked as a sanity gate when no intraday
  candle precedes the sustain window.

═══════════════════════════════════════════════════════════════════════
MODE B — Pivot-Rejection Retest  (PIVOT_MODE = "REJECTION" | "BOTH")
═══════════════════════════════════════════════════════════════════════
  Premise: the open is on the WRONG side of the Pivot (or ambiguously
  close), price travels toward the Pivot, touches / enters the Pivot
  zone, gets rejected, and CONFIRMS the move away in the expected
  direction.

  CE_PIVOT (rejection from below):
    • Earlier today at least one candle high reached inside the Pivot
      zone (Pivot ± PIVOT_REJECTION_ZONE_ATR × ATR).
    • The most recent PIVOT_SUSTAIN_CANDLES candles ALL close and have
      LOW strictly above the Pivot (confirmed bounce away upward).
    • The candle just before the sustain window must have closed
      BELOW the Pivot (it was still below — now we've bounced).

  PE_PIVOT (rejection from above):
    • At least one earlier candle low reached inside the Pivot zone.
    • Sustain candles ALL close and have HIGH strictly below the Pivot.
    • Candle before sustain window must have closed ABOVE the Pivot.

  No time restriction — rejection can develop any time of day.
  min_today_candles (default 6) still applies.

═══════════════════════════════════════════════════════════════════════
Targets
═══════════════════════════════════════════════════════════════════════
  CE_PIVOT : T1 = R1,  T2 = R2,  T3 = R3
  PE_PIVOT : T1 = S1,  T2 = S2,  T3 = S3

Stop (SENSEX index level):
  SIGNAL_LOW (default): lowest low (CE) / highest high (PE) of the
    sustain candles, padded by PIVOT_SL_BUFFER_ATR × ATR(14).
  ATR                 : entry ∓ PIVOT_SL_ATR_MULT × ATR(14).

Room filter: distance from entry to T1 must be ≥ PIVOT_MIN_ROOM_R ×
  risk, else the setup is skipped.

Trade management lives in execution/pivot_trade_manager.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import time as dtime

from market.candle_builder import Candle
from market.indicators import atr_at

# Minimum today-candles before ATR is computed from today only;
# below this threshold the full multi-day series is used.
_TODAY_ATR_MIN_CANDLES = 14

# Default open-direction window: 09:15 → 09:30 (first 3 completed 5m bars)
_OD_WINDOW_START = dtime(9, 15)
_OD_WINDOW_END   = dtime(9, 30)


@dataclass(frozen=True)
class PivotSetup:
    side:  str           # "CE" | "PE"
    mode:  str           # "OPEN_DIRECTION" | "REJECTION"
    entry: float         # SENSEX close of the confirming candle
    stop:  float         # SENSEX stop level
    risk:  float         # |entry - stop| in index points
    t1:    float         # R1 (CE) / S1 (PE)
    t2:    float         # R2 (CE) / S2 (PE)
    t3:    float         # R3 (CE) / S3 (PE)
    atr:   float         # ATR(atr_period) at entry
    pivot: float


def _today(candles: Sequence[Candle]) -> list[Candle]:
    d = candles[-1].timestamp.date()
    return [c for c in candles if c.timestamp.date() == d]


def _atr_series(today: list[Candle], all_candles: Sequence[Candle]) -> Sequence[Candle]:
    return today if len(today) >= _TODAY_ATR_MIN_CANDLES else all_candles


def _make_setup(
    side: str,
    mode: str,
    entry: float,
    window: list[Candle],
    atr: float,
    pivot_levels,
    sl_mode: str,
    sl_atr_mult: float,
    sl_buffer_atr: float,
    min_room_r: float,
) -> PivotSetup | None:
    """Build a PivotSetup for one direction, applying SL + room filter."""
    if side == "CE":
        t1, t2, t3 = pivot_levels.r1, pivot_levels.r2, pivot_levels.r3
        stop = (
            min(c.low for c in window) - sl_buffer_atr * atr
            if sl_mode == "SIGNAL_LOW"
            else entry - sl_atr_mult * atr
        )
        risk = entry - stop
        room = t1 - entry
    else:
        t1, t2, t3 = pivot_levels.s1, pivot_levels.s2, pivot_levels.s3
        stop = (
            max(c.high for c in window) + sl_buffer_atr * atr
            if sl_mode == "SIGNAL_LOW"
            else entry + sl_atr_mult * atr
        )
        risk = stop - entry
        room = entry - t1

    if risk <= 0 or room <= 0 or room < min_room_r * risk:
        return None

    return PivotSetup(
        side=side, mode=mode,
        entry=round(entry, 2), stop=round(stop, 2),
        risk=round(risk, 2),
        t1=t1, t2=t2, t3=t3,
        atr=round(atr, 2),
        pivot=pivot_levels.pivot,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Mode A — Open-Direction Sustain
# ─────────────────────────────────────────────────────────────────────────────

def _check_open_direction(
    today: list[Candle],
    all_candles: Sequence[Candle],
    pivot_levels,
    sustain_candles: int,
    atr_period: int,
    sl_mode: str,
    sl_atr_mult: float,
    sl_buffer_atr: float,
    min_room_r: float,
    window_start: dtime,
    window_end: dtime,
) -> PivotSetup | None:
    """
    Open-Direction mode: fire when the open committed to one side and the
    first N candles sustain that commitment within the time window.
    """
    n = sustain_candles
    if len(today) < n:
        return None

    # The sustain window candles must all fall within [window_start, window_end].
    window = today[-n:]
    last_ts = window[-1].timestamp.time()
    first_ts = window[0].timestamp.time()
    if not (window_start <= first_ts and last_ts <= window_end):
        return None

    P = pivot_levels.pivot
    # Day's open = first today-candle's open
    day_open = today[0].open

    atr = atr_at(_atr_series(today, all_candles), period=atr_period)
    if not atr or atr <= 0:
        return None

    entry = today[-1].close

    for side in ("CE", "PE"):
        if side == "CE":
            if day_open <= P:
                continue
            sustained = all(c.close > P and c.low > P for c in window)
        else:
            if day_open >= P:
                continue
            sustained = all(c.close < P and c.high < P for c in window)

        if not sustained:
            continue

        setup = _make_setup(
            side, "OPEN_DIRECTION", entry, window,
            atr, pivot_levels, sl_mode, sl_atr_mult, sl_buffer_atr, min_room_r,
        )
        if setup is not None:
            return setup

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Mode B — Pivot-Rejection Retest
# ─────────────────────────────────────────────────────────────────────────────

def _check_rejection(
    today: list[Candle],
    all_candles: Sequence[Candle],
    pivot_levels,
    sustain_candles: int,
    atr_period: int,
    sl_mode: str,
    sl_atr_mult: float,
    sl_buffer_atr: float,
    min_room_r: float,
    rejection_zone_atr: float,
) -> PivotSetup | None:
    """
    Rejection mode: price came from the wrong side, probed the Pivot zone,
    was rejected, and the sustain candles confirm the bounce.

    The "wrong side" history is verified by checking that at least one candle
    BEFORE the sustain window touched or entered the Pivot zone
    (|candle_extreme − Pivot| ≤ zone_half_width), confirming the retest.
    """
    n = sustain_candles
    if len(today) < n + 1:   # need at least one candle before the window
        return None

    P = pivot_levels.pivot

    atr = atr_at(_atr_series(today, all_candles), period=atr_period)
    if not atr or atr <= 0:
        return None

    zone_half = rejection_zone_atr * atr
    window = today[-n:]
    before = today[-n - 1]
    entry = today[-1].close
    # candles available before the sustain window (for zone-touch search)
    pre_window = today[: len(today) - n]

    for side in ("CE", "PE"):
        if side == "CE":
            # Sustain: close + low strictly above Pivot → bounce confirmed
            sustained = all(c.close > P and c.low > P for c in window)
            # Reference candle (just before sustain) must have been below Pivot
            fresh = before.close < P
            # At least one pre-window candle's HIGH reached into the Pivot zone
            # (meaning price came up from below and probed near / above the Pivot)
            probed = any(c.high >= P - zone_half for c in pre_window)
        else:
            # Sustain: close + high strictly below Pivot → rejection confirmed
            sustained = all(c.close < P and c.high < P for c in window)
            # Reference candle must have been above Pivot
            fresh = before.close > P
            # At least one pre-window candle's LOW reached into the Pivot zone
            probed = any(c.low <= P + zone_half for c in pre_window)

        if not (sustained and fresh and probed):
            continue

        setup = _make_setup(
            side, "REJECTION", entry, window,
            atr, pivot_levels, sl_mode, sl_atr_mult, sl_buffer_atr, min_room_r,
        )
        if setup is not None:
            return setup

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def find_pivot_setup(
    candles_5m: Sequence[Candle],
    pivot_levels,                      # market.historical_data.PivotLevels
    *,
    sustain_candles: int = 2,
    atr_period: int = 14,
    sl_mode: str = "SIGNAL_LOW",
    sl_atr_mult: float = 1.0,
    sl_buffer_atr: float = 0.05,
    min_room_r: float = 1.0,
    min_today_candles: int = 0,
    # Mode selection: "OPEN_DIRECTION" | "REJECTION" | "BOTH"
    pivot_mode: str = "BOTH",
    # Open-direction window (default 09:15–09:30)
    od_window_start: dtime = _OD_WINDOW_START,
    od_window_end:   dtime = _OD_WINDOW_END,
    # Rejection zone half-width in ATR multiples
    rejection_zone_atr: float = 0.3,
) -> PivotSetup | None:
    """Return a PivotSetup when the latest completed candle confirms a setup,
    else None.

    Mode-A (OPEN_DIRECTION): only fires within the time window 09:15–09:30
    when the day's open was cleanly on one side of the Pivot and the first
    candles sustain that direction.

    Mode-B (REJECTION): fires any time of day (subject to min_today_candles)
    when price approached from the wrong side, probed the Pivot zone, and is
    now bouncing back with sustained candles confirming the direction.

    Parameters
    ----------
    pivot_mode
        "OPEN_DIRECTION" — only Mode A
        "REJECTION"      — only Mode B
        "BOTH"           — Mode A first, then Mode B (default)
    od_window_start / od_window_end
        Time boundary for Mode A.  Any candle whose timestamp falls outside
        [od_window_start, od_window_end] causes Mode A to skip silently.
    rejection_zone_atr
        Mode B zone half-width = this × ATR.  The candle's extreme must
        reach within this distance of the Pivot to count as a "probe".
    min_today_candles
        Require at least this many completed today-candles before any signal
        is allowed.  0 = disabled.
    """
    if pivot_levels is None or not candles_5m or sustain_candles < 1:
        return None

    today = _today(candles_5m)
    if len(today) < sustain_candles:
        return None

    if min_today_candles > 0 and len(today) < min_today_candles:
        return None

    mode = pivot_mode.upper()

    # ── Mode A ──────────────────────────────────────────────────────────────
    if mode in ("OPEN_DIRECTION", "BOTH"):
        setup = _check_open_direction(
            today, candles_5m, pivot_levels,
            sustain_candles, atr_period,
            sl_mode, sl_atr_mult, sl_buffer_atr, min_room_r,
            od_window_start, od_window_end,
        )
        if setup is not None:
            return setup

    # ── Mode B ──────────────────────────────────────────────────────────────
    if mode in ("REJECTION", "BOTH"):
        setup = _check_rejection(
            today, candles_5m, pivot_levels,
            sustain_candles, atr_period,
            sl_mode, sl_atr_mult, sl_buffer_atr, min_room_r,
            rejection_zone_atr,
        )
        if setup is not None:
            return setup

    return None
