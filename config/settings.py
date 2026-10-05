"""
Central configuration loaded from environment variables / .env file.
All trading parameters are read here — no magic numbers anywhere else.
"""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Explicitly resolve the root .env path so running python from any working directory picks it up
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=True)


def _get(key: str, default: str = "") -> str:
    val = os.environ.get(key, "").strip()
    return val if val else default


def _getfloat(key: str, default: float) -> float:
    val = os.environ.get(key, "").strip()
    return float(val) if val else default


def _getint(key: str, default: int) -> int:
    val = os.environ.get(key, "").strip()
    return int(val) if val else default


def _getbool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "").strip()
    return val.lower() in ("true", "1", "yes") if val else default


# ── Broker ────────────────────────────────────────────────────────────────────
KITE_API_KEY: str = _get("KITE_API_KEY")
KITE_API_SECRET: str = _get("KITE_API_SECRET")
KITE_ACCESS_TOKEN: str = _get("KITE_ACCESS_TOKEN")

# ── Trading mode ──────────────────────────────────────────────────────────────
TRADING_MODE: Literal["PAPER", "SHADOW", "LIVE"] = _get("TRADING_MODE", "PAPER").upper()  # type: ignore[assignment]
ENABLE_LIVE_TRADING: bool = _getbool("ENABLE_LIVE_TRADING", False)

# ── Instrument ────────────────────────────────────────────────────────────────
UNDERLYING: str = _get("UNDERLYING", "SENSEX")
QUANTITY: int = _getint("QUANTITY", 20)
# Minimum option premium (LTP) required to place an entry order.
# Entries are skipped when the option LTP is below this threshold.
# Prevents buying near-expiry / deep-OTM options with no recovery room.
# 0 = disabled (no floor). Recommended: 300 for SENSEX weekly options.
MIN_OPTION_ENTRY_PRICE: float = _getfloat("MIN_OPTION_ENTRY_PRICE", 0.0)

# ── Risk parameters ───────────────────────────────────────────────────────────
INITIAL_SL_POINTS: float = _getfloat("INITIAL_SL_POINTS", 30)
BREAK_EVEN_TRIGGER_POINTS: float = _getfloat("BREAK_EVEN_TRIGGER_POINTS", 30)
TRAIL_STEP_POINTS: float = _getfloat("TRAIL_STEP_POINTS", 10)

INITIAL_TARGET_OFFSET_POINTS: float = _getfloat("INITIAL_TARGET_OFFSET_POINTS", 50)
TARGET_TRAIL_STEP_POINTS: float = _getfloat("TARGET_TRAIL_STEP_POINTS", 10)
USE_LIVE_TARGET_ORDER: bool = _getbool("USE_LIVE_TARGET_ORDER", False)

USE_TRAILING_STOP_EXIT: bool = _getbool("USE_TRAILING_STOP_EXIT", True)

# ── ATR-adaptive risk ─────────────────────────────────────────────────────────
# Two active modes, evaluated in priority order:
#
# Mode D — swing high/low as SL  (USE_SWING_SL=true)  [highest priority]
#   SL placed at nearest structural pivot (mirrors TradingView AI Copilot).
#   Falls back to Mode C automatically when no swing level is found.
#   SWING_SL_LENGTH : pivot look-back window (default 10)
#   MIN_RR          : minimum R:R required to place the entry (0 = disabled)
#
# Mode C — SENSEX spot ATR × multiplier  (USE_SPOT_ATR_RISK=true)  [default]
#   SL     = ATR(SPOT_ATR_PERIOD, 5m SENSEX) × SPOT_ATR_SL_MULT × ATM_delta(0.4)
#   Target = SL × SPOT_ATR_TARGET_RR   (R:R ratio, e.g. 1.2)
#   Trail  = SL × SPOT_ATR_TRAIL_RR    (e.g. 0.5 = half the SL)
#   Adapts to market momentum: wide on volatile days, tight on calm days.
#   Mirrors the TradingView "ATR 5 Min Index Study".
#
# Fixed fallback — used only when ATR is unavailable (cold start / insufficient candles).
MIN_SL_POINTS: float            = _getfloat("MIN_SL_POINTS", 20.0)
MIN_TARGET_POINTS: float        = _getfloat("MIN_TARGET_POINTS", 30.0)
MIN_TRAIL_POINTS: float         = _getfloat("MIN_TRAIL_POINTS", 5.0)
# Mode C — SENSEX spot ATR-based risk
USE_SPOT_ATR_RISK: bool         = _getbool("USE_SPOT_ATR_RISK", True)
SPOT_ATR_PERIOD: int            = _getint("SPOT_ATR_PERIOD", 5)
SPOT_ATR_SL_MULT: float         = _getfloat("SPOT_ATR_SL_MULT", 2.5)
SPOT_ATR_TARGET_RR: float       = _getfloat("SPOT_ATR_TARGET_RR", 1.2)
SPOT_ATR_TRAIL_RR: float        = _getfloat("SPOT_ATR_TRAIL_RR", 0.5)
# Mode D — swing high/low as SL
# Falls back to Mode C automatically when no swing level is found.
USE_SWING_SL: bool              = _getbool("USE_SWING_SL", False)
SWING_SL_LENGTH: int            = _getint("SWING_SL_LENGTH", 10)
MIN_RR: float                   = _getfloat("MIN_RR", 0.0)

# ── Smart Exit Engine ─────────────────────────────────────────────────────────
# All Smart Exit sub-features default OFF.
# Baseline lifecycle: ENTRY → INITIAL SL → BREAK-EVEN → TSL → EOD EXIT.
# Enable sub-features one at a time once the core lifecycle is verified reliable
# in paper/shadow mode and the P&L attribution is clearly understood.
ENABLE_SMART_EXIT: bool           = _getbool("ENABLE_SMART_EXIT", False)
ENABLE_REVERSAL_EXIT: bool        = _getbool("ENABLE_REVERSAL_EXIT", False)
ENABLE_EMA_COLLAPSE_EXIT: bool    = _getbool("ENABLE_EMA_COLLAPSE_EXIT", False)
ENABLE_PROFIT_LOCK_EXIT: bool     = _getbool("ENABLE_PROFIT_LOCK_EXIT", False)
ENABLE_TIME_DECAY_EXIT: bool      = _getbool("ENABLE_TIME_DECAY_EXIT", False)
ENABLE_DAILY_LOSS_LIMIT: bool     = _getbool("ENABLE_DAILY_LOSS_LIMIT", False)
PROFIT_LOCK_MULTIPLIER: float     = _getfloat("PROFIT_LOCK_MULTIPLIER", 2.0)
# ATR-based profit lock — threshold = entry + ATR(14) × this multiplier.
# When > 0, contributes a candidate threshold alongside PROFIT_LOCK_MIN_PCT.
# 0.0 = disabled.  Recommended: 1.0
# Example: entry=225, ATR=55 → threshold = 225 + 55 = 280 pts
PROFIT_LOCK_ATR_MULT: float       = _getfloat("PROFIT_LOCK_ATR_MULT", 0.0)
# %-based profit lock floor — threshold = entry × (1 + this value).
# Ensures the lock scales with the option premium on high-value entries.
# 0.0 = disabled.  Recommended: 0.5 (= 50% gain, i.e. 1.5× entry)
# Example: entry=520, pct=0.5 → threshold = 520 × 1.5 = 780 pts
# Final threshold = max(ATR-based, %-based).  If neither is set → fixed mult.
PROFIT_LOCK_MIN_PCT: float        = _getfloat("PROFIT_LOCK_MIN_PCT", 0.0)
TIME_DECAY_EXIT_AFTER: str        = _get("TIME_DECAY_EXIT_AFTER", "14:45")
TIME_DECAY_MIN_PNL_PTS: float     = _getfloat("TIME_DECAY_MIN_PNL_PTS", 20.0)
DAILY_LOSS_LIMIT_PTS: float       = _getfloat("DAILY_LOSS_LIMIT_PTS", 200.0)

# ── Session ───────────────────────────────────────────────────────────────────
TIMEZONE: str = _get("TIMEZONE", "Asia/Kolkata")
FORCE_EXIT_TIME: str = _get("FORCE_EXIT_TIME", "15:15")
NO_NEW_ENTRY_AFTER: str = _get("NO_NEW_ENTRY_AFTER", "15:00")

# ── Strategy Toggles ──────────────────────────────────────────────────────────
ENABLE_EMA_STRATEGY: bool = _getbool("ENABLE_EMA_STRATEGY", True)
ENABLE_ORB_STRATEGY: bool = _getbool("ENABLE_ORB_STRATEGY", True)

# ── Structure Breakdown Cooldown Bypass ───────────────────────────────────────
# When a signal arrives during cooldown AND the market shows a clear structural
# breakdown (N consecutive lower highs for PE / higher lows for CE) while close
# is already on the wrong side of EMA9, the cooldown is reduced to 1 candle.
#
# Rationale: the cooldown is meant to block re-entries into choppy reversals.
# When 3+ consecutive lower highs are visible AND close < EMA9 (for PE), the
# market is NOT choppy — it is trending.  Blocking in that case costs trades
# exactly as happened on 2026-10-05 with PE_NATR at 10:20.
#
# SMART_ENTRY_STRUCTURE_BYPASS_CANDLES : N consecutive lower highs/higher lows
#   required to trigger the bypass. 0 = disabled. Default 3.
# SMART_ENTRY_STRUCTURE_BYPASS_EMA_CONFIRM : also require close < EMA9 (PE) or
#   close > EMA9 (CE) for the bypass to fire. True = stricter. Default true.
SMART_ENTRY_STRUCTURE_BYPASS_CANDLES: int   = _getint("SMART_ENTRY_STRUCTURE_BYPASS_CANDLES", 0)
SMART_ENTRY_STRUCTURE_BYPASS_EMA_CONFIRM: bool = _getbool("SMART_ENTRY_STRUCTURE_BYPASS_EMA_CONFIRM", True)

# ── Smart Entry Filter ────────────────────────────────────────────────────────
# Quality gate applied AFTER a raw signal (EMA / ORB / OB / MOM) fires.
# All default OFF — set to enable.  Zero behaviour change until opted in.
#
# SMART_ENTRY_MIN_BODY_ATR_RATIO : signal candle body must be >= this fraction
#   of ATR(14).  0.0 = disabled.  Recommended: 0.3
#   Rejects doji / wick-spike candles with no real momentum.
#
# SMART_ENTRY_REQUIRE_EMA_SLOPE  : if true, EMA9 must be rising (CE) or falling
#   (PE) on the signal candle.  Prevents entering a stalling move.
#
# SMART_ENTRY_COOLDOWN_CANDLES   : number of completed 5m candles to block new
#   entries after an SL loss.  0 = disabled.  Recommended: 2
#   Prevents immediately re-entering a choppy / reversing market.
SMART_ENTRY_MIN_BODY_ATR_RATIO: float    = _getfloat("SMART_ENTRY_MIN_BODY_ATR_RATIO",    0.0)
SMART_ENTRY_REQUIRE_EMA_SLOPE: bool      = _getbool("SMART_ENTRY_REQUIRE_EMA_SLOPE",      False)
SMART_ENTRY_COOLDOWN_CANDLES: int        = _getint("SMART_ENTRY_COOLDOWN_CANDLES",         0)
# Filter 4 — minimum EMA gap (0 = disabled; recommended: 10)
# Filter 5 — EMA gap must be widening (false = disabled; recommended: true)
SMART_ENTRY_MIN_EMA_GAP_PTS: float       = _getfloat("SMART_ENTRY_MIN_EMA_GAP_PTS",       0.0)
SMART_ENTRY_REQUIRE_EMA_GAP_WIDENING: bool = _getbool("SMART_ENTRY_REQUIRE_EMA_GAP_WIDENING", False)
# Filter 6 — 15m trend alignment (false = disabled; recommended: true)
# CE only fires when latest 15m candle closes above 15m EMA21; PE vice-versa.
# Skipped (fail-open) when fewer than 21 completed 15m candles are available.
SMART_ENTRY_REQUIRE_15M_TREND: bool      = _getbool("SMART_ENTRY_REQUIRE_15M_TREND",      False)

# Filter 6b — 15m gap threshold (0 = hard binary block; >0 = allow entry when
# 15m close is within this many pts of EMA21, even if technically below it).
# Solves the "squeeze block" problem: when 15m EMA21 is lagging far behind an
# intraday rally, the filter blocks valid CE entries until it catches up.
# Example: SMART_ENTRY_15M_MAX_GAP_PTS=150 → CE is blocked only when 15m close
# is MORE than 150 pts below EMA21; mild bearish-15m entries are allowed.
# 0 = original binary behaviour (any gap blocks).  Recommended: 100–200 pts.
# Only applies when SMART_ENTRY_REQUIRE_15M_TREND=true.
SMART_ENTRY_15M_MAX_GAP_PTS: float       = _getfloat("SMART_ENTRY_15M_MAX_GAP_PTS",       0.0)

# Filter 7 — Momentum squeeze bypass.
# When SMART_ENTRY_SQUEEZE_BYPASS=true, the 15m trend filter and EMA slope
# filter are skipped if the last N consecutive 5m candles are ALL bullish (CE)
# or ALL bearish (PE).  Captures squeeze-and-release moves where the 15m EMA
# hasn't caught up yet but the 5m structure is unambiguous.
# SMART_ENTRY_SQUEEZE_CANDLES: how many consecutive same-direction 5m candles
# are needed to trigger the bypass. 0 = disabled. Recommended: 3.
SMART_ENTRY_SQUEEZE_BYPASS: bool         = _getbool("SMART_ENTRY_SQUEEZE_BYPASS",         False)
SMART_ENTRY_SQUEEZE_CANDLES: int         = _getint("SMART_ENTRY_SQUEEZE_CANDLES",          3)
# Filter 7b — Relaxed body ratio during a squeeze move.
# When squeeze bypass is active (N consecutive same-direction candles),
# the body/ATR check uses this looser ratio instead of SMART_ENTRY_MIN_BODY_ATR_RATIO.
# Rationale: on strong trend days the signal candle is often a smaller continuation
# candle — still valid, but its body is smaller because momentum is already priced in.
# 0.0 = use the same ratio as normal (no relaxation).
# Recommended: 0.25 (vs default 0.35 normal ratio).
SMART_ENTRY_SQUEEZE_BODY_ATR_RATIO: float = _getfloat("SMART_ENTRY_SQUEEZE_BODY_ATR_RATIO", 0.0)

# Filter 8b — Bounce-exempt strategies.
# Comma-separated list of strategy name suffixes that bypass Filters 1, 4 & 5
# (body/ATR ratio, EMA gap magnitude, EMA gap widening).
# These are "bounce" strategies whose own structural level already confirms the
# entry — the EMA gap is expected to be flat at a VWAP retest or NATR crossover.
# Default: "VWAP,NATR" — skip body + EMA-gap filters for CE_VWAP / PE_VWAP /
#   CE_NATR / PE_NATR signals.
# "" = disable (all strategies subject to body/EMA-gap filters equally).
# Example: SMART_ENTRY_BOUNCE_EXEMPT_STRATEGIES=VWAP,NATR,OB
_BOUNCE_EXEMPT_RAW: str = _get("SMART_ENTRY_BOUNCE_EXEMPT_STRATEGIES", "VWAP,NATR")
SMART_ENTRY_BOUNCE_EXEMPT_STRATEGIES: set[str] = (
    {s.strip().upper() for s in _BOUNCE_EXEMPT_RAW.split(",") if s.strip()}
    if _BOUNCE_EXEMPT_RAW.strip()
    else set()
)

# Filter 8 — Option premium extension guard.
# Blocks entry when the option LTP has already risen more than this fraction
# above its first-seen price on today's session.
#
# Problem: EMA fires a CE signal at ₹331 on an option that traded at ₹140
# earlier in the day — the entire move is already done; the bot enters at the
# peak.  This filter kills that scenario.
#
# How it works: the first LTP observed for each option symbol is recorded via
# SmartEntryFilter.notify_option_ltp().  At signal time, if:
#   current_ltp > first_seen_ltp × (1 + SMART_ENTRY_MAX_PREMIUM_EXTENSION_PCT)
# the entry is rejected regardless of EMA alignment.
#
# Examples (with recommended value of 1.5):
#   first_seen=140, current=331 → extension=136% → 136% > 150%? No → allowed
#   first_seen=140, current=360 → extension=157% → 157% > 150%? Yes → BLOCKED
#   first_seen=200, current=350 → extension=75%  → 75% > 150%? No → allowed
#
# 0 = disabled (default — no behaviour change).
# Recommended: 1.5 for SENSEX weekly options (blocks entry after a 150% move).
# Default 1.0 = block entry when the option has already moved >100% from its first-seen
# price today.  This kills the "buy at the peak" scenario (e.g. Rs.140 → Rs.331 = +136%
# which is > 100%, so it would have been blocked).  Set to 0 to disable.
SMART_ENTRY_MAX_PREMIUM_EXTENSION_PCT: float = _getfloat("SMART_ENTRY_MAX_PREMIUM_EXTENSION_PCT", 1.0)

# ── ORB false-breakout filters ────────────────────────────────────────────────
# All default OFF (0 / false) so existing behaviour is unchanged until opted in.
#
# ORB_MIN_BODY_RATIO   : breakout candle body / range must be >= this value.
#                        0.0 = disabled.  0.4 = body must be 40% of the candle
#                        range — rejects doji / wick-only crossovers.
# ORB_BUFFER_ATR_MULT  : close must exceed ORB level by ATR(14)*mult before
#                        the signal fires.  0.0 = disabled.  0.1 = close must
#                        be at least 10% of ATR beyond the ORB boundary.
# ORB_REQUIRE_15M_TREND: if true, CE_ORB only fires when 15m close > 15m EMA21,
#                        PE_ORB only when 15m close < 15m EMA21.
ORB_MIN_BODY_RATIO: float   = _getfloat("ORB_MIN_BODY_RATIO",   0.0)
ORB_BUFFER_ATR_MULT: float  = _getfloat("ORB_BUFFER_ATR_MULT",  0.0)
ORB_REQUIRE_15M_TREND: bool = _getbool("ORB_REQUIRE_15M_TREND", False)
# ORB only fires for candles whose timestamp is at or before this time.
# After this time ORB is silently skipped and EMA takes over.
# "" = no cutoff (active all day).  Default: "11:00"
ORB_ACTIVE_UNTIL: str       = _get("ORB_ACTIVE_UNTIL", "09:40")
# Skip ORB and Momentum signals on Mondays.
# Backtest shows 0% win rate for both strategies on Monday; all other strategies
# (EMA, TRB, OB, VWAP, PDHL) are unaffected and continue to trade normally.
# true = skip ORB + MOMENTUM on Mondays (recommended).  false = no restriction.
ORB_MOMENTUM_SKIP_MONDAY: bool = _getbool("ORB_MOMENTUM_SKIP_MONDAY", True)
# ORB Session Qualifier — data-driven sideways-day filter
#
# When ORB_SESSION_QUALIFIER=true, at 10:00 the bot checks whether the
# opening range breakout is still holding.  Two outcomes:
#
#   SUSTAINED (close outside ORB range at 10:00)
#     → all strategies fire normally for the rest of the day.
#
#   FAILED (close back inside ORB range at 10:00)
#     → EMA, VWAP, TRB, PDHL, OB are BLOCKED from 10:00 until
#       ORB_QUALIFIER_UNBLOCK_TIME.  ORB itself and Momentum Phase 2
#       are always exempt.
#
# ORB_QUALIFIER_UNBLOCK_TIME controls how long the block lasts.
#   "13:30" (default) = unblock at the Momentum afternoon window.
#     Use this if you trust the data — choppy mornings rarely develop
#     a real trend before 13:30.
#   "11:30" = shorter block — EMA / VWAP can still fire in the late
#     morning if they form a real setup.  More signals, more risk.
#   "10:00" = no block at all (same as ORB_SESSION_QUALIFIER=false).
#
# Based on 6-month SENSEX data: 57% of days are sideways.  On those
# days EMA fires 18× and VWAP crosses 9× — pure noise.  This filter
# kills that grinding-loss pattern while preserving the afternoon engine.
#
ORB_SESSION_QUALIFIER: bool      = _getbool("ORB_SESSION_QUALIFIER", False)
ORB_QUALIFIER_UNBLOCK_TIME: str  = _get("ORB_QUALIFIER_UNBLOCK_TIME", "13:30")

# ── Momentum (Phase 2) strategy ───────────────────────────────────────────────
# When enabled, a second entry path fires during the afternoon breakout window
# on large-body candles even if close does not exceed the previous candle high.
ENABLE_MOMENTUM_PHASE: bool = _getbool("ENABLE_MOMENTUM_PHASE", False)
MOMENTUM_MIN_BODY_PTS: float = _getfloat("MOMENTUM_MIN_BODY_PTS", 40.0)
MOMENTUM_WINDOW_START: str = _get("MOMENTUM_WINDOW_START", "13:30")
MOMENTUM_WINDOW_END: str   = _get("MOMENTUM_WINDOW_END",   "14:30")

# ── Order Block (OB) strategy ─────────────────────────────────────────────────
# When enabled, CE_OB / PE_OB signals fire when price closes inside a valid
# (non-breaker) bullish / bearish order block detected on the 5m chart.
# Logic mirrors the "Volumized Order Blocks | Flux Charts" Pine Script indicator.
#
# OB_SWING_LENGTH     : candles used to detect swing highs/lows (Pine default 10)
# OB_MAX_ATR_MULT     : OBs larger than ATR(OB_ATR_PERIOD) * this are discarded (Pine default 3.5)
# OB_ATR_PERIOD       : ATR period for the size cap (Pine default 10)
# OB_MAX_BLOCKS       : max OBs to track per side ("Low"=3, "Medium"=5, "High"=10)
# OB_INVALIDATION     : "Wick" (wick pierces OB bottom/top) or "Close" (close pierces)
ENABLE_OB_STRATEGY: bool  = _getbool("ENABLE_OB_STRATEGY", False)
OB_SWING_LENGTH: int      = _getint("OB_SWING_LENGTH", 10)
OB_MAX_ATR_MULT: float    = _getfloat("OB_MAX_ATR_MULT", 3.5)
OB_ATR_PERIOD: int        = _getint("OB_ATR_PERIOD", 10)
OB_MAX_BLOCKS: int        = _getint("OB_MAX_BLOCKS", 3)
OB_INVALIDATION: str      = _get("OB_INVALIDATION", "Wick")

# ── TRB (Time Range Breakout) strategy ─────────────────────────────────────────
ENABLE_TRB_STRATEGY: bool      = _getbool("ENABLE_TRB_STRATEGY", False)
TRB_CANDLE_START_TIME: str     = _get("TRB_CANDLE_START_TIME", "09:45")
TRB_CANDLE_DURATION_MINS: int  = _getint("TRB_CANDLE_DURATION_MINS", 15)
TRB_MIN_BODY_RATIO: float      = _getfloat("TRB_MIN_BODY_RATIO", 0.0)
TRB_BUFFER_ATR_MULT: float     = _getfloat("TRB_BUFFER_ATR_MULT", 0.0)

# ── VWAP Retest strategy ──────────────────────────────────────────────────────
# Fires CE_VWAP/PE_VWAP when price retests VWAP and bounces back.
# VWAP is calculated intraday from completed 5m candles (resets at 09:15).
ENABLE_VWAP_STRATEGY: bool    = _getbool("ENABLE_VWAP_STRATEGY", False)
# Candles to look back for the retest dip/pop (default 3 = 15 minutes)
VWAP_RETEST_LOOKBACK: int     = _getint("VWAP_RETEST_LOOKBACK", 3)
# Minimum distance close must be above/below VWAP to confirm bounce (0 = disabled)
VWAP_MIN_BOUNCE_PTS: float    = _getfloat("VWAP_MIN_BOUNCE_PTS", 0.0)

# ── PDHL (Previous Day High/Low) Breakout strategy ───────────────────────────
# Fires CE_PDHL/PE_PDHL when price breaks convincingly above PDH or below PDL.
# PDH/PDL are fetched from Zerodha daily historical data at bot startup.
ENABLE_PDHL_STRATEGY: bool    = _getbool("ENABLE_PDHL_STRATEGY", False)
# Extra buffer beyond PDH/PDL the close must clear to avoid noise breakouts (0 = disabled)
PDHL_BUFFER_PTS: float        = _getfloat("PDHL_BUFFER_PTS", 0.0)

# ── NATR Trailing Stop strategy ───────────────────────────────────────────────
# Fires CE_NATR/PE_NATR when the 5m close crosses the ATR-based trailing stop.
# Mirrors the "ATR 5 Min Index Study" indicator.
# The trailing stop ratchets up in uptrends and down in downtrends; a crossover
# signals a trend flip.
# NOTE: This is a SEPARATE strategy from ATR Copilot (band breakout).
ENABLE_NATR_STRATEGY: bool    = _getbool("ENABLE_NATR_STRATEGY", False)
NATR_PERIOD: int              = _getint("NATR_PERIOD", 21)
NATR_MULT: float              = _getfloat("NATR_MULT", 3.0)

# ── ATR Copilot strategy ───────────────────────────────────────────────────────
# Fires CE_ATR/PE_ATR when the 5m candle closes outside the ATR band for the
# first time (breakout from noise zone).
# Bands: EMA(ema_period) ± ATR(atr_period) × band_mult
# Signal fires on the first bar where price closes outside the band (prev close
# was inside, current close is outside).
ENABLE_ATR_COPILOT_STRATEGY: bool  = _getbool("ENABLE_ATR_COPILOT_STRATEGY", False)
ATR_COPILOT_PERIOD: int            = _getint("ATR_COPILOT_PERIOD", 5)
ATR_COPILOT_EMA_PERIOD: int        = _getint("ATR_COPILOT_EMA_PERIOD", 21)
ATR_COPILOT_BAND_MULT: float       = _getfloat("ATR_COPILOT_BAND_MULT", 3.0)
# Minimum R:R gate — PE entries need >= 1.2, CE entries need >= 2.0 (stricter)
ATR_COPILOT_MIN_RR: float          = _getfloat("ATR_COPILOT_MIN_RR", 1.2)
ATR_COPILOT_LONG_MIN_RR: float     = _getfloat("ATR_COPILOT_LONG_MIN_RR", 2.0)
# Minimum clearance past the band required for the signal to fire.
# Expressed as a fraction of ATR(atr_period) so it scales with volatility.
# 0.0 = disabled (any tick past the band fires — raw band-touch behaviour).
# 0.2 = close must clear the band by at least 0.2 × ATR (recommended filter).
# Example: ATR=60 → buffer = 60 × 0.2 = 12 pts minimum clearance past band.
# Default is 0.0 so the bot fires on raw touches unless you explicitly set this
# in your .env file.  Set ATR_COPILOT_BREAKOUT_BUFFER=0.2 to enable the filter.
ATR_COPILOT_BREAKOUT_BUFFER: float = _getfloat("ATR_COPILOT_BREAKOUT_BUFFER", 0.0)

# ── Expiry ────────────────────────────────────────────────────────────────────
EXPIRY_MODE: Literal["CONFIGURED", "AUTO"] = _get("EXPIRY_MODE", "CONFIGURED").upper()  # type: ignore[assignment]
CONFIGURED_EXPIRY: str = _get("CONFIGURED_EXPIRY", "")

# ── Persistence ───────────────────────────────────────────────────────────────
DB_PATH: str = _get("DB_PATH", "trades.db")

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = _get("LOG_LEVEL", "INFO").upper()

# ── Manual-intervention guard ─────────────────────────────────────────────────
RECREATE_SL_ON_MANUAL_CANCEL: bool = _getbool("RECREATE_SL_ON_MANUAL_CANCEL", False)

# ── AI Entry / Exit Confirmation ──────────────────────────────────────────────
# Optional LLM quality gate applied after every rule-based signal fires.
# Disabled by default — zero behaviour change until ENABLE_AI_CONFIRMATION=true.
ENABLE_AI_CONFIRMATION: bool   = _getbool("ENABLE_AI_CONFIRMATION", False)
AI_CONFIRMATION_PROVIDER: str  = _get("AI_CONFIRMATION_PROVIDER", "openai")   # "openai" | "watsonx" | "ollama"
AI_CONFIRMATION_MODEL: str     = _get("AI_CONFIRMATION_MODEL", "gpt-4o-mini")
AI_CONFIRMATION_API_KEY: str     = _get("AI_CONFIRMATION_API_KEY", "")
# Ollama: local server URL (only used when AI_CONFIRMATION_PROVIDER=ollama).
# Default: http://localhost:11434  (standard Ollama install on same machine).
AI_CONFIRMATION_OLLAMA_HOST: str = _get("AI_CONFIRMATION_OLLAMA_HOST", "http://localhost:11434")
# Minimum LLM score (1-10) to allow an entry. Lower = permissive, higher = strict.
AI_ENTRY_SCORE_THRESHOLD: int  = _getint("AI_ENTRY_SCORE_THRESHOLD", 6)
# Minimum LLM score (1-10) to trigger an AI-suggested exit.
AI_EXIT_SCORE_THRESHOLD: int   = _getint("AI_EXIT_SCORE_THRESHOLD", 7)
# Also use AI for exit suggestions on each candle close (ENABLE_AI_CONFIRMATION must be true)
ENABLE_AI_EXIT: bool           = _getbool("ENABLE_AI_EXIT", False)

# ── AI Regime Classifier ──────────────────────────────────────────────────────
# Once per trading day (bot startup), classify the day as TRENDING / CHOPPY /
# VOLATILE and adjust profit-lock thresholds accordingly.
# All default OFF — zero behaviour change until ENABLE_REGIME_CLASSIFIER=true.
ENABLE_REGIME_CLASSIFIER: bool = _getbool("ENABLE_REGIME_CLASSIFIER", False)
REGIME_USE_AI: bool            = _getbool("REGIME_USE_AI", False)
REGIME_AI_PROVIDER: str        = _get("REGIME_AI_PROVIDER", "openai")   # "openai" | "watsonx" | "ollama"
REGIME_AI_MODEL: str           = _get("REGIME_AI_MODEL", "gpt-4o-mini")
REGIME_AI_API_KEY: str         = _get("REGIME_AI_API_KEY", "")
# Ollama: local server URL for regime classifier (only used when REGIME_AI_PROVIDER=ollama)
REGIME_AI_OLLAMA_HOST: str     = _get("REGIME_AI_OLLAMA_HOST", "http://localhost:11434")
# Manual VIX override — set to today's INDIA VIX value (e.g. 14.5). 0 = auto-heuristic.
REGIME_VIX_OVERRIDE: float     = _getfloat("REGIME_VIX_OVERRIDE", 0.0)
# Profit lock ATR mult per regime (replaces PROFIT_LOCK_ATR_MULT when classifier active)
REGIME_ATR_MULT_TRENDING: float  = _getfloat("REGIME_ATR_MULT_TRENDING",  1.5)
REGIME_ATR_MULT_CHOPPY: float    = _getfloat("REGIME_ATR_MULT_CHOPPY",    0.8)
REGIME_ATR_MULT_VOLATILE: float  = _getfloat("REGIME_ATR_MULT_VOLATILE",  1.2)
# Profit lock min pct per regime (replaces PROFIT_LOCK_MIN_PCT when classifier active)
REGIME_MIN_PCT_TRENDING: float   = _getfloat("REGIME_MIN_PCT_TRENDING",   0.6)
REGIME_MIN_PCT_CHOPPY: float     = _getfloat("REGIME_MIN_PCT_CHOPPY",     0.3)
REGIME_MIN_PCT_VOLATILE: float   = _getfloat("REGIME_MIN_PCT_VOLATILE",   0.5)

# ── Validation ────────────────────────────────────────────────────────────────
ALLOWED_MODES = {"PAPER", "SHADOW", "LIVE"}


def validate() -> None:
    if TRADING_MODE not in ALLOWED_MODES:
        raise ValueError(f"TRADING_MODE must be one of {ALLOWED_MODES}, got '{TRADING_MODE}'")
    if TRADING_MODE == "LIVE" and not ENABLE_LIVE_TRADING:
        raise RuntimeError(
            "REFUSE TO START LIVE EXECUTION — "
            "set ENABLE_LIVE_TRADING=true to permit live orders."
        )
    if TRADING_MODE == "LIVE" and not KITE_API_KEY:
        raise ValueError("KITE_API_KEY is required for LIVE mode.")
    if QUANTITY <= 0:
        raise ValueError("QUANTITY must be a positive integer.")
    if EXPIRY_MODE not in ("CONFIGURED", "AUTO"):
        raise ValueError("EXPIRY_MODE must be CONFIGURED or AUTO.")
    if EXPIRY_MODE == "CONFIGURED" and not CONFIGURED_EXPIRY:
        raise ValueError("CONFIGURED_EXPIRY must be set when EXPIRY_MODE=CONFIGURED.")

    # ── Risk parameter sanity checks ──────────────────────────────────────────
    # These protect against misconfigured .env values that would cause the bot
    # to place a live trade with no real stop loss or an inverted risk structure.
    if TRADING_MODE == "LIVE":
        # Mode C: SENSEX spot ATR — verify multiplier is positive
        if USE_SPOT_ATR_RISK and SPOT_ATR_SL_MULT <= 0:
            raise ValueError(
                "SPOT_ATR_SL_MULT must be > 0 when USE_SPOT_ATR_RISK=true in LIVE mode."
            )
        if USE_SPOT_ATR_RISK and SPOT_ATR_TARGET_RR <= 0:
            raise ValueError(
                "SPOT_ATR_TARGET_RR must be > 0 when USE_SPOT_ATR_RISK=true in LIVE mode."
            )
        # Fixed fallback: ensure it is not zero (used when ATR is unavailable)
        if INITIAL_SL_POINTS <= 0:
            raise ValueError(
                "INITIAL_SL_POINTS must be > 0 in LIVE mode — it is the fixed-fallback SL "
                "used when ATR is unavailable at bot startup."
            )
        if INITIAL_TARGET_OFFSET_POINTS <= INITIAL_SL_POINTS:
            raise ValueError(
                f"INITIAL_TARGET_OFFSET_POINTS ({INITIAL_TARGET_OFFSET_POINTS}) must be "
                f"greater than INITIAL_SL_POINTS ({INITIAL_SL_POINTS}) for a positive R:R ratio."
            )

    # ── Smart Exit parameter completeness ─────────────────────────────────────
    # A feature that is enabled but has a missing/zero required parameter would
    # behave silently wrong (e.g. PROFIT_LOCK_MULTIPLIER=0 triggers on every tick).
    # Refuse to start so the operator must fix the configuration explicitly.
    if ENABLE_PROFIT_LOCK_EXIT and PROFIT_LOCK_MULTIPLIER <= 0:
        raise ValueError(
            "ENABLE_PROFIT_LOCK_EXIT=true but PROFIT_LOCK_MULTIPLIER is missing or zero. "
            "Set PROFIT_LOCK_MULTIPLIER to a positive value (e.g. 2.0) or "
            "disable the feature with ENABLE_PROFIT_LOCK_EXIT=false."
        )
    if ENABLE_TIME_DECAY_EXIT and not TIME_DECAY_EXIT_AFTER.strip():
        raise ValueError(
            "ENABLE_TIME_DECAY_EXIT=true but TIME_DECAY_EXIT_AFTER is blank. "
            "Set a valid IST time (e.g. TIME_DECAY_EXIT_AFTER=14:45) or "
            "disable the feature with ENABLE_TIME_DECAY_EXIT=false."
        )
    if ENABLE_TIME_DECAY_EXIT and TIME_DECAY_MIN_PNL_PTS <= 0:
        raise ValueError(
            "ENABLE_TIME_DECAY_EXIT=true but TIME_DECAY_MIN_PNL_PTS is missing or zero. "
            "Set a positive threshold (e.g. TIME_DECAY_MIN_PNL_PTS=20.0) or "
            "disable the feature with ENABLE_TIME_DECAY_EXIT=false."
        )
    if ENABLE_DAILY_LOSS_LIMIT and DAILY_LOSS_LIMIT_PTS <= 0:
        raise ValueError(
            "ENABLE_DAILY_LOSS_LIMIT=true but DAILY_LOSS_LIMIT_PTS is missing or zero. "
            "Set a positive loss cap (e.g. DAILY_LOSS_LIMIT_PTS=200.0) or "
            "disable the feature with ENABLE_DAILY_LOSS_LIMIT=false."
        )
