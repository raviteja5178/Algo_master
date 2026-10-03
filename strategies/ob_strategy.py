"""
Order Block (OB) detection strategy — Python port of the
"Volumized Order Blocks | Flux Charts" Pine Script indicator.

Logic (mirrors the Pine Script exactly):
─────────────────────────────────────────────────────────────────────────
  Swing detection (swingLength = 10):
      A swing HIGH is the highest high in [bar-swingLength ... bar].
      A swing LOW  is the lowest  low  in [bar-swingLength ... bar].

  Bullish Order Block (CE signal):
      Formed when close crosses ABOVE a swing high.
      The OB zone = the lowest-body candle between the swing high and
      the crossing candle (Pine: iterates backwards finding min of low,
      records max of that candle as the box top).
      Invalidated (becomes a breaker) when a later candle's LOW (Wick
      method) drops BELOW the OB bottom.
      Deleted when price reclaims above OB top after it broke.

  Bearish Order Block (PE signal):
      Mirror of the above — formed when close crosses BELOW a swing low.
      Invalidated when a later candle's HIGH moves ABOVE the OB top.

  CE_OB signal fires when:
      The current candle's close is inside a valid (non-breaker) bullish OB
      — i.e. OB.bottom <= close <= OB.top.

  PE_OB signal fires when:
      The current candle's close is inside a valid (non-breaker) bearish OB.

  ATR size cap (maxATRMult = 3.5):
      A newly detected OB is discarded if its height > ATR(10) * 3.5.

Config knobs (all in settings.py):
    ENABLE_OB_STRATEGY          bool  (default False — opt-in)
    OB_SWING_LENGTH             int   (default 10)
    OB_MAX_ATR_MULT             float (default 3.5)
    OB_ATR_PERIOD               int   (default 10)
    OB_MAX_BLOCKS               int   (default 3, "Low" zone count)
    OB_INVALIDATION             str   "Wick" | "Close"  (default "Wick")
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from market.candle_builder import Candle
from market.indicators import atr_at

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class OrderBlock:
    """
    A detected order block zone.

    top / bottom  : price boundaries of the box
    ob_type       : "Bull" or "Bear"
    start_idx     : candle index (in the input sequence) where OB was formed
    breaker       : True once price has broken through the OB
    break_idx     : candle index when it became a breaker
    """
    top:        float
    bottom:     float
    ob_type:    str          # "Bull" | "Bear"
    start_idx:  int
    breaker:    bool  = False
    break_idx:  int | None = None


# ── Core detection ────────────────────────────────────────────────────────────

def detect_order_blocks(
    candles: Sequence[Candle],
    *,
    swing_length: int   = 10,
    max_atr_mult: float = 3.5,
    atr_period:   int   = 10,
    max_blocks:   int   = 3,
    invalidation: str   = "Wick",   # "Wick" | "Close"
) -> tuple[list[OrderBlock], list[OrderBlock]]:
    """
    Scan *candles* (chronological, oldest first) and return:
        (bullish_obs, bearish_obs)

    Each list is ordered newest-first (index 0 = most recently formed OB).
    Already-broken OBs are included (marked .breaker = True) so callers can
    show "historic zones" or filter them out.

    This mirrors the Pine Script pass exactly:
      - findOBSwings  -> detect swing highs/lows with rolling highest/lowest
      - bullish/bearish OB formation on close crossover of swing
      - breaker invalidation when price violates the OB boundary
      - ATR size cap at formation time
    """
    n = len(candles)
    if n < swing_length + 2:
        return [], []

    bull_obs: list[OrderBlock] = []
    bear_obs: list[OrderBlock] = []

    # Swing state — mirrors Pine `var swingType` (0=up, 1=down, -1=unset)
    # Using -1 (unset) as initial value ensures the very first detected swing
    # always fires the "new swing" branch (prev != current), matching Pine behaviour
    # where var swingType = 0 never suppresses a first swing-high detection because
    # Pine only transitions when the condition is newly true on the pivot bar.
    swing_type: int = -1

    # Last confirmed swing points (bar index, price)
    swing_top_idx:    int   = 0
    swing_top_price:  float = 0.0
    swing_top_used:   bool  = True   # prevent reuse until a new swing forms

    swing_btm_idx:    int   = 0
    swing_btm_price:  float = 0.0
    swing_btm_used:   bool  = True

    for i in range(swing_length, n):
        c = candles[i]

        # ── 1. Swing detection (mirrors findOBSwings) ──────────────────────
        # Pine: upper = ta.highest(len)  ->  max HIGH of bars [i-len+1 .. i]
        #        swingType = high[len] > upper ? 0 : ...
        # Pivot = candles[i - swing_length]  (the bar `len` steps back)
        # Condition: pivot.high > max(window) -> pivot is a swing HIGH
        window = candles[i - swing_length + 1: i + 1]
        upper = max(c2.high for c2 in window)
        lower = min(c2.low  for c2 in window)

        pivot_bar    = i - swing_length
        pivot_candle = candles[pivot_bar]

        prev_swing_type = swing_type
        if pivot_candle.high > upper:
            swing_type = 0
        elif pivot_candle.low < lower:
            swing_type = 1

        if swing_type == 0 and prev_swing_type != 0:
            swing_top_idx   = pivot_bar
            swing_top_price = pivot_candle.high
            swing_top_used  = False

        if swing_type == 1 and prev_swing_type != 1:
            swing_btm_idx   = pivot_bar
            swing_btm_price = pivot_candle.low
            swing_btm_used  = False

        # ── 2. Update existing bullish OBs (breaker / delete logic) ────────
        for ob in list(bull_obs):
            if not ob.breaker:
                breach_price = c.low if invalidation == "Wick" else min(c.open, c.close)
                if breach_price < ob.bottom:
                    ob.breaker   = True
                    ob.break_idx = i
            else:
                # After becoming a breaker, remove when price reclaims above top
                if c.high > ob.top:
                    bull_obs.remove(ob)

        # ── 3. New bullish OB: close crosses above swing top ────────────────
        if (
            not swing_top_used
            and i > 0
            and candles[i - 1].close <= swing_top_price
            and c.close > swing_top_price
        ):
            swing_top_used = True

            # Find the lowest-low candle between swing_top_idx and current bar
            # (Pine: iterates i=1 to bar_index - top.x - 1)
            box_bottom = candles[i - 1].high   # seed: Pine uses max[1]
            box_top    = candles[i - 1].low
            for k in range(1, i - swing_top_idx):
                if candles[i - k].low < box_bottom:
                    box_bottom = candles[i - k].low
                    box_top    = candles[i - k].high

            # ATR size cap
            ob_height = abs(box_top - box_bottom)
            current_atr = atr_at(candles[:i + 1], period=atr_period)
            if current_atr and ob_height > current_atr * max_atr_mult:
                logger.debug(
                    "Bullish OB at index %d discarded: height %.1f > ATR*%.1f = %.1f",
                    i, ob_height, max_atr_mult, current_atr * max_atr_mult,
                )
            else:
                new_ob = OrderBlock(
                    top=box_top, bottom=box_bottom,
                    ob_type="Bull", start_idx=i,
                )
                bull_obs.insert(0, new_ob)
                if len(bull_obs) > max_blocks * 10:   # internal cap (generous)
                    bull_obs.pop()

        # ── 4. Update existing bearish OBs ──────────────────────────────────
        for ob in list(bear_obs):
            if not ob.breaker:
                breach_price = c.high if invalidation == "Wick" else max(c.open, c.close)
                if breach_price > ob.top:
                    ob.breaker   = True
                    ob.break_idx = i
            else:
                if c.low < ob.bottom:
                    bear_obs.remove(ob)

        # ── 5. New bearish OB: close crosses below swing bottom ─────────────
        if (
            not swing_btm_used
            and i > 0
            and candles[i - 1].close >= swing_btm_price
            and c.close < swing_btm_price
        ):
            swing_btm_used = True

            box_top    = candles[i - 1].low    # Pine: min[1]
            box_bottom = candles[i - 1].high
            for k in range(1, i - swing_btm_idx):
                if candles[i - k].high > box_top:
                    box_top    = candles[i - k].high
                    box_bottom = candles[i - k].low

            ob_height = abs(box_top - box_bottom)
            current_atr = atr_at(candles[:i + 1], period=atr_period)
            if current_atr and ob_height > current_atr * max_atr_mult:
                logger.debug(
                    "Bearish OB at index %d discarded: height %.1f > ATR*%.1f = %.1f",
                    i, ob_height, current_atr * max_atr_mult, max_atr_mult,
                )
            else:
                new_ob = OrderBlock(
                    top=box_top, bottom=box_bottom,
                    ob_type="Bear", start_idx=i,
                )
                bear_obs.insert(0, new_ob)
                if len(bear_obs) > max_blocks * 10:
                    bear_obs.pop()

    # Return only the most-recent max_blocks non-breaker + breaker OBs
    return bull_obs[:max_blocks], bear_obs[:max_blocks]


# ── Signal functions (called by signal_engine) ────────────────────────────────

def is_ob_ce_signal(
    candles_5m: Sequence[Candle],
    *,
    swing_length: int   = 10,
    max_atr_mult: float = 3.5,
    atr_period:   int   = 10,
    max_blocks:   int   = 3,
    invalidation: str   = "Wick",
) -> bool:
    """
    CE signal: latest candle close is inside a valid (non-breaker) bullish OB.

    Requires today's candle and at least swing_length + 2 candles.
    """
    if len(candles_5m) < swing_length + 2:
        return False

    latest = candles_5m[-1]
    if latest.timestamp.date() != date.today():
        return False

    bull_obs, _ = detect_order_blocks(
        candles_5m,
        swing_length=swing_length,
        max_atr_mult=max_atr_mult,
        atr_period=atr_period,
        max_blocks=max_blocks,
        invalidation=invalidation,
    )

    close = latest.close

    # Signal: close is inside a valid (non-breaker) bullish OB zone
    for ob in bull_obs:
        if ob.breaker:
            continue
        if ob.bottom <= close <= ob.top:
            logger.debug(
                "CE_OB: close %.2f inside bull OB [%.2f - %.2f]",
                close, ob.bottom, ob.top,
            )
            return True

    return False


def is_ob_pe_signal(
    candles_5m: Sequence[Candle],
    *,
    swing_length: int   = 10,
    max_atr_mult: float = 3.5,
    atr_period:   int   = 10,
    max_blocks:   int   = 3,
    invalidation: str   = "Wick",
) -> bool:
    """
    PE signal: latest candle close is inside a valid (non-breaker) bearish OB.
    """
    if len(candles_5m) < swing_length + 2:
        return False

    latest = candles_5m[-1]
    if latest.timestamp.date() != date.today():
        return False

    _, bear_obs = detect_order_blocks(
        candles_5m,
        swing_length=swing_length,
        max_atr_mult=max_atr_mult,
        atr_period=atr_period,
        max_blocks=max_blocks,
        invalidation=invalidation,
    )

    close = latest.close

    # Signal: close is inside a valid (non-breaker) bearish OB zone
    for ob in bear_obs:
        if ob.breaker:
            continue
        if ob.bottom <= close <= ob.top:
            logger.debug(
                "PE_OB: close %.2f inside bear OB [%.2f - %.2f]",
                close, ob.bottom, ob.top,
            )
            return True

    return False
