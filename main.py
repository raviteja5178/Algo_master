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
from execution.smart_exit import SmartExitEngine
from strategies.ai_confirmation import AIConfirmationFilter
from strategies.regime_classifier import RegimeClassifier
from strategies.smart_entry import SmartEntryFilter
from execution.target_manager import DynamicTargetManager
from execution.trailing_stop import TrailingStopManager
from market.candle_aggregator import CandleAggregator
from market.candle_builder import Candle
from market.historical_data import SENSEX_TOKEN, fetch_historical_candles, fetch_previous_day_hl
from market.vwap import VWAPCalculator
from market.paper_feed import PaperFeed
from market.websocket_client import WebSocketClient
from notifications.notifier import notify
from persistence.trade_store import (
    fetch_active_trade,
    fetch_today_realised_pnl,
    has_action,
    init_db,
    mark_trade_closed,
    mark_trade_closed_with_reason,
    record_action,
    upsert_trade,
)
from risk.safety_manager import SafetyManager
from strategies.signal_engine import evaluate_signals
from market.indicators import atr_at, ema as calc_ema, swing_levels
from utils.latency import LatencyTracker
from utils.logging_config import configure_logging, log_event
from utils.time_utils import IST, is_after_or_equal, now_ist, parse_time_ist

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
        self.entry_atr: float | None = None    # ATR(14) at trade entry — for dynamic profit lock
        self.stop_order_id: str | None = None
        self.trailing: TrailingStopManager | None = None
        self.target: DynamicTargetManager | None = None
        self.strategy_type: str | None = None

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

        # Previous day High / Low — populated at startup from daily historical data
        self.prev_day_high: float | None = None
        self.prev_day_low:  float | None = None

        # WebSocket (LIVE/SHADOW) or paper feed (PAPER)
        self.ws = WebSocketClient() if settings.TRADING_MODE != "PAPER" else None
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
                daily_loss_limit_pts      = settings.DAILY_LOSS_LIMIT_PTS,
                enable_reversal_exit      = settings.ENABLE_REVERSAL_EXIT,
                enable_ema_collapse       = settings.ENABLE_EMA_COLLAPSE_EXIT,
                enable_profit_lock        = settings.ENABLE_PROFIT_LOCK_EXIT,
                enable_time_decay         = settings.ENABLE_TIME_DECAY_EXIT,
                enable_daily_loss_limit   = settings.ENABLE_DAILY_LOSS_LIMIT,
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

    def can_create_entry(self) -> bool:
        if is_after_or_equal(now_ist().time(), self._no_entry_time):
            return False
        # Block new entries if daily loss limit is hit
        if self.smart_exit is not None:
            daily_pnl = fetch_today_realised_pnl()
            if self.smart_exit.is_daily_loss_limit_hit(daily_pnl):
                logger.warning(
                    "Daily loss limit hit (realised=%.2f pts <= -%.2f) - "
                    "no new entries today.", daily_pnl, settings.DAILY_LOSS_LIMIT_PTS,
                )
                return False
        return self.sm.can_enter()


class _TradeStoreFacade:
    """Minimal facade so EODManager can call mark_trade_closed."""
    @staticmethod
    def mark_trade_closed(trade_id, exit_price, exit_time, pnl):
        mark_trade_closed(trade_id, exit_price, exit_time, pnl)


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
|  VWAP Retest:            {_yn(settings.ENABLE_VWAP_STRATEGY):<22} |
|  Prev Day H/L (PDHL):    {_yn(settings.ENABLE_PDHL_STRATEGY):<22} |
|  ATR Copilot:            {_yn(settings.ENABLE_ATR_COPILOT_STRATEGY):<22} |
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

def execute_entry(ctx: BotContext, signal_type: str, sensex_ltp: float,
                  signal_candle_ts=None, candle_completed_ts: str | None = None) -> None:
    if not ctx.can_create_entry():
        logger.info("Entry blocked: state=%s or past no-entry time.", ctx.sm.state)
        return

    action_id = f"{signal_type}_ENTRY_{now_ist().strftime('%Y-%m-%d_%H-%M')}"
    if has_action(action_id):
        logger.info("Entry action %s already recorded — skipping duplicate.", action_id)
        return

    option_type = "CE" if signal_type.startswith("CE") else "PE"

    # ── Latency tracker — one per trade entry attempt ─────────────────────────
    # trade_id is not yet assigned; use a provisional key with the signal type
    # and timestamp so the report is identifiable even if the entry fails.
    ctx.latency = LatencyTracker(
        trade_id=f"{signal_type}_{now_ist().strftime('%Y%m%d_%H%M%S')}"
    )
    # Back-fill CANDLE_COMPLETED using the timestamp recorded by the candle handler
    if candle_completed_ts:
        ctx.latency._checkpoints["CANDLE_COMPLETED"] = (candle_completed_ts, 0)
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
        _below_min = (
            settings.MIN_OPTION_ENTRY_PRICE > 0
            and _ltp is not None
            and _ltp > 0
            and _ltp < settings.MIN_OPTION_ENTRY_PRICE
        )
        if _below_min:
            _is_itm_fallback = _candidate["strike"] != _candidates[0]["strike"]
            log_event(
                logger, "ENTRY_BLOCKED_MIN_PREMIUM",
                symbol=_sym,
                ltp=_ltp,
                min_required=settings.MIN_OPTION_ENTRY_PRICE,
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

    ctx.tradingsymbol = instrument["tradingsymbol"]
    ctx.instrument_token = instrument["instrument_token"]

    if settings.TRADING_MODE != "PAPER":
        # Subscribe to option LTP on WebSocket
        ctx.ws.add_token(ctx.instrument_token)

    record_action(action_id, None, "ENTRY")
    notify("ENTRY_SENT", symbol=ctx.tradingsymbol, qty=ctx.quantity, signal=signal_type)

    if option_ltp_hint and ctx.latency:
        ctx.latency.set_price("option_ltp_at_signal", option_ltp_hint)

    if ctx.latency:
        ctx.latency.mark("BUY_REQUESTED")

    try:
        fill = ctx.broker.place_buy_order(
            ctx.tradingsymbol,
            ctx.quantity,
            ltp_hint=option_ltp_hint,
        )
    except Exception as exc:
        logger.error("Entry order placement raised an exception: %s", exc, exc_info=True)
        notify("ENTRY_REJECTED", symbol=ctx.tradingsymbol, reason=str(exc))
        ctx.sm.transition(State.IDLE, reason="broker exception on entry")
        return

    if fill["status"] != "COMPLETE" or fill["filled_qty"] == 0:
        logger.error("Entry fill failed: %s", fill)
        notify("ENTRY_REJECTED", symbol=ctx.tradingsymbol, reason=fill.get("status"))
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
    ctx.trade_id = f"TRADE_{signal_type}_{now_ist().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    ctx.strategy_type = signal_type
    if ctx.latency:
        ctx.latency.trade_id = ctx.trade_id   # backfill real trade_id now that we have it

    notify("ENTRY_FILLED", symbol=ctx.tradingsymbol, fill=ctx.entry_price, qty=ctx.quantity)

    # ── Compute risk parameters (ATR-adaptive or fixed) ────────────────────────
    _candles_5m   = ctx.agg_5m.get_completed()
    _option_type  = "CE" if signal_type.startswith("CE") else "PE"

    # Mode D: resolve nearest swing HIGH above and swing LOW below current price
    _swing_high: float | None = None
    _swing_low:  float | None = None
    if settings.USE_SWING_SL and len(_candles_5m) >= settings.SWING_SL_LENGTH + 2:
        _swing_high, _swing_low = swing_levels(
            _candles_5m,
            length=settings.SWING_SL_LENGTH,
            reference_price=sensex_ltp,
        )

    risk = compute_risk_params(
        _candles_5m,
        fixed_sl            = settings.INITIAL_SL_POINTS,
        fixed_target        = settings.INITIAL_TARGET_OFFSET_POINTS,
        fixed_trail         = settings.TRAIL_STEP_POINTS,
        min_sl_pts          = settings.MIN_SL_POINTS,
        min_target_pts      = settings.MIN_TARGET_POINTS,
        min_trail_pts       = settings.MIN_TRAIL_POINTS,
        entry_price         = ctx.entry_price,
        # Mode C: SENSEX spot ATR × multiplier
        use_spot_atr        = settings.USE_SPOT_ATR_RISK,
        spot_atr_period     = settings.SPOT_ATR_PERIOD,
        spot_sl_mult        = settings.SPOT_ATR_SL_MULT,
        target_rr           = settings.SPOT_ATR_TARGET_RR,
        trail_rr            = settings.SPOT_ATR_TRAIL_RR,
        # Mode D: swing high/low as SL (structure-based)
        use_swing_sl           = settings.USE_SWING_SL,
        option_type            = _option_type,
        sensex_ltp             = sensex_ltp,
        swing_high             = _swing_high,
        swing_low              = _swing_low,
        swing_sl_min_atr_mult  = settings.SWING_SL_MIN_ATR_MULT,
    )
    sl_pts     = risk.initial_sl_points
    be_pts     = risk.break_even_trigger_points
    trail_pts  = risk.trail_step_points
    target_pts = risk.initial_target_points
    ctx.entry_atr = risk.atr_value   # stored for dynamic profit lock

    log_event(
        logger, "RISK_PARAMS_APPLIED",
        sl_mode=risk.sl_mode,
        sl_pts=sl_pts, be_pts=be_pts,
        trail_pts=trail_pts, target_pts=target_pts,
        rr=round(target_pts / sl_pts, 2) if sl_pts > 0 else None,
        atr=risk.atr_value,
        swing_high=_swing_high, swing_low=_swing_low,
    )

    # ── MIN_RR gate: block entry if R:R is below the configured minimum ──
    if settings.MIN_RR > 0 and sl_pts > 0:
        actual_rr = target_pts / sl_pts
        if actual_rr < settings.MIN_RR:
            log_event(
                logger, "ENTRY_BLOCKED_MIN_RR",
                signal=signal_type,
                sl_pts=sl_pts,
                target_pts=target_pts,
                actual_rr=round(actual_rr, 2),
                required_rr=settings.MIN_RR,
            )
            ctx.sm.transition(State.IDLE, reason=f"R:R {actual_rr:.2f} below minimum {settings.MIN_RR}")
            return

    # ── SENSEX index-level risk levels (for chart marker display) ─────────────
    # Mode C/D: sl_pts = index_pts × delta (0.4) → invert to get SENSEX distance.
    # Fixed fallback: use option pts as-is (approximation).
    _ATM_DELTA = 0.4
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
        "atr_value": ctx.entry_atr,
        # SENSEX index-level prices for chart marker display
        "sensex_entry": _sx_entry,
        "sensex_sl":    _sx_sl,
        "sensex_t1":    _sx_t1,
        "sensex_t2":    _sx_t2,
    })
    record_action(action_id, ctx.trade_id, "ENTRY", fill["order_id"], "COMPLETE")

    # Signal already recorded atomically in evaluate_signals._gate() before
    # the order was placed — no need to record it again here.

    # Trailing and target managers
    ctx.trailing = TrailingStopManager(
        ctx.entry_price, sl_pts, be_pts, trail_pts,
    )
    ctx.target = DynamicTargetManager(
        ctx.entry_price, target_pts, trail_pts,
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
        "atr_value": ctx.entry_atr,
    })

    ctx.sm.transition(State.POSITION_OPEN, reason="fill confirmed, SL placed")
    logger.info(
        "Position open | %s | entry=%.2f | sl=%.2f | target_ref=%.2f",
        ctx.tradingsymbol, ctx.entry_price, ctx.trailing.current_stop, ctx.target.target_reference,
    )


# ── Option LTP handler (trailing logic) ───────────────────────────────────────

def on_option_ltp(ctx: BotContext, ltp: float) -> None:
    if ctx.sm.state != State.POSITION_OPEN or ctx.trailing is None:
        return

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

    # Trailing stop logic
    new_stop = ctx.trailing.update(ltp)
    if new_stop is not None:
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
        daily_pnl = fetch_today_realised_pnl()
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
    #   3. PAPER: ctx.sensex_ltp (best available proxy)
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
                logger.warning("SHADOW exit ltp_hint: REST fetch failed (%s) — using sensex_ltp.", _exc)
                _sell_ltp_hint = ctx.sensex_ltp if ctx.sensex_ltp > 0 else None
        else:
            _sell_ltp_hint = ctx.sensex_ltp if ctx.sensex_ltp > 0 else None

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
            )
            notify("EXIT_FILLED", symbol=ctx.tradingsymbol,
                   exit_price=exit_price, pnl=pnl, reason="SL_FILLED_AT_EXCHANGE")
            log_event(logger, "SL_FILLED_AT_EXCHANGE",
                      symbol=ctx.tradingsymbol, exit_price=exit_price,
                      pnl=pnl, original_reason=reason)
            ctx.smart_entry.on_trade_closed(pnl / max(ctx.quantity, 1))
            ctx.sm.transition(State.CLOSED, reason="SL filled at exchange")
            ctx.sm.transition(State.IDLE, reason="ready for next trade")
            _close_trade_context(ctx)
            return
        # Any other RuntimeError — genuine failure, halt as before
        logger.error("Exit order placement raised an exception: %s", exc, exc_info=True)
        notify("BOT_HALTED", reason=f"exit_order_exception: {exc}")
        ctx.sm.force_halt(f"exit order exception: {exc}")
        return
    except Exception as exc:
        logger.error("Exit order placement raised an exception: %s", exc, exc_info=True)
        notify("BOT_HALTED", reason=f"exit_order_exception: {exc}")
        ctx.sm.force_halt(f"exit order exception: {exc}")
        return

    # Validate fill — a TIMEOUT/REJECTED sell with qty=0 means the position may still be open
    if fill.get("status") != "COMPLETE" or fill.get("filled_qty", 0) == 0:
        logger.error(
            "Exit fill failed or zero quantity (status=%s, qty=%s) — halting bot. "
            "Manual intervention required for %s.",
            fill.get("status"), fill.get("filled_qty"), ctx.tradingsymbol,
        )
        notify("BOT_HALTED", reason=f"exit_fill_failed_{fill.get('status')}")
        ctx.sm.force_halt(f"exit fill failed: {fill.get('status')}")
        return

    exit_price = fill.get("average_price", 0.0)
    filled_qty = fill.get("filled_qty", 0)
    pnl = (exit_price - ctx.entry_price) * filled_qty

    # Determine smart-exit trigger (non-mechanical reasons)
    _SMART_EXITS = {
        "EMA_COLLAPSE", "REVERSAL_SIGNAL", "PROFIT_LOCK",
        "TIME_DECAY", "DAILY_LOSS_LIMIT",
    }
    _smart_trigger = reason if reason in _SMART_EXITS else None

    mark_trade_closed_with_reason(
        ctx.trade_id, exit_price, now_ist().isoformat(), pnl,
        exit_reason=reason or "MANUAL",
        smart_exit_trigger=_smart_trigger,
    )
    notify("EXIT_FILLED", symbol=ctx.tradingsymbol, exit_price=exit_price, pnl=pnl, reason=reason)

    # Notify smart entry filter so cooldown starts on a loss
    ctx.smart_entry.on_trade_closed(pnl / max(filled_qty, 1))

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

    ctx.trailing = TrailingStopManager(
        entry_price=active["entry_price"],
        initial_sl_points=settings.INITIAL_SL_POINTS,
        break_even_trigger_points=settings.BREAK_EVEN_TRIGGER_POINTS,
        trail_step_points=settings.TRAIL_STEP_POINTS,
    )
    ctx.trailing.current_stop = active["current_stop"] or ctx.trailing.current_stop
    ctx.trailing.highest_ltp = active["highest_ltp"] or ctx.entry_price

    ctx.target = DynamicTargetManager(
        ctx.entry_price,
        settings.INITIAL_TARGET_OFFSET_POINTS,
        settings.TARGET_TRAIL_STEP_POINTS,
    )
    ctx.target.target_reference = active["target_reference"] or ctx.target.target_reference

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
        candles_5m  = ctx.agg_5m.get_completed()
        candles_15m = ctx.agg_15m.get_completed()

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


_MARKET_OPEN_TIME = parse_time_ist("09:15")


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
        if token == SENSEX_TOKEN:
            ctx.sensex_ltp = ltp
            # Feed into candle aggregators
            ctx.agg_5m.on_tick(ltp)
            ctx.agg_15m.on_tick(ltp)
            # Feed VWAP (tick proxy — each tick = 1 volume unit)
            if settings.ENABLE_VWAP_STRATEGY:
                ctx.vwap.on_tick(ltp)
            # In PAPER mode the option price IS the SENSEX spot price,
            # so trail/SL checks run against the SENSEX LTP directly.
            if settings.TRADING_MODE == "PAPER" and ctx.sm.state == State.POSITION_OPEN:
                on_option_ltp(ctx, ltp)
            # Always write LTP immediately so the UI shows every price update.
            # Full state (candles + EMA) only recalculated every N ticks.
            _tick_counter += 1
            if _tick_counter % _FULL_WRITE_INTERVAL == 0:
                _write_state(ctx)
            else:
                _write_ltp(ctx)
        elif ctx.instrument_token and token == ctx.instrument_token:
            # LIVE/SHADOW: option token tick
            on_option_ltp(ctx, ltp)
    return handler


def _make_candle_handler_5m(ctx: BotContext):
    def handler(candle: Candle) -> None:
        # Always write state on candle close so the chart updates immediately
        _write_state(ctx)

        # Latency: record when this candle closed (start of signal evaluation)
        # A fresh tracker is created in execute_entry once a signal is confirmed.
        # We only need the CANDLE_COMPLETED timestamp; store it on ctx for pickup.
        ctx._last_candle_completed_ts = now_ist().isoformat()

        candles_5m  = ctx.agg_5m.get_completed()
        candles_15m = ctx.agg_15m.get_completed()

        # ── VWAP: update from completed candle (most accurate — uses OHLCV) ───
        if settings.ENABLE_VWAP_STRATEGY:
            ctx.vwap.on_candle(candle)

        # ── Smart Entry: tick down cooldown on every candle ────────────────────
        ctx.smart_entry.on_candle()

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

        # ── Smart Exit candle-level checks (EMA collapse) ──────────────────────
        if ctx.smart_exit is not None and ctx.sm.state == State.POSITION_OPEN:
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
        if ctx.sm.is_entry_blocked():
            return

        # Derive live EMA9/EMA21/ATR for AI context
        _ema9_val  = candles_5m[-1].ema9  if candles_5m and hasattr(candles_5m[-1], 'ema9')  else None
        _ema21_val = candles_5m[-1].ema21 if candles_5m and hasattr(candles_5m[-1], 'ema21') else None
        _atr_val   = atr_at(candles_5m, period=14) if len(candles_5m) >= 14 else None

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
            prev_day_high=ctx.prev_day_high if settings.ENABLE_PDHL_STRATEGY else None,
            prev_day_low=ctx.prev_day_low  if settings.ENABLE_PDHL_STRATEGY else None,
            ema9=_ema9_val,
            ema21=_ema21_val,
            atr=_atr_val,
            regime=ctx.ai_regime,
            orb_fired_today=ctx.orb_fired_today,
            orb_direction_today=ctx.orb_direction_today,
            option_ltp=_ai_option_ltp,
            option_day_low=_ai_option_day_low,
            option_day_high=_ai_option_day_high,
        )

        # ── AI exit suggestion (per-candle, only when position open) ──────────
        if (
            settings.ENABLE_AI_EXIT
            and ctx.ai_confirmation is not None
            and ctx.sm.state == State.POSITION_OPEN
            and signal is None   # don't double-exit on reversal candle
            and ctx.strategy_type
        ):
            _opt_ltp = ctx.sensex_ltp if ctx.sensex_ltp > 0 else candle.close
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
        ):
            daily_pnl = fetch_today_realised_pnl()
            smart_reason = ctx.smart_exit.check_on_tick(
                strategy_type          = ctx.strategy_type,
                entry_price            = ctx.entry_price,
                option_ltp             = ctx.sensex_ltp if ctx.sensex_ltp > 0 else candle.close,
                qty                    = ctx.quantity,
                daily_realised_pnl_pts = daily_pnl,
                pending_signal         = signal,
                entry_atr              = ctx.entry_atr,
            )
            if smart_reason:
                execute_exit(ctx, reason=smart_reason)
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


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    configure_logging()
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
    if settings.ENABLE_PDHL_STRATEGY:
        try:
            ctx.prev_day_high, ctx.prev_day_low = fetch_previous_day_hl(SENSEX_TOKEN)
            logger.info(
                "PDHL levels loaded — PDH=%.2f  PDL=%.2f",
                ctx.prev_day_high or 0, ctx.prev_day_low or 0,
            )
        except Exception as exc:
            logger.warning("PDHL fetch failed at startup (%s) — CE_PDHL/PE_PDHL disabled today.", exc)

    # Wire 5m candle handler (signal evaluation fires on every completed 5m candle)
    ctx.agg_5m.subscribe(_make_candle_handler_5m(ctx))

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

    # ── Regime classification — once per day, just before the main loop ───────
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
                if ctx.sm.state == State.POSITION_OPEN and ctx.trade_id:
                    logger.warning(
                        "Past force-exit time (%s IST) — squaring off open position.",
                        settings.FORCE_EXIT_TIME,
                    )
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
                        ctx.trade_id = None
                        ctx.tradingsymbol = None
                        ctx.trailing = None
                        ctx.target = None
                        ctx.stop_order_id = None
                    else:
                        logger.error(
                            "EOD exit FAILED — position may still be open at broker. "
                            "Halting bot to prevent unmanaged exposure."
                        )
                        ctx.sm.force_halt("EOD exit failed")
                        notify("BOT_HALTED", reason="eod_exit_failed")
                _eod_done = True   # only attempt once per session
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt — shutting down.")
    finally:
        if ctx.ws:
            ctx.ws.stop()
        if ctx.paper_feed:
            ctx.paper_feed.stop()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
