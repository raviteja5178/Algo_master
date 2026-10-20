"""
Passive order-flow tick recorder (research data collection only).

Why: Kite's historical API has no bid/ask and no depth, and expired futures vanish from
the instrument master, so true order-flow research needs ticks captured live.  This module
writes the SENSEX future's raw MODE_FULL ticks to daily CSV files for later replay:

    kind    "T"  cumulative volume changed since the previous row (a trade happened)
            "D"  depth snapshot after a quiet ``depth_sample_seconds``
    ltp / ltq / volume (cumulative) / atp / buy_qty / sell_qty / oi
    b1p,b1q .. b5p,b5q   best 5 bids       a1p,a1q .. a5p,a5q   best 5 asks

Every "T" row carries the book at that instant, so the aggressor side can be inferred
offline (ltp >= ask1 -> buyer, ltp <= bid1 -> seller) without re-subscribing.

Isolation contract (this must never affect trading):
    * ``record()`` is called from the WebSocket thread.  It does no I/O: it does a
      ``put_nowait`` onto a bounded queue and returns.  It never raises.
    * A single daemon writer thread owns the file handle.  If the queue is full the tick
      is dropped and counted; if the disk fails the rows are dropped and counted.
    * Nothing in the entry/exit path reads this data.
"""
from __future__ import annotations

import csv
import logging
import queue
import threading
import time
from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Callable

from utils.logging_config import log_event
from utils.time_utils import now_ist

logger = logging.getLogger(__name__)

_SESSION_OPEN = dtime(9, 15)
_SESSION_CLOSE = dtime(15, 30)
_LEVELS = 5
_BATCH_MAX = 5000
_STATS_LOG_INTERVAL_S = 600.0
_STOP = object()

COLUMNS: list[str] = (
    ["recv_ts", "exch_ts", "kind", "symbol", "ltp", "ltq", "volume", "atp", "buy_qty", "sell_qty", "oi"]
    + [f"b{i}{f}" for i in range(1, _LEVELS + 1) for f in ("p", "q")]
    + [f"a{i}{f}" for i in range(1, _LEVELS + 1) for f in ("p", "q")]
)


def default_directory(configured: str = "") -> Path:
    """Configured directory, else ``<repo>/research/data/orderflow``."""
    if configured.strip():
        return Path(configured.strip())
    return Path(__file__).resolve().parent.parent / "research" / "data" / "orderflow"


def _level(side: object, i: int, key: str):
    try:
        return side[i][key]  # type: ignore[index]
    except (IndexError, KeyError, TypeError):
        return ""


def build_row(tick: dict, kind: str, symbol: str, recv: datetime) -> list:
    """Flatten one KiteTicker MODE_FULL tick into a CSV row (order = COLUMNS)."""
    depth = tick.get("depth") or {}
    buys, sells = depth.get("buy"), depth.get("sell")
    exch = tick.get("exchange_timestamp")
    row: list = [
        recv.isoformat(timespec="milliseconds"),
        exch.isoformat() if hasattr(exch, "isoformat") else "",
        kind,
        symbol,
        tick.get("last_price", ""),
        tick.get("last_traded_quantity", ""),
        tick.get("volume_traded", ""),
        tick.get("average_traded_price", ""),
        tick.get("total_buy_quantity", ""),
        tick.get("total_sell_quantity", ""),
        tick.get("oi", ""),
    ]
    for side in (buys, sells):
        for i in range(_LEVELS):
            row.append(_level(side, i, "price"))
            row.append(_level(side, i, "quantity"))
    return row


class OrderFlowRecorder:
    def __init__(
        self,
        directory: Path,
        symbol: str,
        *,
        depth_sample_seconds: float = 1.0,
        max_queue: int = 100_000,
        now_fn: Callable[[], datetime] = now_ist,
    ) -> None:
        self._dir = Path(directory)
        self._symbol = symbol
        self._sample = max(0.0, float(depth_sample_seconds))
        self._now_fn = now_fn
        self._q: queue.Queue = queue.Queue(maxsize=max_queue)

        self._last_volume: float | None = None
        self._last_row_mono: float = float("-inf")

        self._file = None
        self._writer = None
        self._file_day: date | None = None

        self.written = 0
        self.dropped = 0
        self.skipped = 0
        self.errors = 0
        self._last_stats_log = time.monotonic()
        self._last_error_log = float("-inf")

        self._closed = False
        self._thread = threading.Thread(target=self._run, name="orderflow-writer", daemon=True)
        self._thread.start()

    # ── called from the WebSocket thread ──────────────────────────────────────

    def record(self, tick: dict) -> None:
        """Queue one tick.  Non-blocking and never raises."""
        try:
            self._record(tick)
        except Exception:
            self.errors += 1

    def _record(self, tick: dict) -> None:
        if self._closed:
            return
        now = self._now_fn()
        if not (_SESSION_OPEN <= now.time() < _SESSION_CLOSE):
            self.skipped += 1
            return
        volume = tick.get("volume_traded")
        if volume is None:                      # LTP/quote-mode packet: nothing to record
            self.skipped += 1
            return

        mono = time.monotonic()
        if self._last_volume is None or volume != self._last_volume:
            kind = "T"
        elif mono - self._last_row_mono >= self._sample:
            kind = "D"
        else:
            self.skipped += 1
            return

        row = build_row(tick, kind, self._symbol, now)
        try:
            self._q.put_nowait((now.date(), row))
        except queue.Full:
            self.dropped += 1
            return
        self._last_volume = volume
        self._last_row_mono = mono

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def close(self, timeout: float = 5.0) -> None:
        """Flush and stop the writer thread.  Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        try:
            self._q.put(_STOP, timeout=2.0)
        except queue.Full:
            pass
        self._thread.join(timeout)
        log_event(logger, "ORDERFLOW_RECORDER_STOPPED", **self.stats())

    def stats(self) -> dict:
        return {"written": self.written, "dropped": self.dropped,
                "skipped": self.skipped, "errors": self.errors, "queued": self._q.qsize()}

    # ── writer thread ─────────────────────────────────────────────────────────

    def _run(self) -> None:
        stop = False
        while not stop:
            batch: list = []
            try:
                first = self._q.get(timeout=1.0)
            except queue.Empty:
                first = None
            if first is _STOP:
                stop = True
            elif first is not None:
                batch.append(first)
                while len(batch) < _BATCH_MAX:
                    try:
                        nxt = self._q.get_nowait()
                    except queue.Empty:
                        break
                    if nxt is _STOP:
                        stop = True
                        break
                    batch.append(nxt)
            if batch:
                self._write(batch)
            self._maybe_log_stats()
        self._close_file()

    def _write(self, batch: list) -> None:
        try:
            for day, row in batch:
                if self._file_day != day or self._writer is None:
                    self._open(day)
                self._writer.writerow(row)       # type: ignore[union-attr]
                self.written += 1
            self._file.flush()                    # type: ignore[union-attr]
        except Exception as exc:
            self.errors += len(batch)
            self._close_file()
            now = time.monotonic()
            if now - self._last_error_log > 60.0:
                self._last_error_log = now
                logger.warning("Order-flow recorder write failed (rows dropped): %s", exc)

    def _open(self, day: date) -> None:
        self._close_file()
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"ticks_{day.isoformat()}.csv"
        is_new = not path.exists() or path.stat().st_size == 0
        self._file = open(path, "a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._file_day = day
        if is_new:
            self._writer.writerow(COLUMNS)

    def _close_file(self) -> None:
        try:
            if self._file is not None:
                self._file.close()
        except Exception:
            pass
        self._file = None
        self._writer = None
        self._file_day = None

    def _maybe_log_stats(self) -> None:
        now = time.monotonic()
        if now - self._last_stats_log >= _STATS_LOG_INTERVAL_S:
            self._last_stats_log = now
            log_event(logger, "ORDERFLOW_RECORDER_STATS", **self.stats())
