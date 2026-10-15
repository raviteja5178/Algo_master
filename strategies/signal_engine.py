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
from datetime import datetime, time
from typing import Literal

from config import settings
from market.candle_builder import Candle
from market.historical_data import PivotLevels
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

# ── EMA-specific cooldown counter ─────────────────────────────────────────────
# Independent of the global SmartEntry cooldown — only applies to CE/PE signals.
# Started by note_ema_trade() when an EMA entry FILLS; ticked down on every
# completed 5m candle by tick_ema_cooldown(). Reset on date change.
_ema_cooldown_left: int = 0
_ema_cooldown_date: str = ""
_ema_trades_today: int = 0
_ema_consec_losses: int = 0


def _reset_ema_cooldown_if_new_day(day: str) -> None:
    global _ema_cooldown_left, _ema_cooldown_date, _ema_trades_today, _ema_consec_losses
    if _ema_cooldown_date != day:
        _ema_cooldown_date = day
        _ema_cooldown_left = 0
        _ema_trades_today = 0
        _ema_consec_losses = 0


def note_ema_trade(day: str) -> None:
    """Start the EMA cooldown and count the trade after an EMA CE/PE entry has filled."""
    global _ema_cooldown_left, _ema_trades_today
    _reset_ema_cooldown_if_new_day(day)
    _ema_cooldown_left = max(0, settings.EMA_COOLDOWN_CANDLES)
    _ema_trades_today += 1


def note_ema_result(day: str, pnl: float) -> None:
    """Record a closed EMA trade's P&L for the consecutive-loss lockout."""
    global _ema_consec_losses
    _reset_ema_cooldown_if_new_day(day)
    _ema_consec_losses = _ema_consec_losses + 1 if pnl < 0 else 0


def ema_day_block_reason() -> str | None:
    """Return why EMA is locked for the rest of the day, or None."""
    if settings.EMA_MAX_TRADES_PER_DAY > 0 and _ema_trades_today >= settings.EMA_MAX_TRADES_PER_DAY:
        return f"max EMA trades/day reached ({_ema_trades_today})"
    if settings.EMA_MAX_CONSEC_LOSSES > 0 and _ema_consec_losses >= settings.EMA_MAX_CONSEC_LOSSES:
        return f"{_ema_consec_losses} consecutive EMA losses"
    return None


def tick_ema_cooldown() -> None:
    """Count the EMA cooldown down by one candle (call on every closed 5m candle)."""
    global _ema_cooldown_left
    if _ema_cooldown_left > 0:
        _ema_cooldown_left -= 1

SignalType = Literal["CE", "PE", "CE_ORB", "PE_ORB", "CE_OB", "PE_OB", "CE_MOM", "PE_MOM", "CE_TRB", "PE_TRB", "CE_VWAP", "PE_VWAP", "CE_PDHL", "PE_PDHL", "CE_NATR", "PE_NATR", "CE_ATR", "PE_ATR", "CE_PIVOT", "PE_PIVOT", None]

# FIX (Flaw 15): protect last_pivot_setup with a lock.
# The setup is written by evaluate_signals (candle-close thread) and read by
# execute_entry (same thread under _tick_lock), but consume_pivot_setup() makes
# the read-and-clear atomic so there is no window where a second evaluation can
# overwrite the setup between the read and the entry construction.
_pivot_setup_lock = threading.Lock()
_last_pivot_setup = None   # internal — access only via consume_pivot_setup()


def consume_pivot_setup():
    """Atomically read and clear the pending pivot setup.

    Returns the PivotSetup that triggered the most recent CE_PIVOT/PE_PIVOT
    signal, then resets the stored value to None.  Thread-safe: a concurrent
    evaluate_signals call that writes a new setup will not race with this read
    because both operations hold _pivot_setup_lock.
    """
    global _last_pivot_setup
    with _pivot_setup_lock:
        setup = _last_pivot_setup
        _last_pivot_setup = None
        return setup


# FIX (Flaw 17): _pivot_trades_today is seeded from the DB on first access
# so a bot restart mid-day does not reset the counter to 0.
_pivot_trades_today: dict[str, int] = {}
_pivot_counter_seeded: set[str] = set()  # days whose DB count has been loaded


def _seed_pivot_count(day: str) -> None:
    """Load today's filled pivot trade count from the DB (once per day)."""
    if day in _pivot_counter_seeded:
        return
    try:
        from persistence.trade_store import fetch_today_pivot_trade_count
        db_count = fetch_today_pivot_trade_count(day)
        if db_count > _pivot_trades_today.get(day, 0):
            _pivot_trades_today[day] = db_count
    except Exception as exc:
        logger.warning("Could not seed pivot trade counter from DB: %s", exc)
    _pivot_counter_seeded.add(day)


def note_pivot_trade(day: str) -> None:
    """Count a filled Pivot trade toward PIVOT_MAX_TRADES_PER_DAY."""
    _pivot_trades_today[day] = _pivot_trades_today.get(day, 0) + 1


# ── Momentum guards: per-day trade cap + same-direction re-entry cooldown ─────
# Trade count is seeded from the DB once per day (restart-safe).  The re-entry
# cooldown is in-memory only (a restart clears it — fails open).
_mom_trades_today: dict[str, int] = {}
_mom_counter_seeded: set[str] = set()
_mom_cooldown_left: int = 0
_mom_cooldown_side: str | None = None


def _seed_mom_count(day: str) -> None:
    if day in _mom_counter_seeded:
        return
    try:
        from persistence.trade_store import fetch_today_mom_trade_count
        db_count = fetch_today_mom_trade_count(day)
        if db_count > _mom_trades_today.get(day, 0):
            _mom_trades_today[day] = db_count
    except Exception as exc:
        logger.warning("Could not seed MOM trade counter from DB: %s", exc)
    _mom_counter_seeded.add(day)


def note_mom_trade(day: str) -> None:
    """Count a filled CE_MOM / PE_MOM trade toward MOMENTUM_MAX_TRADES_PER_DAY."""
    _mom_trades_today[day] = _mom_trades_today.get(day, 0) + 1


def note_mom_exit(side: str) -> None:
    """Start the same-direction re-entry cooldown after a MOM trade closes."""
    global _mom_cooldown_left, _mom_cooldown_side
    _mom_cooldown_left = max(0, settings.MOMENTUM_REENTRY_COOLDOWN_CANDLES)
    _mom_cooldown_side = side


def tick_mom_cooldown() -> None:
    """Count the MOM re-entry cooldown down by one candle (call per closed 5m candle)."""
    global _mom_cooldown_left
    if _mom_cooldown_left > 0:
        _mom_cooldown_left -= 1


def mom_block_reason(side: str, day: str) -> str | None:
    """Return why a MOM signal on *side* must be skipped, or None."""
    _seed_mom_count(day)
    cap = settings.MOMENTUM_MAX_TRADES_PER_DAY
    if cap > 0 and _mom_trades_today.get(day, 0) >= cap:
        return f"max MOM trades/day reached ({_mom_trades_today.get(day, 0)})"
    if _mom_cooldown_left > 0 and _mom_cooldown_side == side:
        return f"same-direction re-entry cooldown ({_mom_cooldown_left} candles left)"
    return None


# ── Global per-side daily trade cap (applies to ALL strategies) ───────────────
# Counts filled trades per direction (CE / PE) regardless of strategy.
# Seeded from DB once per day on first access so a restart mid-day doesn't
# reset the counter to 0.
_side_trades_today: dict[str, dict[str, int]] = {}   # {day: {"CE": n, "PE": n}}
_side_counter_seeded: set[str] = set()


def _seed_side_count(day: str) -> None:
    """Load today's per-side filled trade counts from the DB (once per day)."""
    if day in _side_counter_seeded:
        return
    try:
        from persistence.trade_store import fetch_today_side_trade_count
        for _s in ("CE", "PE"):
            db_count = fetch_today_side_trade_count(_s, day)
            _side_trades_today.setdefault(day, {})
            if db_count > _side_trades_today[day].get(_s, 0):
                _side_trades_today[day][_s] = db_count
    except Exception as exc:
        logger.warning("Could not seed side trade counter from DB: %s", exc)
    _side_counter_seeded.add(day)


def note_side_trade(side: str, day: str) -> None:
    """Increment the per-side daily counter after a trade entry fills.

    *side* must be 'CE' or 'PE'.  Call this once per filled trade from
    main.py's execute_entry regardless of which strategy triggered the fill.
    """
    _side_trades_today.setdefault(day, {})
    _side_trades_today[day][side] = _side_trades_today[day].get(side, 0) + 1


def side_block_reason(side: str, day: str) -> str | None:
    """Return why a signal on *side* must be blocked by the global cap, or None."""
    _seed_side_count(day)
    cap = settings.MAX_TRADES_PER_SIDE
    if cap <= 0:
        return None
    count = _side_trades_today.get(day, {}).get(side, 0)
    if count >= cap:
        return f"global {side} cap reached ({count}/{cap} trades today)"
    return None


def _signal_id(strategy: str, candle_ts: datetime) -> str:
    """
    Generate a per-candle deduplication key.

    Using date+HH:MM (not just date) means:
      - The same candle never triggers two fills (idempotency preserved).
      - A fresh setup on a *different* candle later in the day CAN trade,
        because it gets a different key.
    One strategy can therefore trade more than once per day, but never
    more than once per unique 5-minute candle close.
    """
    return f"{strategy}_SIGNAL_{candle_ts.strftime('%Y-%m-%d_%H:%M')}"


def _parse_time(hhmm: str) -> time:
    """Parse 'HH:MM' string into a datetime.time object."""
    h, m = hhmm.split(":")
    return time(int(h), int(m))


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
    from datetime import date as _date
    if latest_5m_ts.date() != _date.today():
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
        sig_id = _signal_id(sig, latest_5m_ts)
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
        if (_side_blk := side_block_reason(_sig_side, _gate_day)):
            log_event(logger, "GLOBAL_SIDE_CAP_BLOCKED",
                      signal=sig, side=_sig_side, reason=_side_blk)
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
            elif not smart_entry.allow(sig, candles_5m, candles_15m=candles_15m):
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
    if settings.ENABLE_PIVOT_STRATEGY and pivot_levels is not None:
        global _last_pivot_setup
        from strategies.pivot_strategy import find_pivot_setup
        _day = str(latest_5m_ts.date())
        # FIX (Flaw 17): seed counter from DB on first candle of the day so a
        # mid-day restart does not reset the max-trades guard to 0.
        _seed_pivot_count(_day)
        if _pivot_trades_today.get(_day, 0) < settings.PIVOT_MAX_TRADES_PER_DAY:
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
                enable_acceptance=settings.PIVOT_ACCEPTANCE,
                bounce_zone_atr=settings.PIVOT_BOUNCE_ZONE_ATR,
                bounce_min_range_atr=settings.PIVOT_BOUNCE_MIN_RANGE_ATR,
                bounce_min_wick_pct=settings.PIVOT_BOUNCE_MIN_WICK_PCT,
                bounce_trend_ema=settings.PIVOT_BOUNCE_TREND_EMA,
                bounce_confirm_next=settings.PIVOT_BOUNCE_CONFIRM_NEXT,
            )
            if setup is not None:
                sig_name = f"{setup.side}_PIVOT"
                log_event(logger, f"{sig_name}_SIGNAL", candle=latest_5m_ts,
                          mode=setup.mode, entry=setup.entry,
                          stop=setup.stop, risk=setup.risk,
                          t1=setup.t1, t2=setup.t2, t3=setup.t3, atr=setup.atr)
                # Global per-side cap also applies to pivot signals.
                if (_side_blk := side_block_reason(setup.side, _day)):
                    log_event(logger, "GLOBAL_SIDE_CAP_BLOCKED",
                              signal=sig_name, side=setup.side, reason=_side_blk)
                else:
                    sig_id = _signal_id(sig_name, latest_5m_ts)
                    # Atomically claim the pivot signal — same race-condition guard as
                    # _gate().  claim_signal_atomic returns True only for the first
                    # writer, so a concurrent bot process that races here is blocked.
                    if claim_signal_atomic(sig_id, sig_name, latest_5m_ts.isoformat()):
                        _candle_attempted = True
                        # FIX (Flaw 15): write setup under the lock so consume_pivot_setup()
                        # in execute_entry always sees a consistent value.
                        with _pivot_setup_lock:
                            _last_pivot_setup = setup
                        return sig_name  # type: ignore[return-value]

    # ── VWAP Retest strategy ───────────────────────────────────────────────────
    if settings.ENABLE_VWAP_STRATEGY and not _sq_blocked and not _candle_already_attempted():
        from strategies.vwap_strategy import is_vwap_ce_signal, is_vwap_pe_signal

        _vwap_kwargs = dict(
            retest_lookback=settings.VWAP_RETEST_LOOKBACK,
            min_bounce_pts=settings.VWAP_MIN_BOUNCE_PTS,
            max_submerged_candles=settings.VWAP_MAX_SUBMERGED_CANDLES,
        )

        if is_vwap_ce_signal(candles_5m, vwap, **_vwap_kwargs):
            log_event(logger, "CE_VWAP_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close,
                      vwap=round(vwap, 2) if vwap else None)
            if (sig := _gate("CE_VWAP")) is not None:
                return sig

        if not _candle_already_attempted() and is_vwap_pe_signal(candles_5m, vwap, **_vwap_kwargs):
            log_event(logger, "PE_VWAP_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close,
                      vwap=round(vwap, 2) if vwap else None)
            if (sig := _gate("PE_VWAP")) is not None:
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
    _reset_ema_cooldown_if_new_day(_today_str)

    _ema_window_ok = True
    try:
        _ema_window_ok = latest_5m_ts.time() >= _parse_time(settings.EMA_SCAN_START)
        if settings.EMA_NO_NEW_ENTRY_AFTER:
            _ema_window_ok = _ema_window_ok and latest_5m_ts.time() < _parse_time(settings.EMA_NO_NEW_ENTRY_AFTER)
    except (ValueError, AttributeError, TypeError):
        pass   # bad config — fail open

    if settings.ENABLE_EMA_STRATEGY and _ema_window_ok and not _sq_blocked and not _candle_already_attempted():
        _ema_kwargs = dict(
            rsi_period=settings.EMA_RSI_PERIOD,
            pullback_tol_pts=settings.EMA_PULLBACK_TOL_PTS,
        )
        _day_block = ema_day_block_reason()
        if _day_block:
            log_event(logger, "EMA_BLOCKED_DAY_LOCK", candle=latest_5m_ts, reason=_day_block)
        elif settings.EMA_COOLDOWN_CANDLES > 0 and _ema_cooldown_left > 0:
            log_event(logger, "EMA_BLOCKED_COOLDOWN",
                      candle=latest_5m_ts, candles_remaining=_ema_cooldown_left)
        else:
            if is_ce_signal(candles_5m, candles_15m, rsi_min=settings.EMA_RSI_CE_MIN, **_ema_kwargs):
                log_event(logger, "CE_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close)
                if (sig := _gate("CE")) is not None:
                    return sig

            if not _candle_already_attempted() and is_pe_signal(
                candles_5m, candles_15m, rsi_max=settings.EMA_RSI_PE_MAX, **_ema_kwargs
            ):
                log_event(logger, "PE_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close)
                if (sig := _gate("PE")) is not None:
                    return sig

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
        if (_blk := mom_block_reason("CE", _mom_day)):
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
        if (_blk := mom_block_reason("PE", _mom_day)):
            log_event(logger, "MOM_BLOCKED", signal="PE_MOM", candle=latest_5m_ts, reason=_blk)
        elif (sig := _gate("PE_MOM")) is not None:
            return sig

    return None
