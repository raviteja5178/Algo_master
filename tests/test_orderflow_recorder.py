"""Order-flow tick recorder: row format, sampling, isolation from trading, failure handling."""
from __future__ import annotations

import csv
import struct
import threading
import time
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from kiteconnect import KiteTicker

from market.orderflow_recorder import COLUMNS, OrderFlowRecorder, build_row, default_directory
from market.websocket_client import WebSocketClient
from utils.time_utils import IST

FUT_TOKEN = 221330181


def _ist(h, m, s=0, day=19) -> datetime:
    return IST.localize(datetime(2026, 10, day, h, m, s))


def _real_tick(volume=28900, ltp=74370.10, ltq=20) -> dict:
    """Build a 184-byte MODE_FULL packet and decode it with the real KiteTicker parser."""
    def lvl(q, p, o):
        return struct.pack(">IIHH", q, int(round(p * 100)), o, 0)

    pkt = struct.pack(">IIIIIII", FUT_TOKEN, int(round(ltp * 100)), ltq, 7440000, volume, 1200, 900)
    pkt += struct.pack(">IIII", 7500000, 7520000, 7400000, 7480000)
    pkt += struct.pack(">IIIII", 1760850000, 97920, 98500, 94000, 1760850001)
    for i in range(5):
        pkt += lvl(20 * (i + 1), 74369.0 - i * 5, 1 + i)
    for i in range(5):
        pkt += lvl(20 * (i + 1), 74375.0 + i * 5, 1 + i)
    assert len(pkt) == 184
    data = struct.pack(">HH", 1, len(pkt)) + pkt
    return KiteTicker("k", "t")._parse_binary(data)[0]


def _wait(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def _rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _recorder(tmp_path, clock, **kw):
    return OrderFlowRecorder(tmp_path, "SENSEX26OCTFUT", now_fn=lambda: clock[0], **kw)


# ── row format ────────────────────────────────────────────────────────────────

def test_build_row_matches_columns_and_real_parser_output():
    row = build_row(_real_tick(), "T", "SENSEX26OCTFUT", _ist(10, 30))
    assert len(row) == len(COLUMNS)
    d = dict(zip(COLUMNS, row))
    assert d["kind"] == "T" and d["symbol"] == "SENSEX26OCTFUT"
    assert d["ltp"] == 74370.1 and d["ltq"] == 20 and d["volume"] == 28900
    assert d["buy_qty"] == 1200 and d["sell_qty"] == 900 and d["oi"] == 97920
    assert d["b1p"] == 74369.0 and d["b1q"] == 20 and d["b5p"] == 74349.0
    assert d["a1p"] == 74375.0 and d["a5q"] == 100 and d["a5p"] == 74395.0


def test_build_row_tolerates_missing_depth():
    row = build_row({"last_price": 1.0, "volume_traded": 5}, "T", "X", _ist(10, 0))
    assert len(row) == len(COLUMNS)
    assert dict(zip(COLUMNS, row))["b1p"] == ""


# ── recording behaviour ───────────────────────────────────────────────────────

def test_writes_header_and_trade_row(tmp_path):
    clock = [_ist(10, 30)]
    rec = _recorder(tmp_path, clock)
    rec.record(_real_tick())
    rec.close()
    rows = _rows(tmp_path / "ticks_2026-10-19.csv")
    assert len(rows) == 1 and rows[0]["kind"] == "T" and rows[0]["ltp"] == "74370.1"
    assert list(rows[0].keys()) == COLUMNS


def test_volume_change_is_trade_and_quiet_repeat_is_sampled(tmp_path):
    clock = [_ist(10, 30)]
    rec = _recorder(tmp_path, clock, depth_sample_seconds=3600.0)   # never samples in this test
    rec.record(_real_tick(volume=100))
    rec.record(_real_tick(volume=100))       # same volume, inside sample window -> skipped
    rec.record(_real_tick(volume=120))       # volume moved -> trade row
    rec.close()
    kinds = [r["kind"] for r in _rows(tmp_path / "ticks_2026-10-19.csv")]
    assert kinds == ["T", "T"]
    assert rec.skipped == 1


def test_depth_row_after_quiet_period(tmp_path):
    clock = [_ist(10, 30)]
    rec = _recorder(tmp_path, clock, depth_sample_seconds=0.0)       # sample immediately
    rec.record(_real_tick(volume=100))
    rec.record(_real_tick(volume=100))
    rec.close()
    assert [r["kind"] for r in _rows(tmp_path / "ticks_2026-10-19.csv")] == ["T", "D"]


def test_ignores_ticks_outside_session_and_ltp_packets(tmp_path):
    clock = [_ist(9, 10)]
    rec = _recorder(tmp_path, clock)
    rec.record(_real_tick())                                         # pre-open
    clock[0] = _ist(15, 31)
    rec.record(_real_tick())                                         # post-close
    clock[0] = _ist(10, 0)
    rec.record({"instrument_token": FUT_TOKEN, "last_price": 1.0})   # LTP-mode: no volume field
    rec.close()
    assert not (tmp_path / "ticks_2026-10-19.csv").exists()
    assert rec.skipped == 3 and rec.written == 0


def test_rolls_to_new_file_on_new_day_and_appends_without_second_header(tmp_path):
    clock = [_ist(10, 0, day=19)]
    rec = _recorder(tmp_path, clock)
    rec.record(_real_tick(volume=1))
    assert _wait(lambda: rec.written == 1)
    clock[0] = _ist(10, 0, day=20)
    rec.record(_real_tick(volume=2))
    rec.close()
    assert len(_rows(tmp_path / "ticks_2026-10-19.csv")) == 1
    assert len(_rows(tmp_path / "ticks_2026-10-20.csv")) == 1

    rec2 = OrderFlowRecorder(tmp_path, "SENSEX26OCTFUT", now_fn=lambda: _ist(11, 0, day=20))
    rec2.record(_real_tick(volume=3))
    rec2.close()
    text = (tmp_path / "ticks_2026-10-20.csv").read_text(encoding="utf-8")
    assert text.count("recv_ts") == 1 and len(_rows(tmp_path / "ticks_2026-10-20.csv")) == 2


# ── failure isolation ─────────────────────────────────────────────────────────

def test_record_never_raises_on_garbage(tmp_path):
    rec = _recorder(tmp_path, [_ist(10, 0)])
    for bad in (None, {}, {"volume_traded": object(), "depth": 5}, "tick", {"depth": {"buy": 3}}):
        rec.record(bad)          # type: ignore[arg-type]
    rec.close()


def test_full_queue_drops_instead_of_blocking(tmp_path):
    clock = [_ist(10, 0)]
    rec = _recorder(tmp_path, clock, max_queue=1)
    gate = threading.Event()
    # stall the writer so the queue cannot drain
    rec._write = lambda batch: gate.wait(5)            # type: ignore[method-assign]
    t0 = time.monotonic()
    for v in range(1, 200):
        rec.record(_real_tick(volume=v))
    assert time.monotonic() - t0 < 1.0                  # never blocked the caller
    assert rec.dropped > 0
    gate.set()
    rec.close()


def test_disk_failure_is_counted_not_raised(tmp_path):
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x")                              # a FILE where the directory should be
    rec = OrderFlowRecorder(blocker / "sub", "X", now_fn=lambda: _ist(10, 0))
    rec.record(_real_tick(volume=1))
    rec.close()
    assert rec.errors >= 1 and rec.written == 0


def test_close_is_idempotent_and_record_after_close_is_noop(tmp_path):
    rec = _recorder(tmp_path, [_ist(10, 0)])
    rec.close()
    rec.close()
    rec.record(_real_tick())
    assert rec.written == 0


def test_default_directory():
    assert default_directory("").parts[-3:] == ("research", "data", "orderflow")
    assert str(default_directory("  D:/x  ")).replace("\\", "/") == "D:/x"


# ── WebSocketClient isolation ─────────────────────────────────────────────────

def _ws_client() -> WebSocketClient:
    c = object.__new__(WebSocketClient)
    c._kite = MagicMock()
    c._ticker = MagicMock()
    c._tokens = {265}
    c._option_tokens = set()
    c._flow_tokens = set()
    c._flow_sink = None
    c._ltp_callbacks = []
    c._order_update_callbacks = []
    c._stale_callbacks = []
    c._last_tick_time = 0.0
    c._last_option_tick_time = 0.0
    c._stale_exhausted = False
    c._stale_thread = None
    c._running = True
    return c


def test_flow_ticks_go_to_sink_only_never_to_trading_callbacks():
    c = _ws_client()
    ltp_cb, sink = MagicMock(), MagicMock()
    c.on_ltp(ltp_cb)
    c.add_flow_token(FUT_TOKEN, sink)
    c._on_ticks(None, [_real_tick()])
    sink.assert_called_once()
    ltp_cb.assert_not_called()
    assert FUT_TOKEN not in c._tokens and FUT_TOKEN not in c._option_tokens
    assert c._last_option_tick_time == 0.0                # stale-feed clock untouched


def test_normal_ticks_still_reach_ltp_callbacks_with_flow_enabled():
    c = _ws_client()
    ltp_cb, sink = MagicMock(), MagicMock()
    c.on_ltp(ltp_cb)
    c.add_flow_token(FUT_TOKEN, sink)
    c._on_ticks(None, [{"instrument_token": 265, "last_price": 74400.0}])
    ltp_cb.assert_called_once_with(265, 74400.0)
    sink.assert_not_called()


def test_sink_exception_does_not_break_tick_processing():
    c = _ws_client()
    ltp_cb = MagicMock()
    c.on_ltp(ltp_cb)
    c.add_flow_token(FUT_TOKEN, MagicMock(side_effect=RuntimeError("boom")))
    c._on_ticks(None, [_real_tick(), {"instrument_token": 265, "last_price": 74400.0}])
    ltp_cb.assert_called_once_with(265, 74400.0)


def test_flow_token_subscribed_full_mode_and_on_reconnect():
    c = _ws_client()
    c._ticker.ws = object()
    c._ticker.MODE_FULL = "full"
    c.add_flow_token(FUT_TOKEN, MagicMock())
    c._ticker.subscribe.assert_called_with([FUT_TOKEN])
    c._ticker.set_mode.assert_called_with("full", [FUT_TOKEN])

    ws = MagicMock()
    ws.MODE_FULL, ws.MODE_LTP = "full", "ltp"
    c._on_connect(ws, None)
    subscribed = [t for call in ws.subscribe.call_args_list for t in call.args[0]]
    assert FUT_TOKEN in subscribed
    ws.set_mode.assert_any_call("full", [FUT_TOKEN])
    assert FUT_TOKEN not in c._option_tokens


def test_subscribe_failure_is_swallowed():
    c = _ws_client()
    c._ticker.ws = object()
    c._ticker.subscribe.side_effect = RuntimeError("ws down")
    c.add_flow_token(FUT_TOKEN, MagicMock())               # must not raise
    assert FUT_TOKEN in c._flow_tokens
