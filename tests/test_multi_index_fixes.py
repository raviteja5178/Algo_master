"""Tests for multi-index exchange routing, EOD pricing, REST fallback and log tagging."""

from __future__ import annotations

import logging
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from execution.eod_manager import EODManager
from execution.paper_broker import PaperBroker
from market.websocket_client import STALE_TIMEOUT_SECONDS, WebSocketClient
from utils.exchange_utils import option_exchange, option_quote_key
from utils.logging_config import _UnderlyingFilter, log_underlying


# ── Exchange routing ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("sym,exch", [
    ("SENSEX26N1281500CE", "BFO"),
    ("NIFTY26N1225000PE", "NFO"),
    ("BANKNIFTY26N1256000CE", "NFO"),
    ("FINNIFTY26N1227000CE", "NFO"),
    ("BFO:SENSEX26N1281500CE", "BFO"),
])
def test_option_exchange(sym, exch):
    assert option_exchange(sym) == exch


def test_option_quote_key():
    assert option_quote_key("FINNIFTY26N1227000CE") == "NFO:FINNIFTY26N1227000CE"
    assert option_quote_key("SENSEX26N1281500CE") == "BFO:SENSEX26N1281500CE"


def test_order_manager_uses_symbol_exchange():
    from execution.order_manager import OrderManager

    om = object.__new__(OrderManager)
    om._kite = MagicMock()
    om._kite.TRANSACTION_TYPE_SELL = "SELL"
    om._kite.ORDER_TYPE_SL = "SL"
    om._kite.PRODUCT_MIS = "MIS"
    om._kite.VARIETY_REGULAR = "regular"
    om.place_stop_order("NIFTY26N1225000CE", 75, 100.0)
    assert om._kite.place_order.call_args.kwargs["exchange"] == "NFO"
    om.place_stop_order("SENSEX26N1281500CE", 20, 100.0)
    assert om._kite.place_order.call_args.kwargs["exchange"] == "BFO"


# ── EOD exit pricing ─────────────────────────────────────────────────────────

class _Store:
    def __init__(self):
        self.closed = None

    def mark_trade_closed(self, **kw):
        self.closed = kw


def test_eod_exit_uses_price_hint_not_entry_price():
    broker = PaperBroker()
    sym = "SENSEX26N1281500CE"
    broker.place_buy_order(sym, 20, ltp_hint=570.35)
    store = _Store()
    eod = EODManager(broker, store)
    assert eod.run_eod_exit(sym, 20, "T1", None, 570.35, ltp_hint=612.0)
    assert store.closed["exit_price"] == 612.0
    assert store.closed["pnl"] == pytest.approx((612.0 - 570.35) * 20)


# ── WebSocket: dead feed must not look healthy after reconnect bookkeeping ───

def _ws() -> WebSocketClient:
    c = object.__new__(WebSocketClient)
    c._ticker = MagicMock()
    c._tokens = set()
    c._option_tokens = {99999}
    c._last_tick_time = time.monotonic()
    c._last_option_tick_time = time.monotonic()
    c._last_real_option_tick = time.monotonic() - (STALE_TIMEOUT_SECONDS * 2 + 5)
    return c


def test_feed_stays_dead_after_close_resets_stale_clock():
    c = _ws()
    c._on_close(None, 1006, "closed")      # resets the stale-monitor clock
    assert c._last_option_tick_time > c._last_real_option_tick
    assert c.option_feed_ok is False       # but the feed is still dead
    assert c.option_feed_age > STALE_TIMEOUT_SECONDS * 2


def test_real_option_tick_revives_feed():
    c = _ws()
    c._ltp_callbacks = []
    c._flow_tokens = set()
    c._on_ticks(None, [{"instrument_token": 99999, "last_price": 100.0}])
    assert c.option_feed_ok is True


def test_reconnect_does_not_call_close_which_kills_autoretry(monkeypatch):
    import twisted.internet.reactor as reactor

    called = []
    monkeypatch.setattr(reactor, "callFromThread", lambda fn, *a, **k: called.append(fn))
    c = _ws()
    c._ticker.is_connected.return_value = True
    c.reconnect()
    c._ticker.close.assert_not_called()
    assert called == [c._ticker._close]


# ── Per-index log tagging ────────────────────────────────────────────────────

def _rec(msg="hello"):
    return logging.LogRecord("x", logging.INFO, __file__, 1, msg, (), None)


def test_log_filter_tags_only_inside_context():
    f = _UnderlyingFilter()
    r = _rec()
    f.filter(r)
    assert r.getMessage() == "hello"
    with log_underlying("NIFTY"):
        r = _rec()
        f.filter(r)
        f.filter(r)                         # idempotent
        assert r.getMessage() == "[NIFTY] hello"
    r = _rec()
    f.filter(r)
    assert r.getMessage() == "hello"


def test_ui_log_tail_filters_other_indices(tmp_path, monkeypatch):
    from ui import app as ui_app

    log = tmp_path / "bot.log"
    log.write_text(
        "t | INFO | m | [SENSEX] a\n"
        "t | INFO | m | [NIFTY] b\n"
        "t | INFO | m | global\n"
        "t | INFO | m | [FINNIFTY] c\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ui_app, "_BOT_LOG", log)
    out = ui_app._read_log_tail(50, "NIFTY")
    assert any("[NIFTY] b" in l for l in out)
    assert any("global" in l for l in out)
    assert not any("[SENSEX]" in l or "[FINNIFTY]" in l for l in out)
    assert len(ui_app._read_log_tail(50)) == 4
