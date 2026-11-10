"""
Signal engine — evaluates CE and PE strategies on completed candles,
enforces de-duplication, and emits signals to callers.

Two evaluation phases run in order:

  Phase 1 — EMA strategy (ce_strategy / pe_strategy)
      15m EMA9/21 trend + 5m EMA9 crossover / EMA21 pullback + RSI.
      Active EMA_SCAN_START → EMA_NO_NEW_ENTRY_AFTER (default 09:20–15:00).

  Phase 2 — Momentum strategy (ce_momentum / pe_momentum)
      3-rule acceleration filter: strong candle body + EMA alignment + 5mins trend.
      Only fires in the afternoon breakout window (default 13:30–14:30).
      Enabled by ENABLE_MOMENTUM_PHASE=true in .env.
      Skipped if a standard-phase signal already fired for the same candle.

CE is always checked before PE within each phase.

Smart Entry Filter (optional):
  A SmartEntryFilter instance can be passed to evaluate_signals().  When
  supplied, every raw signal is run through the quality gate before being
  returned to the caller.  A blocked signal is logged and None is returned,
  leaving the candle available for the next strategy phase.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from datetime import datetime, time, timedelta
from utils.time_utils import today_ist
from strategies.trend_gate import daily_trend_ok, strategy_key, trend_15m_ok
from typing import Literal

from config import settings
from market.candle_builder import Candle
from market.historical_data import PivotLevels
from market.indicators import atr_at
from persistence.trade_store import claim_signal_atomic, has_processed_signal, record_processed_signal
from strategies.ce_strategy import is_ce_signal
from strategies.pe_strategy import is_pe_signal
from strategies.session_qualifier import SessionQualifier
from utils.logging_config import log_event

logger = logging.getLogger(__name__)

# ── ORB Session Qualifier (singleton per process) ─────────────────────────────
# Resets automatically on each new trading day inside SessionQualifier.update().
_session_qualifier = SessionQualifier(
    unblock_time=getattr(settings, "ORB_QUALIFIER_UNBLOCK_TIME", None) or "13:30"
)

# ── Multi-index state keying ──────────────────────────────────────────────────
# Several indexes (SENSEX/NIFTY/FINNIFTY/...) run in one process and share this
# module.  Every counter / cooldown / pending setup below is keyed by underlying
# so one index's trades never consume another index's caps.  underlying=None
# (single-index callers, tests) maps to the legacy un-prefixed key.
def _ukey(underlying: str | None) -> str:
    return (underlying or "").upper().strip()


def _dk(day: str, underlying: str | None = None) -> str:
    """Day key, prefixed with the underlying when one is given."""
    u = _ukey(underlying)
    return f"{u}:{day}" if u else day


# ── EMA-specific cooldown counter ─────────────────────────────────────────────
# Independent of the global SmartEntry cooldown — only applies to CE/PE signals.
# Started by note_ema_trade() when an EMA entry FILLS; ticked down on every
# completed 5m candle by tick_ema_cooldown(). Reset on date change.
_ema_cooldown_left: dict[str, int] = {}
_ema_cooldown_date: dict[str, str] = {}
_ema_trades_today: dict[str, int] = {}
_ema_consec_losses: dict[str, int] = {}


def _reset_ema_cooldown_if_new_day(day: str, underlying: str | None = None) -> None:
    u = _ukey(underlying)
    if _ema_cooldown_date.get(u, "") != day:
        _ema_cooldown_date[u] = day
        _ema_cooldown_left[u] = 0
        _ema_trades_today[u] = 0
        _ema_consec_losses[u] = 0


def note_ema_trade(day: str, underlying: str | None = None) -> None:
    """Start the EMA cooldown and count the trade after an EMA CE/PE entry has filled."""
    u = _ukey(underlying)
    _reset_ema_cooldown_if_new_day(day, underlying)
    _ema_cooldown_left[u] = max(0, settings.EMA_COOLDOWN_CANDLES)
    _ema_trades_today[u] = _ema_trades_today.get(u, 0) + 1


def note_ema_result(day: str, pnl: float, underlying: str | None = None) -> None:
    """Record a closed EMA trade's P&L for the consecutive-loss lockout."""
    u = _ukey(underlying)
    _reset_ema_cooldown_if_new_day(day, underlying)
    _ema_consec_losses[u] = _ema_consec_losses.get(u, 0) + 1 if pnl < 0 else 0


def ema_day_block_reason(underlying: str | None = None) -> str | None:
    """Return why EMA is locked for the rest of the day, or None."""
    u = _ukey(underlying)
    trades = _ema_trades_today.get(u, 0)
    losses = _ema_consec_losses.get(u, 0)
    if settings.EMA_MAX_TRADES_PER_DAY > 0 and trades >= settings.EMA_MAX_TRADES_PER_DAY:
        return f"max EMA trades/day reached ({trades})"
    if settings.EMA_MAX_CONSEC_LOSSES > 0 and losses >= settings.EMA_MAX_CONSEC_LOSSES:
        return f"{losses} consecutive EMA losses"
    return None


def tick_ema_cooldown(underlying: str | None = None) -> None:
    """Count the EMA cooldown down by one candle (call on every closed 5m candle)."""
    u = _ukey(underlying)
    if _ema_cooldown_left.get(u, 0) > 0:
        _ema_cooldown_left[u] -= 1

SignalType = Literal["CE", "PE", "CE_ORB", "PE_ORB", "CE_OB", "PE_OB", "CE_MOM", "PE_MOM", "CE_TRB", "PE_TRB", "CE_VWAP", "PE_VWAP", "CE_PDHL", "PE_PDHL", "CE_NATR", "PE_NATR", "CE_ATR", "PE_ATR", "CE_PIVOT", "PE_PIVOT", None]

# FIX (Flaw 15): protect last_pivot_setup with a lock.
# The setup is written by evaluate_signals (candle-close thread) and read by
# execute_entry (same thread under _tick_lock), but consume_pivot_setup() makes
# the read-and-clear atomic so there is no window where a second evaluation can
# overwrite the setup between the read and the entry construction.
_pivot_setup_lock = threading.Lock()
_pivot_setups: dict[str, object] = {}   # internal — keyed by underlying; use consume_pivot_setup()


def consume_pivot_setup(underlying: str | None = None):
    """Atomically read and clear the pending pivot setup for *underlying*.

    Returns the PivotSetup that triggered the most recent CE_PIVOT/PE_PIVOT
    signal, then resets the stored value to None.  Thread-safe: a concurrent
    evaluate_signals call that writes a new setup will not race with this read
    because both operations hold _pivot_setup_lock.
    """
    with _pivot_setup_lock:
        return _pivot_setups.pop(_ukey(underlying), None)


def peek_pivot_setup(underlying: str | None = None):
    """Read the pending pivot setup WITHOUT clearing it (pre-order risk checks)."""
    with _pivot_setup_lock:
        return _pivot_setups.get(_ukey(underlying))


def publish_pivot_setup(setup, underlying: str | None = None) -> None:
    """Store a pivot setup built outside evaluate_signals (Pine engine) so that
    execute_entry's consume_pivot_setup() picks it up."""
    with _pivot_setup_lock:
        _pivot_setups[_ukey(underlying)] = setup


def pivot_day_cap_reason(day: str, underlying: str | None = None) -> str | None:
    """Why PIVOT_MAX_TRADES_PER_DAY blocks a new pivot entry today, or None."""
    _seed_pivot_count(day, underlying)
    count = _pivot_trades_today.get(_dk(day, underlying), 0)
    if count >= settings.PIVOT_MAX_TRADES_PER_DAY:
        return f"pivot daily cap reached ({count}/{settings.PIVOT_MAX_TRADES_PER_DAY})"
    return None


# FIX (Flaw 17): _pivot_trades_today is seeded from the DB on first access
# so a bot restart mid-day does not reset the counter to 0.
# Keys are _dk(day, underlying) — each index has its own daily cap.
_pivot_trades_today: dict[str, int] = {}
_pivot_counter_seeded: set[str] = set()  # day keys whose DB count has been loaded


def _seed_pivot_count(day: str, underlying: str | None = None) -> None:
    """Load today's filled pivot trade count from the DB (once per day per index)."""
    k = _dk(day, underlying)
    if k in _pivot_counter_seeded:
        return
    try:
        from persistence.trade_store import fetch_today_pivot_trade_count
        db_count = fetch_today_pivot_trade_count(day, underlying)
        if db_count > _pivot_trades_today.get(k, 0):
            _pivot_trades_today[k] = db_count
    except Exception as exc:
        logger.warning("Could not seed pivot trade counter from DB: %s", exc)
    _pivot_counter_seeded.add(k)


def note_pivot_trade(day: str, underlying: str | None = None) -> None:
    """Count a filled Pivot trade toward PIVOT_MAX_TRADES_PER_DAY."""
    k = _dk(day, underlying)
    _pivot_trades_today[k] = _pivot_trades_today.get(k, 0) + 1


# Acceptance (Mode C) signals claimed per (day-key, side) — PIVOT_ACCEPT_MAX_PER_SIDE.
# In-memory only (a restart clears it — fails open, like the momentum cooldown).
_pivot_accept_count: dict[tuple[str, str], int] = {}


def _pivot_accept_blocked_sides(day: str, underlying: str | None = None) -> frozenset[str]:
    """Sides whose acceptance signal cap is already used up today."""
    cap = settings.PIVOT_ACCEPT_MAX_PER_SIDE
    if cap <= 0:
        return frozenset()
    k = _dk(day, underlying)
    return frozenset(
        side for side in ("CE", "PE") if _pivot_accept_count.get((k, side), 0) >= cap
    )


# ── Momentum guards: per-day trade cap + same-direction re-entry cooldown ─────
# Trade count is seeded from the DB once per day (restart-safe).  The re-entry
# cooldown is in-memory only (a restart clears it — fails open).
_mom_trades_today: dict[str, int] = {}
_mom_counter_seeded: set[str] = set()
_mom_cooldown_left: dict[str, int] = {}
_mom_cooldown_side: dict[str, str | None] = {}


def _seed_mom_count(day: str, underlying: str | None = None) -> None:
    k = _dk(day, underlying)
    if k in _mom_counter_seeded:
        return
    try:
        from persistence.trade_store import fetch_today_mom_trade_count
        db_count = fetch_today_mom_trade_count(day, underlying)
        if db_count > _mom_trades_today.get(k, 0):
            _mom_trades_today[k] = db_count
    except Exception as exc:
        logger.warning("Could not seed MOM trade counter from DB: %s", exc)
    _mom_counter_seeded.add(k)


def note_mom_trade(day: str, underlying: str | None = None) -> None:
    """Count a filled CE_MOM / PE_MOM trade toward MOMENTUM_MAX_TRADES_PER_DAY."""
    k = _dk(day, underlying)
    _mom_trades_today[k] = _mom_trades_today.get(k, 0) + 1


def note_mom_exit(side: str, underlying: str | None = None) -> None:
    """Start the same-direction re-entry cooldown after a MOM trade closes."""
    u = _ukey(underlying)
    _mom_cooldown_left[u] = max(0, settings.MOMENTUM_REENTRY_COOLDOWN_CANDLES)
    _mom_cooldown_side[u] = side


def tick_mom_cooldown(underlying: str | None = None) -> None:
    """Count the MOM re-entry cooldown down by one candle (call per closed 5m candle)."""
    u = _ukey(underlying)
    if _mom_cooldown_left.get(u, 0) > 0:
        _mom_cooldown_left[u] -= 1


def mom_block_reason(side: str, day: str, underlying: str | None = None) -> str | None:
    """Return why a MOM signal on *side* must be skipped, or None."""
    _seed_mom_count(day, underlying)
    u = _ukey(underlying)
    k = _dk(day, underlying)
    cap = settings.MOMENTUM_MAX_TRADES_PER_DAY
    if cap > 0 and _mom_trades_today.get(k, 0) >= cap:
        return f"max MOM trades/day reached ({_mom_trades_today.get(k, 0)})"
    left = _mom_cooldown_left.get(u, 0)
    if left > 0 and _mom_cooldown_side.get(u) == side:
        return f"same-direction re-entry cooldown ({left} candles left)"
    return None


# ── Global per-side daily trade cap (applies to ALL strategies) ───────────────
# Counts filled trades per direction (CE / PE) regardless of strategy, per index.
# Seeded from DB once per day on first access so a restart mid-day doesn't
# reset the counter to 0.
_side_trades_today: dict[str, dict[str, int]] = {}   # {day-key: {"CE": n, "PE": n}}
_side_counter_seeded: set[str] = set()


def _seed_side_count(day: str, underlying: str | None = None) -> None:
    """Load today's per-side filled trade counts from the DB (once per day per index)."""
    k = _dk(day, underlying)
    if k in _side_counter_seeded:
        return
    try:
        from persistence.trade_store import fetch_today_side_trade_count
        for _s in ("CE", "PE"):
            db_count = fetch_today_side_trade_count(_s, day, underlying)
            _side_trades_today.setdefault(k, {})
            if db_count > _side_trades_today[k].get(_s, 0):
                _side_trades_today[k][_s] = db_count
    except Exception as exc:
        logger.warning("Could not seed side trade counter from DB: %s", exc)
    _side_counter_seeded.add(k)


def note_side_trade(side: str, day: str, underlying: str | None = None) -> None:
    """Increment the per-side daily counter after a trade entry fills.

    *side* must be 'CE' or 'PE'.  Call this once per filled trade from
    main.py's execute_entry regardless of which strategy triggered the fill.
    """
    k = _dk(day, underlying)
    _side_trades_today.setdefault(k, {})
    _side_trades_today[k][side] = _side_trades_today[k].get(side, 0) + 1


def side_block_reason(side: str, day: str, underlying: str | None = None) -> str | None:
    """Return why a signal on *side* must be blocked by the global cap, or None."""
    _seed_side_count(day, underlying)
    cap = settings.MAX_TRADES_PER_SIDE
    if cap <= 0:
        return None
    count = _side_trades_today.get(_dk(day, underlying), {}).get(side, 0)
    if count >= cap:
        return f"global {side} cap reached ({count}/{cap} trades today)"
    return None


def _signal_id(strategy: str, candle_ts: datetime, underlying: str | None = None) -> str:
    """
    Generate a per-candle deduplication key.

    Using date+HH:MM (not just date) means:
      - The same candle never triggers two fills (idempotency preserved).
      - A fresh setup on a *different* candle later in the day CAN trade,
        because it gets a different key.
    One strategy can therefore trade more than once per day, but never
    more than once per unique 5-minute candle close.
    """
    base = f"{strategy}_SIGNAL_{candle_ts.strftime('%Y-%m-%d_%H:%M')}"
    # Multi-index: every index closes the same 5m candle, so the key must be
    # per-underlying or the first index to claim it blocks all the others.
    return f"{underlying}_{base}" if underlying else base


def _parse_time(hhmm: str) -> time:
    """Parse 'HH:MM' string into a datetime.time object."""
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def _is_in_lull_window(t: time, lull_windows: str) -> bool:
    """Check if time `t` falls within any comma-separated 'HH:MM-HH:MM' intervals."""
    if not lull_windows:
        return False
    for window in lull_windows.split(","):
        window = window.strip()
        if not window or "-" not in window:
            continue
        try:
            start_s, end_s = window.split("-")
            start_t = _parse_time(start_s.strip())
            end_t = _parse_time(end_s.strip())
            if start_t <= t <= end_t:
                return True
        except (ValueError, IndexError):
            continue
    return False


def evaluate_signals(
    candles_5m: Sequence[Candle],
    candles_15m: Sequence[Candle],
    candles_15m_orb: Sequence[Candle] | None = None,
    smart_entry=None,          # SmartEntryFilter | None  (avoid circular import)
    ai_confirmation=None,      # AIConfirmationFilter | None  (avoid circular import)
    vwap: float | None = None,
    prev_day_high: float | None = None,
    prev_day_low:  float | None = None,
    pivot_levels: "PivotLevels | None" = None,
    ema9: float | None = None,
    ema21: float | None = None,
    atr: float | None = None,
    regime: str = "UNKNOWN",
    *,
    intraday_regime: str | None = None,   # market_regime.classify_intraday().regime
    orb_fired_today: bool = False,
    orb_direction_today: str | None = None,
    # Option premium context — forwarded to AI confirmation so the LLM can
    # penalise entries where the option has already extended significantly.
    # option_ltp      : current option LTP at signal time
    # option_day_low  : first-seen LTP for this option today (proxy for day low)
    # option_day_high : highest LTP seen today for this option
    option_ltp: float | None = None,
    option_day_low: float | None = None,
    option_day_high: float | None = None,
    # Higher-timeframe trend from main ("UP" / "DOWN" / "UNKNOWN" / None)
    daily_trend: str | None = None,
    underlying: str | None = None,
) -> SignalType:
    """
    Evaluate CE and PE rules on the latest completed candles.

    Returns the signal string or None.
    Only one signal is emitted per completed candle (de-duplication).
    Phase 1 (standard) is evaluated first; Phase 2 (momentum) only runs if
    Phase 1 produced no signal for this candle and momentum is enabled.

    smart_entry : optional SmartEntryFilter instance.  When provided, every
    candidate signal is passed through the quality gate before being returned.
    A blocked signal is discarded (None) so the candle can still generate a
    signal from a later strategy phase.
    """
    if not candles_5m or not candles_15m:
        return None

    latest_5m_ts = candles_5m[-1].timestamp

    # ── Today-only guard ───────────────────────────────────────────────────────
    # The candle aggregator is seeded with historical data from previous days.
    # Never evaluate signals on a candle whose date is not today — that would
    # mean firing on yesterday's EMA state rather than the live session.
    if latest_5m_ts.date() != today_ist():
        return None

    # ── ORB Session Qualifier update ───────────────────────────────────────────
    # Feed the qualifier BEFORE any signal evaluation so it can lock the verdict
    # on the 10:00 candle in the same evaluation cycle that triggers the block.
    if settings.ORB_SESSION_QUALIFIER:
        _session_qualifier.update(
            candles_5m,
            orb_fired=orb_fired_today,
            orb_direction=orb_direction_today,
        )

    # ── Monday filter (ORB + MOMENTUM only) ────────────────────────────────────
    # Backtest over 44 trading days shows 0% win rate for ORB and Momentum on
    # Mondays (market re-gaps, fake breakouts, low follow-through).
    # EMA, OB, TRB, VWAP, PDHL are unaffected and trade normally on Mondays.
    _is_monday = latest_5m_ts.weekday() == 0   # 0 = Monday
    _skip_on_monday = settings.ORB_MOMENTUM_SKIP_MONDAY and _is_monday
    if _skip_on_monday:
        logger.debug("Monday filter active — ORB and MOMENTUM signals suppressed today.")

    # Candle-level "already attempted" guard.
    # Once ANY strategy fires a raw signal on this candle (even if Smart Entry
    # blocks it), we mark the candle as attempted and stop evaluating further
    # strategies on the same candle.  This prevents PE_ORB being blocked by
    # body filter and then PE on the same candle slipping through with a
    # slightly different body measurement.
    _candle_attempted = False

    # Inline helper: apply smart-entry gate if provided, then atomically
    # claim the signal in the DB so no second process can take it.
    # INSERT OR IGNORE means the first writer wins; any concurrent call
    # that races to the same signal_id will get 0 rows inserted and
    # has_processed_signal() will return True, blocking the duplicate.
    def _gate(sig: str) -> SignalType:
        nonlocal _candle_attempted
        sig_id = _signal_id(sig, latest_5m_ts, underlying)
        # Fast-path dedup: already taken (by a prior fill or a racing process)
        if has_processed_signal(sig_id):
            return None
        # Mark that this candle has been attempted regardless of Smart Entry outcome.
        # Subsequent strategies on the same candle are blocked even if this one fails.
        _candle_attempted = True
        # ── Global per-side daily cap ──────────────────────────────────────────
        # Derive side from the signal name prefix ("CE" or "PE").
        _sig_side = "CE" if sig.startswith("CE") else "PE"
        _gate_day = str(latest_5m_ts.date())
        if (_side_blk := side_block_reason(_sig_side, _gate_day, underlying)):
            log_event(logger, "GLOBAL_SIDE_CAP_BLOCKED",
                      signal=sig, side=_sig_side, reason=_side_blk)
            return None
        # ── Higher-timeframe trend gate (trend-following strategies only) ──────
        _ema_5m_only = settings.EMA_IGNORE_15M and sig in ("CE", "PE")
        if (settings.TREND_GATE_15M or settings.TREND_GATE_DAILY) \
                and strategy_key(sig) in settings.TREND_GATE_STRATEGIES:
            _why = None
            if settings.TREND_GATE_15M and not _ema_5m_only \
                    and not trend_15m_ok(_sig_side, candles_15m):
                _why = "against 15m trend (close/EMA21 slope)"
            elif settings.TREND_GATE_DAILY and not daily_trend_ok(_sig_side, daily_trend):
                _why = f"against daily trend ({daily_trend})"
            if _why:
                log_event(logger, "TREND_GATE_BLOCKED", signal=sig, side=_sig_side,
                          reason=_why, daily_trend=daily_trend)
                return None
        # Rule-based quality gate.
        # EMA CE/PE with EMA_SKIP_SMART_FILTERS: skip the candle filters (the
        # rule-set has its own 15m trend + RSI) but keep the post-loss cooldown.
        if smart_entry is not None:
            if sig in ("CE", "PE") and settings.EMA_SKIP_SMART_FILTERS:
                if smart_entry.cooldown_active:
                    log_event(logger, "SMART_ENTRY_BLOCKED_COOLDOWN",
                              direction=sig, candles_remaining=smart_entry.cooldown_remaining)
                    return None
            elif not smart_entry.allow(
                sig, candles_5m, candles_15m=None if _ema_5m_only else candles_15m
            ):
                return None
        # AI confirmation gate (optional — fails safely to ALLOW)
        if ai_confirmation is not None:
            verdict = ai_confirmation.confirm(
                signal=sig,
                candles_5m=candles_5m,
                ema9=ema9,
                ema21=ema21,
                atr=atr,
                regime=regime,
                vwap=vwap,
                option_ltp=option_ltp,
                option_day_low=option_day_low,
                option_day_high=option_day_high,
            )
            if not verdict.allowed:
                log_event(logger, "AI_CONFIRMATION_BLOCKED",
                          signal=sig, score=verdict.score, reason=verdict.reason)
                return None
        # Atomically claim this signal — INSERT OR IGNORE returns rowcount=1 only
        # for the first writer.  A concurrent bot process that races here will get
        # rowcount=0 and the signal will be silently dropped, preventing a duplicate
        # order even if two processes receive the same candle close simultaneously.
        if not claim_signal_atomic(sig_id, sig, latest_5m_ts.isoformat()):
            log_event(logger, "SIGNAL_CLAIM_LOST_RACE", signal=sig, sig_id=sig_id)
            return None
        return sig  # type: ignore[return-value]

    def _candle_already_attempted() -> bool:
        """True if any strategy already fired (and was blocked or taken) on this candle."""
        return _candle_attempted

    # ── Session qualifier gate (non-momentum strategies) ───────────────────────
    # When ORB_SESSION_QUALIFIER is on and the ORB was not sustained at 10:00,
    # all non-momentum strategies are blocked between 10:00 and MOM window start.
    # ORB itself is always evaluated regardless (it has its own entry-window guard).
    # The Momentum phase is always exempt — it runs in its own window below.
    _sq_blocked = (
        settings.ORB_SESSION_QUALIFIER
        and _session_qualifier.is_blocked(latest_5m_ts)
    )

    # ── Order Block (OB) strategy ──────────────────────────────────────────────
    if settings.ENABLE_OB_STRATEGY and not _sq_blocked and not _candle_already_attempted():
        from strategies.ob_strategy import is_ob_ce_signal, is_ob_pe_signal

        _ob_kwargs = dict(
            swing_length=settings.OB_SWING_LENGTH,
            max_atr_mult=settings.OB_MAX_ATR_MULT,
            atr_period=settings.OB_ATR_PERIOD,
            max_blocks=settings.OB_MAX_BLOCKS,
            invalidation=settings.OB_INVALIDATION,
            approach_buffer_atr_mult=settings.OB_APPROACH_BUFFER_ATR_MULT,
        )

        if is_ob_ce_signal(candles_5m, **_ob_kwargs):
            log_event(logger, "CE_OB_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close)
            if (sig := _gate("CE_OB")) is not None:
                return sig

        if not _candle_already_attempted() and is_ob_pe_signal(candles_5m, **_ob_kwargs):
            log_event(logger, "PE_OB_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close)
            if (sig := _gate("PE_OB")) is not None:
                return sig

    # ── Opening Range Breakout (ORB) strategy ──────────────────────────────────
    # ORB is only valid up to ORB_ACTIVE_UNTIL (default 11:00).
    # After that time EMA takes over as the sole entry strategy.
    # Priority: ORB fires first — if it passes, EMA is skipped for that candle
    # (enforced by _candle_already_attempted).
    _orb_cutoff_ok = True
    if settings.ORB_ACTIVE_UNTIL:
        try:
            _cutoff = _parse_time(settings.ORB_ACTIVE_UNTIL)
            _orb_cutoff_ok = latest_5m_ts.time() <= _cutoff
        except (ValueError, AttributeError):
            pass   # bad config — fail open (allow ORB)

    if settings.ENABLE_ORB_STRATEGY and _orb_cutoff_ok and not _skip_on_monday and not _candle_already_attempted():
        if settings.ORB_NO_THURSDAY and latest_5m_ts.weekday() == 3:
            log_event(logger, "ORB_BLOCKED_THURSDAY", candle=latest_5m_ts)
        else:
            from strategies.orb_strategy import is_orb_ce_signal, is_orb_pe_signal

            _orb_15m = candles_15m_orb if candles_15m_orb is not None else candles_15m
            _orb_kwargs = dict(
                min_body_ratio=settings.ORB_MIN_BODY_RATIO,
                buffer_atr_mult=settings.ORB_BUFFER_ATR_MULT,
                require_15m_trend=settings.ORB_REQUIRE_15M_TREND,
            )

            if is_orb_ce_signal(candles_5m, _orb_15m, **_orb_kwargs):
                log_event(logger, "CE_ORB_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close)
                if (sig := _gate("CE_ORB")) is not None:
                    return sig

            if not _candle_already_attempted() and is_orb_pe_signal(candles_5m, _orb_15m, **_orb_kwargs):
                log_event(logger, "PE_ORB_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close)
                if (sig := _gate("PE_ORB")) is not None:
                    return sig

    # ── Pivot Sustain strategy ─────────────────────────────────────────────────
    # Own risk engine — deliberately bypasses SmartEntry (the sustain + room
    # filters are its quality gate; validated in _pivot_research.py).
    # FIX (Flaw 6): pivot is evaluated independently of _candle_already_attempted()
    # because it has its own DB-backed dedup (has_processed_signal).  Sharing the
    # candle guard with EMA/VWAP/ORB would silently skip valid pivot setups whenever
    # another strategy fired first on the same candle.  Pivot DOES set
    # _candle_attempted=True after firing so it blocks other strategies.
    # PIVOT_PINE_MODE replaces this whole block: main.py drives the Pine
    # reversal engine (strategies/pivot_reversal.py) from candle closes + ticks.
    if (settings.ENABLE_PIVOT_STRATEGY and not settings.PIVOT_PINE_MODE
            and pivot_levels is not None):
        from strategies.pivot_strategy import find_pivot_setup
        _day = str(latest_5m_ts.date())
        # FIX (Flaw 17): seed counter from DB on first candle of the day so a
        # mid-day restart does not reset the max-trades guard to 0.
        _seed_pivot_count(_day, underlying)
        if _pivot_trades_today.get(_dk(_day, underlying), 0) < settings.PIVOT_MAX_TRADES_PER_DAY:
            # ── Pivot-specific time and day gates ──────────────────────────
            if settings.PIVOT_NO_FRIDAY and latest_5m_ts.weekday() == 4:
                log_event(logger, "PIVOT_BLOCKED_FRIDAY", candle=latest_5m_ts)
            elif (
                settings.PIVOT_NO_NEW_ENTRY_AFTER
                and (latest_5m_ts + timedelta(minutes=5)).time()
                    >= _parse_time(settings.PIVOT_NO_NEW_ENTRY_AFTER)
            ):
                log_event(logger, "PIVOT_BLOCKED_TIME",
                          candle=latest_5m_ts, after=settings.PIVOT_NO_NEW_ENTRY_AFTER)
            elif (
                settings.PIVOT_SKIP_LULLS
                and _is_in_lull_window((latest_5m_ts + timedelta(minutes=5)).time(), settings.PIVOT_LULL_WINDOWS)
            ):
                log_event(logger, "PIVOT_BLOCKED_LULL",
                          candle=latest_5m_ts, windows=settings.PIVOT_LULL_WINDOWS)
            else:
                # ── end pivot gates ─────────────────────────────────────────
                _accept_on = settings.PIVOT_ACCEPTANCE
                if (
                    _accept_on
                    and intraday_regime
                    and intraday_regime.upper() in settings.PIVOT_ACCEPT_BLOCK_REGIMES
                ):
                    _accept_on = False
                    log_event(logger, "PIVOT_ACCEPT_BLOCKED_REGIME",
                              candle=latest_5m_ts, regime=intraday_regime)
                setup = find_pivot_setup(
                    candles_5m, pivot_levels,
                    sustain_candles=settings.PIVOT_SUSTAIN_CANDLES,
                    atr_period=settings.PIVOT_ATR_PERIOD,
                    sl_mode=settings.PIVOT_SL_MODE,
                    sl_atr_mult=settings.PIVOT_SL_ATR_MULT,
                    sl_buffer_atr=settings.PIVOT_SL_BUFFER_ATR,
                    min_room_r=settings.PIVOT_MIN_ROOM_R,
                    min_today_candles=settings.PIVOT_MIN_TODAY_CANDLES,
                    pivot_mode=settings.PIVOT_MODE,
                    od_window_start=_parse_time(settings.PIVOT_OD_WINDOW_START),
                    od_window_end=_parse_time(settings.PIVOT_OD_WINDOW_END),
                    rejection_zone_atr=settings.PIVOT_REJECTION_ZONE_ATR,
                    min_od_gap_atr=settings.PIVOT_OD_MIN_GAP_ATR,
                    first_candle_confirm=settings.PIVOT_OD_FIRST_CANDLE_CONFIRM,
                    max_first_wick_atr=settings.PIVOT_OD_MAX_FIRST_WICK_ATR,
                    enable_acceptance=_accept_on,
                    acceptance_min_dist_atr=settings.PIVOT_ACCEPT_MIN_DIST_ATR,
                    acceptance_min_room_r=settings.PIVOT_ACCEPT_MIN_ROOM_R,
                    acceptance_blocked_sides=_pivot_accept_blocked_sides(_day, underlying),
                    acceptance_require_confirm_body=settings.PIVOT_ACCEPT_REQUIRE_CONFIRM_BODY,
                    bounce_zone_atr=settings.PIVOT_BOUNCE_ZONE_ATR,
                    bounce_min_range_atr=settings.PIVOT_BOUNCE_MIN_RANGE_ATR,
                    bounce_min_wick_pct=settings.PIVOT_BOUNCE_MIN_WICK_PCT,
                    bounce_trend_ema=settings.PIVOT_BOUNCE_TREND_EMA,
                    bounce_confirm_next=settings.PIVOT_BOUNCE_CONFIRM_NEXT,
                    enable_swing_pivot=settings.PIVOT_ENABLE_SWING,
                    swing_pivot_left=settings.PIVOT_SWING_LEFT,
                    swing_pivot_right=settings.PIVOT_SWING_RIGHT,
                    swing_pivot_trend_ema=settings.PIVOT_SWING_TREND_EMA,
                    swing_pivot_rr_t1=settings.PIVOT_SWING_RR_T1,
                    swing_pivot_rr_t2=settings.PIVOT_SWING_RR_T2,
                    swing_pivot_rr_t3=settings.PIVOT_SWING_RR_T3,
                    swing_pivot_use_atr_sl=settings.PIVOT_SWING_USE_ATR_SL,
                    swing_pivot_atr_mult=settings.PIVOT_SWING_ATR_MULT,
                    swing_pivot_max_sl_atr=settings.PIVOT_SWING_MAX_SL_ATR,
                    swing_pivot_max_risk_pts=settings.PIVOT_SWING_MAX_RISK_PTS,
                )
                if setup is not None:
                    sig_name = f"{setup.side}_PIVOT"
                    log_event(logger, f"{sig_name}_SIGNAL", candle=latest_5m_ts,
                              mode=setup.mode, entry=setup.entry,
                              stop=setup.stop, risk=setup.risk,
                              t1=setup.t1, t2=setup.t2, t3=setup.t3, atr=setup.atr)
                    # Global per-side cap also applies to pivot signals.
                    if (_side_blk := side_block_reason(setup.side, _day, underlying)):
                        log_event(logger, "GLOBAL_SIDE_CAP_BLOCKED",
                                  signal=sig_name, side=setup.side, reason=_side_blk)
                    else:
                        sig_id = _signal_id(sig_name, latest_5m_ts, underlying)
                        # Atomically claim the pivot signal — same race-condition guard as
                        # _gate().  claim_signal_atomic returns True only for the first
                        # writer, so a concurrent bot process that races here is blocked.
                        if claim_signal_atomic(sig_id, sig_name, latest_5m_ts.isoformat()):
                            _candle_attempted = True
                            if setup.mode == "ACCEPTANCE":
                                _k = (_dk(_day, underlying), setup.side)
                                _pivot_accept_count[_k] = _pivot_accept_count.get(_k, 0) + 1
                            # FIX (Flaw 15): write setup under the lock so consume_pivot_setup()
                            # in execute_entry always sees a consistent value.
                            with _pivot_setup_lock:
                                _pivot_setups[_ukey(underlying)] = setup
                            return sig_name  # type: ignore[return-value]

    # ── VWAP Retest strategy ───────────────────────────────────────────────────
    # VWAP_NO_NEW_ENTRY_AFTER: afternoon VWAP crosses are mostly chop + theta
    # (270-day replay: net R per trade −0.10 after 12:00, −0.15 after 13:30).
    if (settings.ENABLE_VWAP_STRATEGY
            and (not settings.VWAP_NO_NEW_ENTRY_AFTER
                 or latest_5m_ts.time() < _parse_time(settings.VWAP_NO_NEW_ENTRY_AFTER))
            and not _sq_blocked and not _candle_already_attempted()):
        from strategies.vwap_strategy import is_vwap_ce_signal, is_vwap_pe_signal

        _vwap_kwargs = dict(
            retest_lookback=settings.VWAP_RETEST_LOOKBACK,
            min_bounce_pts=settings.VWAP_MIN_BOUNCE_PTS,
            max_submerged_candles=settings.VWAP_MAX_SUBMERGED_CANDLES,
            slope_lookback=settings.VWAP_SLOPE_LOOKBACK,
        )

        def _vwap_level_blocked(side: str) -> bool:
            """Opt-in S/R room check (ENABLE_VWAP_LEVEL_FILTER)."""
            if not settings.ENABLE_VWAP_LEVEL_FILTER:
                return False
            from strategies.level_filter import collect_levels, level_room_blocked
            levels = collect_levels(
                candles_5m,
                prev_day_high=prev_day_high,
                prev_day_low=prev_day_low,
                pivot_levels=pivot_levels,
                use_pivots=settings.VWAP_LEVEL_USE_PIVOTS,
                use_day_extremes=settings.VWAP_LEVEL_USE_DAY_EXTREMES,
            )
            blocked, level, room = level_room_blocked(
                side, candles_5m[-1].close, atr_at(candles_5m, period=14),
                levels, settings.VWAP_LEVEL_MIN_ROOM_ATR,
            )
            if blocked:
                log_event(logger, "VWAP_BLOCKED_LEVEL", side=side, candle=latest_5m_ts,
                          close=candles_5m[-1].close, level=level,
                          room_pts=round(room, 1), min_room_atr=settings.VWAP_LEVEL_MIN_ROOM_ATR)
            return blocked

        if settings.ENABLE_CE_VWAP and is_vwap_ce_signal(candles_5m, vwap, **_vwap_kwargs):
            log_event(logger, "CE_VWAP_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close,
                      vwap=round(vwap, 2) if vwap else None)
            if _vwap_level_blocked("CE"):
                _candle_attempted = True
            elif (sig := _gate("CE_VWAP")) is not None:
                return sig

        if not _candle_already_attempted() and settings.ENABLE_PE_VWAP and is_vwap_pe_signal(candles_5m, vwap, **_vwap_kwargs):
            log_event(logger, "PE_VWAP_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close,
                      vwap=round(vwap, 2) if vwap else None)
            if _vwap_level_blocked("PE"):
                _candle_attempted = True
            elif (sig := _gate("PE_VWAP")) is not None:
                return sig

    # ── PDHL (Previous Day High/Low) Breakout strategy ─────────────────────────
    if settings.ENABLE_PDHL_STRATEGY and not _sq_blocked and not _candle_already_attempted():
        from strategies.pdhl_strategy import is_pdhl_ce_signal, is_pdhl_pe_signal

        if is_pdhl_ce_signal(candles_5m, prev_day_high, buffer_pts=settings.PDHL_BUFFER_PTS):
            log_event(logger, "CE_PDHL_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close,
                      pdh=prev_day_high)
            if (sig := _gate("CE_PDHL")) is not None:
                return sig

        if not _candle_already_attempted() and is_pdhl_pe_signal(candles_5m, prev_day_low, buffer_pts=settings.PDHL_BUFFER_PTS):
            log_event(logger, "PE_PDHL_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close,
                      pdl=prev_day_low)
            if (sig := _gate("PE_PDHL")) is not None:
                return sig

    # ── NATR Trailing Stop strategy ────────────────────────────────────────────
    if settings.ENABLE_NATR_STRATEGY and not _sq_blocked and not _candle_already_attempted():
        from strategies.natr_strategy import is_natr_ce_signal, is_natr_pe_signal

        _natr_kwargs = dict(
            natr_period=settings.NATR_PERIOD,
            natr_mult=settings.NATR_MULT,
        )

        if is_natr_ce_signal(candles_5m, **_natr_kwargs):
            log_event(logger, "CE_NATR_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close)
            if (sig := _gate("CE_NATR")) is not None:
                return sig

        if not _candle_already_attempted() and is_natr_pe_signal(candles_5m, **_natr_kwargs):
            log_event(logger, "PE_NATR_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close)
            if (sig := _gate("PE_NATR")) is not None:
                return sig

    # ── ATR Copilot strategy ───────────────────────────────────────────────────
    if settings.ENABLE_ATR_COPILOT_STRATEGY and not _sq_blocked and not _candle_already_attempted():
        from strategies.atr_copilot_strategy import is_atr_copilot_ce_signal, is_atr_copilot_pe_signal

        _atr_copilot_kwargs = dict(
            atr_period=settings.ATR_COPILOT_PERIOD,
            ema_period=settings.ATR_COPILOT_EMA_PERIOD,
            band_mult=settings.ATR_COPILOT_BAND_MULT,
            breakout_buffer=settings.ATR_COPILOT_BREAKOUT_BUFFER,
        )

        if is_atr_copilot_ce_signal(candles_5m, **_atr_copilot_kwargs):
            log_event(logger, "CE_ATR_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close)
            if (sig := _gate("CE_ATR")) is not None:
                return sig

        if not _candle_already_attempted() and is_atr_copilot_pe_signal(candles_5m, **_atr_copilot_kwargs):
            log_event(logger, "PE_ATR_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close)
            if (sig := _gate("PE_ATR")) is not None:
                return sig

    # ── Time Range Breakout (TRB) strategy ─────────────────────────────────────
    if settings.ENABLE_TRB_STRATEGY and not _sq_blocked and not _candle_already_attempted():
        from strategies.trb_strategy import is_trb_ce_signal, is_trb_pe_signal

        _trb_kwargs = dict(
            min_body_ratio=settings.TRB_MIN_BODY_RATIO,
            buffer_atr_mult=settings.TRB_BUFFER_ATR_MULT,
            window_end=_parse_time(settings.TRB_WINDOW_END) if settings.TRB_WINDOW_END else None,
            first_breakout_only=settings.TRB_FIRST_BREAKOUT_ONLY,
        )

        if is_trb_ce_signal(candles_5m, candles_15m, **_trb_kwargs):
            log_event(logger, "CE_TRB_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close)
            if (sig := _gate("CE_TRB")) is not None:
                return sig

        if not _candle_already_attempted() and is_trb_pe_signal(candles_5m, candles_15m, **_trb_kwargs):
            log_event(logger, "PE_TRB_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close)
            if (sig := _gate("PE_TRB")) is not None:
                return sig

    # ── Phase 1: EMA 9/21 + RSI strategy ───────────────────────────────────────
    # Pivot filters are intentionally NOT applied to EMA (rule-set has its own
    # 15m trend + RSI logic).  Cooldown is started by note_ema_trade() only when
    # an EMA entry actually fills, and ticks down on every closed 5m candle via
    # tick_ema_cooldown() — not here.
    _today_str = str(latest_5m_ts.date())
    _reset_ema_cooldown_if_new_day(_today_str, underlying)

    _ema_window_ok = True
    try:
        _ema_window_ok = latest_5m_ts.time() >= _parse_time(settings.EMA_SCAN_START)
        if settings.EMA_NO_NEW_ENTRY_AFTER:
            _ema_window_ok = _ema_window_ok and latest_5m_ts.time() < _parse_time(settings.EMA_NO_NEW_ENTRY_AFTER)
        if settings.EMA_MIDDAY_PAUSE_START and settings.EMA_MIDDAY_PAUSE_END:
            _m_start = _parse_time(settings.EMA_MIDDAY_PAUSE_START)
            _m_end = _parse_time(settings.EMA_MIDDAY_PAUSE_END)
            if _m_start <= latest_5m_ts.time() < _m_end:
                _ema_window_ok = False
    except (ValueError, AttributeError, TypeError):
        pass   # bad config — fail open

    if settings.ENABLE_EMA_STRATEGY and _ema_window_ok and not _sq_blocked and not _candle_already_attempted():
        _ema_kwargs = dict(
            rsi_period=settings.EMA_RSI_PERIOD,
            pullback_tol_pts=settings.EMA_PULLBACK_TOL_PTS,
            ema_cross=settings.EMA_CROSS_TRIGGER,
            cross_without_15m=settings.EMA_CROSS_IGNORE_15M,
            cross_only=settings.EMA_CROSS_ONLY,
            ignore_15m=settings.EMA_IGNORE_15M,
            require_candle_color=settings.EMA_REQUIRE_CANDLE_COLOR,
            min_body_atr=settings.EMA_MIN_BODY_ATR,
        )
        _atr_state = 0
        if settings.EMA_ATR_CONFIRM:
            from strategies.natr_strategy import natr_state
            _atr_state = natr_state(candles_5m, natr_period=settings.NATR_PERIOD,
                                    natr_mult=settings.NATR_MULT)
        _day_block = ema_day_block_reason(underlying)
        if _day_block:
            log_event(logger, "EMA_BLOCKED_DAY_LOCK", candle=latest_5m_ts, reason=_day_block)
        elif settings.EMA_COOLDOWN_CANDLES > 0 and _ema_cooldown_left.get(_ukey(underlying), 0) > 0:
            log_event(logger, "EMA_BLOCKED_COOLDOWN",
                      candle=latest_5m_ts, candles_remaining=_ema_cooldown_left.get(_ukey(underlying), 0))
        else:
            _vwap_ok_ce = True
            _vwap_ok_pe = True
            if settings.EMA_REQUIRE_VWAP and vwap is not None:
                _close = candles_5m[-1].close
                _vwap_ok_ce = _close >= vwap
                _vwap_ok_pe = _close <= vwap

            if _atr_state >= 0 and is_ce_signal(
                candles_5m, candles_15m, rsi_min=settings.EMA_RSI_CE_MIN, **_ema_kwargs
            ):
                if _vwap_ok_ce:
                    log_event(logger, "CE_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close)
                    if (sig := _gate("CE")) is not None:
                        return sig
                else:
                    log_event(logger, "EMA_BLOCKED_VWAP", side="CE", close=candles_5m[-1].close, vwap=round(vwap, 2))

            if _atr_state <= 0 and not _candle_already_attempted() and is_pe_signal(
                candles_5m, candles_15m, rsi_max=settings.EMA_RSI_PE_MAX, **_ema_kwargs
            ):
                if _vwap_ok_pe:
                    log_event(logger, "PE_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close)
                    if (sig := _gate("PE")) is not None:
                        return sig
                else:
                    log_event(logger, "EMA_BLOCKED_VWAP", side="PE", close=candles_5m[-1].close, vwap=round(vwap, 2))

    # ── Phase 2: Momentum strategy (opt-in) ────────────────────────────────────
    if not settings.ENABLE_MOMENTUM_PHASE or _skip_on_monday or _candle_already_attempted():
        return None

    from strategies.ce_momentum import is_ce_momentum_signal
    from strategies.pe_momentum import is_pe_momentum_signal

    try:
        win_start = _parse_time(settings.MOMENTUM_WINDOW_START)
        win_end   = _parse_time(settings.MOMENTUM_WINDOW_END)
    except (ValueError, AttributeError):
        logger.warning("Invalid MOMENTUM_WINDOW_START/END in config — skipping phase 2.")
        return None

    min_body = float(settings.MOMENTUM_MIN_BODY_PTS)

    _mom_day = str(latest_5m_ts.date())

    if is_ce_momentum_signal(candles_5m, candles_15m,
                              min_body_pts=min_body,
                              window_start=win_start,
                              window_end=win_end):
        log_event(logger, "CE_MOMENTUM_SIGNAL",
                  candle=latest_5m_ts, close=candles_5m[-1].close,
                  body=round(candles_5m[-1].close - candles_5m[-1].open, 2))
        if (_blk := mom_block_reason("CE", _mom_day, underlying)):
            log_event(logger, "MOM_BLOCKED", signal="CE_MOM", candle=latest_5m_ts, reason=_blk)
        elif (sig := _gate("CE_MOM")) is not None:
            return sig

    if not _candle_already_attempted() and is_pe_momentum_signal(candles_5m, candles_15m,
                              min_body_pts=min_body,
                              window_start=win_start,
                              window_end=win_end):
        log_event(logger, "PE_MOMENTUM_SIGNAL",
                  candle=latest_5m_ts, close=candles_5m[-1].close,
                  body=round(candles_5m[-1].open - candles_5m[-1].close, 2))
        if (_blk := mom_block_reason("PE", _mom_day, underlying)):
            log_event(logger, "MOM_BLOCKED", signal="PE_MOM", candle=latest_5m_ts, reason=_blk)
        elif (sig := _gate("PE_MOM")) is not None:
            return sig

    return None
