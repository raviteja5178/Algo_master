"""
Millisecond-precision trade lifecycle latency tracker.

Records named checkpoints (wall-clock + monotonic) and emits a structured
LATENCY_REPORT log when the lifecycle is complete.  One LatencyTracker
instance per trade entry attempt — discard and create a new one for the
next trade.

Checkpoint names (in expected order):
    CANDLE_COMPLETED        — 5m candle closed, evaluation begins
    SIGNAL_CONFIRMED        — all strategy conditions passed
    BUY_REQUESTED           — place_buy_order() called
    ORDER_ID_RECEIVED       — broker returned an order_id (REST ACK)
    EXCHANGE_COMPLETE       — exchange COMPLETE status received
                              (WebSocket postback or REST poll)
    FILL_PRICE_CONFIRMED    — actual fill average_price > 0
    SL_REQUESTED            — place_stop_order() called
    SL_ACKNOWLEDGED         — broker returned a stop order_id

Derived report metrics:
    signal_processing_ms    SIGNAL_CONFIRMED − CANDLE_COMPLETED
    api_submission_ms       ORDER_ID_RECEIVED − BUY_REQUESTED
    exchange_fill_ms        EXCHANGE_COMPLETE − ORDER_ID_RECEIVED
    fill_confirmation_ms    FILL_PRICE_CONFIRMED − EXCHANGE_COMPLETE
    unprotected_window_ms   SL_ACKNOWLEDGED − FILL_PRICE_CONFIRMED
    total_signal_to_sl_ms   SL_ACKNOWLEDGED − SIGNAL_CONFIRMED

Price observations (LTP vs fill, for slippage attribution):
    sensex_ltp_at_signal    — SENSEX spot when signal fired
    option_ltp_at_signal    — option bid/ask when order was sent
    fill_price              — actual average_price from broker
    sensex_ltp_at_fill      — SENSEX spot when fill confirmed

These allow distinguishing:
    bot latency       (api_submission_ms + fill_confirmation_ms)
    exchange latency  (exchange_fill_ms)
    market slippage   (fill_price − option_ltp_at_signal)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

from utils.logging_config import log_event
from utils.time_utils import now_ist

logger = logging.getLogger(__name__)


class LatencyTracker:
    """
    Single-trade lifecycle timer.

    Usage:
        tracker = LatencyTracker(trade_id="TRADE_CE_20250918_092500_abc123")
        tracker.mark("CANDLE_COMPLETED")
        ...
        tracker.set_price("sensex_ltp_at_signal", 74310.0)
        tracker.mark("SIGNAL_CONFIRMED")
        ...
        tracker.report()   # emits LATENCY_REPORT log
    """

    # Ordered pairs used to compute derived intervals.
    # (metric_name, from_checkpoint, to_checkpoint)
    _INTERVALS = [
        ("signal_processing_ms",  "CANDLE_COMPLETED",      "SIGNAL_CONFIRMED"),
        ("api_submission_ms",     "BUY_REQUESTED",          "ORDER_ID_RECEIVED"),
        ("exchange_fill_ms",      "ORDER_ID_RECEIVED",      "EXCHANGE_COMPLETE"),
        ("fill_confirmation_ms",  "EXCHANGE_COMPLETE",      "FILL_PRICE_CONFIRMED"),
        ("unprotected_window_ms", "FILL_PRICE_CONFIRMED",   "SL_ACKNOWLEDGED"),
        ("total_signal_to_sl_ms", "SIGNAL_CONFIRMED",       "SL_ACKNOWLEDGED"),
    ]

    def __init__(self, trade_id: str = "") -> None:
        self.trade_id = trade_id
        # {checkpoint_name: (wall_clock_isoformat, monotonic_ns)}
        self._checkpoints: dict[str, tuple[str, int]] = {}
        self._prices: dict[str, float] = {}

    def mark(self, checkpoint: str) -> None:
        """Record a checkpoint at the current instant."""
        self._checkpoints[checkpoint] = (now_ist().isoformat(), time.monotonic_ns())
        logger.debug(
            "[LATENCY] %s | checkpoint=%s | t=%s",
            self.trade_id, checkpoint, self._checkpoints[checkpoint][0],
        )

    def set_price(self, key: str, value: float) -> None:
        """Store a price observation for slippage analysis."""
        self._prices[key] = value

    def report(self) -> dict:
        """
        Compute all intervals and emit a structured LATENCY_REPORT log.
        Returns the full report dict (useful for tests).
        """
        report: dict = {"trade_id": self.trade_id, "checkpoints": {}, "intervals_ms": {}}

        # Raw checkpoint wall-clock times
        for name, (wall, _) in self._checkpoints.items():
            report["checkpoints"][name] = wall

        # Derived interval durations in milliseconds
        for metric, start_cp, end_cp in self._INTERVALS:
            start = self._checkpoints.get(start_cp)
            end   = self._checkpoints.get(end_cp)
            if start and end:
                ms = (end[1] - start[1]) / 1_000_000
                report["intervals_ms"][metric] = round(ms, 3)

        # Price observations
        report.update(self._prices)

        log_event(logger, "LATENCY_REPORT", **{
            "trade_id": self.trade_id,
            **{f"cp_{k}": v for k, v in report["checkpoints"].items()},
            **{k: v for k, v in report["intervals_ms"].items()},
            **self._prices,
        })

        return report
