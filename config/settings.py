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
KITE_TOKEN_DATE: str = _get("KITE_TOKEN_DATE")   # ISO date when token was generated (YYYY-MM-DD)

# ── Trading mode ──────────────────────────────────────────────────────────────
TRADING_MODE: Literal["PAPER", "SHADOW", "LIVE"] = _get("TRADING_MODE", "PAPER").upper()  # type: ignore[assignment]
ENABLE_LIVE_TRADING: bool = _getbool("ENABLE_LIVE_TRADING", False)

# ── Instrument ────────────────────────────────────────────────────────────────
UNDERLYING: str = _get("UNDERLYING", "SENSEX")
QUANTITY: int = _getint("QUANTITY", 20)
# EMA-specific overrides — applied only when the signal is CE or PE (pure EMA strategy).
# When set, these override the global value for EMA trades only.
# 0 / empty = use the global value.
EMA_QUANTITY: int           = _getint("EMA_QUANTITY", 0)        # 0 = use QUANTITY
# Minimum option premium (LTP) required to place an entry order.
# Entries are skipped when the option LTP is below this threshold.
# Prevents buying near-expiry / deep-OTM options with no recovery room.
# 0 = disabled (no floor). Recommended: 300 for SENSEX weekly options.
MIN_OPTION_ENTRY_PRICE: float = _getfloat("MIN_OPTION_ENTRY_PRICE", 0.0)

# ── Risk parameters ───────────────────────────────────────────────────────────
INITIAL_SL_POINTS: float = _getfloat("INITIAL_SL_POINTS", 30)
BREAK_EVEN_TRIGGER_POINTS: float = _getfloat("BREAK_EVEN_TRIGGER_POINTS", 30)
# BE_TRIGGER_RR: move the SL to break-even once the trade is up this many R
#   (multiple of the SL distance).  Applies to the generic ATR/swing/fixed risk
#   modes; Pivot and EMA trades use PIVOT_BE_TRIGGER_R / EMA_BE_TRIGGER_R.
#   0.5 = previous hard-coded behaviour.  BREAK_EVEN_TRIGGER_POINTS is only a
#   fallback for restarted trades that have no stored be_points.
BE_TRIGGER_RR: float = _getfloat("BE_TRIGGER_RR", 0.5)
TRAIL_STEP_POINTS: float = _getfloat("TRAIL_STEP_POINTS", 10)

INITIAL_TARGET_OFFSET_POINTS: float = _getfloat("INITIAL_TARGET_OFFSET_POINTS", 50)
TARGET_TRAIL_STEP_POINTS: float = _getfloat("TARGET_TRAIL_STEP_POINTS", 10)
# TARGET_TRAIL_WITH_STOP: raise the target each time the trailing stop steps up.
#   False (default) keeps the target fixed at entry + target points so it can
#   actually be hit.  With True the target moves with the stop and, in ATR-trail
#   mode (one "step" per tick-level stop update), runs away from price.
TARGET_TRAIL_WITH_STOP: bool = _getbool("TARGET_TRAIL_WITH_STOP", False)
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
# ATR-dynamic TSL — replaces the fixed trail_step with a live ATR-based distance.
# When TSL_ATR_TRAIL_MULT > 0, the trailing stop floats at:
#   stop = highest_ltp - ATR(TSL_ATR_PERIOD, 5m SENSEX) × TSL_ATR_TRAIL_MULT × ATM_delta(0.4)
# This adapts automatically: tight trail on calm days, wider on volatile/trending days.
# The fixed trail_step (SPOT_ATR_TRAIL_RR) is used as the BE-activation step only.
# 0.0 = disabled (use fixed step trail — legacy behaviour).
# Recommended: 0.5  →  at ATR=147, trail distance ≈ 29 pts (147 × 0.5 × 0.4)
TSL_ATR_TRAIL_MULT: float       = _getfloat("TSL_ATR_TRAIL_MULT", 0.0)
TSL_ATR_PERIOD: int             = _getint("TSL_ATR_PERIOD", 5)
# Mode D — swing high/low as SL
# Falls back to Mode C automatically when no swing level is found.
USE_SWING_SL: bool              = _getbool("USE_SWING_SL", False)
SWING_SL_LENGTH: int            = _getint("SWING_SL_LENGTH", 10)
MIN_RR: float                   = _getfloat("MIN_RR", 0.0)
# MAX_RISK_RUPEES_PER_TRADE: skip an entry (before any order) when its expected
# loss at the SL — option SL points × quantity (Pivot: index risk × delta × qty)
# — exceeds this.  EMA CE/PE keep their own EMA_MAX_RISK_RUPEES.  0 = off.
MAX_RISK_RUPEES_PER_TRADE: float = _getfloat("MAX_RISK_RUPEES_PER_TRADE", 0.0)
# SWING_SL_MIN_ATR_MULT: Mode D adequacy guard.
#   If the swing level is so close to entry that the resulting index-point SL
#   is less than  ATR(SPOT_ATR_PERIOD) × this multiplier, Mode D is treated as
#   "structurally too tight" and the bot falls through to Mode C instead.
#
#   Problem it solves (today's trade):
#     ATR(5) = 90.77 pts  →  swing_low 44 pts away  →  44 < 90.77 × 0.6 = 54.5
#     Mode D rejected; Mode C used: SL = 90.77 × 3.0 × 0.4 = 108 pts (proper width)
#
#   0.0 = disabled (original behaviour — always trust the swing level). Default.
#   0.5 = fall through when swing SL index pts < ATR × 0.5  (mild gate)
#   0.6 = fall through when swing SL index pts < ATR × 0.6  (recommended for SENSEX 5m)
#   1.0 = fall through unless swing is at least 1 full ATR away  (strict)
SWING_SL_MIN_ATR_MULT: float    = _getfloat("SWING_SL_MIN_ATR_MULT", 0.0)
# ATM_DELTA: converts SENSEX index pts -> option premium pts for Mode C/D SL sizing.
#   0.4 under-sized the option SL (live ATM options moved ~0.5 per index pt), so
#   trades stopped out on normal noise.  Higher delta = wider option SL/target.
ATM_DELTA: float                = _getfloat("ATM_DELTA", 0.5)
# ENTRY_MARGIN_CHECK: LIVE only. Before sending a BUY, ask Kite for the required
#   margin and skip the entry (logged as ENTRY_REJECTED) when it exceeds the
#   available balance, instead of letting the broker reject the order.
ENTRY_MARGIN_CHECK: bool        = _getbool("ENTRY_MARGIN_CHECK", True)
# MAX_SL_PCT: caps the initial SL at this fraction of the option entry price.
#   Prevents the swing/ATR SL from being crushed on cheap OTM options.
#   e.g. entry=128, max_sl_pct=0.50 → SL ceiling = 64 pts (was 35% = 44 pts)
#   Raise this when trades are stopping out within seconds of entry.
#   0.50 recommended for SENSEX weekly options (was 0.35 default).
MAX_SL_PCT: float               = _getfloat("MAX_SL_PCT", 0.35)

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
# UNITS: despite the "_PTS" name this is MONEY (Rs), not index/option points.  It is compared
# with the sum of realized_pnl for today's closed trades, and realized_pnl is stored as
# (exit_price - entry_price) x filled_qty.  E.g. 3000 = stop new entries after Rs 3000 of
# realised loss.  Pivot trades: blocks NEW entries only (an open pivot trade is not closed
# by it).  EMA trades: also closes an open position (needs ENABLE_SMART_EXIT).
# Env key is DAILY_LOSS_LIMIT_RUPEES; the legacy key DAILY_LOSS_LIMIT_PTS is still read as a
# fallback so existing .env files keep working.
DAILY_LOSS_LIMIT_RUPEES: float    = _getfloat("DAILY_LOSS_LIMIT_RUPEES",
                                              _getfloat("DAILY_LOSS_LIMIT_PTS", 200.0))

# ── Session ───────────────────────────────────────────────────────────────────
TIMEZONE: str = _get("TIMEZONE", "Asia/Kolkata")
FORCE_EXIT_TIME: str = _get("FORCE_EXIT_TIME", "15:15")
NO_NEW_ENTRY_AFTER: str = _get("NO_NEW_ENTRY_AFTER", "15:00")

# EMA-specific time and RR overrides
# EMA_SCAN_START: EMA CE/PE signals are only evaluated on 5m candles that START
#   at or after this time (09:20 = skip the 09:15 opening candle).
EMA_SCAN_START: str = _get("EMA_SCAN_START", "09:20")
# EMA_NO_NEW_ENTRY_AFTER: stop taking new EMA CE/PE signals after this time.
#   Empty = use global NO_NEW_ENTRY_AFTER.
EMA_NO_NEW_ENTRY_AFTER: str = _get("EMA_NO_NEW_ENTRY_AFTER", "15:00")
# EMA_TARGET_RR: EMA CE/PE hard target = this × index risk (EMA risk engine below).
#   0 = default 3.0. Mode D/C is only a fallback when the EMA engine has no plan.
EMA_TARGET_RR: float        = _getfloat("EMA_TARGET_RR", 3.0)
# EMA_COOLDOWN_CANDLES: cooldown after an EMA trade before the next EMA signal is allowed.
#   0 = disabled.
EMA_COOLDOWN_CANDLES: int   = _getint("EMA_COOLDOWN_CANDLES", 0)

# EMA 9/21 + RSI rule-set (strategies/ce_strategy.py, strategies/pe_strategy.py)
# EMA_RSI_PERIOD       : RSI length on 5m spot.
# EMA_RSI_CE_MIN       : CE requires RSI > this.
# EMA_RSI_PE_MAX       : PE requires RSI < this.
# EMA_PULLBACK_TOL_PTS : "closes flat on 5m EMA21" = |close − EMA21| <= this (index pts).
EMA_RSI_PERIOD: int          = _getint("EMA_RSI_PERIOD", 14)
EMA_RSI_CE_MIN: float        = _getfloat("EMA_RSI_CE_MIN", 55.0)
EMA_RSI_PE_MAX: float        = _getfloat("EMA_RSI_PE_MAX", 45.0)
EMA_PULLBACK_TOL_PTS: float  = _getfloat("EMA_PULLBACK_TOL_PTS", 10.0)
# EMA_CROSS_TRIGGER: true = also fire on the EMA9 x EMA21 cross (CE: EMA9 crosses above
#   EMA21; PE: below), in addition to the close-vs-EMA9 crossover and EMA21 pullback.
#   15m trend gate, RSI and daily-trend gate still apply. Off by default.
EMA_CROSS_TRIGGER: bool      = _getbool("EMA_CROSS_TRIGGER", False)
# EMA_CROSS_IGNORE_15M: with EMA_CROSS_TRIGGER, the EMA9 x EMA21 cross itself may fire even
#   when the 15m EMA trend is not aligned (RSI still applies). Crossover/pullback still need it.
EMA_CROSS_IGNORE_15M: bool   = _getbool("EMA_CROSS_IGNORE_15M", False)
# EMA_CROSS_ONLY: true = the EMA9 x EMA21 cross on 5m candles is the ONLY EMA entry trigger
#   (the close-vs-EMA9 crossover and EMA21 pullback are switched off).  RSI, the 15m trend
#   (unless EMA_CROSS_IGNORE_15M) and the usual gates / SmartEntry still confirm.  Off by default.
EMA_CROSS_ONLY: bool         = _getbool("EMA_CROSS_ONLY", False)
# EMA_REQUIRE_CANDLE_COLOR: true = every EMA trigger (close>EMA9 crossover, EMA9xEMA21
#   cross, EMA21 pullback) also needs the signal candle to be bullish for CE (close > open)
#   or bearish for PE (close < open).  Off by default.
EMA_REQUIRE_CANDLE_COLOR: bool = _getbool("EMA_REQUIRE_CANDLE_COLOR", False)
# EMA_MIN_BODY_ATR: every EMA trigger also needs the signal candle's body (|close - open|)
#   to be >= this many x ATR(14) on the 5m chart (0.35 = same threshold as SmartEntry's
#   body filter).  Works even with EMA_SKIP_SMART_FILTERS=true.  0 = off (default).
EMA_MIN_BODY_ATR: float      = _getfloat("EMA_MIN_BODY_ATR", 0.0)
# EMA_IGNORE_15M: true (default) = EMA CE/PE use 5m candles ONLY.  The 15m trend
#   requirement in the EMA rule-set, the 15m TREND_GATE and SmartEntry Filter 6 (15m
#   trend) are all skipped for EMA signals (other strategies are unaffected).
EMA_IGNORE_15M: bool         = _getbool("EMA_IGNORE_15M", True)
# EMA_ATR_CONFIRM: true = an EMA CE/PE entry additionally needs the ATR trailing-stop
#   ("ATR 5 Min Index Study", NATR_PERIOD / NATR_MULT) to be in the same state on the
#   5m chart: CE only while close > ATR line (buy state), PE only while close < it
#   (sell state).  Fails open while the line is not computable.
EMA_ATR_CONFIRM: bool        = _getbool("EMA_ATR_CONFIRM", True)
# EMA_SKIP_SMART_FILTERS: true = EMA CE/PE bypass SmartEntry candle filters
#   (body/ATR, EMA9 slope, EMA gap, gap widening, 15m trend) — the rule-set has its
#   own trend + RSI logic. Post-loss cooldown and premium-extension guard still apply.
EMA_SKIP_SMART_FILTERS: bool = _getbool("EMA_SKIP_SMART_FILTERS", False)
# EMA_OPTION_EMA_CHECK: true = only buy when option premium > EMA9 of the option's
#   own 5m chart. Skipped in PAPER mode (no option data). Fails open on data errors.
EMA_OPTION_EMA_CHECK: bool   = _getbool("EMA_OPTION_EMA_CHECK", True)
# EMA_MAX_SLIPPAGE_PCT: reject the EMA entry when best ask is more than this % above
#   the option LTP (wide spread). 0 = disabled. SHADOW/LIVE only.
EMA_MAX_SLIPPAGE_PCT: float  = _getfloat("EMA_MAX_SLIPPAGE_PCT", 3.5)
# ── EMA risk engine (execution/ema_trade_manager.py) — SENSEX index based ─────
# Stop  = swing low/high (EMA_SWING_LENGTH pivots) ∓ EMA_SWING_BUFFER_ATR × ATR,
#         distance clamped to [EMA_SL_MIN_ATR, EMA_SL_MAX_ATR] × ATR(SPOT_ATR_PERIOD).
#         No swing → EMA_SL_FALLBACK_ATR × ATR.
# Skip  = trade if premium risk (index risk × delta × qty) > EMA_MAX_RISK_RUPEES.
# BE    = at EMA_BE_TRIGGER_R × risk, stop → entry + EMA_BE_BUFFER_PTS.
# Trail = best − EMA_TRAIL_ATR_MULT × ATR(TSL_ATR_PERIOD); optional 5m close through EMA9.
# Time  = exit after EMA_TIME_STOP_BARS candles if never reached EMA_TIME_STOP_MIN_R.
# Target= EMA_TARGET_RR × risk (fixed, never drifts).
EMA_SWING_LENGTH: int          = _getint("EMA_SWING_LENGTH", 5)
EMA_SWING_BUFFER_ATR: float    = _getfloat("EMA_SWING_BUFFER_ATR", 0.25)
EMA_SL_MIN_ATR: float          = _getfloat("EMA_SL_MIN_ATR", 1.0)
EMA_SL_MAX_ATR: float          = _getfloat("EMA_SL_MAX_ATR", 2.0)
EMA_SL_FALLBACK_ATR: float     = _getfloat("EMA_SL_FALLBACK_ATR", 1.5)
EMA_OPTION_DELTA: float        = _getfloat("EMA_OPTION_DELTA", 0.5)
EMA_EXPIRY_DELTA: float        = _getfloat("EMA_EXPIRY_DELTA", 0.6)
EMA_MAX_SL_PCT: float          = _getfloat("EMA_MAX_SL_PCT", 0.30)
EMA_EXPIRY_MAX_SL_PCT: float   = _getfloat("EMA_EXPIRY_MAX_SL_PCT", 0.25)
EMA_HARD_SL_CUSHION: float     = _getfloat("EMA_HARD_SL_CUSHION", 1.1)
EMA_MAX_RISK_RUPEES: float     = _getfloat("EMA_MAX_RISK_RUPEES", 1500.0)
EMA_BE_TRIGGER_R: float        = _getfloat("EMA_BE_TRIGGER_R", 1.0)
EMA_BE_BUFFER_PTS: float       = _getfloat("EMA_BE_BUFFER_PTS", 4.0)
EMA_TRAIL_ATR_MULT: float      = _getfloat("EMA_TRAIL_ATR_MULT", 2.0)
EMA_TRAIL_EMA9_EXIT: bool      = _getbool("EMA_TRAIL_EMA9_EXIT", True)
# EMA_NATR_RISK: true = EMA trades are risk-managed by the NATR trailing line
#   ("ATR 5 Min Index Study", NATR_PERIOD / NATR_MULT) instead of swing SL + BE +
#   chandelier: initial SL = NATR line (or entry ∓ NATR_MULT × ATR if the line is
#   still on the other side), TSL = ratchets with the NATR line each 5m close,
#   target = EMA_NATR_TARGET_RR × initial risk (0 = no target).  EMA9-trail, time
#   stop and reversal exits are bypassed; the EMA-collapse smart exit, TIME_DECAY and
#   daily-loss limit stay active.  Off by default.
# EMA_NATR_MAX_RISK_RUPEES: skip when index risk × delta × qty exceeds this (0 = off).
EMA_NATR_RISK: bool              = _getbool("EMA_NATR_RISK", False)
EMA_NATR_TARGET_RR: float        = _getfloat("EMA_NATR_TARGET_RR", 2.0)
EMA_NATR_MAX_RISK_RUPEES: float  = _getfloat("EMA_NATR_MAX_RISK_RUPEES", 0.0)
# EMA_NATR_BROKER_TRAIL: true (default) = the bot keeps the ONE SL order placed at entry in
#   sync with its own NATR stop: each time the bot moves the stop it calls modify_stop_order
#   on that same order (no broker-side trailing order is created).  The index stop is
#   converted to a premium trigger with a fixed delta.  false = the SL order is never
#   modified; only the bot's index logic exits.
EMA_NATR_BROKER_TRAIL: bool      = _getbool("EMA_NATR_BROKER_TRAIL", True)
EMA_TIME_STOP_BARS: int        = _getint("EMA_TIME_STOP_BARS", 6)
EMA_TIME_STOP_MIN_R: float     = _getfloat("EMA_TIME_STOP_MIN_R", 0.5)
# Room filter: skip when nearest opposing level (PDH/PDL, day H/L, R1/S1) < this × risk. 0 = off.
EMA_MIN_ROOM_R: float          = _getfloat("EMA_MIN_ROOM_R", 1.5)
# EMA collapse exit needs this many consecutive 5m closes beyond EMA21.
EMA_COLLAPSE_CLOSES: int       = _getint("EMA_COLLAPSE_CLOSES", 2)
# EMA_PROFIT_LOCK: false = EMA CE/PE skip the smart-exit profit lock (trail + target manage exits).
EMA_PROFIT_LOCK: bool          = _getbool("EMA_PROFIT_LOCK", False)
EMA_MAX_TRADES_PER_DAY: int    = _getint("EMA_MAX_TRADES_PER_DAY", 3)
EMA_MAX_CONSEC_LOSSES: int     = _getint("EMA_MAX_CONSEC_LOSSES", 2)
# Expiry day: no new EMA entries at/after this time ("" = off).
EMA_EXPIRY_NO_ENTRY_AFTER: str = _get("EMA_EXPIRY_NO_ENTRY_AFTER", "13:30")

# Expiry-day rollover: on the day the nearest weekly expiry expires, switch new
# contract selection to the next expiry at/after this time. "" = disabled.
# Only applies to EXPIRY_MODE=AUTO.
EXPIRY_DAY_ROLLOVER_TIME: str = _get("EXPIRY_DAY_ROLLOVER_TIME", "12:30")

# ── Global per-side daily trade cap ───────────────────────────────────────────
# MAX_TRADES_PER_SIDE: maximum filled trades per side (CE or PE) per day, across
# ALL strategies combined.  0 = unlimited.  Default 3 means the bot takes at
# most 3 CE trades and 3 PE trades in a single session regardless of which
# strategy triggered them.
MAX_TRADES_PER_SIDE: int = _getint("MAX_TRADES_PER_SIDE", 3)

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
#
# Filter 4b — gap rate-of-change bypass (0 = disabled; recommended: 15)
#   When the directed EMA gap is below SMART_ENTRY_MIN_EMA_GAP_PTS, the block is
#   waived if the gap is CLOSING toward the signal direction by at least this many
#   points per candle.  This lets a fast V-reversal through while still blocking
#   flat / diverging gaps.
#
#   Calculation (CE example):
#     gap_velocity = (EMA9[0] - EMA21[0]) - (EMA9[-1] - EMA21[-1])
#     CE: gap_velocity > gap_close_rate → bypass the gap block
#     PE: -gap_velocity > gap_close_rate → bypass the gap block
#
#   Recommended: 15 pts/candle on SENSEX 5m (today's reversal moved +21–24 pts/candle)
#   0 = disabled (original hard-block behaviour, no rate-of-change check).
# Filter 5 — EMA gap must be widening (false = disabled; recommended: true)
SMART_ENTRY_MIN_EMA_GAP_PTS: float       = _getfloat("SMART_ENTRY_MIN_EMA_GAP_PTS",       0.0)
SMART_ENTRY_GAP_CLOSE_RATE: float        = _getfloat("SMART_ENTRY_GAP_CLOSE_RATE",         0.0)
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
# Filter 7c — Squeeze-exempt strategies.
# Comma-separated list of strategy suffixes that are NEVER subject to squeeze bypass,
# even when SMART_ENTRY_SQUEEZE_BYPASS=true.
# Rationale: bounce/retest strategies (VWAP, NATR) use a pullback candle sequence as
# the retest setup itself — those same candles would incorrectly trigger squeeze bypass
# and silence the 15m trend filter, allowing counter-trend entries on trending days.
# Default: "VWAP,NATR" — these strategies always go through Filter 6 (15m trend).
# "" = no exemptions (all strategies subject to squeeze bypass equally).
_SQUEEZE_EXEMPT_RAW: str = _get("SMART_ENTRY_SQUEEZE_EXEMPT_STRATEGIES", "VWAP,NATR")
SMART_ENTRY_SQUEEZE_EXEMPT_STRATEGIES: set[str] = (
    {s.strip().upper() for s in _SQUEEZE_EXEMPT_RAW.split(",") if s.strip()}
    if _SQUEEZE_EXEMPT_RAW.strip()
    else set()
)
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
# Default: "VWAP,NATR,ORB" — skip body + EMA-gap filters for CE_VWAP / PE_VWAP /
#   CE_NATR / PE_NATR / CE_ORB / PE_ORB signals.
# "" = disable (all strategies subject to body/EMA-gap filters equally).
# Example: SMART_ENTRY_BOUNCE_EXEMPT_STRATEGIES=VWAP,NATR,ORB,OB
_BOUNCE_EXEMPT_RAW: str = _get("SMART_ENTRY_BOUNCE_EXEMPT_STRATEGIES", "VWAP,NATR,ORB")
SMART_ENTRY_BOUNCE_EXEMPT_STRATEGIES: set[str] = (
    {s.strip().upper() for s in _BOUNCE_EXEMPT_RAW.split(",") if s.strip()}
    if _BOUNCE_EXEMPT_RAW.strip()
    else set()
)

# Filter 2b — Slope-exempt strategies.
# Comma-separated list of strategy name suffixes that bypass Filter 2 (EMA9 slope).
# NATR is exempt by default: its trailing-stop crossover IS the trend-flip signal —
# requiring EMA slope confirmation is double-filtering because EMA9 lags the crossover
# by 1-2 candles and fires in the wrong direction right at the inflection point.
# Default: "NATR" — skip EMA slope filter for CE_NATR / PE_NATR signals.
# "" = disable (all strategies subject to slope filter equally).
# Example: SMART_ENTRY_SLOPE_EXEMPT_STRATEGIES=NATR,ATR
_SLOPE_EXEMPT_RAW: str = _get("SMART_ENTRY_SLOPE_EXEMPT_STRATEGIES", "NATR")
SMART_ENTRY_SLOPE_EXEMPT_STRATEGIES: set[str] = (
    {s.strip().upper() for s in _SLOPE_EXEMPT_RAW.split(",") if s.strip()}
    if _SLOPE_EXEMPT_RAW.strip()
    else set()
)

# Per-strategy minimum option entry price override.
# Overrides MIN_OPTION_ENTRY_PRICE for specific strategy types.
# NATR fires early in a trend flip — before the ATM option has inflated to a
# high premium.  A 300-pt floor blocks legitimate early-move entries at ₹250-280.
# Set a lower floor specifically for NATR so the global MIN_OPTION_ENTRY_PRICE
# (intended for deep-OTM / near-expiry protection) does not apply.
# 0.0 = use MIN_OPTION_ENTRY_PRICE (no override).  Recommended: 150
NATR_MIN_OPTION_ENTRY_PRICE: float = _getfloat("NATR_MIN_OPTION_ENTRY_PRICE", 0.0)

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
ORB_BUFFER_ATR_MULT: float  = _getfloat("ORB_BUFFER_ATR_MULT",  0.1)
ORB_REQUIRE_15M_TREND: bool = _getbool("ORB_REQUIRE_15M_TREND", True)
# ORB only fires for candles whose timestamp is at or before this time.
# After this time ORB is silently skipped and EMA takes over.
# "" = no cutoff (active all day).  Default: "11:00"
ORB_ACTIVE_UNTIL: str       = _get("ORB_ACTIVE_UNTIL", "09:40")
# Skip ORB and Momentum signals on Mondays.
# Backtest shows 0% win rate for both strategies on Monday; all other strategies
# (EMA, TRB, OB, VWAP, PDHL) are unaffected and continue to trade normally.
# true = skip ORB + MOMENTUM on Mondays (recommended).  false = no restriction.
ORB_MOMENTUM_SKIP_MONDAY: bool = _getbool("ORB_MOMENTUM_SKIP_MONDAY", True)
# ORB_NO_THURSDAY: when true, no new ORB entries are allowed on Thursdays (expiry day).
# Backtest shows Thursdays: 7 trades, 0% WR, −₹3,671 (PF 0.00).
ORB_NO_THURSDAY: bool       = _getbool("ORB_NO_THURSDAY", False)
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
# Momentum guards (all default OFF = legacy behaviour):
#   MOMENTUM_MAX_TRADES_PER_DAY        : max filled MOM trades per day (0 = unlimited).
#   MOMENTUM_REENTRY_COOLDOWN_CANDLES  : block a same-direction MOM signal for N 5m
#                                        candles after the last MOM exit (0 = off).
#   MOMENTUM_MAX_SL_ATR                : block when distance to the swing SL is more
#                                        than N × ATR(SPOT_ATR_PERIOD) (0 = off).
#   MOMENTUM_MIN_ROOM_ATR              : block when price is within N × ATR below the
#                                        prior day high (CE) / above the prior day low
#                                        (PE); excludes the last 3 candles (0 = off).
MOMENTUM_MAX_TRADES_PER_DAY: int       = _getint("MOMENTUM_MAX_TRADES_PER_DAY", 0)
MOMENTUM_REENTRY_COOLDOWN_CANDLES: int = _getint("MOMENTUM_REENTRY_COOLDOWN_CANDLES", 0)
MOMENTUM_MAX_SL_ATR: float             = _getfloat("MOMENTUM_MAX_SL_ATR", 0.0)
MOMENTUM_MIN_ROOM_ATR: float           = _getfloat("MOMENTUM_MIN_ROOM_ATR", 0.0)

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
# OB_APPROACH_BUFFER_ATR_MULT : extend the OB signal to fire when price
#   *approaches* the OB from outside, not only when it is already inside.
#   For bearish OBs (PE): signal fires when close >= ob.bottom - buffer_pts
#     (price is within buffer_pts below the OB bottom — on the retest approach).
#   For bullish OBs (CE): signal fires when close <= ob.top + buffer_pts
#     (price is within buffer_pts above the OB top).
#   buffer_pts = OB_APPROACH_BUFFER_ATR_MULT × ATR(OB_ATR_PERIOD)
#   0.0 = disabled — only fires when close is actually inside the zone (original).
#   0.2 = recommended — fires ≈ 0.2×ATR (~22 pts at ATR5=111) before zone entry.
#   Mirrors TradingView AI Copilot "sell the retest" entries which fire 1-2
#   candles before price reaches the OB bottom.
OB_APPROACH_BUFFER_ATR_MULT: float = _getfloat("OB_APPROACH_BUFFER_ATR_MULT", 0.0)

# ── TRB (Time Range Breakout) strategy ─────────────────────────────────────────
ENABLE_TRB_STRATEGY: bool      = _getbool("ENABLE_TRB_STRATEGY", False)
TRB_CANDLE_START_TIME: str     = _get("TRB_CANDLE_START_TIME", "09:45")
TRB_CANDLE_DURATION_MINS: int  = _getint("TRB_CANDLE_DURATION_MINS", 15)
TRB_MIN_BODY_RATIO: float      = _getfloat("TRB_MIN_BODY_RATIO", 0.0)
TRB_BUFFER_ATR_MULT: float     = _getfloat("TRB_BUFFER_ATR_MULT", 0.0)
# Only the first breakout per side per day counts; re-crosses are range whipsaw
# (a 270-day replay without this fired ~3 TRB signals/day at −0.20R net each).
TRB_FIRST_BREAKOUT_ONLY: bool  = _getbool("TRB_FIRST_BREAKOUT_ONLY", True)
# No TRB signals at/after this time ("" = no cut-off).
TRB_WINDOW_END: str            = _get("TRB_WINDOW_END", "11:30")

# ── VWAP Retest strategy ──────────────────────────────────────────────────────
# Fires CE_VWAP/PE_VWAP when price retests VWAP and bounces back.
# VWAP is calculated intraday from completed 5m candles (resets at 09:15).
ENABLE_VWAP_STRATEGY: bool    = _getbool("ENABLE_VWAP_STRATEGY", False)
# Enable / disable CE (Call) and PE (Put) VWAP entries independently (default True)
ENABLE_CE_VWAP: bool          = _getbool("ENABLE_CE_VWAP", True)
ENABLE_PE_VWAP: bool          = _getbool("ENABLE_PE_VWAP", True)
# Candles to look back for the retest dip/pop (default 3 = 15 minutes)
VWAP_RETEST_LOOKBACK: int     = _getint("VWAP_RETEST_LOOKBACK", 3)
# Minimum distance close must be above/below VWAP to confirm bounce (0 = disabled)
VWAP_MIN_BOUNCE_PTS: float    = _getfloat("VWAP_MIN_BOUNCE_PTS", 0.0)
# Maximum consecutive candles price can stay on the opposite side of VWAP before bouncing (0 = disabled)
VWAP_MAX_SUBMERGED_CANDLES: int = _getint("VWAP_MAX_SUBMERGED_CANDLES", 3)
# VWAP slope guard: CE needs VWAP rising (or flat) and PE falling (or flat)
# versus N completed candles ago, computed from today's candles.  0 = disabled.
VWAP_SLOPE_LOOKBACK: int      = _getint("VWAP_SLOPE_LOOKBACK", 3)
# No new VWAP entries on candles starting at/after this time ("" = no cut-off).
VWAP_NO_NEW_ENTRY_AFTER: str  = _get("VWAP_NO_NEW_ENTRY_AFTER", "")
# VWAP_CROSS_EXIT: while a CE_VWAP or PE_VWAP trade is open, exit on the first
# completed 5m candle that closes back through VWAP — the structural thesis
# (price above VWAP for CE / below for PE) is invalidated.  This fires before
# the ATR-based option SL backstop and keeps losses small.
# true = enabled (recommended).  false = rely on ATR SL only (legacy behaviour).
VWAP_CROSS_EXIT: bool = _getbool("VWAP_CROSS_EXIT", True)

# ── Higher-timeframe trend gate (strategies/trend_gate.py) ─────────────────────
# Blocks signals that fight the 15m trend and/or the daily trend, for the
# strategies listed in TREND_GATE_STRATEGIES only (keys: EMA, VWAP, TRB, NATR,
# ATR, PDHL, OB, ORB, MOM).  Do NOT add PIVOT: its edge comes from level entries
# taken against short-term momentum (backtest: gating would cut ~55% of its R).
# ── Index-anchored exits for generic strategies ───────────────────────────────
# GENERIC_INDEX_EXITS: manage VWAP/ORB/NATR/ATR/PDHL/TRB/OB/MOM trades on SENSEX
#   levels (execution.ema_trade_manager.IndexTradeManager) like Pivot/EMA do:
#   SL at the swing/ATR index stop, BE at BE_TRIGGER_RR, chandelier trail
#   GENERIC_TRAIL_ATR_MULT × ATR(TSL_ATR_PERIOD), exit at the index target.
#   The broker option SL is a GENERIC_HARD_SL_CUSHION-wider backstop.
#   Off = previous behaviour (option-premium SL/TSL via an assumed delta).
GENERIC_INDEX_EXITS: bool       = _getbool("GENERIC_INDEX_EXITS", False)
GENERIC_TRAIL_ATR_MULT: float   = _getfloat("GENERIC_TRAIL_ATR_MULT", 2.0)
# Break-even stop sits this many index pts beyond entry (≈ round-trip costs).
GENERIC_BE_BUFFER_PTS: float    = _getfloat("GENERIC_BE_BUFFER_PTS", 12.0)
GENERIC_HARD_SL_CUSHION: float  = _getfloat("GENERIC_HARD_SL_CUSHION", 1.5)

TREND_GATE_15M: bool               = _getbool("TREND_GATE_15M", False)
TREND_GATE_DAILY: bool             = _getbool("TREND_GATE_DAILY", False)
TREND_GATE_DAILY_EMA: int          = _getint("TREND_GATE_DAILY_EMA", 20)
TREND_GATE_STRATEGIES: frozenset[str] = frozenset(
    s.strip().upper() for s in _get("TREND_GATE_STRATEGIES", "EMA,VWAP,TRB,NATR").split(",") if s.strip()
)
# Support/resistance room filter for VWAP entries (OFF by default).
# A 193-day replay showed no robust edge (helps PE, hurts CE, unstable across
# halves), so it ships opt-in only.  When on, a CE is blocked if the nearest
# resistance above the close is < VWAP_LEVEL_MIN_ROOM_ATR x ATR(14) away
# (PE: nearest support below).  VWAP_LEVEL_USE_PIVOTS / _DAY_EXTREMES choose
# which levels count; prev-day high/low are always included.
ENABLE_VWAP_LEVEL_FILTER: bool    = _getbool("ENABLE_VWAP_LEVEL_FILTER", False)
VWAP_LEVEL_MIN_ROOM_ATR: float    = _getfloat("VWAP_LEVEL_MIN_ROOM_ATR", 1.0)
VWAP_LEVEL_USE_PIVOTS: bool       = _getbool("VWAP_LEVEL_USE_PIVOTS", True)
VWAP_LEVEL_USE_DAY_EXTREMES: bool = _getbool("VWAP_LEVEL_USE_DAY_EXTREMES", True)

# ── Pivot Levels ─────────────────────────────────────────────────────────────
# Pivot levels computed from previous day's H/L/C.
# PIVOT_FORMULA: "FIBONACCI" (default) or "TRADITIONAL"
#   Fibonacci (symmetric golden ratios):
#     P  = (H+L+C)/3
#     R1 = P + 0.382×(H−L)   R2 = P + 0.618×(H−L)   R3 = P + 1.000×(H−L)
#     S1 = P − 0.382×(H−L)   S2 = P − 0.618×(H−L)   S3 = P − 1.000×(H−L)
#   Traditional (standard floor):
#     P  = (H+L+C)/3
#     R1 = 2P−L              R2 = P+(H−L)           R3 = H+2(P−L)
#     S1 = 2P−H              S2 = P−(H−L)           S3 = L−2(H−P)
#
# ENABLE_PIVOT_LEVELS: fetch and store pivot levels at startup (for display + filter).
#   false = no pivot computation, no filter, no display. Default.
#   true  = levels fetched, shown on dashboard, and optionally filter EMA signals.
#
# PIVOT_ZONE_BUFFER: half-width (pts) of the no-trade zone around each pivot level.
#   When price closes within this distance of P, R1, R2, S1, or S2 the EMA signal
#   is suppressed — price is in a congestion/decision zone, not a clean breakout.
#   0 = disabled (no zone filter).  Recommended: 20–30 pts for SENSEX.
#
# PIVOT_COUNTER_TREND_BLOCK: block EMA CE signals when close < Pivot (bearish bias)
#   and EMA PE signals when close > Pivot (bullish bias).
#   Only trade in the direction the pivot structure supports.
#   false = disabled (recommended to start — can kill valid trend trades).
#
# PIVOT_BREAKOUT_CONFIRM: require price to be ABOVE R1 for CE (momentum above resistance)
#   and BELOW S1 for PE (breakdown below support) before allowing EMA signal.
#   false = disabled.  Use only on strongly trending days.
PIVOT_FORMULA: str              = os.getenv("PIVOT_FORMULA", "FIBONACCI").upper()
ENABLE_PIVOT_LEVELS: bool       = _getbool("ENABLE_PIVOT_LEVELS", False)
PIVOT_ZONE_BUFFER: float        = _getfloat("PIVOT_ZONE_BUFFER", 25.0)
PIVOT_COUNTER_TREND_BLOCK: bool = _getbool("PIVOT_COUNTER_TREND_BLOCK", False)
PIVOT_BREAKOUT_CONFIRM: bool    = _getbool("PIVOT_BREAKOUT_CONFIRM", False)

# ── Pivot strategy (CE_PIVOT / PE_PIVOT) ──────────────────────────────────────
# Two entry modes:
#   OPEN_DIRECTION : open is already on one side of Pivot; first candles sustain.
#                    Only fires in the 09:15–09:30 window.
#   REJECTION      : open on wrong side, price travels to Pivot, gets rejected;
#                    fires any time of day.
#   BOTH           : Mode A checked first, then Mode B (default).
#   + ACCEPTANCE   : optional Mode C (PIVOT_ACCEPTANCE=true), checked last —
#                    cross Pivot, then first N clean candles on the new side.
#
# Targets: CE → R1 (T1), R2 (T2), R3 (T3)  |  PE → S1 (T1), S2 (T2), S3 (T3)
# Has its OWN SL/BE/TSL/target engine (execution/pivot_trade_manager.py) —
# the generic TSL/target/smart-exit logic is bypassed.
# Requires ENABLE_PIVOT_LEVELS=true.
ENABLE_PIVOT_STRATEGY: bool     = _getbool("ENABLE_PIVOT_STRATEGY", False)
# Entry mode: "OPEN_DIRECTION" | "REJECTION" | "BOTH"
PIVOT_MODE: str                 = _get("PIVOT_MODE", "BOTH").upper()
PIVOT_SUSTAIN_CANDLES: int      = _getint("PIVOT_SUSTAIN_CANDLES", 2)
PIVOT_ATR_PERIOD: int           = _getint("PIVOT_ATR_PERIOD", 14)
PIVOT_SL_MODE: str              = _get("PIVOT_SL_MODE", "SIGNAL_LOW").upper()   # SIGNAL_LOW | ATR
PIVOT_SL_ATR_MULT: float        = _getfloat("PIVOT_SL_ATR_MULT", 1.0)          # ATR mode only
# SIGNAL_LOW padding.  0.3 (was 0.05): a 1-year replay (research/pivot_sensitivity.py)
# showed +14% total points and a better CE side; the stop is wider, so each loss is larger.
PIVOT_SL_BUFFER_ATR: float      = _getfloat("PIVOT_SL_BUFFER_ATR", 0.3)
PIVOT_MIN_ROOM_R: float         = _getfloat("PIVOT_MIN_ROOM_R", 1.0)           # T1 distance >= this × risk
# Minimum today-candles before pivot signal is allowed.
# For REJECTION mode: must be > PIVOT_SUSTAIN_CANDLES (at least 1 pre-window candle needed).
# 3 = allow REJECTION from the 4th candle onward (09:30).  0 = disabled.
PIVOT_MIN_TODAY_CANDLES: int    = _getint("PIVOT_MIN_TODAY_CANDLES", 3)
# Open-Direction window: only fires when last sustain candle is within [start, end].
# Default 09:15–09:30 = first three 5-minute bars of the session.
PIVOT_OD_WINDOW_START: str      = _get("PIVOT_OD_WINDOW_START", "09:15")
PIVOT_OD_WINDOW_END: str        = _get("PIVOT_OD_WINDOW_END", "09:30")
# ── Open-Direction quality filters ────────────────────────────────────────────
# These three settings tighten the Mode-A (Open-Direction Sustain) entry
# quality.  All default OFF so existing behaviour is unchanged.
#
# PIVOT_OD_MIN_GAP_ATR: open must be at least this many ATR multiples away from
#   Pivot before an OD entry is allowed.  Blocks setups where the open is inside
#   the Pivot noise band and has not truly committed to one side.
#   Root cause Oct 9: open=71838, Pivot=71871, gap=33 pts = 0.29×ATR(114) →
#   the market had NOT committed below Pivot; 0.4 would have blocked the trade.
#   Recommended: 0.4.  0.0 = disabled (legacy behaviour).
PIVOT_OD_MIN_GAP_ATR: float     = _getfloat("PIVOT_OD_MIN_GAP_ATR", 0.0)
#
# PIVOT_OD_FIRST_CANDLE_CONFIRM: require the first 5m candle's body to confirm
#   the OD direction before firing.
#   CE: first candle must close > open (bullish body).
#   PE: first candle must close < open (bearish body).
#   Blocks OD entries when the first candle is a doji or moves against the
#   expected direction (e.g. a flat/bullish first candle on a PE setup).
#   Recommended: true.  false = disabled (legacy behaviour).
PIVOT_OD_FIRST_CANDLE_CONFIRM: bool = _getbool("PIVOT_OD_FIRST_CANDLE_CONFIRM", False)
#
# PIVOT_OD_MAX_FIRST_WICK_ATR: block the OD trade if the first candle's
#   counter-direction wick is >= this × ATR.
#   PE: upper wick reaching toward Pivot = bullish probe — block.
#   CE: lower wick reaching toward Pivot = bearish probe — block.
#   Root cause Oct 9: first candle upper wick = 32.45 pts = 0.28×ATR → set to
#   0.25 to block it while still allowing minor wicks (< 0.25×ATR).
#   Recommended: 0.25.  0.0 = disabled (legacy behaviour).
PIVOT_OD_MAX_FIRST_WICK_ATR: float = _getfloat("PIVOT_OD_MAX_FIRST_WICK_ATR", 0.0)
# Rejection zone: how close the pre-window high/low must come to the Pivot to
# count as a genuine probe.  Expressed as a multiple of ATR.
# 0.3 = within 0.3×ATR of the Pivot (e.g. ATR=150 → within 45 pts).
PIVOT_REJECTION_ZONE_ATR: float = _getfloat("PIVOT_REJECTION_ZONE_ATR", 0.3)
# PIVOT_ACCEPTANCE: also enable Mode C (cross-and-acceptance).  Fires once per
#   Pivot cross when price closed/opened on the wrong side, crossed the Pivot,
#   and the first N clean candles (close + wick on the new side) confirm it.
#   Catches trend days where the cross candle wicks back through Pivot
#   (Oct 9 2026).  false = disabled (legacy behaviour).
PIVOT_ACCEPTANCE: bool          = _getbool("PIVOT_ACCEPTANCE", False)
# Acceptance (Mode C) quality guards.  Two candles closing 1-2 pts beyond the Pivot
# are noise when price is hovering on it (Oct 19 2026: both PE_PIVOT acceptance
# entries were stopped out within 7 / 25 minutes).
#   PIVOT_ACCEPT_MIN_DIST_ATR  : signal close must be >= this x ATR beyond the Pivot.
#   PIVOT_ACCEPT_MIN_ROOM_R    : T1 room must be >= this x risk (acceptance only;
#                                overrides PIVOT_MIN_ROOM_R when larger).
#   PIVOT_ACCEPT_BLOCK_REGIMES : comma list of intraday regimes (market_regime.py)
#                                in which acceptance is skipped.  Empty = no gate (default).
#   PIVOT_ACCEPT_MAX_PER_SIDE  : max acceptance signals per side per day (0 = no cap, default).
#   PIVOT_ACCEPT_REQUIRE_CONFIRM_BODY : when true, the signal (latest) candle must have a
#                                confirming body: CE close > open (bullish), PE close <
#                                open (bearish).  Blocks acceptance on red CE / green PE
#                                signal candles that satisfy the geometry but are already
#                                reversing away from the Pivot.
# The regime and per-side gates are OFF by default: a 400-day index backtest showed they
# cut total R (CHOPPY block 54 -> 17.5R, 1-per-side 54 -> 35R); distance + room held up.
PIVOT_ACCEPT_MIN_DIST_ATR: float = _getfloat("PIVOT_ACCEPT_MIN_DIST_ATR", 0.5)
PIVOT_ACCEPT_MIN_ROOM_R: float   = _getfloat("PIVOT_ACCEPT_MIN_ROOM_R", 1.5)
PIVOT_ACCEPT_BLOCK_REGIMES: frozenset[str] = frozenset(
    s.strip().upper() for s in _get("PIVOT_ACCEPT_BLOCK_REGIMES", "").split(",") if s.strip()
)
PIVOT_ACCEPT_MAX_PER_SIDE: int   = _getint("PIVOT_ACCEPT_MAX_PER_SIDE", 0)
PIVOT_ACCEPT_REQUIRE_CONFIRM_BODY: bool = _getbool("PIVOT_ACCEPT_REQUIRE_CONFIRM_BODY", False)
# PIVOT_BOUNCE_ZONE_ATR: support-bounce (CE) / resistance-rejection (PE) at
#   every pivot level S3..R3.  Zone half-width = this × ATR; the signal candle
#   must wick into the zone and close back on its approach side with a
#   confirming body.  Targets = next levels.  0.0 = disabled (legacy behaviour).
PIVOT_BOUNCE_ZONE_ATR: float    = _getfloat("PIVOT_BOUNCE_ZONE_ATR", 0.0)
# Bounce quality filters (only used when PIVOT_BOUNCE_ZONE_ATR > 0):
#   PIVOT_BOUNCE_MIN_RANGE_ATR : signal candle range >= this × ATR.
#                                Rejects tiny doji wicks at the level.  Recommended: 0.5.
#   PIVOT_BOUNCE_MIN_WICK_PCT  : rejection wick >= this × candle range (e.g. 0.5).
#   PIVOT_BOUNCE_TREND_EMA     : CE only above EMA(N), PE only below.  Recommended: 21.
#   PIVOT_BOUNCE_CONFIRM_NEXT  : next candle must close above signal high (CE) /
#                                below signal low (PE); entry on that candle.
#                                STRONGLY RECOMMENDED = true.  Without it the bot enters
#                                on the wick-touch candle alone — no follow-through
#                                evidence that the S/R level is actually holding.
PIVOT_BOUNCE_MIN_RANGE_ATR: float = _getfloat("PIVOT_BOUNCE_MIN_RANGE_ATR", 0.0)
PIVOT_BOUNCE_MIN_WICK_PCT: float  = _getfloat("PIVOT_BOUNCE_MIN_WICK_PCT", 0.0)
PIVOT_BOUNCE_TREND_EMA: int       = _getint("PIVOT_BOUNCE_TREND_EMA", 0)
PIVOT_BOUNCE_CONFIRM_NEXT: bool   = _getbool("PIVOT_BOUNCE_CONFIRM_NEXT", False)

# ── Fractal Swing Pivot Reversal / Breakout (TradingView Pivot Reversal) ─────
# PIVOT_ENABLE_SWING: enable fractal swing high/low breakout mode.
PIVOT_ENABLE_SWING: bool        = _getbool("PIVOT_ENABLE_SWING", False)
PIVOT_SWING_LEFT: int           = _getint("PIVOT_SWING_LEFT", 4)
PIVOT_SWING_RIGHT: int          = _getint("PIVOT_SWING_RIGHT", 2)
PIVOT_SWING_TREND_EMA: int      = _getint("PIVOT_SWING_TREND_EMA", 50)         # 0 = disabled
PIVOT_SWING_RR_T1: float        = _getfloat("PIVOT_SWING_RR_T1", 1.5)
PIVOT_SWING_RR_T2: float        = _getfloat("PIVOT_SWING_RR_T2", 2.5)
PIVOT_SWING_RR_T3: float        = _getfloat("PIVOT_SWING_RR_T3", 3.5)
PIVOT_SWING_USE_ATR_SL: bool    = _getbool("PIVOT_SWING_USE_ATR_SL", False)    # False = structural swing low/high
PIVOT_SWING_ATR_MULT: float     = _getfloat("PIVOT_SWING_ATR_MULT", 1.2)

# Move to breakeven after +N R.  1.5 (was 1.0): replay showed +10% total points; win rate
# drops (58% -> ~50%) because fewer trades are protected early.
PIVOT_BE_TRIGGER_R: float       = _getfloat("PIVOT_BE_TRIGGER_R", 1.5)
PIVOT_BE_BUFFER_PTS: float      = _getfloat("PIVOT_BE_BUFFER_PTS", 5.0)        # index pts above entry at BE
PIVOT_T1_LOCK_PCT: float        = _getfloat("PIVOT_T1_LOCK_PCT", 0.5)          # lock 50% of T1 gain at T1
PIVOT_T2_LOCK_PCT: float        = _getfloat("PIVOT_T2_LOCK_PCT", 0.5)          # lock 50% of T1→T2 range at T2
PIVOT_TRAIL_ATR_MULT: float     = _getfloat("PIVOT_TRAIL_ATR_MULT", 1.0)       # chandelier after T1
PIVOT_T2_TRAIL_ATR_MULT: float  = _getfloat("PIVOT_T2_TRAIL_ATR_MULT", 0.75)   # tighter trail after T2 (0=same)
PIVOT_HARD_SL_CUSHION: float    = _getfloat("PIVOT_HARD_SL_CUSHION", 1.75)     # broker SL backstop width
PIVOT_OPTION_DELTA: float       = _getfloat("PIVOT_OPTION_DELTA", 0.4)
PIVOT_MAX_TRADES_PER_DAY: int   = _getint("PIVOT_MAX_TRADES_PER_DAY", 3)
# PIVOT_NO_NEW_ENTRY_AFTER: block new pivot entries at or after this time (HH:MM).
# Backtest shows 14:00+ entries: 17 trades, 0 wins, −₹11,841 (PF 0.00).
# Empty string = disabled (use global NO_NEW_ENTRY_AFTER).
PIVOT_NO_NEW_ENTRY_AFTER: str   = _get("PIVOT_NO_NEW_ENTRY_AFTER", "")
# PIVOT_NO_FRIDAY: when true, no new pivot entries are allowed on Fridays.
# Backtest shows Fridays: 20 trades, 15% WR, −₹9,096 (PF 0.37).
PIVOT_NO_FRIDAY: bool           = _getbool("PIVOT_NO_FRIDAY", False)


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

# ── Intraday market regime (rule-based, no AI) ────────────────────────────────
# Classifies TRENDING / CHOPPY / MIXED (+ a VOLATILE overlay) on every closed
# 5m candle from Efficiency Ratio, ADX and ATR-vs-baseline.  Observational only:
# shown on the dashboard and stored in trades.smart_entry_flags; it never blocks
# or alters an entry/exit.
ENABLE_INTRADAY_REGIME: bool     = _getbool("ENABLE_INTRADAY_REGIME", True)
INTRADAY_REGIME_ER_PERIOD: int   = _getint("INTRADAY_REGIME_ER_PERIOD", 12)       # candles (12 = 1h)
INTRADAY_REGIME_ADX_PERIOD: int  = _getint("INTRADAY_REGIME_ADX_PERIOD", 14)
INTRADAY_REGIME_ER_TRENDING: float  = _getfloat("INTRADAY_REGIME_ER_TRENDING", 0.5)
INTRADAY_REGIME_ER_CHOPPY: float    = _getfloat("INTRADAY_REGIME_ER_CHOPPY", 0.3)
INTRADAY_REGIME_ADX_TRENDING: float = _getfloat("INTRADAY_REGIME_ADX_TRENDING", 25.0)
INTRADAY_REGIME_VOL_RATIO: float    = _getfloat("INTRADAY_REGIME_VOL_RATIO", 1.5)  # ATR / baseline ATR

# ── Order-flow tick recorder (research data collection, default OFF) ──────────
# Subscribes the near-month SENSEX future in MODE_FULL (separate from the trading
# tokens) and writes ticks + 5-level depth to daily CSVs for offline order-flow
# research.  Never read by any entry/exit logic.  LIVE/SHADOW only (needs the
# WebSocket); ignored in PAPER.
#   ORDERFLOW_RECORD_DIR            : output folder ("" = research/data/orderflow)
#   ORDERFLOW_DEPTH_SAMPLE_SECONDS  : also store a depth row after this much quiet time
#   ORDERFLOW_FUT_MIN_DAYS_TO_EXPIRY: roll to the next-month contract this many days
#                                     before expiry (liquidity migrates early)
ENABLE_ORDERFLOW_RECORDER: bool            = _getbool("ENABLE_ORDERFLOW_RECORDER", False)
ORDERFLOW_RECORD_DIR: str                  = _get("ORDERFLOW_RECORD_DIR", "")
ORDERFLOW_DEPTH_SAMPLE_SECONDS: float      = _getfloat("ORDERFLOW_DEPTH_SAMPLE_SECONDS", 1.0)
ORDERFLOW_FUT_MIN_DAYS_TO_EXPIRY: int      = _getint("ORDERFLOW_FUT_MIN_DAYS_TO_EXPIRY", 3)

# ── Expiry-day iron butterfly (SHADOW only) ───────────────────────────────────
# Research strategy (research/output/strategy_lab/STRATEGY_REPORT.md): on SENSEX
# weekly expiry day, sell the ATM CE+PE and buy CE/PE FLY_WING_POINTS away, then
# stop at a FLY_STOP_PCT loss of the credit or exit at FLY_EXIT_TIME.  It trades
# four legs at once, which the live order path does not support, so it runs ONLY
# in SHADOW: fills are simulated at the real bid/ask, and every entry stores the
# real quotes so they can be compared with the backtest's modelled prices
# (python -m research.fly_vs_model).  ENABLE_EXPIRY_FLY with TRADING_MODE=LIVE is
# refused at startup.
#   FLY_QUANTITY          : units per leg (one SENSEX lot = 20)
#   FLY_MIN_CREDIT        : skip entry if the net credit (points) is below this
#   FLY_SKIP_DATES        : comma list of YYYY-MM-DD event days to sit out
#   FLY_EXTRA_SLIPPAGE_PTS: extra points per leg per side on top of bid/ask
ENABLE_EXPIRY_FLY: bool        = _getbool("ENABLE_EXPIRY_FLY", False)
FLY_ENTRY_TIME: str            = _get("FLY_ENTRY_TIME", "10:30")
FLY_EXIT_TIME: str             = _get("FLY_EXIT_TIME", "15:10")
FLY_WING_POINTS: int           = _getint("FLY_WING_POINTS", 1000)
FLY_STOP_PCT: float            = _getfloat("FLY_STOP_PCT", 0.5)
FLY_QUANTITY: int              = _getint("FLY_QUANTITY", 20)
FLY_MIN_CREDIT: float          = _getfloat("FLY_MIN_CREDIT", 50.0)
FLY_SKIP_DATES: str            = _get("FLY_SKIP_DATES", "")
FLY_EXTRA_SLIPPAGE_PTS: float  = _getfloat("FLY_EXTRA_SLIPPAGE_PTS", 0.0)

# ── Validation ────────────────────────────────────────────────────────────────
ALLOWED_MODES = {"PAPER", "SHADOW", "LIVE"}


def validate() -> None:
    if ENABLE_EXPIRY_FLY and TRADING_MODE == "LIVE":
        raise RuntimeError(
            "ENABLE_EXPIRY_FLY is SHADOW-only: the live order path cannot place a "
            "four-leg position safely.  Set TRADING_MODE=SHADOW or disable it."
        )
    if ENABLE_EXPIRY_FLY and (FLY_WING_POINTS <= 0 or FLY_QUANTITY <= 0 or FLY_STOP_PCT <= 0):
        raise ValueError("FLY_WING_POINTS, FLY_QUANTITY and FLY_STOP_PCT must be positive.")
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
    if ENABLE_DAILY_LOSS_LIMIT and DAILY_LOSS_LIMIT_RUPEES <= 0:
        raise ValueError(
            "ENABLE_DAILY_LOSS_LIMIT=true but DAILY_LOSS_LIMIT_RUPEES is missing or zero. "
            "Set a positive loss cap in RUPEES (e.g. DAILY_LOSS_LIMIT_RUPEES=3000) or "
            "disable the feature with ENABLE_DAILY_LOSS_LIMIT=false."
        )
