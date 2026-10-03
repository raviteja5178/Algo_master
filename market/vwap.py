"""
Intraday VWAP calculator.

VWAP = cumulative(typical_price × volume) / cumulative(volume)
     where typical_price = (high + low + close) / 3

Resets automatically at 09:15 IST each trading day.
Fed by on_tick() for live price updates and on_candle() for completed candles.

When volume is unavailable (e.g. index ticks from WebSocket), a tick-count
proxy is used (each tick counts as 1 unit).
"""

from __future__ import annotations

import threading
from datetime import date, datetime

from utils.time_utils import IST


class VWAPCalculator:
    """
    Running intraday VWAP.

    Feed completed candles (with OHLCV) via on_candle() for best accuracy.
    Alternatively feed raw ticks via on_tick() — VWAP will be less accurate
    but still useful as a directional reference.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reset()

    # ── Public API ─────────────────────────────────────────────────────────────

    def on_candle(self, candle) -> None:
        """
        Update VWAP from a completed Candle (preferred — has OHLCV).
        Resets automatically when the candle date changes.
        """
        with self._lock:
            self._maybe_reset(candle.timestamp.date())
            tp  = (candle.high + candle.low + candle.close) / 3.0
            vol = candle.volume if candle.volume > 0 else 1
            self._cum_tp_vol += tp * vol
            self._cum_vol    += vol

    def on_tick(self, ltp: float, ts: datetime | None = None) -> None:
        """
        Update VWAP from a raw price tick.
        Each tick is treated as 1 volume unit (proxy when volume is unavailable).
        """
        now = ts or datetime.now(IST)
        with self._lock:
            self._maybe_reset(now.date())
            self._cum_tp_vol += ltp          # tick proxy: TP = LTP, vol = 1
            self._cum_vol    += 1

    @property
    def value(self) -> float | None:
        """Current VWAP value, or None if no data yet today."""
        with self._lock:
            if self._cum_vol == 0:
                return None
            return self._cum_tp_vol / self._cum_vol

    @property
    def today(self) -> date | None:
        """The date this VWAP instance is currently tracking."""
        return self._current_date

    def reset(self) -> None:
        """Force a manual reset (e.g. on bot restart)."""
        with self._lock:
            self._reset()

    # ── Private ────────────────────────────────────────────────────────────────

    def _reset(self) -> None:
        self._cum_tp_vol: float = 0.0
        self._cum_vol:    float = 0.0
        self._current_date: date | None = None

    def _maybe_reset(self, today: date) -> None:
        """Reset accumulators when the trading date rolls over."""
        if self._current_date != today:
            self._reset()
            self._current_date = today
