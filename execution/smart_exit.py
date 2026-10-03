"""
Smart Exit Engine — autonomous position management.

Evaluates five exit triggers on every option-tick and every 5m candle close.
All triggers fire execute_exit() directly — zero human interaction required.

Triggers (evaluated in priority order):
  1. REVERSAL_SIGNAL   — opposite signal fired while in position (CE→PE or PE→CE)
  2. EMA_COLLAPSE      — entry-side EMA condition reversed on 5m candle close
  3. PROFIT_LOCK       — option LTP reached PROFIT_LOCK_MULTIPLIER × entry price
  4. TIME_DECAY        — after TIME_DECAY_EXIT_AFTER IST with small unrealised P&L
  5. DAILY_LOSS_LIMIT  — cumulative daily realised loss exceeds DAILY_LOSS_LIMIT pts

Each trigger logs a structured event and returns the exit reason string,
or None if no exit is warranted.
"""

from __future__ import annotations

import logging
from datetime import time
from typing import Callable

from market.candle_builder import Candle
from market.indicators import ema
from utils.logging_config import log_event
from utils.time_utils import now_ist, parse_time_ist

logger = logging.getLogger(__name__)


class SmartExitEngine:
    """
    Stateless on each call — all state comes from BotContext.

    Usage:
        engine = SmartExitEngine(settings)
        # on every option tick:
        reason = engine.check_on_tick(strategy_type, entry_price, option_ltp,
                                       qty, daily_realised_pnl)
        # on every 5m candle close:
        reason = engine.check_on_candle(strategy_type, candles_5m, candles_15m)
        if reason:
            execute_exit(ctx, reason=reason)
    """

    def __init__(
        self,
        profit_lock_multiplier: float = 2.0,
        profit_lock_atr_mult: float = 0.0,
        profit_lock_min_pct: float = 0.0,
        time_decay_after: str = "14:45",
        time_decay_min_pnl_pts: float = 20.0,
        daily_loss_limit_pts: float = 200.0,
        enable_reversal_exit: bool = True,
        enable_ema_collapse: bool = True,
        enable_profit_lock: bool = True,
        enable_time_decay: bool = True,
        enable_daily_loss_limit: bool = True,
    ) -> None:
        self._profit_lock_mult     = profit_lock_multiplier
        self._profit_lock_atr_mult = profit_lock_atr_mult   # 0 = use fixed mult
        self._profit_lock_min_pct  = profit_lock_min_pct    # 0 = disabled
        self._time_decay_time    = parse_time_ist(time_decay_after)
        self._time_decay_min_pnl = time_decay_min_pnl_pts
        self._daily_loss_limit   = daily_loss_limit_pts
        self._profit_locked      = False   # reset when a new trade opens

        self._en_reversal     = enable_reversal_exit
        self._en_ema_collapse = enable_ema_collapse
        self._en_profit_lock  = enable_profit_lock
        self._en_time_decay   = enable_time_decay
        self._en_daily_loss   = enable_daily_loss_limit

    # ── Called when a new trade opens ─────────────────────────────────────────

    def reset(self) -> None:
        """Reset per-trade state. Call when a new position opens."""
        self._profit_locked = False

    # ── Tick-level checks ──────────────────────────────────────────────────────

    def check_on_tick(
        self,
        strategy_type: str,        # "CE" or "PE"
        entry_price: float,
        option_ltp: float,
        qty: int,
        daily_realised_pnl_pts: float,
        pending_signal: str | None = None,  # latest signal from evaluate_signals()
        entry_atr: float | None = None,     # ATR(14) at trade entry, for dynamic lock
    ) -> str | None:
        """
        Check all tick-level exit triggers.
        Returns exit reason string or None.
        """

        # ── Trigger 1: Reversal signal ─────────────────────────────────────────
        if self._en_reversal and pending_signal is not None:
            sig_side = "CE" if pending_signal.startswith("CE") else "PE"
            pos_side = "CE" if strategy_type.startswith("CE") else "PE"
            if sig_side != pos_side:
                log_event(logger, "SMART_EXIT_REVERSAL",
                          position=strategy_type, signal=pending_signal,
                          option_ltp=option_ltp)
                return "REVERSAL_SIGNAL"

        # ── Trigger 3: Profit lock ─────────────────────────────────────────────
        # Threshold = max of all enabled modes:
        #   ATR-based : entry + ATR × atr_mult   — scales with index volatility
        #   % of entry: entry × (1 + min_pct)    — scales with premium size
        #   Fixed mult : entry × fixed_mult       — simple fallback
        #
        # Using max() means:
        #   • On low-premium entries (≈₹225): ATR-based usually wins → tight lock
        #   • On high-premium entries (≈₹520): %-based wins → lets winners run
        if self._en_profit_lock and not self._profit_locked:
            candidates: list[tuple[float, str]] = []

            if self._profit_lock_atr_mult > 0 and entry_atr and entry_atr > 0:
                candidates.append((
                    entry_price + entry_atr * self._profit_lock_atr_mult,
                    "atr",
                ))
            if self._profit_lock_min_pct > 0:
                candidates.append((
                    entry_price * (1.0 + self._profit_lock_min_pct),
                    "pct",
                ))
            if not candidates:
                # neither ATR nor % enabled — fall back to fixed multiplier
                candidates.append((
                    entry_price * self._profit_lock_mult,
                    "fixed",
                ))

            threshold, mode = max(candidates, key=lambda x: x[0])

            if option_ltp >= threshold:
                self._profit_locked = True
                log_event(logger, "SMART_EXIT_PROFIT_LOCK",
                          entry=entry_price, ltp=option_ltp,
                          threshold=round(threshold, 2),
                          mode=mode,
                          atr=round(entry_atr, 2) if entry_atr else None)
                return "PROFIT_LOCK"

        # ── Trigger 4: Time decay ──────────────────────────────────────────────
        if self._en_time_decay:
            now_time = now_ist().time()
            if now_time >= self._time_decay_time:
                unrealised_pts = option_ltp - entry_price
                if unrealised_pts < self._time_decay_min_pnl:
                    log_event(logger, "SMART_EXIT_TIME_DECAY",
                              time=str(now_time), unrealised_pts=round(unrealised_pts, 2),
                              min_required=self._time_decay_min_pnl)
                    return "TIME_DECAY"

        # ── Trigger 5: Daily loss limit ────────────────────────────────────────
        if self._en_daily_loss:
            if daily_realised_pnl_pts <= -abs(self._daily_loss_limit):
                log_event(logger, "SMART_EXIT_DAILY_LOSS_LIMIT",
                          daily_pnl_pts=round(daily_realised_pnl_pts, 2),
                          limit=self._daily_loss_limit)
                return "DAILY_LOSS_LIMIT"

        return None

    # ── Candle-level checks ────────────────────────────────────────────────────

    def check_on_candle(
        self,
        strategy_type: str,
        candles_5m: list[Candle],
        candles_15m: list[Candle],
    ) -> str | None:
        """
        Check candle-close exit triggers (EMA collapse).
        Returns exit reason string or None.
        """

        # ── Trigger 2: EMA collapse ────────────────────────────────────────────
        if self._en_ema_collapse and len(candles_5m) >= 21:
            ema9_vals  = ema(candles_5m, 9)
            ema21_vals = ema(candles_5m, 21)
            e9  = ema9_vals[-1]
            e21 = ema21_vals[-1]
            if e9 is None or e21 is None:
                return None

            close = candles_5m[-1].close

            if strategy_type == "CE":
                # Entry required EMA9 > EMA21. Exit if EMA9 ≤ EMA21 or close < EMA21.
                if e9 <= e21 or close < e21:
                    log_event(logger, "SMART_EXIT_EMA_COLLAPSE",
                              side="CE", ema9=round(e9, 2), ema21=round(e21, 2),
                              close=round(close, 2))
                    return "EMA_COLLAPSE"

            elif strategy_type == "PE":
                # Entry required EMA9 < EMA21. Exit if EMA9 ≥ EMA21 or close > EMA21.
                if e9 >= e21 or close > e21:
                    log_event(logger, "SMART_EXIT_EMA_COLLAPSE",
                              side="PE", ema9=round(e9, 2), ema21=round(e21, 2),
                              close=round(close, 2))
                    return "EMA_COLLAPSE"

        return None

    # ── Daily loss guard (entry gate) ──────────────────────────────────────────

    def is_daily_loss_limit_hit(self, daily_realised_pnl_pts: float) -> bool:
        """
        Returns True if the daily loss limit is hit — blocks new entries.
        Call from BotContext.can_create_entry().
        """
        if not self._en_daily_loss:
            return False
        return daily_realised_pnl_pts <= -abs(self._daily_loss_limit)
