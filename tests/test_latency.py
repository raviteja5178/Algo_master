"""LatencyTracker: back-filled CANDLE_COMPLETED must use a real monotonic reading."""
from __future__ import annotations

import time

from utils.latency import LatencyTracker


def test_backfilled_candle_checkpoint_gives_sane_signal_processing_ms():
    t0 = time.monotonic_ns()
    tr = LatencyTracker("T")
    tr.mark_at("CANDLE_COMPLETED", "2026-10-19T10:15:00+05:30", t0)
    time.sleep(0.01)
    tr.mark("SIGNAL_CONFIRMED")
    ms = tr.report()["intervals_ms"]["signal_processing_ms"]
    assert 5 <= ms < 5_000      # regression: monotonic 0 gave ~uptime (billions of ms)
