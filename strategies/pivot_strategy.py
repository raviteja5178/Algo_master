"""
Pivot strategy — two complementary entry modes (CE_PIVOT / PE_PIVOT).

Pivot levels are computed from the PREVIOUS day's SENSEX High / Low / Close
(see market.historical_data.compute_pivot_levels; PIVOT_FORMULA selects the formula).
Default FIBONACCI (range = H − L):
    PP = (H + L + C) / 3
    R1 = PP + 0.382×range   S1 = PP − 0.382×range
    R2 = PP + 0.618×range   S2 = PP − 0.618×range
    R3 = PP + 1.000×range   S3 = PP − 1.000×range
TRADITIONAL (PIVOT_FORMULA=TRADITIONAL):
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

  Additional quality filters (all opt-in, default OFF to preserve existing
  behaviour; enable via .env):

  min_od_gap_atr  (PIVOT_OD_MIN_GAP_ATR, default 0.0):
      Require the day's open to be at least this many ATR multiples away
      from Pivot before the OD mode is allowed to fire.  When the open is
      within the noise band around Pivot the market has not committed to a
      direction — it is hovering in the pivot zone.
      Example: atr=114, gap_atr=0.5 → open must be ≥57 pts from Pivot.
      Root-cause Oct 9: open was only 33 pts (0.29×ATR) below Pivot — too
      close to be considered a genuine below-Pivot open.  A value of 0.4
      would have blocked the PE_PIVOT that day.

  first_candle_confirm  (PIVOT_OD_FIRST_CANDLE_CONFIRM, default False):
      Require the first today-candle's body to confirm the OD direction.
      CE: first candle must close ABOVE its open (bullish body).
      PE: first candle must close BELOW its open (bearish body).
      Prevents entering a PE when the first candle was a doji or a candle
      that probed Pivot from below (bullish signal, not bearish).

  max_first_wick_atr  (PIVOT_OD_MAX_FIRST_WICK_ATR, default 0.0):
      For PE: block if the first candle's UPPER wick ≥ this × ATR.
      For CE: block if the first candle's LOWER wick ≥ this × ATR.
      A long upper wick on the first candle reaching into / near Pivot
      (as happened on Oct 9) signals a bullish probe — not a clean
      below-Pivot open.  0.0 = disabled.
      Root-cause Oct 9: first candle high=71871.28 touched Pivot exactly;
      upper wick = high − close = 71871.28 − 71838.83 = 32.45 pts ≈ 0.28×ATR.
      Setting max_first_wick_atr=0.25 would have blocked that trade.

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
MODE C — Cross-and-Acceptance  (opt-in: enable_acceptance=True)
═══════════════════════════════════════════════════════════════════════
  Premise: price was on the wrong side of the Pivot (a candle CLOSED on
  that side, or the day OPENED there), crossed it, and is now ACCEPTED on
  the new side.  This catches the classic trend day that opens below the
  Pivot, reclaims it and never looks back (Oct 9 2026: open 95 pts below
  P, crossed at 09:25, every candle from 09:30 held above P, day high
  72669 ≈ 800 pts above P).

  Modes A / B miss this when the cross candle itself wicks back through
  the Pivot: B then never sees "closed-below candle directly followed by
  N clean candles", and A needs the open on the trade side.

  CE_PIVOT:
    • Reference = last today-candle that CLOSED below Pivot (or the day
      open, if it was below Pivot and no later candle closed below).
    • Every candle after the reference closes above Pivot.
    • The latest N candles are CLEAN: close AND low strictly above Pivot.
    • This is the FIRST clean N-window after the reference → one signal
      per cross, no repeated entries on every later candle.
  PE_PIVOT mirrors with highs below Pivot.

  No time restriction; room filter + min_today_candles still apply.

═══════════════════════════════════════════════════════════════════════
BOUNCE — S/R Level Bounce / Rejection  (opt-in: bounce_zone_atr > 0)
═══════════════════════════════════════════════════════════════════════
  Premise: price approaches a pivot level (S3..S1, P, R1..R3) from one
  side, wicks into its zone (level ± bounce_zone_atr × ATR) and the SAME
  candle closes back on the original side with a confirming body.

  CE_PIVOT (support bounce): previous candle closed above the level,
    signal candle low ≤ level + zone, close > level, bullish body, close
    in the upper half of the range.
  PE_PIVOT (resistance rejection): mirror image.

  Stop   : below / above the zone or signal-candle extreme, padded by
           PIVOT_SL_BUFFER_ATR × ATR.
  Targets: the next three levels in the trade direction.
  Checked last, so Modes A / B / C keep priority.  One signal per touch.

  Optional quality filters (default OFF):
    PIVOT_BOUNCE_MIN_RANGE_ATR  signal candle range >= N × ATR
    PIVOT_BOUNCE_MIN_WICK_PCT   rejection wick >= N × candle range
    PIVOT_BOUNCE_TREND_EMA      CE only above EMA(N), PE only below
    PIVOT_BOUNCE_CONFIRM_NEXT   next candle must close beyond the signal
                                candle's high (CE) / low (PE) → entry there

═══════════════════════════════════════════════════════════════════════
SWING PIVOT — Fractal Swing High/Low Breakout (TradingView Pivot Reversal)
═══════════════════════════════════════════════════════════════════════
  Premise: price forms fractal swing highs/lows using lookback left/right
  bars (default Left=4, Right=2). When price breaks out above the latest
  confirmed swing high (CE) or breaks down below the latest confirmed swing
  low (PE), enter in the breakout direction.

  Filters & Risk:
    • Trend alignment via EMA (e.g. 50 EMA): CE only when close > EMA,
      PE only when close < EMA.
    • Stop Loss: placed at recent structural swing low/high or ATR multiple.
    • Targets: calibrated via Risk-to-Reward multiples (T1=1.5R, T2=2.5R, T3=3.5R).

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
from market.indicators import atr_at, ema

# Minimum today-candles before ATR is computed from today only;
# below this threshold the full multi-day series is used.
_TODAY_ATR_MIN_CANDLES = 14

# Default open-direction window: 09:15 → 09:30 (first 3 completed 5m bars)
_OD_WINDOW_START = dtime(9, 15)
_OD_WINDOW_END   = dtime(9, 30)


@dataclass(frozen=True)
class PivotSetup:
    side:  str           # "CE" | "PE"
    mode:  str           # "OPEN_DIRECTION" | "REJECTION" | "ACCEPTANCE" | "BOUNCE"
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
    targets: tuple[float, float, float] | None = None,
    stop: float | None = None,
) -> PivotSetup | None:
    """Build a PivotSetup for one direction, applying SL + room filter.

    ``targets`` / ``stop`` override the default R1-R3 / S1-S3 targets and the
    sl_mode-derived stop (used by the level-bounce setup).
    """
    if side == "CE":
        t1, t2, t3 = targets or (pivot_levels.r1, pivot_levels.r2, pivot_levels.r3)
        if stop is None:
            stop = (
                min(c.low for c in window) - sl_buffer_atr * atr
                if sl_mode == "SIGNAL_LOW"
                else entry - sl_atr_mult * atr
            )
        risk = entry - stop
        room = t1 - entry
    else:
        t1, t2, t3 = targets or (pivot_levels.s1, pivot_levels.s2, pivot_levels.s3)
        if stop is None:
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
    min_od_gap_atr: float = 0.0,
    first_candle_confirm: bool = False,
    max_first_wick_atr: float = 0.0,
) -> PivotSetup | None:
    """
    Open-Direction mode: fire when the open committed to one side and the
    first N candles sustain that commitment within the time window.

    Optional quality filters (all default-OFF):
      min_od_gap_atr      — open must be >= this × ATR away from Pivot.
      first_candle_confirm — first candle body must confirm the direction.
      max_first_wick_atr  — first candle counter-direction wick must be
                            < this × ATR (0 = disabled).
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
    first_candle = today[0]

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

        # ── Filter 1: open must be far enough from Pivot ───────────────────
        # Prevents OD trades when the open is inside the Pivot noise band.
        if min_od_gap_atr > 0:
            gap = abs(day_open - P)
            if gap < min_od_gap_atr * atr:
                import logging as _log
                _log.getLogger(__name__).info(
                    "[OD_BLOCKED_GAP] side=%s day_open=%.2f pivot=%.2f "
                    "gap=%.2f min_gap=%.2f (%.2f×ATR)",
                    side, day_open, P, gap, min_od_gap_atr * atr, min_od_gap_atr,
                )
                continue

        # ── Filter 2: first candle body must confirm direction ─────────────
        # Prevents OD trades when the opening candle is a doji or moves
        # against the expected direction (e.g. bullish first candle on PE).
        if first_candle_confirm:
            if side == "CE" and first_candle.close <= first_candle.open:
                import logging as _log
                _log.getLogger(__name__).info(
                    "[OD_BLOCKED_FIRST_CANDLE] side=CE first_candle: "
                    "open=%.2f close=%.2f — bearish/doji body, CE blocked",
                    first_candle.open, first_candle.close,
                )
                continue
            if side == "PE" and first_candle.close >= first_candle.open:
                import logging as _log
                _log.getLogger(__name__).info(
                    "[OD_BLOCKED_FIRST_CANDLE] side=PE first_candle: "
                    "open=%.2f close=%.2f — bullish/doji body, PE blocked",
                    first_candle.open, first_candle.close,
                )
                continue

        # ── Filter 3: first candle counter-wick must not probe Pivot ──────
        # A long upper wick on the first candle toward Pivot on a PE setup
        # (or long lower wick on CE) signals that buyers (sellers) tested
        # Pivot and were not fully rejected — the direction is uncertain.
        if max_first_wick_atr > 0:
            max_wick = max_first_wick_atr * atr
            if side == "PE":
                # upper wick = high - max(open, close)
                upper_wick = first_candle.high - max(first_candle.open, first_candle.close)
                if upper_wick >= max_wick:
                    import logging as _log
                    _log.getLogger(__name__).info(
                        "[OD_BLOCKED_FIRST_WICK] side=PE upper_wick=%.2f "
                        "max_wick=%.2f (%.2f×ATR=%.2f) — bullish probe on first candle",
                        upper_wick, max_wick, max_first_wick_atr, atr,
                    )
                    continue
            else:  # CE
                # lower wick = min(open, close) - low
                lower_wick = min(first_candle.open, first_candle.close) - first_candle.low
                if lower_wick >= max_wick:
                    import logging as _log
                    _log.getLogger(__name__).info(
                        "[OD_BLOCKED_FIRST_WICK] side=CE lower_wick=%.2f "
                        "max_wick=%.2f (%.2f×ATR=%.2f) — bearish probe on first candle",
                        lower_wick, max_wick, max_first_wick_atr, atr,
                    )
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
# Level Bounce / Rejection (support bounce → CE, resistance rejection → PE)
# ─────────────────────────────────────────────────────────────────────────────

def _is_bounce(c: Candle, prev: Candle, level: float, zone_half: float, side: str) -> bool:
    """True when ``c`` is a confirmed rejection of ``level``.

    CE (support): prev closed above the level (approach from above), ``c``
    wicked into the zone (low <= level + zone), closed back above the level
    with a bullish body and its close in the upper half of the range.
    PE (resistance) mirrors.
    """
    rng = c.high - c.low
    if rng <= 0:
        return False
    if side == "CE":
        return (prev.close > level and c.low <= level + zone_half
                and c.close > level and c.close > c.open
                and (c.close - c.low) >= 0.5 * rng)
    return (prev.close < level and c.high >= level - zone_half
            and c.close < level and c.close < c.open
            and (c.high - c.close) >= 0.5 * rng)


def _check_bounce(
    today: list[Candle],
    all_candles: Sequence[Candle],
    pivot_levels,
    atr_period: int,
    sl_buffer_atr: float,
    min_room_r: float,
    zone_atr: float,
    min_range_atr: float = 0.0,
    min_wick_pct: float = 0.0,
    trend_ema: int = 0,
    confirm_next: bool = False,
) -> PivotSetup | None:
    """Bounce off a support level (CE) or rejection at a resistance (PE).

    Levels: S3..S1, Pivot, R1..R3.  The nearest level to price is tested first.
    Stop  : beyond the zone / signal-candle extreme, padded by sl_buffer_atr×ATR.
    Target: the next three levels in the trade direction.
    Fires once per touch: skipped when the candle before the signal candle was
    itself a bounce of the same level.

    Optional quality filters (all default OFF):
      min_range_atr — signal candle range must be >= this × ATR.
      min_wick_pct  — rejection wick (CE lower / PE upper) must be >= this
                      fraction of the signal candle range.
      trend_ema     — CE only when entry close > EMA(trend_ema); PE only
                      when below.  0 = disabled.
      confirm_next  — the signal candle is the PREVIOUS candle; the latest
                      candle must close above its high (CE) / below its
                      low (PE).  Entry = confirmation candle close.
    """
    need = 3 if confirm_next else 2
    if len(today) < need:
        return None

    atr = atr_at(_atr_series(today, all_candles), period=atr_period)
    if not atr or atr <= 0:
        return None

    zone_half = zone_atr * atr
    levels = sorted({pivot_levels.s3, pivot_levels.s2, pivot_levels.s1, pivot_levels.pivot,
                     pivot_levels.r1, pivot_levels.r2, pivot_levels.r3})
    k = -2 if confirm_next else -1           # index of the signal candle
    c, prev = today[k], today[k - 1]
    prev2 = today[k - 2] if len(today) >= -k + 2 else None
    last = today[-1]
    entry = last.close

    trend = None
    if trend_ema > 0:
        series = ema([x.close for x in all_candles], trend_ema)
        trend = series[-1] if series else None
        if trend is None:
            return None

    rng = c.high - c.low
    if min_range_atr > 0 and rng < min_range_atr * atr:
        return None

    for side in ("CE", "PE"):
        if trend is not None and (entry <= trend if side == "CE" else entry >= trend):
            continue
        if min_wick_pct > 0:
            wick = (min(c.open, c.close) - c.low) if side == "CE" else (c.high - max(c.open, c.close))
            if wick < min_wick_pct * rng:
                continue
        if confirm_next and not (last.close > c.high if side == "CE" else last.close < c.low):
            continue

        if side == "CE":
            candidates = sorted((lv for lv in levels if lv < c.close), reverse=True)
        else:
            candidates = sorted(lv for lv in levels if lv > c.close)

        for level in candidates:
            if not _is_bounce(c, prev, level, zone_half, side):
                continue
            if prev2 is not None and _is_bounce(prev, prev2, level, zone_half, side):
                continue   # already signalled on this touch

            if side == "CE":
                stop = min(c.low, level - zone_half) - sl_buffer_atr * atr
                ahead = [lv for lv in levels if lv > entry]
            else:
                stop = max(c.high, level + zone_half) + sl_buffer_atr * atr
                ahead = sorted((lv for lv in levels if lv < entry), reverse=True)
            if not ahead:
                continue
            t1, t2, t3 = (ahead + [ahead[-1]] * 2)[:3]

            setup = _make_setup(
                side, "BOUNCE", entry, [c], atr, pivot_levels,
                "SIGNAL_LOW", 0.0, sl_buffer_atr, min_room_r,
                targets=(t1, t2, t3), stop=stop,
            )
            if setup is not None:
                return setup

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Swing Pivot Reversal / Breakout (Fractal Pivot High / Low Breakout)
# ─────────────────────────────────────────────────────────────────────────────

def _check_swing_pivot(
    today: list[Candle],
    all_candles: Sequence[Candle],
    pivot_levels,
    atr_period: int,
    left_bars: int = 4,
    right_bars: int = 2,
    trend_ema: int = 50,
    rr_t1: float = 1.5,
    rr_t2: float = 2.5,
    rr_t3: float = 3.5,
    use_atr_sl: bool = False,
    sl_atr_mult: float = 1.2,
    sl_buffer_atr: float = 0.05,
    min_room_r: float = 1.0,
) -> PivotSetup | None:
    """Fractal Swing High/Low breakout strategy.

    Finds the latest confirmed pivot high and pivot low in recent candles.
    Fires CE on fresh breakout above pivot high (with close > EMA if enabled).
    Fires PE on fresh breakdown below pivot low (with close < EMA if enabled).
    """
    total_candles = len(all_candles)
    min_needed = left_bars + right_bars + 2
    if total_candles < min_needed or len(today) < 2:
        return None

    atr = atr_at(_atr_series(today, all_candles), period=atr_period)
    if not atr or atr <= 0:
        return None

    last_candle = all_candles[-1]
    prev_candle = all_candles[-2]
    entry = last_candle.close

    # Trend filter via EMA
    trend = None
    if trend_ema > 0:
        series = ema([x.close for x in all_candles], trend_ema)
        trend = series[-1] if series else None
        if trend is None:
            return None

    # Scan backwards for the latest confirmed pivot high and pivot low
    hprice = None
    lprice = None

    # We only scan up to the candle that could be confirmed by right_bars
    # A pivot at bar k is confirmed at bar k + right_bars <= total_candles - 1
    max_k = total_candles - 1 - right_bars
    min_k = max(0, total_candles - 60) # lookback up to 60 candles

    for k in range(max_k, min_k - 1, -1):
        if hprice is None:
            cand_h = all_candles[k].high
            is_ph = True
            for j in range(max(0, k - left_bars), min(total_candles, k + right_bars + 1)):
                if j != k and all_candles[j].high >= cand_h:
                    is_ph = False
                    break
            if is_ph:
                hprice = cand_h

        if lprice is None:
            cand_l = all_candles[k].low
            is_pl = True
            for j in range(max(0, k - left_bars), min(total_candles, k + right_bars + 1)):
                if j != k and all_candles[j].low <= cand_l:
                    is_pl = False
                    break
            if is_pl:
                lprice = cand_l

        if hprice is not None and lprice is not None:
            break

    # ── Check CE Breakout (Cross above Swing High) ──────────────────────────
    if hprice is not None:
        # Fresh cross: prior candle high <= hprice, current candle high > hprice
        if prev_candle.high <= hprice and last_candle.high > hprice:
            if trend is None or entry > trend:
                # Determine SL: structural swing low or ATR
                if use_atr_sl or lprice is None:
                    stop = entry - sl_atr_mult * atr
                else:
                    stop = lprice - sl_buffer_atr * atr
                risk = entry - stop
                if risk > 0:
                    t1 = entry + rr_t1 * risk
                    t2 = entry + rr_t2 * risk
                    t3 = entry + rr_t3 * risk
                    setup = _make_setup(
                        "CE", "SWING_PIVOT", entry, [last_candle], atr, pivot_levels,
                        "SIGNAL_LOW", 0.0, sl_buffer_atr, min_room_r,
                        targets=(t1, t2, t3), stop=stop,
                    )
                    if setup is not None:
                        return setup

    # ── Check PE Breakdown (Cross below Swing Low) ──────────────────────────
    if lprice is not None:
        # Fresh cross: prior candle low >= lprice, current candle low < lprice
        if prev_candle.low >= lprice and last_candle.low < lprice:
            if trend is None or entry < trend:
                # Determine SL: structural swing high or ATR
                if use_atr_sl or hprice is None:
                    stop = entry + sl_atr_mult * atr
                else:
                    stop = hprice + sl_buffer_atr * atr
                risk = stop - entry
                if risk > 0:
                    t1 = entry - rr_t1 * risk
                    t2 = entry - rr_t2 * risk
                    t3 = entry - rr_t3 * risk
                    setup = _make_setup(
                        "PE", "SWING_PIVOT", entry, [last_candle], atr, pivot_levels,
                        "SIGNAL_LOW", 0.0, sl_buffer_atr, min_room_r,
                        targets=(t1, t2, t3), stop=stop,
                    )
                    if setup is not None:
                        return setup

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Mode C — Cross-and-Acceptance
# ─────────────────────────────────────────────────────────────────────────────

def _check_acceptance(
    today: list[Candle],
    all_candles: Sequence[Candle],
    pivot_levels,
    sustain_candles: int,
    atr_period: int,
    sl_mode: str,
    sl_atr_mult: float,
    sl_buffer_atr: float,
    min_room_r: float,
    min_dist_atr: float = 0.0,
    min_room_r_accept: float = 0.0,
    blocked_sides: frozenset[str] = frozenset(),
    require_confirm_body: bool = False,
) -> PivotSetup | None:
    """
    Acceptance mode: price closed (or opened) on the wrong side of the Pivot,
    crossed it, and the latest N candles are the FIRST clean N-window on the
    new side since that cross.

    Extra guards (0 / empty = disabled):
      min_dist_atr      signal close must be >= this x ATR beyond the Pivot.
      min_room_r_accept T1 room must be >= this x risk (max with min_room_r).
      blocked_sides     sides ("CE"/"PE") for which acceptance is skipped.
      require_confirm_body signal candle must have a confirming body (CE: close >
                        open; PE: close < open).  Blocks entries on red CE /
                        green PE candles that satisfy the geometry but are
                        already reversing away from the Pivot.
    """
    n = sustain_candles
    if len(today) < n:
        return None

    P = pivot_levels.pivot
    last = len(today) - 1

    for side in ("CE", "PE"):
        if side in blocked_sides:
            continue
        if side == "CE":
            wrong = lambda c: c.close < P                       # noqa: E731
            clean = lambda c: c.close > P and c.low > P         # noqa: E731
            opened_wrong = today[0].open < P
        else:
            wrong = lambda c: c.close > P                       # noqa: E731
            clean = lambda c: c.close < P and c.high < P        # noqa: E731
            opened_wrong = today[0].open > P

        # Reference: index of the last wrong-side close; -1 = the day open.
        ref = next((i for i in range(last, -1, -1) if wrong(today[i])), None)
        if ref is None:
            if not opened_wrong:
                continue
            ref = -1
        if ref >= last - n + 1:          # window would include the wrong-side candle
            continue

        # All candles after the reference must have closed on the new side
        # (guaranteed for the close test by ref being the LAST wrong close,
        # but a close exactly AT Pivot is neither side → reject).
        after = today[ref + 1:]
        if not all(c.close > P if side == "CE" else c.close < P for c in after):
            continue

        # First clean N-window after the reference must end at the latest candle.
        first_end = next(
            (k for k in range(ref + n, last + 1)
             if all(clean(c) for c in today[k - n + 1:k + 1])),
            None,
        )
        if first_end != last:
            continue

        # ── Confirming body filter ─────────────────────────────────────────
        if require_confirm_body:
            sig = today[-1]
            if side == "CE" and sig.close <= sig.open:
                import logging as _log
                _log.getLogger(__name__).info(
                    "[PIVOT_ACCEPT_BLOCKED_BODY] side=CE close=%.2f open=%.2f"
                    " (red candle — rejected)",
                    sig.close, sig.open,
                )
                continue
            if side == "PE" and sig.close >= sig.open:
                import logging as _log
                _log.getLogger(__name__).info(
                    "[PIVOT_ACCEPT_BLOCKED_BODY] side=PE close=%.2f open=%.2f"
                    " (green candle — rejected)",
                    sig.close, sig.open,
                )
                continue

        atr = atr_at(_atr_series(today, all_candles), period=atr_period)
        if not atr or atr <= 0:
            return None

        dist = abs(today[-1].close - P)
        if min_dist_atr > 0 and dist < min_dist_atr * atr:
            import logging as _log
            _log.getLogger(__name__).info(
                "[PIVOT_ACCEPT_BLOCKED_DISTANCE] side=%s close=%.2f pivot=%.2f "
                "dist_pts=%.1f min_dist_atr=%.2f atr=%.1f",
                side, today[-1].close, P, dist, min_dist_atr, atr,
            )
            continue

        setup = _make_setup(
            side, "ACCEPTANCE", today[-1].close, today[-n:],
            atr, pivot_levels, sl_mode, sl_atr_mult, sl_buffer_atr,
            max(min_room_r, min_room_r_accept),
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
    # ── Open-Direction quality filters (default OFF) ─────────────────────
    # min_od_gap_atr: open must be >= N×ATR away from Pivot (0 = disabled).
    min_od_gap_atr: float = 0.0,
    # first_candle_confirm: first candle body must confirm OD direction.
    first_candle_confirm: bool = False,
    # max_first_wick_atr: first candle counter-wick cap (0 = disabled).
    max_first_wick_atr: float = 0.0,
    # enable_acceptance: also run Mode C (cross-and-acceptance).
    enable_acceptance: bool = False,
    # Acceptance guards — see _check_acceptance.
    acceptance_min_dist_atr: float = 0.0,
    acceptance_min_room_r: float = 0.0,
    acceptance_blocked_sides: frozenset[str] = frozenset(),
    acceptance_require_confirm_body: bool = False,
    # bounce_zone_atr: S/R bounce-rejection zone half-width (0 = disabled).
    bounce_zone_atr: float = 0.0,
    # ── Bounce quality filters (default OFF) ─────────────────────────────
    bounce_min_range_atr: float = 0.0,
    bounce_min_wick_pct: float = 0.0,
    bounce_trend_ema: int = 0,
    bounce_confirm_next: bool = False,
    # ── Swing Pivot (Fractal breakout) ───────────────────────────────────
    enable_swing_pivot: bool = False,
    swing_pivot_left: int = 4,
    swing_pivot_right: int = 2,
    swing_pivot_trend_ema: int = 50,
    swing_pivot_rr_t1: float = 1.5,
    swing_pivot_rr_t2: float = 2.5,
    swing_pivot_rr_t3: float = 3.5,
    swing_pivot_use_atr_sl: bool = False,
    swing_pivot_atr_mult: float = 1.2,
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
    min_od_gap_atr
        Open-Direction only. Open must be >= this × ATR from Pivot. Blocks
        OD trades when the open is hovering in the Pivot noise band.
        Recommended: 0.4 for SENSEX (blocks opens within ~46 pts of Pivot).
    first_candle_confirm
        Open-Direction only. Require the first 5m candle's body to confirm
        the direction (CE: bullish body; PE: bearish body).
    max_first_wick_atr
        Open-Direction only. Block if the first candle's counter-direction
        wick is >= this × ATR — signals a probe toward Pivot. 0 = disabled.
        Recommended: 0.25 for SENSEX (blocks a wick >= 0.25×ATR toward Pivot).
    enable_acceptance
        Also evaluate Mode C (cross-and-acceptance) after Modes A / B.
    bounce_zone_atr
        When > 0, also evaluate support-bounce (CE) / resistance-rejection
        (PE) at every pivot level (S3..R3).  Zone = level ± this × ATR.
    bounce_min_range_atr / bounce_min_wick_pct / bounce_trend_ema /
    bounce_confirm_next
        Bounce-only quality filters — see ``_check_bounce``.
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
            min_od_gap_atr=min_od_gap_atr,
            first_candle_confirm=first_candle_confirm,
            max_first_wick_atr=max_first_wick_atr,
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

    # ── Mode C ──────────────────────────────────────────────────────────────
    if enable_acceptance:
        setup = _check_acceptance(
            today, candles_5m, pivot_levels,
            sustain_candles, atr_period,
            sl_mode, sl_atr_mult, sl_buffer_atr, min_room_r,
            min_dist_atr=acceptance_min_dist_atr,
            min_room_r_accept=acceptance_min_room_r,
            blocked_sides=acceptance_blocked_sides,
            require_confirm_body=acceptance_require_confirm_body,
        )
        if setup is not None:
            return setup

    # ── Level bounce / rejection ────────────────────────────────────────────
    if bounce_zone_atr > 0:
        setup = _check_bounce(
            today, candles_5m, pivot_levels,
            atr_period, sl_buffer_atr, min_room_r, bounce_zone_atr,
            min_range_atr=bounce_min_range_atr,
            min_wick_pct=bounce_min_wick_pct,
            trend_ema=bounce_trend_ema,
            confirm_next=bounce_confirm_next,
        )
        if setup is not None:
            return setup

    # ── Swing Pivot Reversal / Breakout ─────────────────────────────────────
    if enable_swing_pivot:
        setup = _check_swing_pivot(
            today, candles_5m, pivot_levels,
            atr_period=atr_period,
            left_bars=swing_pivot_left,
            right_bars=swing_pivot_right,
            trend_ema=swing_pivot_trend_ema,
            rr_t1=swing_pivot_rr_t1,
            rr_t2=swing_pivot_rr_t2,
            rr_t3=swing_pivot_rr_t3,
            use_atr_sl=swing_pivot_use_atr_sl,
            sl_atr_mult=swing_pivot_atr_mult,
            sl_buffer_atr=sl_buffer_atr,
            min_room_r=min_room_r,
        )
        if setup is not None:
            return setup

    return None
