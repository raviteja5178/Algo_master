"""
VWAP Retest Strategy.

Logic:
──────
Institutions use VWAP as a benchmark — large orders cluster around it.
When price pulls back to VWAP after a directional move and a 5m candle
closes back on the right side, it signals resumption of that move.

CE_VWAP signal (bullish retest):
    1. At least one of the previous N candles closed BELOW VWAP
       (price touched / dipped into VWAP — the "retest").
    2. The current candle closes ABOVE VWAP (price reclaimed VWAP).
    3. The current candle close > previous candle high (momentum confirmation).
    4. VWAP itself is rising (or flat) — not in a downtrend.

PE_VWAP signal (bearish retest):
    Mirror of the above — dip above VWAP then close back below.

Enhanced Mean-Reversion filters (all opt-in via settings):
──────────────────────────────────────────────────────────
    VWAP_MR_ZSCORE_ENTRY     float  min |z-score| to enter (default 0 = off)
    VWAP_MR_ADX_MAX          float  block trade if ADX >= this value (default 0 = off)
    VWAP_MR_RSI_CONFIRM      bool   require RSI reversal confirmation (default False)
    VWAP_MR_VOLUME_SPIKE     float  require current vol > N × avg vol (default 0 = off)
    VWAP_MR_MIN_RR           float  min reward-to-VWAP / risk ratio (default 0 = off)
    VWAP_MR_MIN_SCORE        int    min setup quality score 0–6 (default 0 = off)
    VWAP_MR_VWAP_CROSS_MIN   int    min VWAP crossings today before entry (default 0 = off)

Config knobs (all in settings.py):
    ENABLE_VWAP_STRATEGY        bool   (default False — opt-in)
    ENABLE_CE_VWAP              bool   (default True — set False to disable CE signals)
    ENABLE_PE_VWAP              bool   (default True — set False to disable PE signals)
    VWAP_RETEST_LOOKBACK        int    candles to look back for the retest (default 3)
    VWAP_MIN_BOUNCE_PTS         float  minimum distance close must be above/below VWAP (default 0)
    VWAP_MAX_SUBMERGED_CANDLES  int    maximum consecutive candles on opposite side (default 3)
    VWAP_SLOPE_LOOKBACK         int    candles back for the VWAP-slope check in rule 4 (0 = off)
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from utils.time_utils import today_ist

from market.candle_builder import Candle

logger = logging.getLogger(__name__)


# ── Helper: VWAP z-score ──────────────────────────────────────────────────────

def vwap_zscore(
    candles_5m: Sequence[Candle],
    vwap: float,
    period: int = 20,
) -> float | None:
    """
    Return the z-score of the latest close relative to VWAP, using today's
    candles only.  z = (close - vwap) / std(closes[-period:]).

    Returns None when fewer than 3 today-candles are available (std undefined).
    Positive = above VWAP, negative = below VWAP.
    """
    day = candles_5m[-1].timestamp.date()
    today = [c for c in candles_5m if c.timestamp.date() == day]
    window = [c.close for c in today[-period:]]
    if len(window) < 3:
        return None
    mean = sum(window) / len(window)
    variance = sum((x - mean) ** 2 for x in window) / len(window)
    if variance <= 0:
        return None
    std = variance ** 0.5
    return (candles_5m[-1].close - vwap) / std


# ── Helper: ADX regime filter ─────────────────────────────────────────────────

def adx_regime_ok(candles_5m: Sequence[Candle], adx_max: float) -> bool:
    """
    Return True when the 5m ADX(14) is BELOW adx_max (non-trending / rotational).
    Returns True when adx_max <= 0 (disabled) or when ADX cannot be computed yet.
    """
    if adx_max <= 0:
        return True
    from strategies.market_regime import adx_latest
    result = adx_latest(candles_5m, period=14)
    if result is None:
        return True          # not enough data — allow trade
    adx_val, _, _ = result
    ok = adx_val < adx_max
    if not ok:
        logger.debug("VWAP MR: ADX %.1f >= max %.1f — regime too trendy", adx_val, adx_max)
    return ok


# ── Helper: VWAP crossing count ───────────────────────────────────────────────

def vwap_cross_count(candles_5m: Sequence[Candle], vwap: float) -> int:
    """
    Count how many times today's 5m closes crossed the VWAP line
    (i.e. consecutive candles on opposite sides of VWAP).
    """
    day = candles_5m[-1].timestamp.date()
    today = [c for c in candles_5m if c.timestamp.date() == day]
    if len(today) < 2:
        return 0
    crossings = 0
    for i in range(1, len(today)):
        prev_above = today[i - 1].close > vwap
        curr_above = today[i].close > vwap
        if prev_above != curr_above:
            crossings += 1
    return crossings


# ── Helper: RSI reversal confirmation ────────────────────────────────────────

def rsi_reversal_ok(
    candles_5m: Sequence[Candle],
    side: str,
    period: int = 14,
    oversold: float = 30.0,
    overbought: float = 70.0,
) -> bool:
    """
    CE: RSI crossed back above *oversold* — previous candle RSI <= oversold,
        current RSI > oversold.
    PE: RSI crossed back below *overbought* — previous candle RSI >= overbought,
        current RSI < overbought.

    Returns True when not enough data to compute RSI (safe default: allow trade).
    """
    from market.indicators import rsi as _rsi
    closes = [c.close for c in candles_5m]
    rsi_vals = _rsi(closes, period)
    # Need at least the two most recent values
    valid = [v for v in rsi_vals[-2:] if v is not None]
    if len(valid) < 2:
        return True
    prev_rsi, curr_rsi = valid[0], valid[1]
    if side == "CE":
        ok = prev_rsi <= oversold and curr_rsi > oversold
    else:
        ok = prev_rsi >= overbought and curr_rsi < overbought
    if not ok:
        logger.debug(
            "VWAP MR: RSI reversal not confirmed (%s) — prev=%.1f curr=%.1f",
            side, prev_rsi, curr_rsi,
        )
    return ok


# ── Helper: volume spike ──────────────────────────────────────────────────────

def volume_spike(
    candles_5m: Sequence[Candle],
    multiplier: float = 1.5,
    lookback: int = 20,
) -> bool:
    """
    Return True when the current candle's volume exceeds multiplier × the
    average volume of the previous *lookback* candles.

    Returns True when multiplier <= 0 (disabled) or when there are not
    enough candles to compute a baseline.
    """
    if multiplier <= 0:
        return True
    if len(candles_5m) < lookback + 1:
        return True      # not enough history — allow trade
    prev = candles_5m[-(lookback + 1):-1]
    vols = [c.volume for c in prev if c.volume > 0]
    if not vols:
        return True
    avg_vol = sum(vols) / len(vols)
    curr_vol = candles_5m[-1].volume
    ok = curr_vol > multiplier * avg_vol
    if not ok:
        logger.debug(
            "VWAP MR: no volume spike — curr vol=%d, avg=%.0f, required=%.0fx",
            curr_vol, avg_vol, multiplier,
        )
    return ok


# ── Helper: reward-to-risk ratio ─────────────────────────────────────────────

def reward_to_risk_ok(
    close: float,
    vwap: float,
    stop: float,
    min_rr: float = 1.5,
) -> bool:
    """
    Return True when |close - vwap| / |close - stop| >= min_rr.

    CE: close < vwap (reward = vwap - close, risk = close - stop).
    PE: close > vwap (reward = close - vwap, risk = stop - close).

    Returns True when min_rr <= 0 (disabled) or when risk is zero/negative.
    """
    if min_rr <= 0:
        return True
    reward = abs(close - vwap)
    risk = abs(close - stop)
    if risk <= 0:
        return True
    rr = reward / risk
    ok = rr >= min_rr
    if not ok:
        logger.debug(
            "VWAP MR: R:R %.2f < min %.2f (reward=%.1f risk=%.1f)",
            rr, min_rr, reward, risk,
        )
    return ok


# ── Helper: setup quality score ───────────────────────────────────────────────

def setup_score(
    candles_5m: Sequence[Candle],
    vwap: float,
    side: str,
    stop: float,
    *,
    zscore_threshold: float = 2.0,
    adx_max: float = 25.0,
    min_rr: float = 1.5,
    vol_multiplier: float = 1.5,
    rsi_period: int = 14,
    oversold: float = 30.0,
    overbought: float = 70.0,
) -> int:
    """
    Score the VWAP mean-reversion setup on 6 criteria (1 point each):

      1. |z-score| >= zscore_threshold
      2. ADX < adx_max  (rotational regime)
      3. RSI reversal confirmed
      4. Volume spike present
      5. Reward-to-VWAP / risk >= min_rr
      6. VWAP cross count >= 1 today (market is oscillating)

    Returns an integer 0–6.
    """
    score = 0
    close = candles_5m[-1].close

    z = vwap_zscore(candles_5m, vwap)
    if z is not None and abs(z) >= zscore_threshold:
        score += 1

    if adx_regime_ok(candles_5m, adx_max):
        score += 1

    if rsi_reversal_ok(candles_5m, side, period=rsi_period,
                       oversold=oversold, overbought=overbought):
        score += 1

    if volume_spike(candles_5m, multiplier=vol_multiplier):
        score += 1

    if reward_to_risk_ok(close, vwap, stop, min_rr=min_rr):
        score += 1

    if vwap_cross_count(candles_5m, vwap) >= 1:
        score += 1

    return score


# ── Original helpers (unchanged) ──────────────────────────────────────────────

def vwap_retest_ts(
    candles_5m: Sequence[Candle],
    vwap: float,
    side: str,
    retest_lookback: int = 3,
) -> datetime | None:
    """
    Timestamp of the retest candle behind a VWAP signal on the latest candle:
    the most recent candle in the lookback window (current candle excluded)
    that closed below VWAP for CE, or above VWAP for PE.  None if there is none.
    """
    lookback = candles_5m[-(retest_lookback + 1):-1]
    for c in reversed(lookback):
        if (c.close < vwap) if side == "CE" else (c.close > vwap):
            return c.timestamp
    return None


def vwap_slope_ok(candles_5m: Sequence[Candle], side: str, lookback: int) -> bool:
    """
    Rule 4: CE needs VWAP rising (or flat), PE falling (or flat).

    Compares the point-in-time VWAP after the candle *lookback* bars ago
    against the VWAP after the latest candle — both computed as running
    cumulative VWAPs from the start of today's session.  This gives a true
    "was VWAP higher / lower N bars ago?" slope check.

    Passes when disabled (lookback=0) or when today has too few candles.
    """
    if lookback <= 0 or not candles_5m:
        return True
    day = candles_5m[-1].timestamp.date()
    today = [c for c in candles_5m if c.timestamp.date() == day]
    if len(today) <= lookback:
        return True

    def _running_vwap(cs: Sequence[Candle]) -> float:
        """Cumulative VWAP up to and including the last candle in cs."""
        num = den = 0.0
        for c in cs:
            vol = c.volume if c.volume > 0 else 1
            num += (c.high + c.low + c.close) / 3.0 * vol
            den += vol
        return num / den if den else 0.0

    vwap_now    = _running_vwap(today)            # VWAP including latest candle
    vwap_before = _running_vwap(today[:-lookback])  # VWAP N candles ago
    ok = vwap_now >= vwap_before if side == "CE" else vwap_now <= vwap_before
    if not ok:
        logger.debug("VWAP %s: slope against signal — VWAP now=%.2f vs %.2f (%d candles ago)",
                     side, vwap_now, vwap_before, lookback)
    return ok


def is_vwap_ce_signal(
    candles_5m: Sequence[Candle],
    vwap: float | None,
    *,
    retest_lookback: int = 3,
    min_bounce_pts: float = 0.0,
    max_submerged_candles: int = 3,
    slope_lookback: int = 0,
    # Enhanced mean-reversion filters (all default off for backward compatibility)
    mr_zscore_entry: float = 0.0,
    mr_adx_max: float = 0.0,
    mr_rsi_confirm: bool = False,
    mr_volume_spike: float = 0.0,
    mr_min_rr: float = 0.0,
    mr_min_score: int = 0,
    mr_vwap_cross_min: int = 0,
) -> bool:
    """
    Return True when:
      1. VWAP is available and valid.
      2. Within the last *retest_lookback* completed candles, at least one
         closed BELOW VWAP (the retest dip).
      3. The current (latest) candle closes ABOVE VWAP.
      4. Current close > previous candle high (momentum confirmation).
      5. Close is at least min_bounce_pts above VWAP.
      6. VWAP is rising or flat (slope_lookback > 0).

    Enhanced filters (all opt-in, default disabled):
      7.  |z-score| >= mr_zscore_entry     (price far enough from VWAP)
      8.  ADX < mr_adx_max                 (non-trending regime)
      9.  RSI crossed back above 30         (mr_rsi_confirm=True)
      10. Volume spike present              (mr_volume_spike > 0)
      11. Reward-to-VWAP / risk >= mr_min_rr
      12. Setup score >= mr_min_score       (composite quality gate)
      13. VWAP crossed >= mr_vwap_cross_min times today
    """
    if vwap is None or vwap <= 0:
        return False
    if len(candles_5m) < retest_lookback + 1:
        return False

    c0 = candles_5m[-1]
    c1 = candles_5m[-2]

    if c0.timestamp.date() != today_ist():
        return False

    # Current candle must close above VWAP
    if c0.close <= vwap:
        return False

    # Momentum: close must break above previous candle high
    if c0.close <= c1.high:
        return False

    # Minimum bounce distance above VWAP
    if min_bounce_pts > 0 and (c0.close - vwap) < min_bounce_pts:
        return False

    if not vwap_slope_ok(candles_5m, "CE", slope_lookback):
        return False

    # At least one candle in the lookback window must have closed below VWAP
    if vwap_retest_ts(candles_5m, vwap, "CE", retest_lookback) is None:
        logger.debug(
            "VWAP CE: no retest — none of last %d candles closed below VWAP %.2f",
            retest_lookback, vwap,
        )
        return False

    # Excessive submerge check: price must not have spent too many consecutive
    # TODAY candles below VWAP (prevents false breakouts from an extended downtrend).
    # Restricted to today-only candles — previous-day data sits below today's
    # freshly-reset VWAP and would trigger a spurious block on morning signals.
    if max_submerged_candles > 0:
        _today_date = c0.timestamp.date()
        submerged_count = 0
        for c in reversed(candles_5m[:-1]):
            if c.timestamp.date() != _today_date:
                break
            if c.close < vwap:
                submerged_count += 1
            else:
                break
        if submerged_count > max_submerged_candles:
            logger.debug(
                "VWAP CE: excessive submerge — %d consecutive candles closed below VWAP > max %d",
                submerged_count, max_submerged_candles,
            )
            return False

    # ── Enhanced mean-reversion filters ──────────────────────────────────────

    if mr_zscore_entry > 0:
        z = vwap_zscore(candles_5m, vwap)
        # For CE, price was below VWAP — z should be sufficiently negative before bounce
        if z is not None and abs(z) < mr_zscore_entry:
            logger.debug("VWAP CE: z-score %.2f < required %.2f", abs(z) if z else 0, mr_zscore_entry)
            return False

    if not adx_regime_ok(candles_5m, mr_adx_max):
        return False

    if mr_rsi_confirm and not rsi_reversal_ok(candles_5m, "CE"):
        return False

    if mr_volume_spike > 0 and not volume_spike(candles_5m, multiplier=mr_volume_spike):
        return False

    if mr_vwap_cross_min > 0 and vwap_cross_count(candles_5m, vwap) < mr_vwap_cross_min:
        logger.debug("VWAP CE: cross count %d < required %d",
                     vwap_cross_count(candles_5m, vwap), mr_vwap_cross_min)
        return False

    if mr_min_rr > 0:
        # Stop is estimated as the low of the reversal candle (c0.low)
        if not reward_to_risk_ok(c0.close, vwap, c0.low, min_rr=mr_min_rr):
            return False

    if mr_min_score > 0:
        score = setup_score(
            candles_5m, vwap, "CE", stop=c0.low,
            zscore_threshold=max(mr_zscore_entry, 2.0),
            adx_max=mr_adx_max if mr_adx_max > 0 else 25.0,
            min_rr=mr_min_rr if mr_min_rr > 0 else 1.5,
            vol_multiplier=mr_volume_spike if mr_volume_spike > 0 else 1.5,
        )
        if score < mr_min_score:
            logger.debug("VWAP CE: setup score %d < required %d", score, mr_min_score)
            return False

    return True


def is_vwap_pe_signal(
    candles_5m: Sequence[Candle],
    vwap: float | None,
    *,
    retest_lookback: int = 3,
    min_bounce_pts: float = 0.0,
    max_submerged_candles: int = 3,
    slope_lookback: int = 0,
    # Enhanced mean-reversion filters (all default off for backward compatibility)
    mr_zscore_entry: float = 0.0,
    mr_adx_max: float = 0.0,
    mr_rsi_confirm: bool = False,
    mr_volume_spike: float = 0.0,
    mr_min_rr: float = 0.0,
    mr_min_score: int = 0,
    mr_vwap_cross_min: int = 0,
) -> bool:
    """
    Return True when:
      1. VWAP is available and valid.
      2. Within the last *retest_lookback* completed candles, at least one
         closed ABOVE VWAP (the retest pop).
      3. The current (latest) candle closes BELOW VWAP.
      4. Current close < previous candle low (momentum confirmation).
      5. Close is at least min_bounce_pts below VWAP.
      6. VWAP is falling or flat (slope_lookback > 0).

    Enhanced filters (all opt-in, default disabled):
      7.  |z-score| >= mr_zscore_entry     (price far enough from VWAP)
      8.  ADX < mr_adx_max                 (non-trending regime)
      9.  RSI crossed back below 70         (mr_rsi_confirm=True)
      10. Volume spike present              (mr_volume_spike > 0)
      11. Reward-to-VWAP / risk >= mr_min_rr
      12. Setup score >= mr_min_score       (composite quality gate)
      13. VWAP crossed >= mr_vwap_cross_min times today
    """
    if vwap is None or vwap <= 0:
        return False
    if len(candles_5m) < retest_lookback + 1:
        return False

    c0 = candles_5m[-1]
    c1 = candles_5m[-2]

    if c0.timestamp.date() != today_ist():
        return False

    # Current candle must close below VWAP
    if c0.close >= vwap:
        return False

    # Momentum: close must break below previous candle low
    if c0.close >= c1.low:
        return False

    # Minimum bounce distance below VWAP
    if min_bounce_pts > 0 and (vwap - c0.close) < min_bounce_pts:
        return False

    if not vwap_slope_ok(candles_5m, "PE", slope_lookback):
        return False

    # At least one candle in the lookback window must have closed above VWAP
    if vwap_retest_ts(candles_5m, vwap, "PE", retest_lookback) is None:
        logger.debug(
            "VWAP PE: no retest — none of last %d candles closed above VWAP %.2f",
            retest_lookback, vwap,
        )
        return False

    # Excessive submerge check: price must not have spent too many consecutive
    # TODAY candles above VWAP (prevents false breakdowns from an extended uptrend).
    # Restricted to today-only candles — previous-day data sits below today's
    # freshly-reset VWAP and would trigger a spurious block on morning signals.
    if max_submerged_candles > 0:
        _today_date = c0.timestamp.date()
        emerged_count = 0
        for c in reversed(candles_5m[:-1]):
            if c.timestamp.date() != _today_date:
                break
            if c.close > vwap:
                emerged_count += 1
            else:
                break
        if emerged_count > max_submerged_candles:
            logger.debug(
                "VWAP PE: excessive submerge — %d consecutive candles closed above VWAP > max %d",
                emerged_count, max_submerged_candles,
            )
            return False

    # ── Enhanced mean-reversion filters ──────────────────────────────────────

    if mr_zscore_entry > 0:
        z = vwap_zscore(candles_5m, vwap)
        # For PE, price was above VWAP — z should be sufficiently positive before rejection
        if z is not None and abs(z) < mr_zscore_entry:
            logger.debug("VWAP PE: z-score %.2f < required %.2f", abs(z) if z else 0, mr_zscore_entry)
            return False

    if not adx_regime_ok(candles_5m, mr_adx_max):
        return False

    if mr_rsi_confirm and not rsi_reversal_ok(candles_5m, "PE"):
        return False

    if mr_volume_spike > 0 and not volume_spike(candles_5m, multiplier=mr_volume_spike):
        return False

    if mr_vwap_cross_min > 0 and vwap_cross_count(candles_5m, vwap) < mr_vwap_cross_min:
        logger.debug("VWAP PE: cross count %d < required %d",
                     vwap_cross_count(candles_5m, vwap), mr_vwap_cross_min)
        return False

    if mr_min_rr > 0:
        # Stop is estimated as the high of the reversal candle (c0.high)
        if not reward_to_risk_ok(c0.close, vwap, c0.high, min_rr=mr_min_rr):
            return False

    if mr_min_score > 0:
        score = setup_score(
            candles_5m, vwap, "PE", stop=c0.high,
            zscore_threshold=max(mr_zscore_entry, 2.0),
            adx_max=mr_adx_max if mr_adx_max > 0 else 25.0,
            min_rr=mr_min_rr if mr_min_rr > 0 else 1.5,
            vol_multiplier=mr_volume_spike if mr_volume_spike > 0 else 1.5,
        )
        if score < mr_min_score:
            logger.debug("VWAP PE: setup score %d < required %d", score, mr_min_score)
            return False

    return True
