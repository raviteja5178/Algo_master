"""
Main bot orchestrator.

Ties together all subsystems:
  - config validation
  - logging
  - DB init + restart recovery
  - instrument master
  - historical candle seed
  - WebSocket live feed
  - candle aggregation + signal evaluation
  - order execution (paper or live)
  - trailing stop management
  - EOD forced exit
  - broker reconciliation
"""

from __future__ import annotations

import json
import logging
import sys

# Force UTF-8 stdout/stderr on Windows (cp1252 crashes on box-drawing chars,
# em-dashes, and other non-ASCII in log/print output).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import time
import uuid
from datetime import datetime
from pathlib import Path

from config import settings
from execution.atr_risk import compute_risk_params
from execution.eod_manager import EODManager
from execution.option_selector import select_atm_candidates, select_atm_option
from execution.position_manager import State, StateMachine
from execution.protective_stop import ProtectiveStop
from execution.pivot_trade_manager import PivotTradeManager
from execution.ema_trade_manager import EmaTradeManager, IndexTradeManager, plan_ema_risk
from execution.smart_exit import SmartExitEngine
from strategies.ai_confirmation import AIConfirmationFilter
from strategies.regime_classifier import RegimeClassifier
from strategies.market_regime import classify_intraday
from strategies.smart_entry import SmartEntryFilter
from execution.target_manager import DynamicTargetManager
from execution.trailing_stop import TrailingStopManager
from market.candle_aggregator import CandleAggregator
from market.candle_builder import Candle
from market.historical_data import (
    SENSEX_TOKEN,
    fetch_historical_candles,
    fetch_daily_trend,
    fetch_previous_day_hl,
    PivotLevels,
    compute_pivot_levels,
)
from market.vwap import VWAPCalculator
from market.paper_feed import PaperFeed
from market.websocket_client import WebSocketClient
from notifications.notifier import notify
from persistence.trade_store import (
    add_live_order_event,
    claim_entry_slot_atomic,
    fetch_active_trade,
    fetch_today_realised_pnl,
    has_action,
    init_db,
    mark_trade_closed,
    mark_trade_closed_with_reason,
    record_action,
    release_entry_slot,
    upsert_trade,
)
from risk.safety_manager import SafetyManager
from strategies.signal_engine import (
    evaluate_signals, note_ema_result, note_ema_trade, tick_ema_cooldown,
    note_mom_exit, note_mom_trade, tick_mom_cooldown,
    note_side_trade,
)
from market.indicators import atr_at, ema as calc_ema, swing_levels
from utils.latency import LatencyTracker
from utils.logging_config import configure_logging, log_event
from utils.price_utils import round_to_tick
from utils.time_utils import IST, is_after_or_equal, market_open, now_ist, parse_time_ist

# Shared state file read by the UI process
_STATE_FILE = Path(__file__).resolve().parent / ".bot_state.json"

logger = logging.getLogger(__name__)


# ── Broker adapter factory ─────────────────────────────────────────────────────

def _build_broker():
    if settings.TRADING_MODE == "LIVE":
        from execution.order_manager import OrderManager
        return OrderManager()
    elif settings.TRADING_MODE == "SHADOW":
        # SHADOW watches the live feed but never sends real orders
        from execution.paper_broker import PaperBroker
        return PaperBroker()
    else:
        from execution.paper_broker import PaperBroker
        return PaperBroker()


# ── Global bot state ──────────────────────────────────────────────────────────

class BotContext:
    def __init__(self) -> None:
        self.sm = StateMachine()
        self.broker = _build_broker()
        self.safety = SafetyManager(self.sm)
        self.eod = EODManager(self.broker, _TradeStoreFacade())

        # Active trade tracking
        self.trade_id: str | None = None
        self.tradingsymbol: str | None = None
        self.instrument_token: int | None = None
        self.quantity: int = settings.QUANTITY
        self.entry_price: float = 0.0
        # Last option premium seen by on_option_ltp (0 when flat)
        self.last_option_ltp: float = 0.0
        self.entry_atr: float | None = None    # ATR(14) at trade entry — for dynamic profit lock
        self.stop_order_id: str | None = None
        self.trailing: TrailingStopManager | None = None
        self.target: DynamicTargetManager | None = None
        self.strategy_type: str | None = None
        # Pivot strategy owns its own SL/BE/TSL/target engine (None for other strategies)
        self.pivot_mgr: PivotTradeManager | None = None

        # Last known SENSEX spot LTP (updated by every tick)
        self.sensex_ltp: float = 0.0

        # WebSocket order postback delivery.
        # order_id -> dict payload (set by _on_order_update, consumed by _wait_for_fill)
        # This is the PRIMARY fill-confirmation mechanism in LIVE/SHADOW mode.
        self.order_fill_events: dict[str, dict] = {}

        # Per-trade latency tracker (reset on each new entry attempt)
        self.latency: LatencyTracker | None = None

        # Candle aggregators
        self.agg_5m = CandleAggregator(5)
        self.agg_15m = CandleAggregator(15)

        # VWAP calculator — fed by completed 5m candles + every SENSEX tick
        self.vwap = VWAPCalculator()

        # Previous day High / Low / Close — populated at startup from daily historical data
        self.prev_day_high:  float | None = None
        self.prev_day_low:   float | None = None
        self.prev_day_close: float | None = None
        # Higher-timeframe trend for the trend gate ("UP"/"DOWN"/"UNKNOWN"),
        # loaded once at startup — the bot restarts each session.
        self.daily_trend: str | None = None

        # Pivot levels (P, R1, R2, S1, S2) — computed from prev-day OHLC at startup
        self.pivot_levels: PivotLevels | None = None

        # WebSocket (LIVE/SHADOW) or paper feed (PAPER)
        self.ws = WebSocketClient() if settings.TRADING_MODE != "PAPER" else None
        # Research-only order-flow tick recorder (ENABLE_ORDERFLOW_RECORDER); never read by trading logic
        self.orderflow_recorder = None
        self.paper_feed = PaperFeed()  # Always initialize PaperFeed for SENSEX REST polling fallback.

        # ORB session qualifier state — set when an ORB signal is accepted today
        self.orb_fired_today: bool = False
        self.orb_direction_today: str | None = None  # "CE" | "PE"

        # No-new-entry time
        self._no_entry_time = parse_time_ist(settings.NO_NEW_ENTRY_AFTER)

        # Smart Exit Engine (created only when ENABLE_SMART_EXIT=true)
        self.smart_exit: SmartExitEngine | None = (
            SmartExitEngine(
                profit_lock_multiplier    = settings.PROFIT_LOCK_MULTIPLIER,
                profit_lock_atr_mult      = settings.PROFIT_LOCK_ATR_MULT,
                profit_lock_min_pct       = settings.PROFIT_LOCK_MIN_PCT,
                time_decay_after          = settings.TIME_DECAY_EXIT_AFTER,
                time_decay_min_pnl_pts    = settings.TIME_DECAY_MIN_PNL_PTS,
                daily_loss_limit_pts      = settings.DAILY_LOSS_LIMIT_RUPEES,
                enable_reversal_exit      = settings.ENABLE_REVERSAL_EXIT,
                enable_ema_collapse       = settings.ENABLE_EMA_COLLAPSE_EXIT,
                enable_profit_lock        = settings.ENABLE_PROFIT_LOCK_EXIT,
                enable_time_decay         = settings.ENABLE_TIME_DECAY_EXIT,
                enable_daily_loss_limit   = settings.ENABLE_DAILY_LOSS_LIMIT,
                ema_collapse_closes       = settings.EMA_COLLAPSE_CLOSES,
                ema_profit_lock           = settings.EMA_PROFIT_LOCK,
            ) if settings.ENABLE_SMART_EXIT else None
        )

        # Regime Classifier (created only when ENABLE_REGIME_CLASSIFIER=true)
        self.regime_classifier: RegimeClassifier | None = (
            RegimeClassifier(
                enable             = True,
                provider           = settings.REGIME_AI_PROVIDER,
                api_key            = settings.REGIME_AI_API_KEY,
                model              = settings.REGIME_AI_MODEL,
                use_ai             = settings.REGIME_USE_AI,
                atr_mult_trending  = settings.REGIME_ATR_MULT_TRENDING,
                atr_mult_choppy    = settings.REGIME_ATR_MULT_CHOPPY,
                atr_mult_volatile  = settings.REGIME_ATR_MULT_VOLATILE,
                min_pct_trending   = settings.REGIME_MIN_PCT_TRENDING,
                min_pct_choppy     = settings.REGIME_MIN_PCT_CHOPPY,
                min_pct_volatile   = settings.REGIME_MIN_PCT_VOLATILE,
                ollama_host        = settings.REGIME_AI_OLLAMA_HOST,
            ) if settings.ENABLE_REGIME_CLASSIFIER else None
        )

        # Smart Entry Filter — always created; filters are disabled when params=0/false
        self.smart_entry = SmartEntryFilter(
            min_body_atr_ratio          = settings.SMART_ENTRY_MIN_BODY_ATR_RATIO,
            require_ema_slope           = settings.SMART_ENTRY_REQUIRE_EMA_SLOPE,
            cooldown_candles            = settings.SMART_ENTRY_COOLDOWN_CANDLES,
            min_ema_gap_pts             = settings.SMART_ENTRY_MIN_EMA_GAP_PTS,
            gap_close_rate              = settings.SMART_ENTRY_GAP_CLOSE_RATE,
            require_ema_gap_widening    = settings.SMART_ENTRY_REQUIRE_EMA_GAP_WIDENING,
            require_15m_trend           = settings.SMART_ENTRY_REQUIRE_15M_TREND,
            max_15m_gap_pts             = settings.SMART_ENTRY_15M_MAX_GAP_PTS,
            squeeze_bypass              = settings.SMART_ENTRY_SQUEEZE_BYPASS,
            squeeze_candles             = settings.SMART_ENTRY_SQUEEZE_CANDLES,
            max_premium_extension_pct   = settings.SMART_ENTRY_MAX_PREMIUM_EXTENSION_PCT,
            squeeze_body_atr_ratio      = settings.SMART_ENTRY_SQUEEZE_BODY_ATR_RATIO,
            structure_bypass_candles    = settings.SMART_ENTRY_STRUCTURE_BYPASS_CANDLES,
            structure_bypass_ema_confirm= settings.SMART_ENTRY_STRUCTURE_BYPASS_EMA_CONFIRM,
            bounce_exempt_strategies    = settings.SMART_ENTRY_BOUNCE_EXEMPT_STRATEGIES,
            slope_exempt_strategies     = settings.SMART_ENTRY_SLOPE_EXEMPT_STRATEGIES,
            squeeze_exempt_strategies   = settings.SMART_ENTRY_SQUEEZE_EXEMPT_STRATEGIES,
        )

        # AI Confirmation Filter (created only when ENABLE_AI_CONFIRMATION=true)
        self.ai_confirmation: AIConfirmationFilter | None = (
            AIConfirmationFilter(
                provider         = settings.AI_CONFIRMATION_PROVIDER,
                api_key          = settings.AI_CONFIRMATION_API_KEY,
                model            = settings.AI_CONFIRMATION_MODEL,
                entry_threshold  = settings.AI_ENTRY_SCORE_THRESHOLD,
                exit_threshold   = settings.AI_EXIT_SCORE_THRESHOLD,
                ollama_host      = settings.AI_CONFIRMATION_OLLAMA_HOST,
            ) if settings.ENABLE_AI_CONFIRMATION else None
        )
        # Current day's AI regime label (updated after classify())
        self.ai_regime: str = "UNKNOWN"

        # Intraday rule-based regime (TRENDING/CHOPPY/MIXED + volatile overlay).
        # Refreshed on every closed 5m candle; observational only (dashboard +
        # trades.smart_entry_flags) — never read by entry/exit logic.
        self.intraday_regime: dict | None = None

    def can_create_entry(self, signal_type: str = "") -> bool:
        # EMA-specific no-new-entry cutoff (overrides global when set)
        _is_ema = signal_type in ("CE", "PE")
        if _is_ema and settings.EMA_NO_NEW_ENTRY_AFTER:
            from utils.time_utils import parse_time_ist
            _ema_cutoff = parse_time_ist(settings.EMA_NO_NEW_ENTRY_AFTER)
            if is_after_or_equal(now_ist().time(), _ema_cutoff):
                return False
        elif is_after_or_equal(now_ist().time(), self._no_entry_time):
            return False
        # Block new entries if daily loss limit is hit
        if self.smart_exit is not None:
            daily_pnl = fetch_today_realised_pnl()
            if self.smart_exit.is_daily_loss_limit_hit(daily_pnl):
                logger.warning(
                    "Daily loss limit hit (realised=Rs %.2f <= -Rs %.2f) - "
                    "no new entries today.", daily_pnl, settings.DAILY_LOSS_LIMIT_RUPEES,
                )
                return False
        return self.sm.can_enter()

    def entry_block_reason(self) -> str:
        """Return why can_create_entry() returned False (called only when it did)."""
        _now = now_ist().time()
        if is_after_or_equal(_now, self._no_entry_time):
            return f"past NO_NEW_ENTRY_AFTER {settings.NO_NEW_ENTRY_AFTER} (now {_now.hour:02d}:{_now.minute:02d})"
        if self.smart_exit is not None:
            daily_pnl = fetch_today_realised_pnl()
            if self.smart_exit.is_daily_loss_limit_hit(daily_pnl):
                return f"daily loss limit hit (realised=Rs {daily_pnl:.2f} <= -Rs {settings.DAILY_LOSS_LIMIT_RUPEES:.2f})"
        return f"state={self.sm.state} — position already open or bot not IDLE"


class _TradeStoreFacade:
    """Minimal facade so EODManager can call mark_trade_closed."""
    @staticmethod
    def mark_trade_closed(trade_id, exit_price, exit_time, pnl):
        mark_trade_closed_with_reason(trade_id, exit_price, exit_time, pnl,
                                      exit_reason="EOD_SQUARE_OFF")


# ── Startup ────────────────────────────────────────────────────────────────────

def print_startup_summary() -> None:
    def _yn(flag: bool) -> str:
        return "YES" if flag else "no"

    # Risk mode label
    if settings.USE_SWING_SL:
        risk_mode = f"Mode D (swing SL, length={settings.SWING_SL_LENGTH}) → fallback Mode C"
    elif settings.USE_SPOT_ATR_RISK:
        risk_mode = f"Mode C (spot ATR×{settings.SPOT_ATR_SL_MULT} / RR={settings.SPOT_ATR_TARGET_RR})"
    else:
        risk_mode = "fixed params (ATR unavailable fallback)"

    # Smart Entry filter summary
    se_filters = []
    if settings.SMART_ENTRY_MIN_BODY_ATR_RATIO > 0:
        se_filters.append(f"body>={settings.SMART_ENTRY_MIN_BODY_ATR_RATIO}xATR")
    if settings.SMART_ENTRY_REQUIRE_EMA_SLOPE:
        se_filters.append("EMA9 slope")
    if settings.SMART_ENTRY_COOLDOWN_CANDLES > 0:
        se_filters.append(f"cooldown {settings.SMART_ENTRY_COOLDOWN_CANDLES}c")
    if settings.SMART_ENTRY_MIN_EMA_GAP_PTS > 0:
        se_filters.append(f"gap>={settings.SMART_ENTRY_MIN_EMA_GAP_PTS}pts")
    if settings.SMART_ENTRY_REQUIRE_EMA_GAP_WIDENING:
        se_filters.append("gap widening")
    se_str = ", ".join(se_filters) if se_filters else "none (all OFF)"

    # Profit lock summary
    if settings.PROFIT_LOCK_ATR_MULT > 0 and settings.PROFIT_LOCK_MIN_PCT > 0:
        pl_str = f"max(entry+ATR x{settings.PROFIT_LOCK_ATR_MULT}, entry x{1+settings.PROFIT_LOCK_MIN_PCT:.1f})"
    elif settings.PROFIT_LOCK_ATR_MULT > 0:
        pl_str = f"entry + ATR x{settings.PROFIT_LOCK_ATR_MULT}"
    elif settings.PROFIT_LOCK_MIN_PCT > 0:
        pl_str = f"entry x{1 + settings.PROFIT_LOCK_MIN_PCT:.2f}"
    else:
        pl_str = f"entry x{settings.PROFIT_LOCK_MULTIPLIER} (fixed)"

    # Regime summary
    if settings.ENABLE_REGIME_CLASSIFIER:
        regime_str = f"ON  ({'AI: ' + settings.REGIME_AI_MODEL if settings.REGIME_USE_AI else 'heuristic'})"
    else:
        regime_str = "OFF"

    if not settings.ENABLE_VWAP_STRATEGY:
        vwap_str = "NO"
    elif not settings.ENABLE_CE_VWAP and not settings.ENABLE_PE_VWAP:
        vwap_str = "NO (all disabled)"
    elif not settings.ENABLE_CE_VWAP:
        vwap_str = "YES (PE only)"
    elif not settings.ENABLE_PE_VWAP:
        vwap_str = "YES (CE only)"
    else:
        vwap_str = "YES"

    print(f"""
+--------------------------------------------------+
|        SENSEX CE/PE Automated Trader             |
+--------------------------------------------------+
|  Mode:                   {settings.TRADING_MODE:<22} |
|  Underlying:             {settings.UNDERLYING:<22} |
|  Quantity:               {settings.QUANTITY:<22} |
+--------------------------------------------------+
|  STRATEGIES                                      |
|  EMA crossover:          {_yn(settings.ENABLE_EMA_STRATEGY):<22} |
|  ORB breakout:           {_yn(settings.ENABLE_ORB_STRATEGY):<22} |
|  Order Block (OB):       {_yn(settings.ENABLE_OB_STRATEGY):<22} |
|  Momentum phase:         {_yn(settings.ENABLE_MOMENTUM_PHASE):<22} |
|  Time Range TRB:         {_yn(settings.ENABLE_TRB_STRATEGY):<22} |
|  VWAP Retest:            {vwap_str:<22} |
|  Prev Day H/L (PDHL):    {_yn(settings.ENABLE_PDHL_STRATEGY):<22} |
|  ATR Copilot:            {_yn(settings.ENABLE_ATR_COPILOT_STRATEGY):<22} |
|  Expiry iron fly:        {_yn(settings.ENABLE_EXPIRY_FLY):<22} |
+--------------------------------------------------+
|  SMART ENTRY FILTERS                             |
|  {se_str:<48} |
+--------------------------------------------------+
|  RISK                                            |
|  Risk mode:   {risk_mode:<35}|
|  Initial SL:             {settings.INITIAL_SL_POINTS:<18.0f} pts |
|  Break-even trigger:     +{settings.BREAK_EVEN_TRIGGER_POINTS:<17.0f} pts |
|  Trail step:             {settings.TRAIL_STEP_POINTS:<18.0f} pts |
|  Initial target ref:     +{settings.INITIAL_TARGET_OFFSET_POINTS:<17.0f} pts |
|  Trailing stop (UST):    {_yn(settings.USE_TRAILING_STOP_EXIT):<22} |
+--------------------------------------------------+
|  SMART EXIT                                      |
|  Smart exit engine:      {_yn(settings.ENABLE_SMART_EXIT):<22} |
|  EMA collapse:           {_yn(settings.ENABLE_EMA_COLLAPSE_EXIT):<22} |
|  Reversal exit:          {_yn(settings.ENABLE_REVERSAL_EXIT):<22} |
|  Profit lock:            {_yn(settings.ENABLE_PROFIT_LOCK_EXIT):<22} |
|  Profit lock mode: {pl_str:<30}|
|  Time decay exit:        {_yn(settings.ENABLE_TIME_DECAY_EXIT):<22} |
|  Daily loss limit:       {_yn(settings.ENABLE_DAILY_LOSS_LIMIT):<22} |
+--------------------------------------------------+
|  AI REGIME CLASSIFIER                            |
|  {regime_str:<48} |
+--------------------------------------------------+
|  SESSION                                         |
|  Force exit:             {settings.FORCE_EXIT_TIME:<22} |
|  No new entry after:     {settings.NO_NEW_ENTRY_AFTER:<22} |
|  Live trading enabled:   {str(settings.ENABLE_LIVE_TRADING).lower():<22} |
+--------------------------------------------------+
""")


# ── Entry execution ────────────────────────────────────────────────────────────

def _ema_option_block_reason(instrument: dict, option_ltp: float | None) -> str | None:
    """
    EMA rule-set option-level checks (SHADOW/LIVE only — PAPER has no option data).

      1. Slippage: best ask must not be more than EMA_MAX_SLIPPAGE_PCT above LTP.
      2. Option trend: option LTP must be above EMA9 of the option's own 5m chart.

    Returns a block reason, or None to allow.  Data errors fail open (allow).
    """
    if settings.TRADING_MODE == "PAPER" or not option_ltp or option_ltp <= 0:
        return None
    from broker.kite_client import get_kite as _gk
    symbol = instrument["tradingsymbol"]

    if settings.EMA_MAX_SLIPPAGE_PCT > 0:
        try:
            q = _gk().quote([f"BFO:{symbol}"])[f"BFO:{symbol}"]
            asks = [d.get("price", 0) for d in (q.get("depth", {}).get("sell") or []) if d.get("price", 0) > 0]
            if asks:
                slip_pct = (asks[0] - option_ltp) / option_ltp * 100
                if slip_pct > settings.EMA_MAX_SLIPPAGE_PCT:
                    return f"slippage {slip_pct:.2f}% > {settings.EMA_MAX_SLIPPAGE_PCT}% (ask={asks[0]} ltp={option_ltp})"
        except Exception as exc:
            logger.warning("EMA slippage check skipped for %s: %s", symbol, exc)

    if settings.EMA_OPTION_EMA_CHECK:
        try:
            opt_candles = fetch_historical_candles(int(instrument["instrument_token"]), "5minute", days_back=4)
            e9 = calc_ema(opt_candles, 9)[-1] if len(opt_candles) >= 9 else None
            if e9 is not None and option_ltp <= e9:
                return f"option premium {option_ltp} <= option 5m EMA9 {e9:.2f}"
        except Exception as exc:
            logger.warning("EMA option-EMA9 check skipped for %s: %s", symbol, exc)
    return None


def _plan_ema_entry(ctx: BotContext, side: str, sensex_ltp: float):
    """
    Pre-fill EMA risk plan on the SENSEX index.
    Returns (plan | None, delta, max_sl_pct, block_reason | None).
    """
    from broker.instrument_repository import is_expiry_day
    expiry = settings.TRADING_MODE != "PAPER" and is_expiry_day()
    # PAPER trades the index itself as the "option" price → delta 1
    delta = 1.0 if settings.TRADING_MODE == "PAPER" else (
        settings.EMA_EXPIRY_DELTA if expiry else settings.EMA_OPTION_DELTA)
    max_sl_pct = settings.EMA_EXPIRY_MAX_SL_PCT if expiry else settings.EMA_MAX_SL_PCT
    if expiry and settings.EMA_EXPIRY_NO_ENTRY_AFTER:
        try:
            if is_after_or_equal(now_ist().time(), parse_time_ist(settings.EMA_EXPIRY_NO_ENTRY_AFTER)):
                return None, delta, max_sl_pct, f"expiry day — no EMA entries after {settings.EMA_EXPIRY_NO_ENTRY_AFTER}"
        except ValueError:
            pass

    c5 = ctx.agg_5m.get_completed()
    atr = atr_at(c5, period=settings.SPOT_ATR_PERIOD)
    sh, sl = (swing_levels(c5, length=settings.EMA_SWING_LENGTH, reference_price=sensex_ltp)
              if len(c5) >= settings.EMA_SWING_LENGTH + 2 else (None, None))

    # Opposing levels for the room filter. Day high/low excludes the last 3
    # candles (the move that produced the signal is not resistance/support).
    # Pivot levels are intentionally not used: EMA is independent of pivots.
    today = now_ist().date()
    day = [c for c in c5[:-3] if c.timestamp.date() == today]
    if side == "CE":
        levels = [ctx.prev_day_high, max((c.high for c in day), default=None)]
    else:
        levels = [ctx.prev_day_low, min((c.low for c in day), default=None)]

    plan, reason = plan_ema_risk(
        side, sensex_ltp, atr, sh, sl,
        swing_buffer_atr=settings.EMA_SWING_BUFFER_ATR,
        min_atr=settings.EMA_SL_MIN_ATR,
        max_atr=settings.EMA_SL_MAX_ATR,
        fallback_atr=settings.EMA_SL_FALLBACK_ATR,
        target_rr=settings.EMA_TARGET_RR if settings.EMA_TARGET_RR > 0 else 3.0,
        levels=[lv for lv in levels if lv],
        min_room_r=settings.EMA_MIN_ROOM_R,
    )
    if plan is not None:
        # Rupee risk always estimated with the real option delta (also in PAPER)
        _rd = settings.EMA_EXPIRY_DELTA if expiry else settings.EMA_OPTION_DELTA
        plan["risk_rupees"] = round(plan["risk"] * _rd * ctx.quantity, 2)
        if settings.EMA_MAX_RISK_RUPEES > 0 and plan["risk_rupees"] > settings.EMA_MAX_RISK_RUPEES:
            reason = f"risk ₹{plan['risk_rupees']:.0f} > max ₹{settings.EMA_MAX_RISK_RUPEES:.0f}"
            plan = None
    log_event(logger, "EMA_RISK_PLAN", side=side, sensex=round(sensex_ltp, 2),
              atr=round(atr, 2) if atr else None, swing_high=sh, swing_low=sl,
              delta=delta, expiry=expiry, plan=plan, blocked=reason)
    return plan, delta, max_sl_pct, reason


def _live_event(event_type: str, **fields) -> None:
    """Record an order event for the LIVE order panel (LIVE mode only; never raises)."""
    if settings.TRADING_MODE != "LIVE":
        return
    add_live_order_event(event_type, now_ist().isoformat(), **fields)



_ORDER_TERMINAL = ("COMPLETE", "REJECTED", "CANCELLED")


def _resolve_entry_fill(ctx: BotContext, fill: dict,
                        option_ltp_hint: float | None) -> tuple[str, dict]:
    """
    Turn a raw place_buy_order result into one of three outcomes:

      ("FILLED",  fill)  — a position is open for fill["filled_qty"]; status is
                           normalised to COMPLETE so the caller protects it.
      ("NO_FILL", fill)  — nothing filled and the order is dead; safe to release
                           the entry slot and return to IDLE.
      ("HALTED",  fill)  — the order's fate is unknown; the bot was halted.

    A TIMEOUT order may still be live at the broker, so it is cancelled first
    and its real filled quantity re-read.  CANCELLED with filled_qty > 0 and
    PRICE_UNCONFIRMED are open positions, not rejections — releasing the slot
    for them would leave a live position with no SL.
    """
    status = fill.get("status")
    if status == "TIMEOUT" and fill.get("order_id"):
        log_event(
            logger, "ENTRY_TIMEOUT_CANCEL",
            symbol=ctx.tradingsymbol, order_id=fill["order_id"],
            filled_qty=fill.get("filled_qty", 0),
        )
        confirmed = ctx.broker.cancel_unfilled_order(
            fill["order_id"], ctx.tradingsymbol, ctx.quantity,
        )
        if confirmed.get("status") not in _ORDER_TERMINAL:
            logger.error(
                "Entry order %s for %s timed out and the cancel could not be "
                "confirmed — it may still fill. Bot is halted; check Zerodha and "
                "use 'Import Position' on the dashboard if a position exists.",
                fill["order_id"], ctx.tradingsymbol,
            )
            notify("BOT_HALTED", reason=f"entry_cancel_unconfirmed_{fill['order_id']}")
            _live_event(
                "ENTRY_UNCONFIRMED", trade_id=ctx.trade_id, symbol=ctx.tradingsymbol,
                order_id=fill["order_id"], qty=ctx.quantity, status="UNCONFIRMED",
                filled_qty=confirmed.get("filled_qty", 0),
            )
            ctx.sm.force_halt("entry order timed out and cancel unconfirmed — manual check required")
            return "HALTED", fill
        fill = dict(confirmed, limit_price=fill.get("limit_price"))
        status = fill["status"]

    filled_qty = int(fill.get("filled_qty") or 0)
    if filled_qty <= 0 or status not in ("COMPLETE", "CANCELLED", "PRICE_UNCONFIRMED"):
        return "NO_FILL", fill

    fill = dict(fill)
    if status != "COMPLETE" or filled_qty < ctx.quantity:
        log_event(
            logger, "ENTRY_PARTIAL_FILL",
            symbol=ctx.tradingsymbol, order_id=fill.get("order_id"),
            status=status, filled_qty=filled_qty, requested_qty=ctx.quantity,
        )
    if float(fill.get("average_price") or 0.0) <= 0:
        # The BUY limit price is an upper bound on the real fill, so an SL
        # derived from it sits at or above where the true SL would be.
        estimate = fill.get("limit_price") or option_ltp_hint
        if estimate and estimate > 0:
            log_event(
                logger, "FILL_PRICE_ESTIMATED",
                symbol=ctx.tradingsymbol, order_id=fill.get("order_id"),
                status=status, estimated_price=estimate, qty=filled_qty,
                message="No exchange fill price — protecting with limit-price "
                        "estimate. Reconcile entry price against Zerodha.",
            )
            fill["average_price"] = float(estimate)
    fill["status"] = "COMPLETE"
    return "FILLED", fill


def execute_entry(ctx: BotContext, signal_type: str, sensex_ltp: float,
                  signal_candle_ts=None, candle_completed_ts: str | None = None) -> None:
    if not ctx.can_create_entry(signal_type=signal_type):
        logger.warning("Entry blocked [%s]: %s.", signal_type, ctx.entry_block_reason())
        return
    # Apply EMA-specific quantity override
    _is_ema_signal = signal_type in ("CE", "PE")
    if _is_ema_signal and settings.EMA_QUANTITY > 0:
        ctx.quantity = settings.EMA_QUANTITY
    else:
        ctx.quantity = settings.QUANTITY

    action_id = f"{signal_type}_ENTRY_{now_ist().strftime('%Y-%m-%d_%H-%M')}"
    if has_action(action_id):
        logger.info("Entry action %s already recorded — skipping duplicate.", action_id)
        return

    # Second-line defence against duplicate orders from concurrent bot processes:
    # the state machine above is in-memory and cannot protect across processes.
    # A DB check here catches the case where another process already opened a
    # trade (wrote it to DB) since the state-machine check above passed.
    if fetch_active_trade() is not None:
        logger.warning(
            "Entry blocked [%s]: an OPEN trade already exists in DB "
            "(concurrent process guard).", signal_type,
        )
        return

    option_type = "CE" if signal_type.startswith("CE") else "PE"

    # ── Latency tracker — one per trade entry attempt ─────────────────────────
    # trade_id is not yet assigned; use a provisional key with the signal type
    # and timestamp so the report is identifiable even if the entry fails.
    ctx.latency = LatencyTracker(
        trade_id=f"{signal_type}_{now_ist().strftime('%Y%m%d_%H%M%S')}"
    )
    # Back-fill CANDLE_COMPLETED using the timestamp recorded by the candle handler
    # The monotonic reading must come from the same instant as the wall-clock
    # string; a 0 here made signal_processing_ms equal the machine uptime.
    _candle_mono = getattr(ctx, "_last_candle_completed_mono", None)
    if candle_completed_ts and _candle_mono is not None:
        ctx.latency.mark_at("CANDLE_COMPLETED", candle_completed_ts, _candle_mono)
    ctx.latency.mark("SIGNAL_CONFIRMED")
    ctx.latency.set_price("sensex_ltp_at_signal", sensex_ltp)

    ctx.sm.transition(
        State.CE_SIGNAL if option_type == "CE" else State.PE_SIGNAL,
        reason=f"{signal_type} signal confirmed",
    )
    ctx.sm.transition(State.ENTRY_PENDING, reason="placing entry order")

    # ── Option selection with ITM fallback ────────────────────────────────────
    # Get ordered candidates: [ATM, one-step ITM, two-step ITM].
    # We iterate through them, fetching the LTP for each, and use the first
    # whose premium is at or above the minimum floor.  This prevents the OTM
    # problem where the nearest-ATM strike is priced below the minimum (e.g.
    # 72800PE @ ₹262 when SENSEX=72788) while the next ITM strike (72900PE)
    # would clear the floor.
    try:
        _candidates = select_atm_candidates(sensex_ltp, option_type)  # type: ignore[arg-type]
    except Exception as exc:
        logger.error("ATM selection failed: %s", exc)
        ctx.sm.transition(State.IDLE, reason="ATM selection failed")
        return

    import time as _time
    from broker.kite_client import get_kite as _get_kite

    instrument = None
    option_ltp_hint: float | None = None

    for _candidate in _candidates:
        _sym = _candidate["tradingsymbol"]

        # Fetch LTP for this candidate.
        if settings.TRADING_MODE == "PAPER":
            # Pure paper — no live connection; use SENSEX LTP as a proxy for all
            # candidates (no per-strike REST call available without live auth).
            _sltp = sensex_ltp if sensex_ltp > 0 else ctx.sensex_ltp
            if _sltp <= 0:
                try:
                    from broker.kite_client import get_kite
                    _q = get_kite().quote(["BSE:SENSEX"])
                    _sltp = float(_q["BSE:SENSEX"]["last_price"])
                    logger.info("PAPER ltp_hint: resolved SENSEX LTP %.2f via REST fallback.", _sltp)
                except Exception as _exc:
                    logger.warning("PAPER ltp_hint: REST fallback failed (%s) — ltp_hint=None.", _exc)
                    _sltp = 0.0
            _ltp: float | None = _sltp if _sltp > 0 else None
        else:
            # SHADOW / LIVE: fetch the real option LTP from Zerodha REST.
            _quote_key = f"BFO:{_sym}"
            _ltp = None
            for _attempt in range(2):
                try:
                    _q = _get_kite().quote([_quote_key])
                    _ltp = float(_q[_quote_key]["last_price"])
                    logger.info(
                        "%s option ltp_hint: %.2f for %s (attempt %d)",
                        settings.TRADING_MODE, _ltp, _sym, _attempt + 1,
                    )
                    break
                except Exception as _exc:
                    logger.warning(
                        "%s option ltp_hint: REST fetch attempt %d failed (%s)%s",
                        settings.TRADING_MODE, _attempt + 1, _exc,
                        " — retrying in 500ms" if _attempt == 0 else " — ltp_hint=None",
                    )
                    if _attempt == 0:
                        _time.sleep(0.5)

        # Accept this candidate if premium check passes (or check is disabled).
        # NATR signals use NATR_MIN_OPTION_ENTRY_PRICE when set (> 0), because
        # NATR fires early in a trend flip before the ATM option has inflated —
        # the global MIN_OPTION_ENTRY_PRICE (intended for deep-OTM protection)
        # would otherwise block legitimate ₹250-280 early-move NATR entries.
        _is_natr = signal_type is not None and "NATR" in signal_type
        _effective_min = (
            settings.NATR_MIN_OPTION_ENTRY_PRICE
            if _is_natr and settings.NATR_MIN_OPTION_ENTRY_PRICE > 0
            else settings.MIN_OPTION_ENTRY_PRICE
        )
        _below_min = (
            _effective_min > 0
            and _ltp is not None
            and _ltp > 0
            and _ltp < _effective_min
        )
        if _below_min:
            _is_itm_fallback = _candidate["strike"] != _candidates[0]["strike"]
            log_event(
                logger, "ENTRY_BLOCKED_MIN_PREMIUM",
                symbol=_sym,
                ltp=_ltp,
                min_required=_effective_min,
                signal=signal_type,
                itm_fallback_attempted=_is_itm_fallback,
            )
            # Try the next ITM candidate if available.
            continue

        # This candidate clears the premium floor — use it.
        instrument = _candidate
        option_ltp_hint = _ltp
        # Feed first-seen LTP for Filter 7 (premium extension guard).
        # Do this before the allow() check below so it has data on first encounter.
        if _ltp is not None and _ltp > 0:
            ctx.smart_entry.notify_option_ltp(_sym, _ltp)
        if _candidate["strike"] != _candidates[0]["strike"]:
            log_event(
                logger, "ITM_FALLBACK_SELECTED",
                symbol=_sym,
                strike=_candidate["strike"],
                atm_strike=_candidates[0]["strike"],
                ltp=_ltp,
                signal=signal_type,
            )
        break

    # If every candidate was below the minimum, block the entry.
    if instrument is None:
        ctx.sm.transition(State.IDLE, reason="option premium below minimum")
        return

    # ── Filter 7: premium extension late gate ─────────────────────────────────
    # This runs after option selection because the option symbol and its current
    # LTP are only known at this point.  All candle-based filters already ran
    # inside evaluate_signals/_gate; this is the option-level extension check.
    if option_ltp_hint is not None and not ctx.smart_entry.allow(
        signal_type,
        [],           # candle filters already ran — pass empty to skip them
        option_ltp=option_ltp_hint,
        tradingsymbol=instrument["tradingsymbol"],
    ):
        ctx.sm.transition(State.IDLE, reason="entry blocked: premium extension")
        return

    # ── EMA rule-set: slippage + option EMA9 checks + index risk plan ─────────
    _ema_plan = None
    _ema_delta = settings.EMA_OPTION_DELTA
    _ema_max_sl_pct = settings.EMA_MAX_SL_PCT
    if signal_type in ("CE", "PE"):
        _ema_block = _ema_option_block_reason(instrument, option_ltp_hint)
        if not _ema_block:
            _ema_plan, _ema_delta, _ema_max_sl_pct, _ema_block = _plan_ema_entry(ctx, option_type, sensex_ltp)
        if _ema_block:
            log_event(logger, "EMA_ENTRY_BLOCKED", signal=signal_type,
                      symbol=instrument["tradingsymbol"], reason=_ema_block)
            ctx.sm.transition(State.IDLE, reason=f"EMA entry blocked: {_ema_block}")
            return

    # ── Momentum: SL-distance and room-to-day-extreme guards ──────────────────
    if signal_type in ("CE_MOM", "PE_MOM") and (
            settings.MOMENTUM_MAX_SL_ATR > 0 or settings.MOMENTUM_MIN_ROOM_ATR > 0):
        _c5 = ctx.agg_5m.get_completed()
        _atr = atr_at(_c5, period=settings.SPOT_ATR_PERIOD)
        _reason = None
        if _atr and settings.MOMENTUM_MAX_SL_ATR > 0:
            _sh, _sl = (swing_levels(_c5, length=settings.SWING_SL_LENGTH, reference_price=sensex_ltp)
                        if len(_c5) >= settings.SWING_SL_LENGTH + 2 else (None, None))
            _swing = _sl if option_type == "CE" else _sh
            _dist = abs(sensex_ltp - _swing) if _swing is not None else None
            if _dist is not None and _dist > settings.MOMENTUM_MAX_SL_ATR * _atr:
                _reason = (f"swing SL {_dist:.1f} pts = {_dist / _atr:.2f}×ATR "
                           f"> {settings.MOMENTUM_MAX_SL_ATR}×ATR")
        if _atr and _reason is None and settings.MOMENTUM_MIN_ROOM_ATR > 0:
            # Prior day extreme, excluding the last 3 candles (the signal move).
            _day = [c for c in _c5[:-3] if c.timestamp.date() == now_ist().date()]
            if _day:
                _room = (max(c.high for c in _day) - sensex_ltp if option_type == "CE"
                         else sensex_ltp - min(c.low for c in _day))
                if 0 <= _room < settings.MOMENTUM_MIN_ROOM_ATR * _atr:
                    _reason = (f"only {_room:.1f} pts = {_room / _atr:.2f}×ATR to prior day "
                               f"{'high' if option_type == 'CE' else 'low'} "
                               f"< {settings.MOMENTUM_MIN_ROOM_ATR}×ATR")
        if _reason:
            log_event(logger, "MOM_ENTRY_BLOCKED", signal=signal_type, reason=_reason)
            ctx.sm.transition(State.IDLE, reason=f"MOM entry blocked: {_reason}")
            return

    # ── Compute risk parameters (ATR-adaptive or fixed) ────────────────────────
    _candles_5m   = ctx.agg_5m.get_completed()
    _option_type  = "CE" if signal_type.startswith("CE") else "PE"
    # EMA CE/PE always use Mode D (swing SL) with Mode C (spot ATR) as fallback,
    # regardless of the global USE_SWING_SL / USE_SPOT_ATR_RISK toggles.
    _is_ema_signal = signal_type in ("CE", "PE")
    _use_swing_sl  = settings.USE_SWING_SL or _is_ema_signal
    _use_spot_atr  = settings.USE_SPOT_ATR_RISK or _is_ema_signal

    # Mode D: resolve nearest swing HIGH above and swing LOW below current price
    _swing_high: float | None = None
    _swing_low:  float | None = None
    if _use_swing_sl and len(_candles_5m) >= settings.SWING_SL_LENGTH + 2:
        _swing_high, _swing_low = swing_levels(
            _candles_5m,
            length=settings.SWING_SL_LENGTH,
            reference_price=sensex_ltp,
        )

    def _compute_risk(entry_price: float):
        return compute_risk_params(
            _candles_5m,
            fixed_sl            = settings.INITIAL_SL_POINTS,
            fixed_target        = settings.INITIAL_TARGET_OFFSET_POINTS,
            fixed_trail         = settings.TRAIL_STEP_POINTS,
            min_sl_pts          = settings.MIN_SL_POINTS,
            min_target_pts      = settings.MIN_TARGET_POINTS,
            min_trail_pts       = settings.MIN_TRAIL_POINTS,
            entry_price         = entry_price,
            # Mode C: SENSEX spot ATR × multiplier
            use_spot_atr        = _use_spot_atr,
            spot_atr_period     = settings.SPOT_ATR_PERIOD,
            spot_sl_mult        = settings.SPOT_ATR_SL_MULT,
            target_rr           = (
                settings.EMA_TARGET_RR
                if signal_type in ("CE", "PE") and settings.EMA_TARGET_RR > 0
                else settings.SPOT_ATR_TARGET_RR
            ),
            trail_rr            = settings.SPOT_ATR_TRAIL_RR,
            # Mode D: swing high/low as SL (structure-based)
            use_swing_sl           = _use_swing_sl,
            option_type            = _option_type,
            sensex_ltp             = sensex_ltp,
            swing_high             = _swing_high,
            swing_low              = _swing_low,
            swing_sl_min_atr_mult  = settings.SWING_SL_MIN_ATR_MULT,
            atm_delta              = settings.ATM_DELTA,
            max_sl_pct             = settings.MAX_SL_PCT,
            be_trigger_rr          = settings.BE_TRIGGER_RR,
        )

    # ── MIN_RR gate (pre-order) ───────────────────────────────────────────────
    # Checked BEFORE the order, using the option LTP as the expected fill.
    # Once filled, a position must be protected, never abandoned for its R:R.
    _is_pivot_signal = signal_type.endswith("_PIVOT")
    if settings.MIN_RR > 0 and not _is_pivot_signal and _ema_plan is None:
        _est = _compute_risk(option_ltp_hint or 0.0)
        _est_sl, _est_tgt = _est.initial_sl_points, _est.initial_target_points
        if _est_sl > 0 and round(_est_tgt / _est_sl, 2) < settings.MIN_RR:
            log_event(
                logger, "ENTRY_BLOCKED_MIN_RR",
                signal=signal_type, sl_pts=_est_sl, target_pts=_est_tgt,
                actual_rr=round(_est_tgt / _est_sl, 2), required_rr=settings.MIN_RR,
                estimated_entry=option_ltp_hint,
            )
            ctx.sm.transition(
                State.IDLE,
                reason=f"R:R {_est_tgt / _est_sl:.2f} below minimum {settings.MIN_RR}",
            )
            return

    # ── Per-trade rupee risk cap (pre-order) ──────────────────────────────────
    # A setup whose structural SL is far away is skipped rather than taken with
    # an outsized loss — the stop is never shrunk into the noise to fit.
    if settings.MAX_RISK_RUPEES_PER_TRADE > 0 and _ema_plan is None:
        if _is_pivot_signal:
            from strategies import signal_engine as _se_peek
            _pv_peek = _se_peek.peek_pivot_setup()
            # Real option delta in every mode (PAPER prices the index itself,
            # but the rupee loss being capped is an option loss).
            _risk_pts = _pv_peek.risk * settings.PIVOT_OPTION_DELTA if _pv_peek is not None else None
        else:
            _risk_pts = _compute_risk(option_ltp_hint or 0.0).initial_sl_points
        if _risk_pts and _risk_pts * ctx.quantity > settings.MAX_RISK_RUPEES_PER_TRADE:
            log_event(
                logger, "ENTRY_BLOCKED_MAX_RISK",
                signal=signal_type, risk_pts=round(_risk_pts, 2), qty=ctx.quantity,
                risk_rupees=round(_risk_pts * ctx.quantity, 2),
                max_rupees=settings.MAX_RISK_RUPEES_PER_TRADE,
            )
            ctx.sm.transition(
                State.IDLE,
                reason=f"risk ₹{_risk_pts * ctx.quantity:.0f} > max ₹{settings.MAX_RISK_RUPEES_PER_TRADE:.0f}",
            )
            return

    ctx.tradingsymbol = instrument["tradingsymbol"]
    ctx.instrument_token = instrument["instrument_token"]

    # ── Atomic entry-slot claim ───────────────────────────────────────────────
    # Generate trade_id NOW (before the order) and INSERT a PENDING row so any
    # concurrent bot process racing here will see status IN ('OPEN','PENDING')
    # in fetch_active_trade() and block itself — closing the race window between
    # the fetch_active_trade() check above and the upsert_trade(OPEN) after fill.
    ctx.trade_id = (
        f"TRADE_{signal_type}_{now_ist().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    )
    ctx.strategy_type = signal_type
    if not claim_entry_slot_atomic(
        ctx.trade_id, signal_type, ctx.tradingsymbol,
        ctx.instrument_token, ctx.quantity, now_ist().isoformat(),
    ):
        logger.warning(
            "Entry blocked [%s]: concurrent process claimed the entry slot first.",
            signal_type,
        )
        ctx.sm.transition(State.IDLE, reason="entry slot claimed by concurrent process")
        return

    if settings.TRADING_MODE != "PAPER":
        # Subscribe to option LTP on WebSocket
        ctx.ws.add_token(ctx.instrument_token)

    record_action(action_id, None, "ENTRY")
    notify("ENTRY_SENT", symbol=ctx.tradingsymbol, qty=ctx.quantity, signal=signal_type)

    if option_ltp_hint and ctx.latency:
        ctx.latency.set_price("option_ltp_at_signal", option_ltp_hint)

    if ctx.latency:
        ctx.latency.mark("BUY_REQUESTED")

    _live_event(
        "ENTRY_SENT", trade_id=ctx.trade_id, symbol=ctx.tradingsymbol,
        price=option_ltp_hint, qty=ctx.quantity, status="SENT",
        signal=signal_type, sensex_ltp=sensex_ltp, regime=ctx.intraday_regime,
    )
    try:
        fill = ctx.broker.place_buy_order(
            ctx.tradingsymbol,
            ctx.quantity,
            ltp_hint=option_ltp_hint,
        )
    except Exception as exc:
        logger.error("Entry order placement raised an exception: %s", exc, exc_info=True)
        notify("ENTRY_REJECTED", symbol=ctx.tradingsymbol, reason=str(exc))
        _live_event(
            "ENTRY_REJECTED", trade_id=ctx.trade_id, symbol=ctx.tradingsymbol,
            price=option_ltp_hint, qty=ctx.quantity, status="EXCEPTION",
            reason=str(exc), signal=signal_type, sensex_ltp=sensex_ltp,
            regime=ctx.intraday_regime,
        )
        release_entry_slot(ctx.trade_id)
        ctx.sm.transition(State.IDLE, reason="broker exception on entry")
        return

    _entry_outcome, fill = _resolve_entry_fill(ctx, fill, option_ltp_hint)
    if _entry_outcome == "HALTED":
        return
    if _entry_outcome == "NO_FILL":
        logger.error("Entry fill failed: %s", fill)
        notify("ENTRY_REJECTED", symbol=ctx.tradingsymbol, reason=fill.get("status"))
        _live_event(
            "ENTRY_REJECTED", trade_id=ctx.trade_id, symbol=ctx.tradingsymbol,
            order_id=fill.get("order_id"), price=option_ltp_hint, qty=ctx.quantity,
            status=fill.get("status"), reason=fill.get("reason") or fill.get("status"),
            signal=signal_type, sensex_ltp=sensex_ltp, regime=ctx.intraday_regime,
        )
        release_entry_slot(ctx.trade_id)
        ctx.sm.transition(State.IDLE, reason="entry rejected/timeout")
        return

    if fill["average_price"] <= 0:
        if settings.TRADING_MODE in ("PAPER", "SHADOW"):
            # PAPER and SHADOW both use PaperBroker — no real order was sent,
            # so a zero price is safe to recover from.
            #
            # SHADOW: try the real option REST quote first (avoids storing the
            #   SENSEX index level as the entry price, which corrupts SL maths).
            #   Fall back to SENSEX LTP only if that also fails.
            # PAPER: no option Kite connection — use SENSEX LTP directly.
            _fallback_price: float = 0.0
            if settings.TRADING_MODE == "SHADOW":
                try:
                    from broker.kite_client import get_kite as _gk2
                    _qf = _gk2().quote([f"BFO:{ctx.tradingsymbol}"])
                    _fallback_price = float(_qf[f"BFO:{ctx.tradingsymbol}"]["last_price"])
                    logger.info(
                        "SHADOW fill fallback: resolved option LTP %.2f for %s via REST.",
                        _fallback_price, ctx.tradingsymbol,
                    )
                except Exception as _exc2:
                    logger.warning(
                        "SHADOW fill fallback: option REST fetch failed (%s) — "
                        "cannot use SENSEX LTP as substitute. Skipping entry.",
                        _exc2,
                    )
            else:
                # PAPER mode: use SENSEX LTP as the option price proxy.
                _fallback_price = ctx.sensex_ltp
                if _fallback_price <= 0:
                    try:
                        from broker.kite_client import get_kite
                        _q = get_kite().quote(["BSE:SENSEX"])
                        _fallback_price = float(_q["BSE:SENSEX"]["last_price"])
                    except Exception as _exc:
                        logger.warning("%s fill fallback REST fetch failed: %s", settings.TRADING_MODE, _exc)
            if _fallback_price > 0:
                logger.warning(
                    "%s entry fill for %s had average_price=0.0 — "
                    "using fallback LTP %.2f as simulated fill price.",
                    settings.TRADING_MODE, ctx.tradingsymbol, _fallback_price,
                )
                fill = dict(fill)
                fill["average_price"] = _fallback_price
            else:
                logger.error(
                    "%s entry fill for %s: average_price=0.0 and all LTP "
                    "fallbacks failed. Skipping entry — bot returns to IDLE.",
                    settings.TRADING_MODE, ctx.tradingsymbol,
                )
                release_entry_slot(ctx.trade_id)
                ctx.sm.transition(State.IDLE, reason="shadow/paper zero fill — no LTP available")
                return
        else:
            # LIVE only: a COMPLETE order with zero price means a real position
            # may exist at Zerodha. Do NOT go back to IDLE — that would allow a
            # re-entry and create a double position. Halt and require manual fix.
            logger.error(
                "Entry fill for %s is COMPLETE at broker (order_id=%s) but "
                "average_price=0.0 could not be resolved. "
                "Bot is halted to prevent a double position. "
                "Check Zerodha, verify the actual fill price, and use "
                "'Import Position' on the dashboard to re-sync the bot.",
                ctx.tradingsymbol, fill.get("order_id"),
            )
            notify("BOT_HALTED", reason=f"zero_fill_price_on_complete_{fill.get('order_id')}")
            ctx.sm.force_halt("zero fill price on confirmed order — manual intervention required")
            return

    if ctx.latency:
        ctx.latency.mark("FILL_PRICE_CONFIRMED")
        ctx.latency.set_price("fill_price", fill["average_price"])
        ctx.latency.set_price("sensex_ltp_at_fill", ctx.sensex_ltp)

    ctx.entry_price = fill["average_price"]
    ctx.quantity = fill["filled_qty"]
    # trade_id and strategy_type were already set before the order (atomic slot claim)
    if ctx.latency:
        ctx.latency.trade_id = ctx.trade_id   # backfill real trade_id now that we have it
    _fill_day = str(now_ist().date())
    _fill_side = "CE" if signal_type.startswith("CE") else "PE"
    note_side_trade(_fill_side, _fill_day)     # global per-side daily cap counter
    if signal_type in ("CE", "PE"):
        note_ema_trade(_fill_day)              # EMA cooldown starts only on a real fill
    elif signal_type in ("CE_MOM", "PE_MOM"):
        note_mom_trade(_fill_day)

    notify("ENTRY_FILLED", symbol=ctx.tradingsymbol, fill=ctx.entry_price, qty=ctx.quantity)

    risk = _compute_risk(ctx.entry_price)
    sl_pts     = risk.initial_sl_points
    be_pts     = risk.break_even_trigger_points
    trail_pts  = risk.trail_step_points
    target_pts = risk.initial_target_points
    ctx.entry_atr = risk.atr_value   # stored for dynamic profit lock

    # ── Pivot strategy: replace generic risk with its own index-based engine ──
    from strategies import signal_engine as _se
    # FIX (Flaw 15): snapshot last_pivot_setup under the tick lock (already held
    # by the caller) rather than reading the module global twice.  The local
    # variable is immutable (frozen dataclass) so it is safe to use below.
    _pv_setup = _se.consume_pivot_setup()
    _is_pivot = signal_type.endswith("_PIVOT") and _pv_setup is not None and _pv_setup.side == _option_type
    if _is_pivot:
        ctx.pivot_mgr = PivotTradeManager(
            _pv_setup.side, sensex_ltp, _pv_setup.stop,
            _pv_setup.t1, _pv_setup.t2, _pv_setup.t3,
            _pv_setup.atr, ctx.entry_price,
            # PAPER mode trades the index itself as the "option" price → delta 1
            delta=1.0 if settings.TRADING_MODE == "PAPER" else settings.PIVOT_OPTION_DELTA,
            be_trigger_r=settings.PIVOT_BE_TRIGGER_R,
            be_buffer_pts=settings.PIVOT_BE_BUFFER_PTS,
            t1_lock_pct=settings.PIVOT_T1_LOCK_PCT,
            t2_lock_pct=settings.PIVOT_T2_LOCK_PCT,
            trail_atr_mult=settings.PIVOT_TRAIL_ATR_MULT,
            t2_trail_atr_mult=settings.PIVOT_T2_TRAIL_ATR_MULT,
            hard_sl_cushion=settings.PIVOT_HARD_SL_CUSHION,
            max_sl_pct=settings.MAX_SL_PCT,
            signal_risk=_pv_setup.risk,
        )
        _pv_delta = ctx.pivot_mgr.delta
        sl_pts     = round(ctx.entry_price - ctx.pivot_mgr.option_stop, 2)
        target_pts = round(abs(_pv_setup.t3 - sensex_ltp) * _pv_delta, 2)
        be_pts     = round(ctx.pivot_mgr.be_trigger_r * ctx.pivot_mgr.risk * _pv_delta, 2)
        trail_pts  = round(settings.PIVOT_TRAIL_ATR_MULT * _pv_setup.atr * _pv_delta, 2)
        log_event(
            logger, "PIVOT_RISK_APPLIED",
            side=_pv_setup.side, mode=_pv_setup.mode,
            sensex_entry=round(sensex_ltp, 2), index_stop=_pv_setup.stop,
            index_risk=ctx.pivot_mgr.risk,
            t1=_pv_setup.t1, t2=_pv_setup.t2, t3=_pv_setup.t3,
            option_entry=ctx.entry_price, option_sl=ctx.pivot_mgr.option_stop,
        )
    else:
        ctx.pivot_mgr = None

    # ── EMA strategy: index-based engine (swing SL clamped by ATR, BE, chandelier) ──
    _is_ema_idx = _ema_plan is not None and not _is_pivot
    if _is_ema_idx:
        _trail_atr = atr_at(_candles_5m, period=settings.TSL_ATR_PERIOD) or _ema_plan["risk"]
        ctx.pivot_mgr = EmaTradeManager(
            _option_type, sensex_ltp, _ema_plan["stop"], _ema_plan["target"],
            _trail_atr, ctx.entry_price,
            delta=_ema_delta,
            be_trigger_r=settings.EMA_BE_TRIGGER_R,
            be_buffer_pts=settings.EMA_BE_BUFFER_PTS,
            trail_atr_mult=settings.EMA_TRAIL_ATR_MULT,
            trail_ema9_exit=settings.EMA_TRAIL_EMA9_EXIT,
            time_stop_bars=settings.EMA_TIME_STOP_BARS,
            time_stop_min_r=settings.EMA_TIME_STOP_MIN_R,
            hard_sl_cushion=settings.EMA_HARD_SL_CUSHION,
            max_sl_pct=_ema_max_sl_pct,
        )
        sl_pts     = round(ctx.entry_price - ctx.pivot_mgr.option_stop, 2)
        target_pts = round(abs(_ema_plan["target"] - sensex_ltp) * _ema_delta, 2)
        be_pts     = round(settings.EMA_BE_TRIGGER_R * ctx.pivot_mgr.risk * _ema_delta, 2)
        trail_pts  = round(settings.EMA_TRAIL_ATR_MULT * _trail_atr * _ema_delta, 2)
        log_event(
            logger, "EMA_RISK_APPLIED",
            side=_option_type, source=_ema_plan["source"],
            sensex_entry=round(sensex_ltp, 2), index_stop=_ema_plan["stop"],
            index_target=_ema_plan["target"], index_risk=_ema_plan["risk"],
            risk_rupees=_ema_plan.get("risk_rupees"), delta=_ema_delta,
            option_entry=ctx.entry_price, option_sl=ctx.pivot_mgr.option_stop,
        )

    # ── Generic strategies: index-anchored engine (GENERIC_INDEX_EXITS) ──────────
    # Fixed-fallback risk has no index meaning, so those trades keep the
    # option-premium TSL.
    _is_generic_idx = (settings.GENERIC_INDEX_EXITS and not _is_pivot and not _is_ema_idx
                       and risk.sl_mode in ("swing_sl", "spot_atr") and sl_pts > 0)
    if _is_generic_idx:
        _gx_sign = 1 if _option_type == "CE" else -1
        _gx_dist = sl_pts / settings.ATM_DELTA            # option SL pts → index pts
        _gx_tgt = target_pts / settings.ATM_DELTA
        _gx_stop = round(sensex_ltp - _gx_sign * _gx_dist, 2)
        _gx_target = round(sensex_ltp + _gx_sign * _gx_tgt, 2)
        _gx_atr = atr_at(_candles_5m, period=settings.TSL_ATR_PERIOD) or _gx_dist
        _gx_delta = 1.0 if settings.TRADING_MODE == "PAPER" else settings.ATM_DELTA
        ctx.pivot_mgr = IndexTradeManager(
            _option_type, sensex_ltp, _gx_stop, _gx_target, _gx_atr, ctx.entry_price,
            delta=_gx_delta,
            be_trigger_r=settings.BE_TRIGGER_RR,
            be_buffer_pts=settings.GENERIC_BE_BUFFER_PTS,
            trail_atr_mult=settings.GENERIC_TRAIL_ATR_MULT,
            hard_sl_cushion=settings.GENERIC_HARD_SL_CUSHION,
            max_sl_pct=settings.MAX_SL_PCT,
        )
        sl_pts     = round(ctx.entry_price - ctx.pivot_mgr.option_stop, 2)   # broker backstop
        be_pts     = round(settings.BE_TRIGGER_RR * _gx_dist * _gx_delta, 2)
        trail_pts  = round(settings.GENERIC_TRAIL_ATR_MULT * _gx_atr * _gx_delta, 2)
        log_event(
            logger, "INDEX_RISK_APPLIED",
            signal=signal_type, side=_option_type, sl_mode=risk.sl_mode,
            sensex_entry=round(sensex_ltp, 2), index_stop=_gx_stop, index_target=_gx_target,
            index_risk=round(_gx_dist, 2), delta=_gx_delta,
            option_entry=ctx.entry_price, option_backstop=ctx.pivot_mgr.option_stop,
        )

    log_event(
        logger, "RISK_PARAMS_APPLIED",
        sl_mode=risk.sl_mode,
        sl_pts=sl_pts, be_pts=be_pts,
        trail_pts=trail_pts, target_pts=target_pts,
        rr=round(target_pts / sl_pts, 2) if sl_pts > 0 else None,
        atr=risk.atr_value,
        swing_high=_swing_high, swing_low=_swing_low,
    )

    # ── MIN_RR re-check at the real fill price ──
    # The gate itself ran before the order.  The position is open now, so a
    # miss here (fill slipped from the LTP estimate) is logged, not acted on —
    # returning to IDLE would abandon a live position with no SL.
    if settings.MIN_RR > 0 and sl_pts > 0 and not _is_pivot and not _is_ema_idx:   # Pivot/EMA have their own room filter
        actual_rr = round(target_pts / sl_pts, 2)
        if actual_rr < settings.MIN_RR:
            log_event(
                logger, "MIN_RR_MISSED_AFTER_FILL",
                signal=signal_type,
                sl_pts=sl_pts,
                target_pts=target_pts,
                actual_rr=actual_rr,
                required_rr=settings.MIN_RR,
                action="position kept and protected",
            )

    # ── SENSEX index-level risk levels (for chart marker display) ─────────────
    # Mode C/D: sl_pts = index_pts × delta (0.4) → invert to get SENSEX distance.
    # Fixed fallback: use option pts as-is (approximation).
    _ATM_DELTA = settings.ATM_DELTA
    is_pe = _option_type == "PE"
    if risk.sl_mode in ("swing_sl", "spot_atr"):
        # sl_pts are option premium pts derived from index pts via delta → invert
        _sl_index_pts  = round(sl_pts     / _ATM_DELTA, 2)
        _tgt_index_pts = round(target_pts / _ATM_DELTA, 2)
    else:
        # Fixed fallback: option pts used directly as rough index approximation
        _sl_index_pts  = sl_pts
        _tgt_index_pts = target_pts
    _sx_entry = round(sensex_ltp, 2)
    _sx_sl    = round(sensex_ltp + _sl_index_pts,     2) if is_pe else round(sensex_ltp - _sl_index_pts,     2)
    _sx_t1    = round(sensex_ltp - _tgt_index_pts,    2) if is_pe else round(sensex_ltp + _tgt_index_pts,    2)
    _sx_t2    = round(sensex_ltp - 2 * _tgt_index_pts,2) if is_pe else round(sensex_ltp + 2 * _tgt_index_pts,2)
    if _is_pivot:   # chart markers = the real Pivot levels
        _sx_sl, _sx_t1, _sx_t2 = _pv_setup.stop, round(_pv_setup.t1, 2), round(_pv_setup.t2, 2)
    elif _is_ema_idx:
        _sx_sl, _sx_t1, _sx_t2 = _ema_plan["stop"], _ema_plan["target"], _ema_plan["target"]
    elif _is_generic_idx:
        _sx_sl, _sx_t1, _sx_t2 = _gx_stop, _gx_target, _gx_target

    # Persist the new trade using the computed risk parameters rather than hardcoded ones
    upsert_trade({
        "trade_id": ctx.trade_id,
        "strategy_type": signal_type,
        "signal_timestamp": now_ist().isoformat(),
        "option_symbol": ctx.tradingsymbol,
        "instrument_token": ctx.instrument_token,
        "quantity": ctx.quantity,
        "entry_order_id": fill["order_id"],
        "entry_price": ctx.entry_price,
        "entry_time": now_ist().isoformat(),
        "current_stop": ctx.entry_price - sl_pts,
        "highest_ltp": ctx.entry_price,
        "target_reference": ctx.entry_price + target_pts,
        "status": "OPEN",
        # Risk snapshot for shadow/paper analysis
        "trade_mode": settings.TRADING_MODE,
        "sl_points": sl_pts,
        "tsl_points": trail_pts,
        "target_points": target_pts,
        "be_points": be_pts,
        "atr_value": ctx.entry_atr,
        # SENSEX index-level prices for chart marker display
        "sensex_entry": _sx_entry,
        "sensex_sl":    _sx_sl,
        "sensex_t1":    _sx_t1,
        "sensex_t2":    _sx_t2,
        # Market regime at entry, for later per-regime P&L analysis
        "smart_entry_flags": json.dumps({"regime": ctx.intraday_regime}) if ctx.intraday_regime else None,
    })
    record_action(action_id, ctx.trade_id, "ENTRY", fill["order_id"], "COMPLETE")
    _live_event(
        "ENTRY_FILLED", trade_id=ctx.trade_id, symbol=ctx.tradingsymbol,
        order_id=fill["order_id"], price=ctx.entry_price, qty=ctx.quantity,
        status="COMPLETE", atr=ctx.entry_atr, sl_points=sl_pts, be_points=be_pts,
        tsl_points=trail_pts, target_points=target_pts,
        initial_stop=round(ctx.entry_price - sl_pts, 2),
        target_price=round(ctx.entry_price + target_pts, 2),
        sl_mode=risk.sl_mode, signal=signal_type,
        regime=ctx.intraday_regime, sensex_entry=_sx_entry,
    )

    # Signal already recorded atomically in evaluate_signals._gate() before
    # the order was placed — no need to record it again here.

    # Trailing and target managers
    ctx.trailing = TrailingStopManager(
        ctx.entry_price, sl_pts, be_pts, trail_pts,
        tsl_atr_trail_mult=settings.TSL_ATR_TRAIL_MULT,
        tsl_atr_period=settings.TSL_ATR_PERIOD,
        atm_delta=settings.ATM_DELTA,
    )
    ctx.target = DynamicTargetManager(
        ctx.entry_price, target_pts, trail_pts,
        ratchet_with_stop=settings.TARGET_TRAIL_WITH_STOP,
    )

    # Protective stop — if placement fails, exit immediately rather than leaving
    # an unprotected live position open.
    if ctx.latency:
        ctx.latency.mark("SL_REQUESTED")
    try:
        pstop = ProtectiveStop(ctx.broker, ctx.tradingsymbol, ctx.quantity, ctx.entry_price,
                               sl_pts)
        ctx.stop_order_id = pstop.place()
        if ctx.latency:
            ctx.latency.mark("SL_ACKNOWLEDGED")
            ctx.latency.report()   # emit the full LATENCY_REPORT now that SL is placed
    except Exception as exc:
        logger.error("Protective stop placement failed: %s — exiting position.", exc)
        notify("BOT_HALTED", reason=f"protective_stop_failed: {exc}")
        # Attempt emergency exit to close the unprotected position.
        try:
            # ENTRY_PENDING -> EXIT_PENDING is not a valid transition; the
            # position IS open, so record that before starting the exit.
            ctx.sm.transition(State.POSITION_OPEN, reason="filled, protective stop missing")
            ctx.sm.transition(State.EXIT_PENDING, reason="protective stop placement failed")
            fill = ctx.broker.place_sell_order(ctx.tradingsymbol, ctx.quantity, tag="SL_PLACEMENT_FAILED")
            if fill.get("status") == "COMPLETE":
                pnl = (fill.get("average_price", 0.0) - ctx.entry_price) * fill.get("filled_qty", 0)
                mark_trade_closed(ctx.trade_id, fill.get("average_price", 0.0), now_ist().isoformat(), pnl)
                ctx.sm.transition(State.CLOSED, reason="emergency exit after SL failure")
                ctx.sm.transition(State.IDLE, reason="ready for next trade")
            else:
                logger.error(
                    "Emergency exit also failed (status=%s) — halting bot. "
                    "Manual intervention required for %s.",
                    fill.get("status"), ctx.tradingsymbol,
                )
                ctx.sm.force_halt("emergency exit failed after SL placement failure")
        except Exception as exit_exc:
            logger.error("Emergency exit raised exception: %s — halting bot.", exit_exc)
            ctx.sm.force_halt("emergency exit exception after SL placement failure")
        ctx.trade_id = None
        ctx.tradingsymbol = None
        ctx.trailing = None
        ctx.target = None
        ctx.stop_order_id = None
        return

    # Reset smart exit per-trade state
    if ctx.smart_exit is not None:
        ctx.smart_exit.reset()

    # Update persisted stop order ID (keep risk snapshot columns)
    upsert_trade({
        "trade_id": ctx.trade_id,
        "strategy_type": signal_type,
        "signal_timestamp": now_ist().isoformat(),
        "option_symbol": ctx.tradingsymbol,
        "instrument_token": ctx.instrument_token,
        "quantity": ctx.quantity,
        "entry_order_id": fill["order_id"],
        "entry_price": ctx.entry_price,
        "entry_time": now_ist().isoformat(),
        "stop_order_id": ctx.stop_order_id,
        "current_stop": ctx.trailing.current_stop,
        "highest_ltp": ctx.entry_price,
        "target_reference": ctx.target.target_reference,
        "status": "OPEN",
        "trade_mode": settings.TRADING_MODE,
        "sl_points": sl_pts,
        "tsl_points": trail_pts,
        "target_points": target_pts,
        "be_points": be_pts,
        "atr_value": ctx.entry_atr,
    })
    _live_event(
        "SL_PLACED", trade_id=ctx.trade_id, symbol=ctx.tradingsymbol,
        order_id=ctx.stop_order_id, price=ctx.trailing.current_stop, qty=ctx.quantity,
        status="PLACED", atr=ctx.entry_atr, sl_points=sl_pts, be_points=be_pts,
        tsl_points=trail_pts, target_points=target_pts,
        target_price=ctx.target.target_reference,
    )

    ctx.sm.transition(State.POSITION_OPEN, reason="fill confirmed, SL placed")
    if ctx.pivot_mgr is not None:
        ctx.pivot_mgr.save(ctx.trade_id)
    # FIX (Flaw 18): count the trade only after the fill is confirmed and the
    # position is open — rejected orders no longer consume today's quota.
    if signal_type and signal_type.endswith("_PIVOT"):
        from strategies import signal_engine as _se_ref
        _se_ref.note_pivot_trade(str(now_ist().date()))
    logger.info(
        "Position open | %s | entry=%.2f | sl=%.2f | target_ref=%.2f",
        ctx.tradingsymbol, ctx.entry_price, ctx.trailing.current_stop, ctx.target.target_reference,
    )


# ── Option LTP handler (trailing logic) ───────────────────────────────────────

def on_pivot_index_price(ctx: BotContext, sensex_ltp: float) -> None:
    """Pivot trades: SL/BE/TSL/T2 decisions are made on the SENSEX index price."""
    mgr = ctx.pivot_mgr
    if mgr is None or ctx.sm.state != State.POSITION_OPEN:
        return
    action = mgr.on_index_price(sensex_ltp)
    if action is None:
        return
    kind, value = action
    if kind == "EXIT":
        log_event(logger, "PIVOT_EXIT", reason=value, sensex=round(sensex_ltp, 2),
                  stage=mgr.stage, index_stop=mgr.stop_index, best=round(mgr.best_index, 2))
        execute_exit(ctx, reason=str(value))
        return
    # STOP_MOVED → ratchet the broker protective SL (option premium)
    new_opt_stop = float(value)
    if ctx.stop_order_id and ctx.trailing and new_opt_stop > ctx.trailing.current_stop:
        _live_event(
            "SL_MODIFIED", trade_id=ctx.trade_id, symbol=ctx.tradingsymbol,
            order_id=ctx.stop_order_id, price=new_opt_stop, qty=ctx.quantity,
            status="MODIFY", old_stop=ctx.trailing.current_stop,
            stage=mgr.stage, sensex=round(sensex_ltp, 2),
        )
        if not ctx.broker.modify_stop_order(ctx.stop_order_id, new_opt_stop):
            logger.error("Pivot: failed to modify stop order; entering safety mode.")
            ctx.sm.force_halt("pivot stop modification failed")
            notify("BOT_HALTED", reason="pivot_stop_modification_failed")
            return
        ctx.trailing.current_stop = new_opt_stop
        was_be = ctx.trailing.break_even_activated
        ctx.trailing.break_even_activated = mgr.stage != "INITIAL"
        # Count each stop-raise after BE as a trail step so the UI TSL-steps
        # counter works correctly for CE_PIVOT / PE_PIVOT trades.
        if was_be:
            ctx.trailing.trail_steps_completed += 1
    mgr.save(ctx.trade_id or "")
    upsert_trade({
        "trade_id": ctx.trade_id,
        "strategy_type": ctx.strategy_type,
        # Do NOT include signal_timestamp here — upsert_trade would overwrite
        # the original signal time with the time of this stop modification.
        "option_symbol": ctx.tradingsymbol,
        "instrument_token": ctx.instrument_token,
        "quantity": ctx.quantity,
        "entry_price": ctx.entry_price,
        "stop_order_id": ctx.stop_order_id,
        "current_stop": mgr.option_stop,
        "highest_ltp": ctx.trailing.highest_ltp if ctx.trailing else ctx.entry_price,
        "target_reference": ctx.target.target_reference if ctx.target else None,
        "status": "OPEN",
    })


def _paper_option_price(ctx: BotContext, index_price: float) -> float:
    """
    PAPER has no option feed, so the SENSEX index stands in for the option
    premium (delta 1).  A PE gains when the index falls, so its price is the
    index mirrored around the entry: entry + (entry - index).  Without this a
    PE's stop sat below entry and fired on the profitable move, and P&L had
    the wrong sign.
    """
    if (index_price > 0 and ctx.entry_price > 0
            and (ctx.strategy_type or "").startswith("PE")
            and ctx.sm.state in (State.POSITION_OPEN, State.EXIT_PENDING)):
        return round(2 * ctx.entry_price - index_price, 2)
    return index_price


def on_option_ltp(ctx: BotContext, ltp: float) -> None:
    if ctx.sm.state != State.POSITION_OPEN or ctx.trailing is None:
        return
    ctx.last_option_ltp = ltp

    # PAPER mode: option "LTP" here is the SENSEX spot price (option token never
    # subscribed in pure-paper mode).
    # SHADOW mode: option "LTP" is the real option premium from the WebSocket
    # (the token is subscribed at entry — see execute_entry).
    # In both cases feed it to PaperBroker so _check_stops can compare against
    # the option-based SL trigger price.
    if settings.TRADING_MODE in ("PAPER", "SHADOW"):
        ctx.broker.update_ltp(ctx.tradingsymbol, ltp)
        # If the paper broker triggered the SL, execute_exit closes the trade.
        if ctx.broker.get_order_status(ctx.stop_order_id) == "COMPLETE":
            logger.info("%s SL triggered for %s at ltp=%.2f", settings.TRADING_MODE, ctx.tradingsymbol, ltp)
            execute_exit(ctx, reason="STOP_HIT", exit_ltp=ltp)
            return

    # Pivot trades: own engine (driven by SENSEX ticks) — only the broker SL
    # backstop above applies here. Track the option high for reporting.
    if ctx.pivot_mgr is not None:
        ctx.trailing.highest_ltp = max(ctx.trailing.highest_ltp, ltp)
        # EMA index engine: keep the daily-loss / time-decay smart exits active
        # (profit lock is skipped for EMA unless EMA_PROFIT_LOCK=true).
        if isinstance(ctx.pivot_mgr, EmaTradeManager) and ctx.smart_exit is not None:
            daily_pnl = fetch_today_realised_pnl() + (ltp - ctx.entry_price) * ctx.quantity
            smart_reason = ctx.smart_exit.check_on_tick(
                strategy_type          = ctx.strategy_type,
                entry_price            = ctx.entry_price,
                option_ltp             = ltp,
                qty                    = ctx.quantity,
                daily_realised_pnl_pts = daily_pnl,
                entry_atr              = ctx.entry_atr,
            )
            if smart_reason:
                execute_exit(ctx, reason=smart_reason)
        return

    # Trailing stop logic — pass latest candles for ATR-dynamic mode
    _candles_for_tsl = (
        ctx.agg_5m.get_completed()
        if settings.TSL_ATR_TRAIL_MULT > 0
        else None
    )
    _old_stop = ctx.trailing.current_stop
    new_stop = ctx.trailing.update(ltp, _candles_for_tsl)
    if new_stop is not None:
        _live_event(
            "BREAK_EVEN" if (ctx.trailing.break_even_activated
                             and ctx.trailing.trail_steps_completed == 0) else "SL_MODIFIED",
            trade_id=ctx.trade_id, symbol=ctx.tradingsymbol,
            order_id=ctx.stop_order_id, price=new_stop, qty=ctx.quantity,
            status="MODIFY", old_stop=_old_stop, ltp=ltp,
            break_even_activated=ctx.trailing.break_even_activated,
            trail_steps=ctx.trailing.trail_steps_completed,
            highest_ltp=ctx.trailing.highest_ltp,
        )
        # Modify broker stop order
        if ctx.stop_order_id:
            ok = ctx.broker.modify_stop_order(ctx.stop_order_id, new_stop)
            if not ok:
                logger.error("Failed to modify stop order; entering safety mode.")
                ctx.sm.force_halt("stop modification failed")
                notify("BOT_HALTED", reason="stop_modification_failed")
                return

        # Sync target reference
        if ctx.target:
            ctx.target.sync_trail_steps(ctx.trailing.trail_steps_completed)

        # Persist
        upsert_trade({
            "trade_id": ctx.trade_id,
            "strategy_type": ctx.strategy_type,
            "signal_timestamp": now_ist().isoformat(),
            "option_symbol": ctx.tradingsymbol,
            "instrument_token": ctx.instrument_token,
            "quantity": ctx.quantity,
            "entry_price": ctx.entry_price,
            "stop_order_id": ctx.stop_order_id,
            "current_stop": ctx.trailing.current_stop,
            "highest_ltp": ctx.trailing.highest_ltp,
            "target_reference": ctx.target.target_reference if ctx.target else None,
            "status": "OPEN",
        })

    # Check trailing stop hit for LIVE mode only
    # (PAPER and SHADOW SL are handled above via PaperBroker._check_stops)
    if settings.TRADING_MODE == "LIVE" and ctx.trailing.is_stop_hit(ltp):
        execute_exit(ctx, reason="TRAILING_STOP_HIT")
        return

    # Check target hit
    if ctx.target and ctx.target.is_target_hit(ltp):
        execute_exit(ctx, reason="TARGET_HIT", exit_ltp=ltp)
        return

    # ── Smart Exit tick-level checks ──────────────────────────────────────────
    if ctx.smart_exit is not None and ctx.sm.state == State.POSITION_OPEN:
        # Daily loss kill switch counts realised P&L PLUS the open trade's
        # unrealised P&L, so the open position is closed once the cap is hit.
        daily_pnl = fetch_today_realised_pnl() + (ltp - ctx.entry_price) * ctx.quantity
        smart_reason = ctx.smart_exit.check_on_tick(
            strategy_type          = ctx.strategy_type,
            entry_price            = ctx.entry_price,
            option_ltp             = ltp,
            qty                    = ctx.quantity,
            daily_realised_pnl_pts = daily_pnl,
            entry_atr              = ctx.entry_atr,
        )
        if smart_reason:
            execute_exit(ctx, reason=smart_reason)


# ── Exit execution ─────────────────────────────────────────────────────────────

def _fetch_broker_orders() -> list:
    """
    Fetch the full order list from Zerodha using the shared kite client.
    Returns an empty list on any failure — callers must treat [] as unknown.
    Works regardless of which broker adapter (OrderManager or PaperBroker)
    is in use, because it goes directly to get_kite() instead of ctx.broker._kite.
    """
    try:
        from broker.kite_client import get_kite as _get_kite
        return _get_kite().orders() or []
    except Exception as exc:
        logger.warning("Could not fetch broker order list: %s", exc)
        return []


def _resolve_sl_fill_price(ctx: BotContext) -> float:
    """
    Called when the position is already flat at the broker (qty=0) because the
    SL order fired at the exchange before the bot's trailing-stop handler ran.

    PAPER / SHADOW: the SL trigger_price IS the fill price — read it directly
    from the paper broker's completed stop order record.

    LIVE: fetch order history from Zerodha to find the actual fill price.

    Falls back to ctx.entry_price if the fill price cannot be determined.
    """
    fallback = ctx.entry_price

    # ── PAPER / SHADOW: read fill price from the paper broker's stop record ───
    if settings.TRADING_MODE in ("PAPER", "SHADOW"):
        try:
            order = getattr(ctx.broker, "_open_orders", {}).get(ctx.stop_order_id)
            if order and order.get("status") == "COMPLETE":
                return float(order["trigger_price"])
        except Exception as exc:
            logger.warning("Could not read paper SL fill price: %s", exc)
        return fallback

    # ── LIVE: look up completed SELL order in Zerodha order history ───────────
    try:
        orders = _fetch_broker_orders()
        sells = [
            o for o in orders
            if o.get("tradingsymbol") == ctx.tradingsymbol
            and o.get("transaction_type") == "SELL"
            and o.get("status") == "COMPLETE"
        ]
        if sells:
            return float(sells[-1].get("average_price", fallback))
    except Exception as exc:
        logger.warning("Could not fetch SL fill price from order history: %s", exc)
    return fallback


def _close_trade_context(ctx: BotContext) -> None:
    """Clear all active-trade fields on ctx after a confirmed exit."""
    if getattr(ctx, "strategy_type", None) in ("CE_MOM", "PE_MOM"):
        note_mom_exit(ctx.strategy_type[:2])
    # Unsubscribe option token from WebSocket so the stale monitor stops watching it.
    # Without this the option token stays in _option_tokens after trade close and the
    # stale alarm fires continuously after market hours with no ticks arriving.
    if getattr(ctx, "ws", None) is not None and getattr(ctx, "instrument_token", None) is not None:
        ctx.ws.remove_token(ctx.instrument_token)
    ctx.trade_id = None
    ctx.tradingsymbol = None
    ctx.instrument_token = None
    ctx.trailing = None
    ctx.target = None
    ctx.stop_order_id = None
    ctx.last_option_ltp = 0.0
    if getattr(ctx, "pivot_mgr", None) is not None:
        type(ctx.pivot_mgr).clear()
    ctx.pivot_mgr = None


def _reprotect_position(ctx: BotContext, qty: int, why: str) -> bool:
    """
    Re-place the protective SL after a failed exit.  execute_exit cancels the
    stop before selling, so a sell that does not complete leaves the position
    naked unless the stop is put back.  Returns True if a stop is working.
    """
    if qty <= 0 or not ctx.tradingsymbol:
        return False
    stop = None
    try:
        stop = ctx.trailing.current_stop if ctx.trailing is not None else None
        if not stop or stop <= 0:
            stop = ctx.entry_price - settings.INITIAL_SL_POINTS
        pstop = ProtectiveStop(ctx.broker, ctx.tradingsymbol, qty, ctx.entry_price, 0.0)
        pstop.initial_sl_price = pstop.current_stop = round_to_tick(stop)
        ctx.stop_order_id = pstop.place()
    except Exception as exc:
        log_event(logger, "SL_REPLACE_FAILED", symbol=ctx.tradingsymbol,
                  qty=qty, sl=stop, reason=why, error=str(exc))
        ctx.stop_order_id = None
        return False
    ctx.quantity = qty
    log_event(logger, "SL_REPLACED_AFTER_EXIT_FAILURE", symbol=ctx.tradingsymbol,
              qty=qty, sl=stop, order_id=ctx.stop_order_id, reason=why)
    _live_event(
        "SL_PLACED", trade_id=ctx.trade_id, symbol=ctx.tradingsymbol,
        order_id=ctx.stop_order_id, price=stop, qty=qty, status="PLACED",
        reason=why,
    )
    upsert_trade({"trade_id": ctx.trade_id, "stop_order_id": ctx.stop_order_id,
                  "quantity": qty})
    return True


def _halt_after_exit_failure(ctx: BotContext, remaining_qty: int, why: str) -> None:
    """Put the stop back for whatever is still open, then halt."""
    protected = _reprotect_position(ctx, remaining_qty, why)
    sl_state = "replaced" if protected else "missing"
    logger.error(
        "Exit failed (%s) — %d qty of %s still open, SL %s (%s). Halting bot. "
        "Manual intervention required.",
        why, remaining_qty, ctx.tradingsymbol, sl_state, ctx.stop_order_id,
    )
    notify("BOT_HALTED", reason=f"exit_failed_{why}_sl_{sl_state}")
    ctx.sm.force_halt(f"exit failed: {why} (SL {sl_state})")


def _settle_failed_sell(ctx: BotContext, fill: dict) -> tuple[int, float] | None:
    """
    Make sure a non-COMPLETE sell order is dead and return the (qty, avg_price)
    it did fill.  Returns None when its fate is unknown (cancel not confirmed):
    the order may still fill, so no further sell or SL must be sent.
    """
    if fill.get("status") in _ORDER_TERMINAL or not fill.get("order_id"):
        return int(fill.get("filled_qty") or 0), float(fill.get("average_price") or 0.0)
    confirmed = ctx.broker.cancel_unfilled_order(
        fill["order_id"], ctx.tradingsymbol, ctx.quantity,
    )
    if confirmed.get("status") not in _ORDER_TERMINAL:
        return None
    return int(confirmed.get("filled_qty") or 0), float(confirmed.get("average_price") or 0.0)


def _recover_failed_exit(ctx: BotContext, fill: dict, reason: str,
                         ltp_hint: float | None) -> dict | None:
    """
    The exit sell did not complete.  Cancel it and retry once at a fresh price
    for whatever is still open; if that also fails, re-place the SL and halt.
    Returns a combined COMPLETE fill dict, or None when the bot was halted.
    """
    original_qty = ctx.quantity
    done_qty, done_value = 0, 0.0
    last_order_id = fill.get("order_id")

    for attempt in (1, 2):
        settled = _settle_failed_sell(ctx, fill)
        if settled is None:
            # The sell may still be working — an SL or another sell on top of
            # it could oversell into a naked short.
            logger.error(
                "Exit sell %s for %s did not complete and its cancel could not be "
                "confirmed — it may still fill. Halting without sending new orders.",
                fill.get("order_id"), ctx.tradingsymbol,
            )
            notify("BOT_HALTED", reason=f"exit_cancel_unconfirmed_{fill.get('order_id')}")
            ctx.sm.force_halt("exit sell timed out and cancel unconfirmed — manual check required")
            return None
        part_qty, part_price = settled
        done_qty += part_qty
        done_value += part_qty * part_price

        remaining = original_qty - done_qty
        try:
            remaining = min(remaining, ctx.broker.get_position_qty(ctx.tradingsymbol))
        except Exception as exc:
            logger.warning("Position check after failed exit unavailable: %s", exc)
        log_event(logger, "EXIT_FILL_INCOMPLETE", symbol=ctx.tradingsymbol,
                  status=fill.get("status"), order_id=fill.get("order_id"),
                  filled_so_far=done_qty, remaining=remaining, attempt=attempt)

        if remaining <= 0:
            break
        if attempt == 2:
            _halt_after_exit_failure(ctx, remaining, f"sell_{fill.get('status')}")
            return None

        # Retry once — in LIVE place_sell_order re-fetches the LTP, so the
        # limit is repriced to the current market.
        try:
            fill = ctx.broker.place_sell_order(
                ctx.tradingsymbol, remaining, tag=reason,  # Kite caps tags at 20 chars
                ltp_hint=ltp_hint if settings.TRADING_MODE != "LIVE" else None,
            )
        except Exception as exc:
            logger.error("Exit retry raised an exception: %s", exc, exc_info=True)
            _halt_after_exit_failure(ctx, remaining, "retry_exception")
            return None
        last_order_id = fill.get("order_id") or last_order_id
        retry_qty = int(fill.get("filled_qty") or 0)
        if fill.get("status") == "COMPLETE" and retry_qty >= remaining:
            done_qty += retry_qty
            done_value += retry_qty * float(fill.get("average_price") or 0.0)
            break

    if done_qty <= 0:
        _halt_after_exit_failure(ctx, original_qty, "no_fill")
        return None
    return {
        "order_id": last_order_id,
        "status": "COMPLETE",
        "filled_qty": done_qty,
        "average_price": round(done_value / done_qty, 2),
    }


def execute_exit(ctx: BotContext, reason: str = "", exit_ltp: float | None = None) -> None:
    if ctx.sm.state not in (State.POSITION_OPEN,):
        return

    ctx.sm.transition(State.EXIT_PENDING, reason=reason)

    # Cancel stop order first — log failure but continue with market sell
    if ctx.stop_order_id:
        if not ctx.broker.cancel_order(ctx.stop_order_id):
            logger.warning(
                "Could not cancel stop order %s before exit — proceeding anyway.",
                ctx.stop_order_id,
            )

    # PaperBroker (used in PAPER and SHADOW) needs an explicit ltp_hint because
    # the option token is never subscribed (_last_ltp stays 0.0 in PAPER, and
    # in SHADOW the on_option_ltp callback feeds SENSEX ticks not option ticks).
    # Priority:
    #   1. Caller-supplied exit_ltp (already the correct option price when passed)
    #   2. SHADOW: fetch real option LTP from Zerodha REST
    #   3. PAPER: the index as the option price (mirrored for PE, see _paper_option_price)
    _sell_ltp_hint: float | None = None
    if settings.TRADING_MODE in ("PAPER", "SHADOW"):
        if exit_ltp and exit_ltp > 0:
            _sell_ltp_hint = exit_ltp
        elif settings.TRADING_MODE == "SHADOW" and ctx.tradingsymbol:
            try:
                from broker.kite_client import get_kite as _get_kite
                _quote_key = f"BFO:{ctx.tradingsymbol}"
                _q = _get_kite().quote([_quote_key])
                _sell_ltp_hint = float(_q[_quote_key]["last_price"])
                logger.info("SHADOW exit ltp_hint: %.2f for %s", _sell_ltp_hint, ctx.tradingsymbol)
            except Exception as _exc:
                # Never the SENSEX level: that would book the index as the option price.
                logger.warning("SHADOW exit ltp_hint: REST fetch failed (%s) — using last option tick.", _exc)
                _sell_ltp_hint = getattr(ctx, "last_option_ltp", 0.0) or None
        else:
            _paper_px = _paper_option_price(ctx, ctx.sensex_ltp)
            _sell_ltp_hint = _paper_px if _paper_px > 0 else None

    try:
        fill = ctx.broker.place_sell_order(ctx.tradingsymbol, ctx.quantity, tag=reason, ltp_hint=_sell_ltp_hint)
    except RuntimeError as exc:
        exc_str = str(exc)
        # ── SL already filled at the exchange ──────────────────────────────────
        # place_sell_order raises PRE_SELL_QTY_MISMATCH when the broker already
        # reports qty=0 for the symbol.  This means the protective SL order was
        # triggered and filled at the exchange (race between the broker's SL
        # execution and our trailing-stop handler).  The position is already flat —
        # there is nothing to sell.  Close the trade record cleanly and return to
        # IDLE instead of halting.
        if "PRE_SELL_QTY_MISMATCH" in exc_str:
            exit_price = _resolve_sl_fill_price(ctx)
            pnl = (exit_price - ctx.entry_price) * ctx.quantity
            mark_trade_closed_with_reason(
                ctx.trade_id, exit_price, now_ist().isoformat(), pnl,
                exit_reason="SL_FILLED_AT_EXCHANGE",
                smart_exit_trigger=reason if reason not in ("", "STOP_HIT") else None,
                highest_ltp=ctx.trailing.highest_ltp if ctx.trailing else None,
            )
            notify("EXIT_FILLED", symbol=ctx.tradingsymbol,
                   exit_price=exit_price, pnl=pnl, reason="SL_FILLED_AT_EXCHANGE")
            log_event(logger, "SL_FILLED_AT_EXCHANGE",
                      symbol=ctx.tradingsymbol, exit_price=exit_price,
                      pnl=pnl, original_reason=reason)
            _live_event(
                "SL_FILLED_AT_EXCHANGE", trade_id=ctx.trade_id, symbol=ctx.tradingsymbol,
                order_id=ctx.stop_order_id, price=exit_price, qty=ctx.quantity,
                status="COMPLETE", reason=reason or "STOP_HIT", pnl=round(pnl, 2),
                entry_price=ctx.entry_price,
                highest_ltp=ctx.trailing.highest_ltp if ctx.trailing else None,
                final_stop=ctx.trailing.current_stop if ctx.trailing else None,
                break_even_activated=ctx.trailing.break_even_activated if ctx.trailing else None,
                trail_steps=ctx.trailing.trail_steps_completed if ctx.trailing else None,
            )
            ctx.smart_entry.on_trade_closed(pnl / max(ctx.quantity, 1))
            if ctx.strategy_type in ("CE", "PE"):
                note_ema_result(str(now_ist().date()), pnl)
            ctx.sm.transition(State.CLOSED, reason="SL filled at exchange")
            ctx.sm.transition(State.IDLE, reason="ready for next trade")
            _close_trade_context(ctx)
            return
        # Any other RuntimeError — genuine failure.  The stop was cancelled
        # above, so put it back before halting.
        logger.error("Exit order placement raised an exception: %s", exc, exc_info=True)
        _halt_after_exit_failure(ctx, ctx.quantity, "exit_order_exception")
        return
    except Exception as exc:
        logger.error("Exit order placement raised an exception: %s", exc, exc_info=True)
        _halt_after_exit_failure(ctx, ctx.quantity, "exit_order_exception")
        return

    # Validate fill — a TIMEOUT/REJECTED sell means the position may still be
    # open with its stop already cancelled: cancel, retry once, else re-protect.
    if fill.get("status") != "COMPLETE" or fill.get("filled_qty", 0) == 0:
        fill = _recover_failed_exit(ctx, fill, reason, _sell_ltp_hint)
        if fill is None:
            return

    exit_price = fill.get("average_price", 0.0)
    filled_qty = fill.get("filled_qty", 0)
    pnl = (exit_price - ctx.entry_price) * filled_qty

    # Determine smart-exit trigger (non-mechanical reasons)
    _SMART_EXITS = {
        "EMA_COLLAPSE", "REVERSAL_SIGNAL", "PROFIT_LOCK",
        "TIME_DECAY", "DAILY_LOSS_LIMIT",
        "PIVOT_SL_HIT", "PIVOT_BE_STOP", "PIVOT_TSL_HIT", "PIVOT_TARGET_T2", "PIVOT_TARGET_T3",
        "EMA_SL_HIT", "EMA_BE_STOP", "EMA_TSL_HIT", "EMA_TARGET",
        "EMA_TRAIL_EMA9", "EMA_TIME_STOP",
        "IDX_SL_HIT", "IDX_BE_STOP", "IDX_TSL_HIT", "IDX_TARGET",
        "VWAP_CROSS_EXIT",
    }
    _smart_trigger = reason if reason in _SMART_EXITS else None

    mark_trade_closed_with_reason(
        ctx.trade_id, exit_price, now_ist().isoformat(), pnl,
        exit_reason=reason or "MANUAL",
        smart_exit_trigger=_smart_trigger,
        highest_ltp=ctx.trailing.highest_ltp if ctx.trailing else None,
    )
    notify("EXIT_FILLED", symbol=ctx.tradingsymbol, exit_price=exit_price, pnl=pnl, reason=reason)
    _live_event(
        "EXIT_FILLED", trade_id=ctx.trade_id, symbol=ctx.tradingsymbol,
        order_id=fill.get("order_id"), price=exit_price, qty=filled_qty,
        status="COMPLETE", reason=reason or "MANUAL", pnl=round(pnl, 2),
        entry_price=ctx.entry_price,
        highest_ltp=ctx.trailing.highest_ltp if ctx.trailing else None,
        final_stop=ctx.trailing.current_stop if ctx.trailing else None,
        break_even_activated=ctx.trailing.break_even_activated if ctx.trailing else None,
        trail_steps=ctx.trailing.trail_steps_completed if ctx.trailing else None,
    )

    # Notify smart entry filter so cooldown starts on a loss
    ctx.smart_entry.on_trade_closed(pnl / max(filled_qty, 1))
    if ctx.strategy_type in ("CE", "PE"):
        note_ema_result(str(now_ist().date()), pnl)

    ctx.sm.transition(State.CLOSED, reason=reason)
    ctx.sm.transition(State.IDLE, reason="ready for next trade")
    _close_trade_context(ctx)


# ── Restart recovery ──────────────────────────────────────────────────────────

def recover_from_restart(ctx: BotContext) -> None:
    active = fetch_active_trade()
    if not active:
        logger.info("No active trade found in DB — starting fresh.")
        return

    logger.info("Active trade found: %s — reconciling with broker.", active["trade_id"])
    symbol = active["option_symbol"]
    expected_qty = active["quantity"]

    # PAPER / SHADOW: positions live only in the PaperBroker's in-memory dict and
    # are always absent from the real Zerodha API.  Calling reconcile_position()
    # (which hits get_net_position_qty()) would therefore always see qty=0, triggering
    # a spurious STALE_TRADE_AUTO_CLOSE on every restart mid-trade.
    # Instead, restore the paper position into the broker's internal state and
    # continue — the SL and trailing managers will resume from the persisted values.
    if settings.TRADING_MODE in ("PAPER", "SHADOW"):
        logger.info(
            "PAPER/SHADOW restart recovery — restoring position %s qty=%d "
            "into paper broker (no real-broker reconciliation).",
            symbol, expected_qty,
        )
        ctx.broker._positions[symbol] = expected_qty
    else:
        # LIVE: verify the position still exists at Zerodha before restoring.
        ok = ctx.safety.reconcile_position(symbol, expected_qty)
        if not ok:
            # Position is gone at the broker (qty=0). The DB record is stale.
            # Auto-close it using the best available exit price and start fresh.
            logger.warning(
                "Position %s not found at broker on startup — "
                "closing stale DB record and starting fresh.",
                symbol,
            )
            exit_price = float(active["entry_price"])  # conservative fallback
            try:
                orders = _fetch_broker_orders()
                sells = [
                    o for o in orders
                    if o.get("tradingsymbol") == symbol
                    and o.get("transaction_type") == "SELL"
                    and o.get("status") == "COMPLETE"
                ]
                if sells:
                    exit_price = float(sells[-1].get("average_price", exit_price))
            except Exception:
                pass
            pnl = (exit_price - float(active["entry_price"])) * int(active["quantity"])
            mark_trade_closed(active["trade_id"], exit_price, now_ist().isoformat(), pnl)
            log_event(logger, "STALE_TRADE_AUTO_CLOSED",
                      trade_id=active["trade_id"], symbol=symbol,
                      exit_price=exit_price, pnl=pnl)
            # Reset state machine to IDLE so the bot can trade normally
            ctx.sm._state = State.IDLE  # noqa: SLF001
            return

    # Restore context
    ctx.trade_id = active["trade_id"]
    ctx.tradingsymbol = symbol
    ctx.instrument_token = active["instrument_token"]
    ctx.quantity = expected_qty
    ctx.entry_price = active["entry_price"]
    ctx.stop_order_id = active["stop_order_id"]
    ctx.strategy_type = active["strategy_type"]

    # Rebuild from the trade's own risk snapshot (written at entry); the global
    # fixed-point settings only describe trades with no snapshot (old/imported).
    _sl_pts  = active.get("sl_points") or settings.INITIAL_SL_POINTS
    _be_pts  = active.get("be_points") or settings.BREAK_EVEN_TRIGGER_POINTS
    _tsl_pts = active.get("tsl_points") or settings.TRAIL_STEP_POINTS
    ctx.trailing = TrailingStopManager(
        entry_price=active["entry_price"],
        initial_sl_points=_sl_pts,
        break_even_trigger_points=_be_pts,
        trail_step_points=_tsl_pts,
        tsl_atr_trail_mult=settings.TSL_ATR_TRAIL_MULT,
        tsl_atr_period=settings.TSL_ATR_PERIOD,
        atm_delta=settings.ATM_DELTA,
    )
    ctx.trailing.current_stop = active["current_stop"] or ctx.trailing.current_stop
    ctx.trailing.highest_ltp = active["highest_ltp"] or ctx.entry_price
    # A stop at or above entry means break-even already fired before the restart.
    ctx.trailing.break_even_activated = ctx.trailing.current_stop >= ctx.entry_price

    ctx.target = DynamicTargetManager(
        ctx.entry_price,
        active.get("target_points") or settings.INITIAL_TARGET_OFFSET_POINTS,
        _tsl_pts if active.get("tsl_points") else settings.TARGET_TRAIL_STEP_POINTS,
        ratchet_with_stop=settings.TARGET_TRAIL_WITH_STOP,
    )
    # A fixed target is re-derived from the snapshot: a stored reference may have
    # been ratcheted out of reach by older code.
    if settings.TARGET_TRAIL_WITH_STOP or not active.get("target_points"):
        ctx.target.target_reference = active["target_reference"] or ctx.target.target_reference

    # Restore in-memory paper SL order so trailing stop modifications succeed
    if settings.TRADING_MODE in ("PAPER", "SHADOW") and ctx.stop_order_id:
        if hasattr(ctx.broker, "_open_orders"):
            ctx.broker._open_orders[ctx.stop_order_id] = {
                "type": "SL",
                "tradingsymbol": symbol,
                "quantity": expected_qty,
                "trigger_price": ctx.trailing.current_stop,
                "status": "TRIGGER PENDING",
            }

    # EMA trades: restore the index-based engine (falls back to generic TSL if missing)
    if ctx.strategy_type in ("CE", "PE"):
        ctx.pivot_mgr = EmaTradeManager.load(ctx.trade_id)
        if ctx.pivot_mgr is None:
            logger.warning("EMA trade %s: manager state missing — falling back to generic TSL.", ctx.trade_id)
            notify("EMA_STATE_MISSING", trade_id=ctx.trade_id,
                   reason="ema_trade_manager_state_missing_after_restart")

    # Pivot trades: restore their own SL/BE/TSL engine
    if str(ctx.strategy_type or "").endswith("_PIVOT"):
        ctx.pivot_mgr = PivotTradeManager.load(ctx.trade_id)
        if ctx.pivot_mgr is None:
            # FIX (Flaw 16): escalate to an operator notification so the trader
            # knows the pivot engine is not running — the generic TSL will fire
            # at the wrong levels and the trade will not be managed correctly.
            logger.warning("Pivot trade %s: manager state missing — falling back to generic TSL.", ctx.trade_id)
            notify("PIVOT_STATE_MISSING",
                   trade_id=ctx.trade_id,
                   reason="pivot_trade_manager_state_missing_after_restart")

    # Generic trades opened with GENERIC_INDEX_EXITS: restore the index engine
    # (no saved state → the option-premium TSL rebuilt above manages it).
    if ctx.pivot_mgr is None and not str(ctx.strategy_type or "").endswith("_PIVOT") \
            and ctx.strategy_type not in ("CE", "PE"):
        ctx.pivot_mgr = IndexTradeManager.load(ctx.trade_id)
        if ctx.pivot_mgr is not None:
            log_event(logger, "INDEX_ENGINE_RESTORED", trade_id=ctx.trade_id,
                      stage=ctx.pivot_mgr.stage, index_stop=ctx.pivot_mgr.stop_index)

    ctx.sm._state = State.POSITION_OPEN  # noqa: SLF001

    # ── Place SL if missing (e.g. imported position had no stop_order_id) ────
    if not ctx.stop_order_id and settings.TRADING_MODE == "LIVE":
        logger.info(
            "No stop_order_id on recovered trade — placing protective SL at %.2f",
            ctx.trailing.current_stop,
        )
        try:
            pstop = ProtectiveStop(
                ctx.broker, ctx.tradingsymbol, ctx.quantity,
                ctx.entry_price, settings.INITIAL_SL_POINTS,
            )
            # Override initial_sl_price to use the already-computed trailing stop
            pstop.initial_sl_price = ctx.trailing.current_stop
            pstop.current_stop     = ctx.trailing.current_stop
            ctx.stop_order_id = pstop.place()
            upsert_trade({
                "trade_id":         ctx.trade_id,
                "strategy_type":    ctx.strategy_type,
                "signal_timestamp": now_ist().isoformat(),
                "option_symbol":    ctx.tradingsymbol,
                "instrument_token": ctx.instrument_token,
                "quantity":         ctx.quantity,
                "entry_price":      ctx.entry_price,
                "stop_order_id":    ctx.stop_order_id,
                "current_stop":     ctx.trailing.current_stop,
                "highest_ltp":      ctx.trailing.highest_ltp,
                "target_reference": ctx.target.target_reference,
                "status":           "OPEN",
            })
            notify("INITIAL_SL_PLACED", symbol=ctx.tradingsymbol,
                   sl=ctx.trailing.current_stop, order_id=ctx.stop_order_id)
        except Exception as exc:
            logger.error("Failed to place SL on recovery: %s", exc)
            ctx.sm.force_halt("SL placement failed on recovery")
            return

    logger.info("Restart recovery complete — resuming trade %s.", ctx.trade_id)


# ── State file writer (shared with UI process) ───────────────────────────────

import os as _os

def _atomic_write(path: str, data: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(data)
    _os.replace(tmp, path)


def _write_ltp(ctx: BotContext) -> None:
    """
    Cheap write: update only ltp, bot_state and updated_at in the state file.
    Called on every tick so the UI LTP is always current.
    Reads the existing file, patches the three fields, and writes back atomically.
    Falls back to a full write if the file doesn't exist yet.
    """
    try:
        state_path = str(_STATE_FILE)
        if _os.path.exists(state_path):
            with open(state_path, "r") as f:
                state = json.load(f)
        else:
            state = {}
        state["ltp"] = ctx.sensex_ltp
        state["bot_state"] = ctx.sm.state.value
        state["updated_at"] = now_ist().isoformat()
        _atomic_write(state_path, json.dumps(state))
    except Exception as exc:
        logger.debug("LTP state write failed (non-critical): %s", exc)


def _write_state(ctx: BotContext) -> None:
    """
    Full write: candles + EMA indicators + LTP.
    Called on every candle close and periodically on ticks.
    Failures are silently swallowed — never crash the trading loop.
    """
    try:
        # Strip any post-market frozen candles (15:30+) that may have accumulated
        # in the deque from a previous run or before the session-close guard was
        # applied.  Without this, Wilder ATR smooths toward zero on TR=0 bars,
        # collapsing the ATR Copilot bands to a single line.
        _close_hm = (15, 30)
        candles_5m  = [c for c in ctx.agg_5m.get_completed()
                       if (c.timestamp.hour, c.timestamp.minute) < _close_hm]
        candles_15m = [c for c in ctx.agg_15m.get_completed()
                       if (c.timestamp.hour, c.timestamp.minute) < _close_hm]

        def _ser(candles, limit=60):
            sliced = candles[-limit:]
            return [
                {
                    "t": c.timestamp.isoformat(),
                    "o": c.open, "h": c.high, "l": c.low, "c": c.close,
                    "v": c.volume,
                }
                for c in sliced
            ]

        def _ema_series(candles, period, limit=60):
            vals = calc_ema(candles, period)
            return [round(v, 2) if v is not None else None for v in vals[-limit:]]

        c5  = candles_5m[-60:]
        c15 = candles_15m[-30:]

        # Today-only candle slice — used for chart overlays (VWAP, bands) so they
        # are never silently hidden by the cross-day 60-candle rolling window.
        _today_date = now_ist().date().isoformat()
        candles_5m_today = [c for c in candles_5m if c.timestamp.date().isoformat() == _today_date]

        # Compute OB zones when strategy is enabled (cheap: runs on candle close only)
        ob_zones = None
        if settings.ENABLE_OB_STRATEGY and len(candles_5m) >= settings.OB_SWING_LENGTH + 2:
            try:
                from strategies.ob_strategy import detect_order_blocks
                bull_obs, bear_obs = detect_order_blocks(
                    candles_5m,
                    swing_length=settings.OB_SWING_LENGTH,
                    max_atr_mult=settings.OB_MAX_ATR_MULT,
                    atr_period=settings.OB_ATR_PERIOD,
                    max_blocks=settings.OB_MAX_BLOCKS,
                    invalidation=settings.OB_INVALIDATION,
                )
                ob_zones = {
                    "bull": [{"top": o.top, "bottom": o.bottom, "breaker": o.breaker} for o in bull_obs],
                    "bear": [{"top": o.top, "bottom": o.bottom, "breaker": o.breaker} for o in bear_obs],
                }
            except Exception as ob_exc:
                logger.debug("OB zone compute failed (non-critical): %s", ob_exc)

        # Compute current NATR trailing stop value for the dashboard
        natr_stop_val = None
        if settings.ENABLE_NATR_STRATEGY and len(candles_5m) >= settings.NATR_PERIOD + 3:
            try:
                from strategies.natr_strategy import _compute_natr_stop
                _stops = _compute_natr_stop(candles_5m, settings.NATR_PERIOD, settings.NATR_MULT)
                natr_stop_val = round(_stops[-1], 2) if _stops and _stops[-1] is not None else None
            except Exception:
                pass

        # Compute ATR Copilot bands for the dashboard (dynamic — recomputed every candle close)
        # Emit the FULL time-series (one value per candle) so the chart can draw a proper
        # dynamic curve rather than a flat horizontal line at the latest value only.
        atr_copilot_upper = None          # scalar: latest value (backward-compat)
        atr_copilot_lower = None          # scalar: latest value (backward-compat)
        atr_copilot_upper_series = None   # list:   one value per candle in c5 window
        atr_copilot_lower_series = None   # list:   one value per candle in c5 window
        atr_copilot_ema_val = None
        atr_copilot_atr_val = None
        _cop_min = settings.ATR_COPILOT_EMA_PERIOD + settings.ATR_COPILOT_PERIOD + 2
        if settings.ENABLE_ATR_COPILOT_STRATEGY and len(candles_5m) >= _cop_min:
            try:
                from strategies.atr_copilot_strategy import _compute_bands
                from market.indicators import ema as _cop_ema, atr as _cop_atr
                _cop_upper, _cop_lower = _compute_bands(
                    candles_5m,
                    settings.ATR_COPILOT_PERIOD,
                    settings.ATR_COPILOT_EMA_PERIOD,
                    settings.ATR_COPILOT_BAND_MULT,
                )
                # Scalar latest values (kept for backward compat)
                atr_copilot_upper = round(_cop_upper[-1], 2) if _cop_upper[-1] is not None else None
                atr_copilot_lower = round(_cop_lower[-1], 2) if _cop_lower[-1] is not None else None
                # Full time-series — TODAY's candles only, aligned to the full candles_5m array.
                # We compute bands on all candles for accuracy (warm EMA/ATR) but only emit
                # the today-slice so the chart never shows cross-day stale band points.
                _n_all = len(candles_5m)
                _n_today = len(candles_5m_today)
                # candles_5m_today is a suffix of candles_5m, so its band values are
                # the last _n_today entries of _cop_upper / _cop_lower.
                _upper_today = _cop_upper[_n_all - _n_today:] if _n_today else []
                _lower_today = _cop_lower[_n_all - _n_today:] if _n_today else []
                atr_copilot_upper_series = [
                    {"t": candles_5m_today[i].timestamp.isoformat(),
                     "v": round(_upper_today[i], 2)}
                    for i in range(_n_today)
                    if _upper_today[i] is not None
                ]
                atr_copilot_lower_series = [
                    {"t": candles_5m_today[i].timestamp.isoformat(),
                     "v": round(_lower_today[i], 2)}
                    for i in range(_n_today)
                    if _lower_today[i] is not None
                ]
                _ema_s = _cop_ema(candles_5m, settings.ATR_COPILOT_EMA_PERIOD)
                _atr_s = _cop_atr(candles_5m, settings.ATR_COPILOT_PERIOD)
                atr_copilot_ema_val = round(_ema_s[-1], 2) if _ema_s and _ema_s[-1] is not None else None
                atr_copilot_atr_val = round(_atr_s[-1], 2) if _atr_s and _atr_s[-1] is not None else None
            except Exception:
                pass

        # Count today's trades so the UI knows when to re-fetch signal markers
        _today_str = now_ist().date().isoformat()
        try:
            from persistence.trade_store import fetch_today_realised_pnl as _dummy  # noqa
            import sqlite3 as _sq
            _con = _sq.connect(str(settings.DB_PATH), check_same_thread=False, timeout=5)
            _row = _con.execute(
                "SELECT COUNT(*) FROM trades WHERE entry_time LIKE ?",
                (f"{_today_str}%",),
            ).fetchone()
            _con.close()
            trade_count_today = int(_row[0]) if _row else 0
        except Exception:
            trade_count_today = 0

        state = {
            "ltp": ctx.sensex_ltp,
            "bot_state": ctx.sm.state.value,
            "candles_5m":  _ser(candles_5m,  60),
            "candles_today": _ser(candles_5m_today, 999),   # today-only; no cross-day cut
            "ema9_5m":     _ema_series(c5,  9,  60),
            "ema21_5m":    _ema_series(c5,  20, 60),
            "candles_15m": _ser(candles_15m, 30),
            "ema21_15m":   _ema_series(c15, 20, 30),
            "ob_zones":    ob_zones,
            "vwap":        round(ctx.vwap.value, 2) if ctx.vwap.value else None,
            "prev_day_high": ctx.prev_day_high,
            "prev_day_low":  ctx.prev_day_low,
            "market_regime": ctx.intraday_regime,
            "pivot_levels": {
                "pivot":      ctx.pivot_levels.pivot,
                "r1":         ctx.pivot_levels.r1,
                "r2":         ctx.pivot_levels.r2,
                "s1":         ctx.pivot_levels.s1,
                "s2":         ctx.pivot_levels.s2,
                # Persist prev-day OHLC so an intraday restart that cannot reach
                # the Kite API can still reconstruct PivotLevels with prev_close.
                "prev_high":  ctx.pivot_levels.prev_high,
                "prev_low":   ctx.pivot_levels.prev_low,
                "prev_close": ctx.pivot_levels.prev_close,
            } if ctx.pivot_levels else None,
            "natr_stop":     natr_stop_val,
            "atr_copilot_upper_band":   atr_copilot_upper,
            "atr_copilot_lower_band":   atr_copilot_lower,
            "atr_copilot_upper_series": atr_copilot_upper_series,
            "atr_copilot_lower_series": atr_copilot_lower_series,
            "atr_copilot_ema":          atr_copilot_ema_val,
            "atr_copilot_atr":          atr_copilot_atr_val,
            "trade_count_today":      trade_count_today,
            "active_trade": {
                "symbol":       ctx.tradingsymbol,
                "entry":        ctx.entry_price,
                "current_stop": ctx.trailing.current_stop if ctx.trailing else None,
                "highest_ltp":  ctx.trailing.highest_ltp if ctx.trailing else None,
                "target":       ctx.target.target_reference if ctx.target else None,
                "break_even_activated": ctx.trailing.break_even_activated if ctx.trailing else False,
                "trail_steps_completed": ctx.trailing.trail_steps_completed if ctx.trailing else 0,
                "be_points":    ctx.trailing.break_even_trigger_points if ctx.trailing else None,
            } if ctx.trade_id else None,
            "updated_at": now_ist().isoformat(),
        }
        _atomic_write(str(_STATE_FILE), json.dumps(state))
    except Exception as exc:
        logger.debug("State file write failed (non-critical): %s", exc)


# ── Tick routing (shared by WebSocket and PaperFeed) ─────────────────────────

# Full state (candles + EMA) written every N ticks; LTP written on every tick.
_FULL_WRITE_INTERVAL = 5
_tick_counter = 0


_MARKET_OPEN_TIME  = parse_time_ist("09:15")
# After 15:30 the market is closed and Zerodha streams the last-traded price
# as a heartbeat on every WebSocket keepalive.  These heartbeat ticks have
# True Range = 0, which Wilder-smooths ATR to near-zero after ~25 candles,
# collapsing Upper/Lower bands to a single line.  candle_aggregator.on_tick()
# also drops these, but _write_state must stop recomputing bands from the
# already-in-memory deque (which may still hold frozen candles from before a
# restart).  Solution: _write_state is never called from the tick handler after
# 15:30 — only the cheap _write_ltp (scalar LTP update) keeps the UI live.
_MARKET_CLOSE_TIME = parse_time_ist("15:30")


# Single re-entrant lock shared by the WebSocket (Twisted reactor thread) and the
# PaperFeed (daemon thread).  Both call the same tick_handler concurrently.
# Without this lock, PivotTradeManager.on_index_price() — which mutates best_index,
# stage, stop_index, and option_stop — can be entered from two threads simultaneously:
#   Thread A reads best_index=72080, advances it to 72350, sets moved=True
#   Thread B reads best_index=72080 (stale, before A's write) → returns None
# The net result: moved=False, mgr.save() is never called, BE/TSL never fires.
# A plain threading.Lock() is sufficient — the handler is non-recursive.
import threading as _threading
_tick_lock = _threading.Lock()


def _make_tick_handler(ctx: BotContext):
    global _tick_counter

    def handler(token: int, ltp: float) -> None:
        global _tick_counter
        # Discard any tick that arrives before market opens at 09:15 IST.
        # The bot may start early (pre-open, authentication, etc.) and the
        # WebSocket or REST feed can deliver pre-auction prices that must
        # not pollute candle aggregators or trigger signal evaluation.
        if not is_after_or_equal(now_ist().time(), _MARKET_OPEN_TIME):
            return
        with _tick_lock:
            if token == SENSEX_TOKEN:
                ctx.sensex_ltp = ltp
                # Feed into candle aggregators
                ctx.agg_5m.on_tick(ltp)
                ctx.agg_15m.on_tick(ltp)
                # VWAP is updated from completed candles (on_candle below) for
                # accuracy — tick-level updates would double-count every price
                # because the same data is also accumulated into the 5m candle.
                # Pivot trades manage SL/BE/TSL/T2 on the SENSEX price
                if ctx.pivot_mgr is not None and ctx.sm.state == State.POSITION_OPEN:
                    on_pivot_index_price(ctx, ltp)
                # In PAPER mode the option price IS the SENSEX spot price,
                # so trail/SL checks run against the SENSEX LTP directly.
                if settings.TRADING_MODE == "PAPER" and ctx.sm.state == State.POSITION_OPEN:
                    on_option_ltp(ctx, _paper_option_price(ctx, ltp))
                # After 15:30 only update the scalar LTP — never recompute bands/EMA
                # from the candle buffer, which may contain post-market frozen candles.
                _tick_counter += 1
                _after_close = now_ist().time() >= _MARKET_CLOSE_TIME
                if not _after_close and _tick_counter % _FULL_WRITE_INTERVAL == 0:
                    _write_state(ctx)
                else:
                    _write_ltp(ctx)
            elif ctx.instrument_token and token == ctx.instrument_token:
                # LIVE/SHADOW: option token tick
                on_option_ltp(ctx, ltp)
    return handler


def _start_orderflow_recorder(ctx: BotContext) -> None:
    """
    Start the passive order-flow tick recorder (ENABLE_ORDERFLOW_RECORDER, LIVE/SHADOW).

    Research data collection only: subscribes the near-month future on a separate
    channel of the WebSocket client and never touches trading state.  Any failure
    is logged and ignored -- the bot must trade normally without it.
    """
    if not settings.ENABLE_ORDERFLOW_RECORDER or ctx.ws is None:
        return
    try:
        from broker.instrument_repository import get_near_month_future
        from market.orderflow_recorder import OrderFlowRecorder, default_directory

        fut = get_near_month_future(min_days_to_expiry=settings.ORDERFLOW_FUT_MIN_DAYS_TO_EXPIRY)
        if fut is None:
            logger.warning("Order-flow recorder: no %s future found -- recorder disabled.",
                           settings.UNDERLYING)
            return
        rec = OrderFlowRecorder(
            default_directory(settings.ORDERFLOW_RECORD_DIR),
            fut["tradingsymbol"],
            depth_sample_seconds=settings.ORDERFLOW_DEPTH_SAMPLE_SECONDS,
        )
        ctx.orderflow_recorder = rec
        ctx.ws.add_flow_token(int(fut["instrument_token"]), rec.record)
        log_event(logger, "ORDERFLOW_RECORDER_STARTED", symbol=fut["tradingsymbol"],
                  token=fut["instrument_token"], expiry=str(fut.get("expiry")))
    except Exception as exc:
        logger.warning("Order-flow recorder failed to start (ignored, trading unaffected): %s", exc)


def _refresh_intraday_regime(ctx: BotContext, *, log: bool = True) -> None:
    """Recompute ctx.intraday_regime from completed 5m candles. Never raises."""
    if not settings.ENABLE_INTRADAY_REGIME:
        return
    try:
        snap = classify_intraday(
            ctx.agg_5m.get_completed(),
            er_period=settings.INTRADAY_REGIME_ER_PERIOD,
            adx_period=settings.INTRADAY_REGIME_ADX_PERIOD,
            er_trending=settings.INTRADAY_REGIME_ER_TRENDING,
            er_choppy=settings.INTRADAY_REGIME_ER_CHOPPY,
            adx_trending=settings.INTRADAY_REGIME_ADX_TRENDING,
            vol_ratio_threshold=settings.INTRADAY_REGIME_VOL_RATIO,
        )
        ctx.intraday_regime = {**snap.to_dict(), "label": snap.label}
        if log:
            log_event(
                logger, "REGIME_INTRADAY",
                regime=snap.regime, direction=snap.direction, volatile=snap.volatile,
                er=snap.er, adx=snap.adx, vol_ratio=snap.vol_ratio,
            )
    except Exception as exc:
        logger.debug("Intraday regime compute failed (non-critical): %s", exc)


def _make_candle_handler_5m(ctx: BotContext):
    def handler(candle: Candle) -> None:
        # Refresh the intraday regime first so the state file written just below
        # (and any trade opened on this candle) carries the up-to-date value.
        _refresh_intraday_regime(ctx)

        # Always write state on candle close so the chart updates immediately
        _write_state(ctx)

        # Latency: record when this candle closed (start of signal evaluation)
        # A fresh tracker is created in execute_entry once a signal is confirmed.
        # We only need the CANDLE_COMPLETED timestamp; store it on ctx for pickup.
        ctx._last_candle_completed_ts = now_ist().isoformat()
        ctx._last_candle_completed_mono = time.monotonic_ns()

        candles_5m  = ctx.agg_5m.get_completed()
        candles_15m = ctx.agg_15m.get_completed()

        # ── VWAP: update from completed candle (most accurate — uses OHLCV) ───
        if settings.ENABLE_VWAP_STRATEGY:
            ctx.vwap.on_candle(candle)

        # ── Smart Entry + EMA cooldowns: tick down on every candle ─────────────
        ctx.smart_entry.on_candle()
        tick_ema_cooldown()
        tick_mom_cooldown()

        # ── REST option LTP fallback when WebSocket option feed is dead ────────
        if (
            ctx.ws is not None
            and not ctx.ws.option_feed_ok
            and ctx.sm.state == State.POSITION_OPEN
            and ctx.tradingsymbol
        ):
            try:
                # LIVE mode uses broker._fetch_ltp(); PAPER/SHADOW use Kite directly
                # because PaperBroker has no _fetch_ltp method.
                if settings.TRADING_MODE == "LIVE":
                    rest_ltp = ctx.broker._fetch_ltp(ctx.tradingsymbol, "BFO")
                else:
                    from broker.kite_client import get_kite as _gk
                    _qr = _gk().quote([f"BFO:{ctx.tradingsymbol}"])
                    rest_ltp = float(_qr[f"BFO:{ctx.tradingsymbol}"]["last_price"])
                if rest_ltp and rest_ltp > 0:
                    log_event(logger, "OPTION_LTP_REST_FALLBACK",
                              symbol=ctx.tradingsymbol, ltp=rest_ltp)
                    on_option_ltp(ctx, rest_ltp)
            except Exception as exc:
                logger.warning("REST option LTP fallback failed: %s", exc)

        # ── VWAP cross-exit: close back through VWAP invalidates the thesis ──────
        # CE_VWAP thesis = price above VWAP.  The moment a completed 5m candle
        # closes below VWAP, the level has been surrendered — exit immediately,
        # before the ATR-based option SL backstop fires.  Mirror for PE_VWAP.
        # Only runs when VWAP_CROSS_EXIT=true and the strategy is CE_VWAP/PE_VWAP.
        if (settings.VWAP_CROSS_EXIT
                and ctx.sm.state == State.POSITION_OPEN
                and ctx.strategy_type in ("CE_VWAP", "PE_VWAP")
                and candles_5m
                and ctx.vwap.value is not None):
            _vwap_val = ctx.vwap.value
            _latest_close = candles_5m[-1].close
            _vwap_crossed = (
                ctx.strategy_type == "CE_VWAP" and _latest_close < _vwap_val
            ) or (
                ctx.strategy_type == "PE_VWAP" and _latest_close > _vwap_val
            )
            if _vwap_crossed:
                log_event(
                    logger, "VWAP_CROSS_EXIT",
                    side=ctx.strategy_type,
                    close=round(_latest_close, 2),
                    vwap=round(_vwap_val, 2),
                    candle=candle.timestamp,
                )
                execute_exit(ctx, reason="VWAP_CROSS_EXIT")
                return

        # ── EMA index engine: trail ATR refresh, EMA9 trail exit, time stop, reversal ──
        if isinstance(ctx.pivot_mgr, EmaTradeManager) and ctx.sm.state == State.POSITION_OPEN and candles_5m:
            _emgr = ctx.pivot_mgr
            _tatr = atr_at(candles_5m, period=settings.TSL_ATR_PERIOD)
            if _tatr:
                _emgr.update_atr(_tatr)
            _e9 = calc_ema(candles_5m, 9)[-1] if len(candles_5m) >= 9 else None
            _ema_reason = _emgr.on_candle(candles_5m[-1].close, _e9)
            # Reversal: opposite EMA signal on this candle (side-effect free check)
            if _ema_reason is None and settings.ENABLE_REVERSAL_EXIT and market_open():
                from strategies.ce_strategy import is_ce_signal as _ce_sig
                from strategies.pe_strategy import is_pe_signal as _pe_sig
                _kw = dict(rsi_period=settings.EMA_RSI_PERIOD, pullback_tol_pts=settings.EMA_PULLBACK_TOL_PTS)
                if ctx.strategy_type == "CE" and _pe_sig(candles_5m, candles_15m, rsi_max=settings.EMA_RSI_PE_MAX, **_kw):
                    _ema_reason = "REVERSAL_SIGNAL"
                elif ctx.strategy_type == "PE" and _ce_sig(candles_5m, candles_15m, rsi_min=settings.EMA_RSI_CE_MIN, **_kw):
                    _ema_reason = "REVERSAL_SIGNAL"
            if _ema_reason:
                execute_exit(ctx, reason=_ema_reason)
                return
            _emgr.save(ctx.trade_id or "")

        # ── Smart Exit candle-level checks (EMA collapse) ──────────────────────
        if (ctx.smart_exit is not None and ctx.sm.state == State.POSITION_OPEN
                and (ctx.pivot_mgr is None or isinstance(ctx.pivot_mgr, EmaTradeManager))):
            smart_reason = ctx.smart_exit.check_on_candle(
                strategy_type = ctx.strategy_type,
                candles_5m    = candles_5m,
                candles_15m   = candles_15m,
            )
            if smart_reason:
                execute_exit(ctx, reason=smart_reason)
                return   # position closed — don't evaluate entries this candle

        # ── Reversal signal check (smart exit trigger 1) ────────────────────────
        # evaluate_signals runs here for both entry AND reversal detection.
        # Skip signal evaluation outside market hours — post-15:30 flat candles
        # built from frozen PaperFeed LTP ticks must never reach strategy logic.
        if not market_open():
            return
        # Nothing below applies while halted / mid-order; a POSITION_OPEN bot
        # must still reach the exit checks, so entries are gated further down.
        if ctx.sm.is_entry_blocked() and ctx.sm.state != State.POSITION_OPEN:
            return

        # Derive live EMA9/EMA21/ATR for AI context
        _ema9_val  = candles_5m[-1].ema9  if candles_5m and hasattr(candles_5m[-1], 'ema9')  else None
        _ema21_val = candles_5m[-1].ema21 if candles_5m and hasattr(candles_5m[-1], 'ema21') else None
        _atr_val   = atr_at(candles_5m, period=14) if len(candles_5m) >= 14 else None

        # FIX (Flaw 9): refresh the pivot manager's ATR and delta on every candle
        # close so the chandelier trail uses current-session volatility rather than
        # the frozen entry-time ATR, and the option stop stays delta-accurate.
        if (ctx.pivot_mgr is not None and ctx.sm.state == State.POSITION_OPEN
                and not isinstance(ctx.pivot_mgr, EmaTradeManager)):
            if _atr_val:
                ctx.pivot_mgr.update_atr(_atr_val)
            # FIX (Flaw 10): re-derive delta from SENSEX distance to Pivot t1.
            # As price moves toward / past T1 the option becomes more ITM and
            # delta rises toward 0.5-0.6.  Use a simple linear interpolation:
            #   at entry  → PIVOT_OPTION_DELTA (configured, e.g. 0.4)
            #   at T1     → 0.5
            # beyond T1  → 0.6  (capped; we never reliably know actual greeks)
            if settings.TRADING_MODE != "PAPER":
                _mgr = ctx.pivot_mgr
                _fav_now = _mgr._fav(ctx.sensex_ltp) if ctx.sensex_ltp > 0 else 0.0
                _t1_dist = _mgr._fav(_mgr.t1)
                if _t1_dist > 0:
                    _ratio = min(_fav_now / _t1_dist, 1.5)  # cap at 1.5× T1
                    _base = settings.PIVOT_OPTION_DELTA
                    _new_delta = round(min(0.6, _base + (_ratio * (0.5 - _base))), 3)
                    _mgr.update_delta(_new_delta)

        # Option premium context for AI confirmation — look up the ATM CE/PE option
        # that the bot would select right now (based on SENSEX LTP) and fetch its
        # intraday premium range from the SmartEntryFilter LTP tracker.
        # Falls back gracefully to None if no data is available yet.
        _ai_option_ltp: float | None = None
        _ai_option_day_low: float | None = None
        _ai_option_day_high: float | None = None
        if ctx.ai_confirmation is not None and ctx.sensex_ltp > 0:
            try:
                from execution.option_selector import SENSEX_STRIKE_STEP
                _atm_strike = round(ctx.sensex_ltp / SENSEX_STRIKE_STEP) * SENSEX_STRIKE_STEP
                # Try CE and PE ATM symbols; pick whichever has premium context recorded
                from broker.instrument_repository import get_sensex_options
                _expiry = None  # option_selector will resolve from settings
                from execution.option_selector import resolve_expiry as _re
                _expiry = _re()
                for _ot, _sfx in (("CE", "CE"), ("PE", "PE")):
                    _opts = get_sensex_options(_expiry, _ot)
                    _sym_map = {int(float(o["strike"])): o["tradingsymbol"] for o in _opts}
                    _sym_now = _sym_map.get(int(_atm_strike))
                    if _sym_now:
                        _dl, _dh = ctx.smart_entry.get_premium_context(_sym_now)
                        if _dl is not None:
                            _ai_option_day_low = _dl
                            _ai_option_day_high = _dh
                            # Use last known option LTP from smart_entry highest tracker
                            _ai_option_ltp = _dh  # best approximation of current ltp
                            break
            except Exception:
                pass  # silently fall back to no option context

        signal = evaluate_signals(
            candles_5m, candles_15m,
            smart_entry=ctx.smart_entry,
            ai_confirmation=ctx.ai_confirmation,
            vwap=ctx.vwap.value if settings.ENABLE_VWAP_STRATEGY else None,
            prev_day_high=ctx.prev_day_high if (settings.ENABLE_PDHL_STRATEGY or settings.ENABLE_VWAP_LEVEL_FILTER) else None,
            prev_day_low=ctx.prev_day_low  if (settings.ENABLE_PDHL_STRATEGY or settings.ENABLE_VWAP_LEVEL_FILTER) else None,
            pivot_levels=ctx.pivot_levels if settings.ENABLE_PIVOT_LEVELS else None,
            ema9=_ema9_val,
            ema21=_ema21_val,
            atr=_atr_val,
            regime=ctx.ai_regime,
            intraday_regime=(ctx.intraday_regime or {}).get("regime"),
            orb_fired_today=ctx.orb_fired_today,
            orb_direction_today=ctx.orb_direction_today,
            option_ltp=_ai_option_ltp,
            option_day_low=_ai_option_day_low,
            option_day_high=_ai_option_day_high,
            daily_trend=ctx.daily_trend,
        )

        # ── AI exit suggestion (per-candle, only when position open) ──────────
        if (
            settings.ENABLE_AI_EXIT
            and ctx.ai_confirmation is not None
            and ctx.sm.state == State.POSITION_OPEN
            and signal is None   # don't double-exit on reversal candle
            and ctx.strategy_type
        ):
            _opt_ltp = getattr(ctx, "last_option_ltp", 0.0) or ctx.entry_price
            _unreal = (_opt_ltp - ctx.entry_price) * ctx.quantity
            ai_exit = ctx.ai_confirmation.confirm_exit(
                signal              = ctx.strategy_type,
                candles_5m          = candles_5m,
                entry_price         = ctx.entry_price,
                option_ltp          = _opt_ltp,
                unrealised_pnl_pts  = _unreal,
                ema9                = _ema9_val,
                ema21               = _ema21_val,
                atr                 = _atr_val,
            )
            if ai_exit:
                execute_exit(ctx, reason=ai_exit)
                return

        # Pass reversal signal to smart exit tick handler before entering
        if (
            ctx.smart_exit is not None
            and ctx.sm.state == State.POSITION_OPEN
            and signal is not None
            # Pivot / EMA trades: own exit engine only (generic index trades keep it)
            and (ctx.pivot_mgr is None or isinstance(ctx.pivot_mgr, IndexTradeManager))
        ):
            daily_pnl = fetch_today_realised_pnl()
            smart_reason = ctx.smart_exit.check_on_tick(
                strategy_type          = ctx.strategy_type,
                entry_price            = ctx.entry_price,
                option_ltp             = getattr(ctx, "last_option_ltp", 0.0) or ctx.entry_price,
                qty                    = ctx.quantity,
                daily_realised_pnl_pts = daily_pnl,
                pending_signal         = signal,
                entry_atr              = ctx.entry_atr,
            )
            if smart_reason:
                execute_exit(ctx, reason=smart_reason)
                return

        # Everything above (pivot ATR/delta refresh, AI exit, reversal smart
        # exit) must run while a position is open; only new entries are gated.
        if ctx.sm.is_entry_blocked():
            return

        if signal:
            # Track ORB fires so the session qualifier knows the day's character
            if signal in ("CE_ORB", "PE_ORB") and not ctx.orb_fired_today:
                ctx.orb_fired_today = True
                ctx.orb_direction_today = "CE" if signal == "CE_ORB" else "PE"
            # Use the latest live SENSEX LTP (or candle close as fallback)
            underlying_ltp = ctx.sensex_ltp if ctx.sensex_ltp > 0 else candle.close
            execute_entry(ctx, signal, underlying_ltp, signal_candle_ts=candle.timestamp,
                          candle_completed_ts=getattr(ctx, "_last_candle_completed_ts", None))
    return handler


def _run_eod_exit(ctx: BotContext) -> None:
    """Square off an open position at the force-exit time."""
    if ctx.sm.state != State.POSITION_OPEN or not ctx.trade_id:
        return
    logger.warning(
        "Past force-exit time (%s IST) — squaring off open position.",
        settings.FORCE_EXIT_TIME,
    )
    # POSITION_OPEN -> CLOSED is not a valid direct transition; mark the exit
    # as pending first (this also stops ticks from starting a second exit).
    ctx.sm.transition(State.EXIT_PENDING, reason="EOD square-off")
    eod_ok = ctx.eod.run_eod_exit(
        tradingsymbol=ctx.tradingsymbol,
        quantity=ctx.quantity,
        trade_id=ctx.trade_id,
        stop_order_id=ctx.stop_order_id,
        entry_price=ctx.entry_price,
    )
    if eod_ok:
        ctx.sm.transition(State.CLOSED, reason="EOD")
        ctx.sm.transition(State.IDLE, reason="EOD done")
        _close_trade_context(ctx)
    else:
        logger.error(
            "EOD exit FAILED — position may still be open at broker. "
            "Halting bot to prevent unmanaged exposure."
        )
        ctx.sm.force_halt("EOD exit failed")
        notify("BOT_HALTED", reason="eod_exit_failed")


def bootstrap_session(ctx: BotContext) -> None:
    """
    Per-session startup: seed candles, load prev-day levels, the daily trend
    and pivots, and wire the 5m candle handler.  Shared by main() and the
    full-system backtest (research/system_backtest.py) so both start a
    session identically.
    """
    # Seed historical candles — required for EMA warm-up (min 21 completed candles).
    # Log clearly if this fails so the operator knows signals won't fire for ~1h45m.
    try:
        hist_5m = fetch_historical_candles(SENSEX_TOKEN, "5minute", days_back=5)
        ctx.agg_5m.seed(hist_5m)
        hist_15m = fetch_historical_candles(SENSEX_TOKEN, "15minute", days_back=5)
        ctx.agg_15m.seed(hist_15m)
    except Exception as exc:
        logger.warning(
            "Historical data load failed (%s) — EMA indicators will be cold. "
            "Strategies need 21 completed 5m candles (~1h45m) before any signal can fire.",
            exc,
        )

    # Fetch previous day High / Low for PDHL strategy.
    # Fetch previous day H/L/C — always done when PDHL or Pivot is enabled.
    # fetch_previous_day_hl now returns a 3-tuple (H, L, C).
    if settings.ENABLE_PDHL_STRATEGY or settings.ENABLE_PIVOT_LEVELS:
        try:
            ctx.prev_day_high, ctx.prev_day_low, ctx.prev_day_close = fetch_previous_day_hl(SENSEX_TOKEN)
            logger.info(
                "Prev-day levels loaded — PDH=%.2f  PDL=%.2f  PDC=%.2f",
                ctx.prev_day_high or 0, ctx.prev_day_low or 0, ctx.prev_day_close or 0,
            )
        except Exception as exc:
            logger.warning("Prev-day fetch failed at startup (%s) — trying state file fallback.", exc)
            # Fallback: read prev-day H/L/C from the last saved state file.
            # This keeps PivotLevels alive on an intraday restart when the API
            # is temporarily unreachable.  Only used when the fetch truly fails.
            try:
                import json as _json
                _saved = _json.loads(_STATE_FILE.read_text())
                _pl = _saved.get("pivot_levels") or {}
                if _pl.get("prev_high") and _pl.get("prev_low") and _pl.get("prev_close"):
                    ctx.prev_day_high  = float(_pl["prev_high"])
                    ctx.prev_day_low   = float(_pl["prev_low"])
                    ctx.prev_day_close = float(_pl["prev_close"])
                    logger.info(
                        "Prev-day levels restored from state file — PDH=%.2f  PDL=%.2f  PDC=%.2f",
                        ctx.prev_day_high, ctx.prev_day_low, ctx.prev_day_close,
                    )
                else:
                    logger.warning("State file has no prev-day levels — PDHL/pivot disabled today.")
            except Exception as exc2:
                logger.warning("State file fallback also failed (%s) — PDHL/pivot disabled today.", exc2)

    # Daily trend for the higher-timeframe trend gate (fails to "UNKNOWN" = no gate).
    if settings.TREND_GATE_DAILY:
        ctx.daily_trend = fetch_daily_trend(SENSEX_TOKEN, settings.TREND_GATE_DAILY_EMA)

    # Compute pivot levels from prev-day H/L/C (no extra API call needed).
    # If ENABLE_PIVOT_LEVELS is true and we have the data, build PivotLevels directly.
    if settings.ENABLE_PIVOT_LEVELS and ctx.prev_day_high and ctx.prev_day_low and ctx.prev_day_close:
        ctx.pivot_levels = compute_pivot_levels(
            ctx.prev_day_high,
            ctx.prev_day_low,
            ctx.prev_day_close,
            formula=settings.PIVOT_FORMULA,
        )
        pl = ctx.pivot_levels
        logger.info(
            "Pivot levels computed (%s) — P=%.2f  R1=%.2f  R2=%.2f  R3=%.2f  S1=%.2f  S2=%.2f  S3=%.2f",
            settings.PIVOT_FORMULA, pl.pivot, pl.r1, pl.r2, pl.r3, pl.s1, pl.s2, pl.s3,
        )

    # Seed the intraday regime from the historical candles so the dashboard has a
    # value immediately after a restart instead of waiting for the next candle.
    _refresh_intraday_regime(ctx, log=False)

    # Wire 5m candle handler (signal evaluation fires on every completed 5m candle)
    ctx.agg_5m.subscribe(_make_candle_handler_5m(ctx))


def classify_session_regime(ctx: BotContext) -> None:
    """Once-per-day regime classification (ENABLE_REGIME_CLASSIFIER)."""
    if ctx.regime_classifier is not None and ctx.smart_exit is not None:
        try:
            candles_5m = ctx.agg_5m.get_completed()
            atr = atr_at(candles_5m, 14) or 55.0
            regime = ctx.regime_classifier.classify(
                vix=settings.REGIME_VIX_OVERRIDE,
                sensex_prev_close=candles_5m[-2].close if len(candles_5m) >= 2 else 0.0,
                sensex_open=candles_5m[-1].open if candles_5m else 0.0,
                atr=atr,
            )
            ctx.regime_classifier.adjust_profit_lock(ctx.smart_exit, regime)
            ctx.ai_regime = regime.value   # share with AI confirmation filter
            log_event(logger, "REGIME_CLASSIFIED", regime=regime.value,
                      atr_mult=ctx.smart_exit._profit_lock_atr_mult,
                      min_pct=ctx.smart_exit._profit_lock_min_pct)
        except Exception as exc:
            logger.warning("Regime classification failed (non-critical): %s", exc)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    configure_logging()

    from utils.process_lock import acquire_process_lock
    if not acquire_process_lock("bot"):
        print("[FATAL] Another bot instance is already running. Exiting.", flush=True)
        sys.exit(1)

    settings.validate()
    print_startup_summary()

    init_db()

    # Pre-cache instrument master at startup so ATM lookup at candle close takes 0ms.
    # Run for ALL modes — PAPER mode also needs the instrument master for ATM selection.
    try:
        from broker.instrument_repository import load_instruments
        load_instruments()
    except Exception as exc:
        logger.warning("Instrument master preload failed at startup (will retry on entry): %s", exc)

    ctx = BotContext()
    recover_from_restart(ctx)

    # Expiry-day iron butterfly (SHADOW only; config.validate() refuses LIVE).
    fly_runner = None
    if settings.ENABLE_EXPIRY_FLY and settings.TRADING_MODE == "SHADOW":
        from broker.instrument_repository import get_sensex_options, is_expiry_day
        from broker.kite_client import get_kite
        from execution.fly_runner import ExpiryFlyRunner
        fly_runner = ExpiryFlyRunner(
            kite_fn=get_kite, options_fn=get_sensex_options, expiry_fn=is_expiry_day,
            spot_fn=lambda: ctx.sensex_ltp,
        )
        logger.info("Expiry-day iron butterfly enabled (SHADOW): entry %s, wings %d, stop %.0f%%, exit %s.",
                    settings.FLY_ENTRY_TIME, settings.FLY_WING_POINTS,
                    settings.FLY_STOP_PCT * 100, settings.FLY_EXIT_TIME)

    bootstrap_session(ctx)

    # Write an initial state file immediately after seeding so the UI shows a
    # fresh updated_at right away — prevents false STALE on startup.
    _write_state(ctx)

    # ── Feed setup ────────────────────────────────────────────────────────────
    tick_handler = _make_tick_handler(ctx)

    if settings.TRADING_MODE in ("LIVE", "SHADOW"):
        # PRIMARY feed: KiteTicker WebSocket with SENSEX token 265 subscribed in
        # MODE_FULL.  This gives sub-second ticks with no REST rate-limit risk.
        # Option tokens are added dynamically at trade entry.
        ctx.ws.on_ltp(tick_handler)
        def _on_stale_feed() -> None:
            logger.warning("Option feed stale — no ticks on open position. Auto-reconnect in progress.")
            notify("BOT_HALTED", reason="stale_feed_with_open_position — auto-reconnect triggered")

        ctx.ws.on_stale(_on_stale_feed)

        # ── WebSocket order-update handler (PRIMARY fill confirmation) ─────────
        # Zerodha posts every order-state change here: OPEN → COMPLETE / REJECTED.
        # We store the payload in ctx.order_fill_events keyed by order_id so that
        # OrderManager._wait_for_fill() can check for a WS confirmation before
        # falling back to REST polling.
        def _on_order_update(msg: dict) -> None:
            order_id = str(msg.get("order_id", ""))
            status   = msg.get("status", "")
            if not order_id:
                return
            # Always store the latest payload — any terminal status is useful.
            ctx.order_fill_events[order_id] = msg
            if status == "COMPLETE":
                # Mark EXCHANGE_COMPLETE on the active latency tracker if this
                # matches the current pending entry order.
                if ctx.latency is not None:
                    if "EXCHANGE_COMPLETE" not in ctx.latency._checkpoints:
                        ctx.latency.mark("EXCHANGE_COMPLETE")
                        avg_price = msg.get("average_price")
                        if avg_price:
                            ctx.latency.set_price("fill_price_ws", float(avg_price))
                log_event(
                    logger, "ORDER_FILLED_WS",
                    order_id=order_id,
                    symbol=msg.get("tradingsymbol"),
                    fill=msg.get("average_price"),
                    filled_qty=msg.get("filled_quantity"),
                    exchange_ts=msg.get("exchange_timestamp"),
                )

        ctx.ws.on_order_update(_on_order_update)

        ctx.ws.start([SENSEX_TOKEN])   # subscribe SENSEX spot immediately
        _start_orderflow_recorder(ctx)

        # If we recovered an open position on startup, subscribe its option token now.
        if ctx.sm.state == State.POSITION_OPEN and ctx.instrument_token:
            ctx.ws.add_token(ctx.instrument_token)
            logger.info(
                "Recovery: subscribed option token %d (%s) on WebSocket.",
                ctx.instrument_token, ctx.tradingsymbol,
            )

        # FALLBACK feed: PaperFeed REST poll.  Runs in parallel and fires the same
        # tick_handler.  The candle aggregator and state writer are idempotent, so
        # duplicate ticks from both sources are harmless — the most-recent LTP wins.
        # This ensures continuous data even if the WebSocket reconnects briefly.
        ctx.paper_feed.on_tick(tick_handler)
        ctx.paper_feed.start(fallback=True)   # 5s interval — WebSocket is primary
        logger.info(
            "LIVE feed: SENSEX WebSocket (token %d) as primary + "
            "PaperFeed REST as fallback (5s).", SENSEX_TOKEN
        )
    else:
        # PAPER mode: poll SENSEX LTP via REST every second (no WebSocket)
        ctx.paper_feed.on_tick(tick_handler)
        ctx.paper_feed.start()
        logger.info("PAPER mode — PaperFeed polling SENSEX LTP via REST.")

    classify_session_regime(ctx)

    # Main loop — runs until operator stops manually (Ctrl+C or Stop Bot button).
    # EOD square-off is logged as a warning but the bot keeps running.
    force_exit_time = parse_time_ist(settings.FORCE_EXIT_TIME)
    # If we're already past the force-exit time at startup, don't immediately square off —
    # the bot was started outside market hours.  Mark EOD done so the guard never fires.
    _eod_done = is_after_or_equal(now_ist().time(), force_exit_time)
    if _eod_done:
        logger.info(
            "Started after force-exit time (%s IST) — EOD guard disabled for this session.",
            settings.FORCE_EXIT_TIME,
        )
    _last_reconcile: float = 0.0
    _RECONCILE_INTERVAL = 30   # seconds between broker reconciliation checks
    _last_feed_warn: float = 0.0
    _FEED_WARN_INTERVAL = 60   # warn every 60s if SENSEX LTP is still 0 during market hours

    try:
        while True:
            time.sleep(5)

            if fly_runner is not None:
                try:
                    fly_runner.tick()
                except Exception:
                    logger.exception("Expiry fly tick failed (ignored; trading unaffected).")

            # ── Dead-feed detection: warn if no price received during market hours ──
            now_mono = time.monotonic()
            if (
                ctx.sensex_ltp == 0.0
                and is_after_or_equal(now_ist().time(), _MARKET_OPEN_TIME)
                and not _eod_done
                and now_mono - _last_feed_warn >= _FEED_WARN_INTERVAL
            ):
                _last_feed_warn = now_mono
                # Check whether the thread(s) are still alive
                ws_ok = ctx.ws is not None  # WS liveness tracked by KiteTicker internally
                pf_ok = ctx.paper_feed.is_alive() if ctx.paper_feed else False
                logger.error(
                    "No SENSEX price received since market open — "
                    "candles and signals are frozen. "
                    "websocket=%s paper_feed_alive=%s. "
                    "Check authentication and network.",
                    "active" if ws_ok else "none", pf_ok,
                )

            # ── Periodic reconciliation: detect external closes ────────────────
            now_mono = time.monotonic()
            if (
                ctx.sm.state == State.POSITION_OPEN
                and ctx.trade_id
                and ctx.tradingsymbol
                and settings.TRADING_MODE == "LIVE"
                and now_mono - _last_reconcile >= _RECONCILE_INTERVAL
            ):
                _last_reconcile = now_mono
                try:
                    from broker.position_repository import get_net_position_qty
                    actual_qty = get_net_position_qty(ctx.tradingsymbol)
                    if actual_qty is None:
                        # API failure — cannot determine if position is open or closed;
                        # do nothing and let the next reconcile cycle retry.
                        logger.warning(
                            "Reconciliation skipped — broker API unavailable for %s.",
                            ctx.tradingsymbol,
                        )
                    elif actual_qty == 0:
                        # Position closed externally (manual exit, SL hit at broker, etc.)
                        logger.warning(
                            "Position %s has qty=0 at broker — closed externally. "
                            "Reconciling DB and resetting state.",
                            ctx.tradingsymbol,
                        )
                        # Fetch fill price from broker orders
                        exit_price = ctx.entry_price  # fallback
                        try:
                            orders = ctx.broker._kite.orders()
                            sells = [
                                o for o in orders
                                if o.get("tradingsymbol") == ctx.tradingsymbol
                                and o.get("transaction_type") == "SELL"
                                and o.get("status") == "COMPLETE"
                            ]
                            if sells:
                                exit_price = float(sells[-1].get("average_price", exit_price))
                        except Exception:
                            pass
                        pnl = (exit_price - ctx.entry_price) * ctx.quantity
                        mark_trade_closed(ctx.trade_id, exit_price, now_ist().isoformat(), pnl)
                        notify("EXIT_FILLED", symbol=ctx.tradingsymbol,
                               exit_price=exit_price, pnl=pnl, reason="EXTERNAL_CLOSE")
                        log_event(logger, "EXTERNAL_CLOSE_DETECTED",
                                  symbol=ctx.tradingsymbol, exit_price=exit_price, pnl=pnl)
                        # Cancel any lingering stop order
                        if ctx.stop_order_id:
                            ctx.broker.cancel_order(ctx.stop_order_id)
                        # PAPER/SHADOW: the real broker has no position but the
                        # PaperBroker._positions dict still holds the entry qty.
                        # Decrement it now so the next entry for the same symbol
                        # doesn't accumulate a stale qty, which would cause
                        # PRE_SELL_QTY_MISMATCH on the next SL hit.
                        if settings.TRADING_MODE in ("PAPER", "SHADOW"):
                            _pb_positions = getattr(ctx.broker, "_positions", {})
                            _stale_qty = _pb_positions.get(ctx.tradingsymbol, 0)
                            if _stale_qty > 0:
                                _pb_positions[ctx.tradingsymbol] = max(0, _stale_qty - ctx.quantity)
                                logger.debug(
                                    "EXTERNAL_CLOSE: cleared paper broker position %s "
                                    "(%d → %d).",
                                    ctx.tradingsymbol, _stale_qty,
                                    _pb_positions[ctx.tradingsymbol],
                                )
                        # POSITION_OPEN -> CLOSED is not a valid direct transition;
                        # must pass through EXIT_PENDING first.
                        ctx.sm.transition(State.EXIT_PENDING, reason="external close detected")
                        ctx.sm.transition(State.CLOSED, reason="external close detected")
                        ctx.sm.transition(State.IDLE, reason="ready for next trade")
                        _close_trade_context(ctx)
                        _write_state(ctx)
                except Exception as exc:
                    logger.error("Reconciliation check failed: %s", exc)

            # ── EOD forced exit ────────────────────────────────────────────────
            if not _eod_done and is_after_or_equal(now_ist().time(), force_exit_time):
                _run_eod_exit(ctx)
                _eod_done = True   # only attempt once per session
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt — shutting down.")
    finally:
        if ctx.orderflow_recorder is not None:
            try:
                ctx.orderflow_recorder.close()
            except Exception as exc:
                logger.debug("Order-flow recorder close failed (non-critical): %s", exc)
        if ctx.ws:
            ctx.ws.stop()
        if ctx.paper_feed:
            ctx.paper_feed.stop()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
