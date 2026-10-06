"""
Signal engine — evaluates CE and PE strategies on completed candles,
enforces de-duplication, and emits signals to callers.

Two evaluation phases run in order:

  Phase 1 — Standard strategy (ce_strategy / pe_strategy)
      4-rule EMA crossover with prev-high/low breakout confirmation.
      Active all day (09:15–15:00).

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
from collections.abc import Sequence
from datetime import datetime, time
from typing import Literal

from config import settings
from market.candle_builder import Candle
from persistence.trade_store import has_processed_signal, record_processed_signal
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

SignalType = Literal["CE", "PE", "CE_ORB", "PE_ORB", "CE_OB", "PE_OB", "CE_MOM", "PE_MOM", "CE_TRB", "PE_TRB", "CE_VWAP", "PE_VWAP", "CE_PDHL", "PE_PDHL", "CE_NATR", "PE_NATR", "CE_ATR", "PE_ATR", None]


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
        # Rule-based quality gate
        if smart_entry is not None and not smart_entry.allow(sig, candles_5m, candles_15m=candles_15m):
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
        # Atomically claim this signal before returning it to the caller.
        record_processed_signal(sig_id, sig, latest_5m_ts.isoformat())
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

    # ── VWAP Retest strategy ───────────────────────────────────────────────────
    if settings.ENABLE_VWAP_STRATEGY and not _sq_blocked and not _candle_already_attempted():
        from strategies.vwap_strategy import is_vwap_ce_signal, is_vwap_pe_signal

        _vwap_kwargs = dict(
            retest_lookback=settings.VWAP_RETEST_LOOKBACK,
            min_bounce_pts=settings.VWAP_MIN_BOUNCE_PTS,
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

    # ── Phase 1: Standard EMA strategy ─────────────────────────────────────────
    if settings.ENABLE_EMA_STRATEGY and not _sq_blocked and not _candle_already_attempted():
        if is_ce_signal(candles_5m, candles_15m):
            log_event(logger, "CE_SIGNAL", candle=latest_5m_ts, close=candles_5m[-1].close)
            if (sig := _gate("CE")) is not None:
                return sig

        if not _candle_already_attempted() and is_pe_signal(candles_5m, candles_15m):
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

    if is_ce_momentum_signal(candles_5m, candles_15m,
                              min_body_pts=min_body,
                              window_start=win_start,
                              window_end=win_end):
        log_event(logger, "CE_MOMENTUM_SIGNAL",
                  candle=latest_5m_ts, close=candles_5m[-1].close,
                  body=round(candles_5m[-1].close - candles_5m[-1].open, 2))
        if (sig := _gate("CE_MOM")) is not None:
            return sig

    if not _candle_already_attempted() and is_pe_momentum_signal(candles_5m, candles_15m,
                              min_body_pts=min_body,
                              window_start=win_start,
                              window_end=win_end):
        log_event(logger, "PE_MOMENTUM_SIGNAL",
                  candle=latest_5m_ts, close=candles_5m[-1].close,
                  body=round(candles_5m[-1].open - candles_5m[-1].close, 2))
        if (sig := _gate("PE_MOM")) is not None:
            return sig

    return None
