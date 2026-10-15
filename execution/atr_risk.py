"""
ATR-based adaptive risk manager.

Two active modes, evaluated in priority order:

  MODE D — SENSEX swing high/low as SL  (use_swing_sl=True)
  ────────────────────────────────────────────────────────────────────────────────
  Structure-first: SL is placed at the nearest structural pivot — the exact
  price level where the trade thesis is proven wrong.
    PE trade:  SL = nearest swing HIGH above entry (index points above entry)
    CE trade:  SL = nearest swing LOW  below entry (index points below entry)
    Option SL  = index_distance × ATM_delta (≈ 0.4)
    Target     = SL_option_pts × target_rr   (R:R ratio, e.g. 1.5)
    Trail      = SL_option_pts × trail_rr    (e.g. 0.5 = 50% of SL)
    BE         = SL_option_pts × 0.5
  Falls back to Mode C (spot ATR) automatically when no swing level is found.
  Caller must pass swing_high / swing_low (index prices) and sensex_ltp.

  Mode D adequacy guard  (swing_sl_min_atr_mult > 0):
    If the swing level is so close to entry that the index-point distance is
    less than  ATR(spot_atr_period) × swing_sl_min_atr_mult, Mode D is
    rejected and the bot falls through to Mode C.
    Rationale: a swing only 44 index pts away on an ATR-90 day is inside one
    normal candle's range — not a structural level, just nearby noise.
    Recommended: 0.6  (swing must be at least 60% of one ATR away).

  MODE C — SENSEX spot ATR × multiplier  (use_spot_atr=True)
  ────────────────────────────────────────────────────────────────────────────────
  Momentum-adaptive: SL scales with current market volatility.
    SL     = ATR(spot_atr_period, 5m SENSEX) × spot_sl_mult × ATM_delta(0.4)
    Target = SL × target_rr   (default 1.5, i.e. R:R 1.5:1)
    Trail  = SL × trail_rr    (default 0.5, i.e. 50% of SL)
    BE     = SL × 0.5
  Wide SL on volatile days, tight on calm days.
  Capped at max_sl_pct of entry to prevent negative SL order prices.

  FIXED FALLBACK — used only when ATR is unavailable (cold start / no candles)
  ────────────────────────────────────────────────────────────────────────────────
  Uses configured fixed_sl / fixed_target / fixed_trail values.

All results are clipped to configured minimum values so the bot never
uses a stop or target that is dangerously small.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from market.candle_builder import Candle
from market.indicators import atr_at
from utils.logging_config import log_event
from utils.price_utils import round_to_tick

logger = logging.getLogger(__name__)


@dataclass
class RiskParams:
    """Resolved risk parameters for a single trade."""
    initial_sl_points: float
    break_even_trigger_points: float
    trail_step_points: float
    initial_target_points: float
    atr_value: float | None   # None when ATR fell back to fixed params
    sl_mode: str = "fixed"    # "swing_sl" | "spot_atr" | "fixed"


def compute_risk_params(
    candles_5m: Sequence[Candle],
    *,
    # Fallback fixed values (used when ATR is unavailable)
    fixed_sl: float = 50.0,
    fixed_target: float = 80.0,
    fixed_trail: float = 15.0,
    # Minimum floors
    min_sl_pts: float = 20.0,
    min_target_pts: float = 30.0,
    min_trail_pts: float = 5.0,
    # SL ceiling: cap at this % of entry to prevent a negative SL order price
    max_sl_pct: float = 0.35,
    # Option entry price — used for SL ceiling only
    entry_price: float = 0.0,
    # Mode C — SENSEX spot ATR × multiplier (market-momentum adaptive)
    use_spot_atr: bool = True,
    spot_atr_period: int = 5,
    spot_sl_mult: float = 2.5,
    target_rr: float = 1.5,
    trail_rr: float = 0.5,
    # Mode D — swing high/low as SL (structure-first, like TradingView Copilot)
    use_swing_sl: bool = False,
    option_type: str = "CE",       # "CE" or "PE" — determines which swing level is used
    sensex_ltp: float = 0.0,       # current SENSEX index price at entry
    swing_high: float | None = None,  # nearest confirmed swing HIGH (index pts)
    swing_low:  float | None = None,  # nearest confirmed swing LOW  (index pts)
    # Mode D adequacy guard: reject swing SL when index distance < ATR × this mult
    # 0.0 = disabled (always trust the swing level). Recommended: 0.6
    swing_sl_min_atr_mult: float = 0.0,
) -> RiskParams:
    """
    Compute risk parameters for the current trade.

    MODE D (use_swing_sl=True) — structure-first SL (highest priority):
        PE: SL_index_pts = swing_high − sensex_ltp  (how far to the nearest high)
        CE: SL_index_pts = sensex_ltp − swing_low   (how far to the nearest low)
        SL_option_pts    = SL_index_pts × delta     (delta ≈ 0.4 for ATM)
        Target           = SL_option_pts × target_rr
        Trail            = SL_option_pts × trail_rr
        Falls back to Mode C when swing level is unavailable or SL <= 0.

    MODE C (use_spot_atr=True) — SENSEX spot ATR × multiplier:
        SL     = ATR(spot_atr_period, 5m SENSEX) × spot_sl_mult × ATM_delta
        Target = SL × target_rr
        Trail  = SL × trail_rr

    FIXED FALLBACK — used only when ATR is unavailable:
        Uses fixed_sl / fixed_target / fixed_trail.
    """
    current_atr = atr_at(candles_5m, period=spot_atr_period)

    # ATM delta ≈ 0.4: converts SENSEX index pts → option premium pts.
    # At-the-money SENSEX options have delta ≈ 0.4, meaning a 1-pt move in the
    # SENSEX index changes the option premium by ~0.4 pts.
    _ATM_DELTA = 0.4

    # ── MODE D: swing high/low as SL (structure-first) ───────────────────────
    # SL is placed at the nearest structural pivot: the level where the trade
    # thesis is proven wrong.  Same logic as TradingView AI Copilot.
    if use_swing_sl and sensex_ltp > 0:
        sl_index_pts: float | None = None
        swing_level_used: float | None = None

        if option_type == "PE" and swing_high is not None and swing_high > sensex_ltp:
            # PE (bearish): thesis breaks if SENSEX rallies back above the swing high
            sl_index_pts     = swing_high - sensex_ltp
            swing_level_used = swing_high
        elif option_type == "CE" and swing_low is not None and swing_low < sensex_ltp:
            # CE (bullish): thesis breaks if SENSEX falls back below the swing low
            sl_index_pts     = sensex_ltp - swing_low
            swing_level_used = swing_low

        if sl_index_pts is not None and sl_index_pts > 0:
            # ── Adequacy guard: reject swing if it is too close to entry ──────
            # A swing level within one ATR of entry is just nearby noise, not
            # a true structural level.  Fall through to Mode C when violated.
            if swing_sl_min_atr_mult > 0 and current_atr and current_atr > 0:
                min_index_distance = current_atr * swing_sl_min_atr_mult
                if sl_index_pts < min_index_distance:
                    logger.info(
                        "Mode D swing SL rejected: index_pts=%.1f < ATR(%.0f)×%.2f=%.1f"
                        " — falling through to Mode C",
                        sl_index_pts, spot_atr_period, swing_sl_min_atr_mult, min_index_distance,
                    )
                    sl_index_pts = None  # trigger fall-through

        if sl_index_pts is not None and sl_index_pts > 0:
            sl_option_pts = round_to_tick(sl_index_pts * _ATM_DELTA)
            sl = max(min_sl_pts, sl_option_pts)
            # Cap SL at max_sl_pct of entry price to prevent negative SL order price
            if entry_price > 0 and max_sl_pct > 0:
                sl_ceiling = round_to_tick(entry_price * max_sl_pct)
                if sl > sl_ceiling:
                    logger.info(
                        "Mode D swing SL %.1f capped to %.1f (%.0f%% of entry %.1f)",
                        sl, sl_ceiling, max_sl_pct * 100, entry_price,
                    )
                    sl = sl_ceiling
            tgt   = max(min_target_pts, round_to_tick(sl * target_rr))
            trail = max(min_trail_pts,  round_to_tick(sl * trail_rr))
            be    = max(min_sl_pts * 0.5, round_to_tick(sl * 0.5))
            log_event(
                logger, "RISK_COMPUTED_SWING_SL",
                mode="swing_sl",
                option_type=option_type,
                swing_level=round(swing_level_used, 2),
                sensex_ltp=round(sensex_ltp, 2),
                sl_index_pts=round(sl_index_pts, 2),
                delta=_ATM_DELTA,
                sl=sl, be=be, target=tgt, trail=trail,
                rr=target_rr,
                entry=round(entry_price, 2) if entry_price else "unknown",
            )
            return RiskParams(
                initial_sl_points=sl,
                break_even_trigger_points=be,
                trail_step_points=trail,
                initial_target_points=tgt,
                atr_value=round(current_atr, 2) if current_atr else None,
                sl_mode="swing_sl",
            )
        # No valid swing level — log and fall through to Mode C
        logger.info(
            "Mode D: no valid swing level (type=%s ltp=%.1f high=%s low=%s) — falling back to Mode C",
            option_type, sensex_ltp, swing_high, swing_low,
        )

    # ── MODE C: SENSEX spot ATR × multiplier (market-momentum adaptive) ───────
    # IMPORTANT: spot_atr is a SENSEX index measurement (e.g. 90 index pts).
    # It must be converted to option premium pts via ATM delta before it can
    # be used as an option SL.  Without this, a 90-pt index ATR would produce
    # a 270-pt SL (ATR×3) on an option that may only be priced at ₹150 — the
    # 35% ceiling would then crush the SL to ₹52, making it far too tight.
    if use_spot_atr:
        spot_atr = atr_at(candles_5m, period=spot_atr_period)
        if spot_atr and spot_atr > 0:
            # Convert: index_pts × multiplier × delta → option premium pts
            sl = round_to_tick(spot_atr * spot_sl_mult * _ATM_DELTA)
            sl = max(min_sl_pts, sl)
            # Cap SL at max_sl_pct of entry to prevent a negative SL order price
            if entry_price > 0 and max_sl_pct > 0:
                sl_ceiling = round_to_tick(entry_price * max_sl_pct)
                if sl > sl_ceiling:
                    logger.info(
                        "Mode C ATR SL %.1f capped to %.1f (%.0f%% of entry %.1f)",
                        sl, sl_ceiling, max_sl_pct * 100, entry_price,
                    )
                    sl = sl_ceiling
            tgt   = max(min_target_pts, round_to_tick(sl * target_rr))
            trail = max(min_trail_pts,  round_to_tick(sl * trail_rr))
            be    = max(min_sl_pts * 0.5, round_to_tick(sl * 0.5))
            log_event(
                logger, "RISK_COMPUTED_SPOT_ATR",
                mode="spot_atr_mult",
                spot_atr=round(spot_atr, 2),
                spot_atr_period=spot_atr_period,
                atm_delta=_ATM_DELTA,
                sl=sl, be=be, target=tgt, trail=trail,
                rr=target_rr,
                entry=round(entry_price, 2) if entry_price else "unknown",
            )
            return RiskParams(
                initial_sl_points=sl,
                break_even_trigger_points=be,
                trail_step_points=trail,
                initial_target_points=tgt,
                atr_value=round(spot_atr, 2),
                sl_mode="spot_atr",
            )
        # spot ATR unavailable — fall through to fixed
        logger.warning("Mode C: spot ATR unavailable (period=%d, candles=%d) — falling back to fixed",
                       spot_atr_period, len(candles_5m))

    # ── Fixed fallback — ATR unavailable ──────────────────────────────────────
    be_fixed = round_to_tick(fixed_sl * 0.5)
    logger.info(
        "ATR unavailable — using fixed risk params SL=%.0f BE=%.0f TARGET=%.0f TRAIL=%.0f",
        fixed_sl, be_fixed, fixed_target, fixed_trail,
    )
    return RiskParams(
        initial_sl_points=fixed_sl,
        break_even_trigger_points=be_fixed,
        trail_step_points=fixed_trail,
        initial_target_points=fixed_target,
        atr_value=None,
        sl_mode="fixed",
    )
