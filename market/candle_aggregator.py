"""
Live tick aggregator: builds 5-minute and 15-minute completed candles
from a stream of raw 1-minute (or tick) data.

Design:
  - Maintains a rolling window of completed candles for each timeframe.
  - Only marks a candle complete when its time bucket has closed.
  - Thread-safe via a simple lock (the main loop is single-threaded but
    the WebSocket callback may be on a separate thread).

Pre-market guard (09:15 IST):
  - on_tick()  : ticks whose wall-clock timestamp < 09:15 are silently dropped.
  - seed()     : candles whose timestamp < 09:15 are filtered out before being
                 stored.  The primary filter lives in fetch_historical_candles(),
                 but this second layer defends against any future caller that
                 passes raw unfiltered data.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timedelta
from typing import Callable

from market.candle_builder import Candle
from utils.time_utils import IST

logger = logging.getLogger(__name__)

# Minimum completed candles to hold in memory (warm-up requires 20)
_BUFFER = 60

# Market session starts at 09:15 IST.  Any candle or tick before this
# time is pre-market / pre-open auction data and must not enter the EMA
# indicators or trigger signals.
_SESSION_OPEN = (9, 15)  # (hour, minute) in IST


class CandleAggregator:
    """
    Aggregates incoming 1-minute candles (or ticks) into N-minute candles.

    Call `on_tick(ltp, timestamp)` with every price update.
    Subscribe to completed candles via `on_candle_closed`.
    """

    def __init__(self, interval_minutes: int) -> None:
        self.interval = interval_minutes
        self._completed: deque[Candle] = deque(maxlen=_BUFFER)
        self._wip_open: float | None = None
        self._wip_high: float = 0.0
        self._wip_low: float = float("inf")
        self._wip_close: float = 0.0
        self._wip_volume: int = 0
        self._wip_start: datetime | None = None
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[Candle], None]] = []

    # ── Public API ─────────────────────────────────────────────────────────────

    def subscribe(self, callback: Callable[[Candle], None]) -> None:
        self._callbacks.append(callback)

    def on_tick(self, ltp: float, timestamp: datetime | None = None) -> None:
        """
        Feed a price tick.  timestamp defaults to now(IST).

        Ticks before 09:15 IST are silently dropped — the main tick handler
        in main.py also gates on wall-clock time, but this second check
        covers edge cases such as backdated ticks from a WebSocket reconnect
        burst or test fixtures with explicit timestamps.
        """
        ts = timestamp or datetime.now(IST)
        if (ts.hour, ts.minute) < _SESSION_OPEN:
            return
        closed_candle: Candle | None = None
        with self._lock:
            bucket_start = self._bucket_start(ts)

            # New bucket — close out the in-progress candle
            if self._wip_start is not None and bucket_start > self._wip_start:
                closed_candle = Candle(
                    timestamp=self._wip_start,
                    open=self._wip_open,  # type: ignore[arg-type]
                    high=self._wip_high,
                    low=self._wip_low,
                    close=self._wip_close,
                    volume=self._wip_volume,
                )
                self._completed.append(closed_candle)
                logger.debug("Candle closed [%dm] %s", self.interval, closed_candle)
                # start fresh before releasing lock
                self._reset_wip(bucket_start, ltp)
            elif self._wip_start is None:
                self._reset_wip(bucket_start, ltp)
            else:
                # same bucket
                self._wip_high = max(self._wip_high, ltp)
                self._wip_low = min(self._wip_low, ltp)
                self._wip_close = ltp
                self._wip_volume += 1

        # Fire callbacks OUTSIDE the lock so callbacks can safely call get_completed()
        if closed_candle is not None:
            for cb in self._callbacks:
                try:
                    cb(closed_candle)
                except Exception as exc:
                    logger.error("Candle callback error: %s", exc)

    def ingest_candle(self, candle: Candle) -> None:
        """Directly ingest a completed 1-minute (or lower) candle."""
        closed_candle: Candle | None = None
        with self._lock:
            bucket_start = self._bucket_start(candle.timestamp)
            if self._wip_start is None:
                self._reset_wip(bucket_start, candle.open)

            if bucket_start > self._wip_start:  # type: ignore[operator]
                # close current WIP
                closed_candle = Candle(
                    timestamp=self._wip_start,  # type: ignore[arg-type]
                    open=self._wip_open,  # type: ignore[arg-type]
                    high=self._wip_high,
                    low=self._wip_low,
                    close=self._wip_close,
                    volume=self._wip_volume,
                )
                self._completed.append(closed_candle)
                self._reset_wip(bucket_start, candle.open)

            self._wip_high = max(self._wip_high, candle.high)
            self._wip_low = min(self._wip_low, candle.low)
            self._wip_close = candle.close
            self._wip_volume += candle.volume

        # Fire callbacks OUTSIDE the lock so callbacks can safely call get_completed()
        if closed_candle is not None:
            for cb in self._callbacks:
                try:
                    cb(closed_candle)
                except Exception as exc:
                    logger.error("Candle callback error: %s", exc)

    def get_completed(self) -> list[Candle]:
        """Return completed candles in chronological order (oldest first)."""
        with self._lock:
            return list(self._completed)

    def seed(self, candles: list[Candle]) -> None:
        """
        Pre-load completed candles from historical data.

        Candles whose timestamp is before 09:15 IST are filtered out here as
        a second line of defence.  fetch_historical_candles() already strips
        pre-market candles, but any direct caller that skips that function
        (backtest scripts, import tools, tests) is also protected.
        """
        accepted = 0
        skipped = 0
        with self._lock:
            for c in candles:
                if (c.timestamp.hour, c.timestamp.minute) < _SESSION_OPEN:
                    skipped += 1
                    continue
                self._completed.append(c)
                accepted += 1
        if skipped:
            logger.warning(
                "seed(): dropped %d pre-market candle(s) (before 09:15) "
                "from %dm aggregator.", skipped, self.interval,
            )
        logger.info(
            "Seeded %dm aggregator with %d historical candles (%d pre-market dropped)",
            self.interval, accepted, skipped,
        )

    # ── Private ────────────────────────────────────────────────────────────────

    def _bucket_start(self, ts: datetime) -> datetime:
        minutes_since_midnight = ts.hour * 60 + ts.minute
        bucket_minute = (minutes_since_midnight // self.interval) * self.interval
        return ts.replace(
            hour=bucket_minute // 60,
            minute=bucket_minute % 60,
            second=0,
            microsecond=0,
        )

    def _reset_wip(self, bucket_start: datetime, first_price: float) -> None:
        self._wip_start = bucket_start
        self._wip_open = first_price
        self._wip_high = first_price
        self._wip_low = first_price
        self._wip_close = first_price
        self._wip_volume = 1
