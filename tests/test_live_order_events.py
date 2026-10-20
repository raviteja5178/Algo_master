"""Tests for the LIVE order-event log, rejection reason and /api/live/* endpoints."""
import importlib
import sys
from unittest.mock import patch

import pytest

from persistence import models


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(models.settings, "DB_PATH", str(tmp_path / "t.db"))
    models.init_db()
    return str(tmp_path / "t.db")


def test_add_and_fetch_events_including_rejection(db):
    models.add_live_order_event(
        "ENTRY_REJECTED", "2026-10-16T10:05:00+05:30",
        symbol="SENSEX26O2274500CE", order_id="261016150407890",
        status="REJECTED", reason="Insufficient funds. Margin required: 21619.00",
        qty=20, signal="CE_VWAP",
    )
    models.add_live_order_event(
        "ENTRY_FILLED", "2026-10-16T09:25:01+05:30", trade_id="T1",
        symbol="SENSEX26O2274200CE", price=539.9, atr=55.0,
        sl_points=41.3, be_points=36.0, tsl_points=20.0, target_points=82.0,
    )
    rows = models.fetch_live_order_events(date="2026-10-16")
    assert {r["event_type"] for r in rows} == {"ENTRY_FILLED", "ENTRY_REJECTED"}
    rej = next(r for r in rows if r["event_type"] == "ENTRY_REJECTED")
    assert "Insufficient funds" in rej["reason"]
    assert '"signal": "CE_VWAP"' in rej["extra"]
    fill = next(r for r in rows if r["event_type"] == "ENTRY_FILLED")
    assert (fill["atr"], fill["sl_points"], fill["be_points"]) == (55.0, 41.3, 36.0)
    assert models.fetch_live_order_events(trade_id="T1")[0]["symbol"] == "SENSEX26O2274200CE"
    assert models.fetch_live_dates() == ["2026-10-16"]


def test_add_event_never_raises(monkeypatch):
    monkeypatch.setattr(models.settings, "DB_PATH", "Z:/does/not/exist/x.db")
    models.add_live_order_event("ENTRY_SENT", "2026-10-16T10:00:00")   # must not raise


def test_fetch_live_trades_excludes_paper(db):
    models.upsert_trade({"trade_id": "L", "strategy_type": "CE", "signal_timestamp": "s",
                         "option_symbol": "X", "instrument_token": 1, "quantity": 20,
                         "entry_order_id": "123", "entry_time": "2026-10-16T09:25:00",
                         "trade_mode": "LIVE", "be_points": 36.0})
    models.upsert_trade({"trade_id": "P", "strategy_type": "CE", "signal_timestamp": "s",
                         "option_symbol": "X", "instrument_token": 1, "quantity": 20,
                         "entry_order_id": "PAPER_1", "entry_time": "2026-10-16T09:26:00",
                         "trade_mode": "SHADOW"})
    rows = models.fetch_live_trades("2026-10-16")
    assert [r["trade_id"] for r in rows] == ["L"]
    assert rows[0]["be_points"] == 36.0


def test_wait_for_fill_returns_rejection_reason():
    from execution.order_manager import OrderManager
    import inspect
    src = inspect.getsource(OrderManager._wait_for_fill)
    assert '"reason": o.get("status_message"' in src


@pytest.fixture()
def client(db, monkeypatch):
    ui_app = importlib.import_module("ui.app")
    monkeypatch.setattr(ui_app, "_db_path", lambda: db)
    monkeypatch.setattr(ui_app, "_get_kite_safe", lambda: None)
    ui_app.app.config["TESTING"] = True
    return ui_app.app.test_client()


def test_live_api_endpoints(client, db):
    models.upsert_trade({"trade_id": "L", "strategy_type": "CE_VWAP", "signal_timestamp": "s",
                         "option_symbol": "SENSEX26O2274200CE", "instrument_token": 1,
                         "quantity": 20, "entry_order_id": "999", "entry_price": 500.0,
                         "entry_time": "2026-10-16T09:25:00+05:30", "status": "OPEN",
                         "trade_mode": "LIVE", "sl_points": 40.0, "atr_value": 55.0})
    models.add_live_order_event("ENTRY_REJECTED", "2026-10-16T10:05:00+05:30",
                                symbol="S", reason="Insufficient funds", status="REJECTED")
    t = client.get("/api/live/trades?date=2026-10-16").get_json()
    assert len(t) == 1 and t[0]["atr_value"] == 55.0
    assert client.get("/api/live/dates").get_json() == ["2026-10-16"]
    ev = client.get("/api/live/events?date=2026-10-16&type=ENTRY_REJECTED").get_json()
    assert len(ev) == 1 and ev[0]["reason"] == "Insufficient funds"
    act = client.get("/api/live/active").get_json()
    assert act["option_symbol"] == "SENSEX26O2274200CE"
    assert client.get("/live").status_code == 200
