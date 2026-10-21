"""
Expiry-day iron butterfly: pure logic, the SHADOW runner (entry, stop, time
exit, restart, skips) and the LIVE refusal.
"""

from __future__ import annotations

import json
from datetime import datetime
from itertools import count
from unittest.mock import MagicMock

import pytest

from config import settings
from strategies import expiry_fly as fly
from utils.time_utils import IST


# ── pure logic ───────────────────────────────────────────────────────────────

def _q(bid, ask, last=None):
    return fly.Quote(bid, ask, last if last is not None else (bid + ask) / 2)


def test_quote_from_kite_reads_best_depth_and_last():
    q = fly.Quote.from_kite({"last_price": 101.0, "depth": {
        "buy": [{"price": 100.0}, {"price": 99.0}], "sell": [{"price": 102.5}]}})
    assert (q.bid, q.ask, q.last, q.mid) == (100.0, 102.5, 101.0, 101.25)


def test_quote_without_depth_falls_back_to_last():
    q = fly.Quote.from_kite({"last_price": 50.0})
    assert q.mid == 50.0 and q.buy_px() == 50.0
    assert q.sell_px() == fly.MIN_PX and not q.usable_for_sell()


def test_strikes_atm_and_wings():
    s = fly.pick_strikes(75049.0, 1000)
    assert s == {"SC": (75000, "CE"), "SP": (75000, "PE"),
                 "LC": (76000, "CE"), "LP": (74000, "PE")}
    assert fly.pick_strikes(75051.0, 500)["SC"][0] == 75100


def test_fills_pay_the_spread_and_credit_is_net():
    quotes = {"SC": _q(300, 302), "SP": _q(290, 292), "LC": _q(60, 62), "LP": _q(50, 52)}
    f = fly.entry_fills(quotes)
    assert f == {"SC": 300, "SP": 290, "LC": 62, "LP": 52}
    assert fly.net_credit(f) == 476
    assert fly.net_credit(fly.entry_fills(quotes, 1.0)) == 476 - 4     # 1 pt on each of 4 legs
    out = fly.exit_fills(quotes)
    assert out == {"SC": 302, "SP": 292, "LC": 60, "LP": 50}
    assert fly.buyback_cost(out) == 484


def test_stop_and_pnl():
    assert fly.stop_level(400.0, 0.5) == 600.0
    assert fly.pnl(476, 484, 20) == -160.0
    assert fly.pnl(476, 100, 20) == 7520.0


# ── runner ───────────────────────────────────────────────────────────────────

SYMS = {("CE", 75000): "C75000", ("PE", 75000): "P75000",
        ("CE", 76000): "C76000", ("PE", 74000): "P74000"}


class Clock:
    def __init__(self, hh, mm, day=(2026, 10, 22)):
        self.t = IST.localize(datetime(*day, hh, mm))

    def __call__(self):
        return self.t

    def set(self, hh, mm):
        self.t = self.t.replace(hour=hh, minute=mm)


class FakeKite:
    """quote() returns the prices set in .book: {symbol: (bid, ask)}."""

    def __init__(self):
        self.book = {"C75000": (300, 302), "P75000": (290, 292),
                     "C76000": (60, 62), "P74000": (50, 52)}
        self.fail = False

    def quote(self, keys):
        if self.fail:
            raise RuntimeError("kite down")
        out = {}
        for k in keys:
            if k == "NSE:INDIA VIX":
                out[k] = {"last_price": 14.2}
                continue
            sym = k.split(":", 1)[1]
            bid, ask = self.book[sym]
            out[k] = {"last_price": (bid + ask) / 2,
                      "depth": {"buy": [{"price": bid}], "sell": [{"price": ask}]}}
        return out


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "fly.db"))
    monkeypatch.setattr(settings, "TRADING_MODE", "SHADOW")
    monkeypatch.setattr(settings, "ENABLE_EXPIRY_FLY", True)
    for k, v in dict(FLY_ENTRY_TIME="10:30", FLY_EXIT_TIME="15:10", FLY_WING_POINTS=1000,
                     FLY_STOP_PCT=0.5, FLY_QUANTITY=20, FLY_MIN_CREDIT=50.0,
                     FLY_SKIP_DATES="", FLY_EXTRA_SLIPPAGE_PTS=0.0).items():
        monkeypatch.setattr(settings, k, v)
    import execution.fly_runner as fr
    monkeypatch.setattr(fr, "notify", MagicMock())
    ticker = count()
    monkeypatch.setattr(fr._time, "monotonic", lambda: next(ticker) * 100.0)   # never throttled
    from persistence.models import init_db
    init_db()
    kite, clock = FakeKite(), Clock(10, 30)
    state = {"expiry": True, "spot": 75012.0}

    def options(expiry, opt):
        return [{"strike": float(k), "tradingsymbol": s} for (o, k), s in SYMS.items() if o == opt]

    def make():
        return fr.ExpiryFlyRunner(lambda: kite, options, lambda: state["expiry"],
                                  lambda: state["spot"], now_fn=clock)
    return make, kite, clock, state


def _row(day="2026-10-22"):
    from persistence.trade_store import fly_get
    return fly_get(day)


def test_enters_on_expiry_day_with_real_quotes(env):
    make, kite, clock, state = env
    make().tick()
    r = _row()
    assert r["status"] == "OPEN" and r["quantity"] == 20
    assert r["credit"] == pytest.approx(476.0)          # 300+290-62-52
    assert r["credit_mid"] == pytest.approx(480.0)      # mids: 301+291-61-51
    assert r["stop_value"] == pytest.approx(714.0)      # 476 * 1.5
    assert r["vix_entry"] == 14.2 and r["spot_entry"] == 75012.0
    legs = {l["leg"]: l for l in json.loads(r["legs"])}
    assert legs["SC"]["symbol"] == "C75000" and legs["SC"]["side"] == "SELL"
    assert legs["LP"]["symbol"] == "P74000" and legs["LP"]["entry_px"] == 52


def test_normal_day_does_nothing(env):
    make, kite, clock, state = env
    state["expiry"] = False
    make().tick()
    assert _row() is None


def test_waits_for_entry_time(env):
    make, kite, clock, state = env
    clock.set(10, 0)
    make().tick()
    assert _row() is None


def test_missed_entry_window_is_recorded_as_skipped(env):
    make, kite, clock, state = env
    clock.set(11, 10)
    make().tick()
    assert _row()["status"] == "SKIPPED"
    assert "missed entry window" in _row()["note"]


def test_low_credit_skips(env, monkeypatch):
    make, kite, clock, state = env
    monkeypatch.setattr(settings, "FLY_MIN_CREDIT", 1000.0)
    make().tick()
    assert _row()["status"] == "SKIPPED" and "FLY_MIN_CREDIT" in _row()["note"]


def test_skip_date_is_honoured(env, monkeypatch):
    make, kite, clock, state = env
    monkeypatch.setattr(settings, "FLY_SKIP_DATES", "2026-10-21, 2026-10-22")
    make().tick()
    assert _row()["status"] == "SKIPPED" and "FLY_SKIP_DATES" in _row()["note"]


def test_incomplete_quotes_retry_instead_of_entering(env):
    make, kite, clock, state = env
    kite.book["C75000"] = (0, 302)          # no bid on a short leg
    r = make()
    r.tick()
    assert _row() is None
    kite.book["C75000"] = (300, 302)
    r.tick()
    assert _row()["status"] == "OPEN"


def test_stop_closes_at_ask_and_bid_and_books_loss(env):
    make, kite, clock, state = env
    r = make()
    r.tick()                                              # enter, credit 476, stop 714
    clock.set(12, 0)
    kite.book.update({"C75000": (700, 704), "P75000": (150, 152),
                      "C76000": (260, 262), "P74000": (20, 22)})   # mids: 702+151-261-21 = 571
    r.tick()
    assert _row()["status"] == "OPEN"                     # 571 < 714
    kite.book.update({"C75000": (900, 904), "P75000": (120, 122),
                      "C76000": (300, 302), "P74000": (15, 17)})   # mids: 902+121-301-16 = 706 -> still open
    r.tick()
    assert _row()["status"] == "OPEN"
    kite.book.update({"C75000": (950, 954), "P75000": (120, 122),
                      "C76000": (300, 302), "P74000": (15, 17)})   # mids: 952+121-301-16 = 756 >= 714
    r.tick()
    row = _row()
    assert row["status"] == "CLOSED" and row["exit_reason"] == "STOP"
    assert row["exit_value"] == pytest.approx(954 + 122 - 300 - 15)    # ask, ask, bid, bid
    assert row["gross_pnl"] == pytest.approx((476 - row["exit_value"]) * 20)
    assert row["net_pnl"] == pytest.approx(row["gross_pnl"] - row["charges"])
    assert row["charges"] > 0 and row["peak_value"] >= 756


def test_time_exit_books_profit_after_costs(env):
    make, kite, clock, state = env
    r = make()
    r.tick()
    clock.set(15, 10)
    kite.book.update({"C75000": (80, 82), "P75000": (40, 42),
                      "C76000": (2, 3), "P74000": (1, 2)})
    r.tick()
    row = _row()
    assert row["exit_reason"] == "TIME" and row["status"] == "CLOSED"
    assert row["exit_value"] == pytest.approx(82 + 42 - 2 - 1)         # 121
    assert row["gross_pnl"] == pytest.approx((476 - 121) * 20)
    assert 0 < row["charges"] < row["gross_pnl"]


def test_closed_day_never_reopens_and_restart_resumes_open_fly(env):
    make, kite, clock, state = env
    a = make()
    a.tick()
    b = make()                                           # "restart" mid-trade
    b.tick()
    assert _row()["status"] == "OPEN" and _row()["credit"] == pytest.approx(476.0)
    clock.set(15, 10)
    b.tick()
    assert _row()["status"] == "CLOSED"
    c = make()                                           # restart after close
    c.tick()
    assert _row()["status"] == "CLOSED"


def test_stale_quotes_after_exit_time_close_on_last_marks(env):
    make, kite, clock, state = env
    r = make()
    r.tick()
    kite.fail = True
    clock.set(15, 12)
    r.tick()
    assert _row()["status"] == "OPEN"                     # keeps trying inside the grace period
    clock.set(15, 30)
    r.tick()
    assert _row()["status"] == "CLOSED" and _row()["exit_reason"] == "TIME_STALE"


def test_disabled_flag_does_nothing(env, monkeypatch):
    make, kite, clock, state = env
    monkeypatch.setattr(settings, "ENABLE_EXPIRY_FLY", False)
    make().tick()
    assert _row() is None


# ── LIVE is refused ──────────────────────────────────────────────────────────

def test_live_mode_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "TRADING_MODE", "LIVE")
    monkeypatch.setattr(settings, "ENABLE_EXPIRY_FLY", True)
    with pytest.raises(RuntimeError, match="SHADOW-only"):
        settings.validate()
    from execution.fly_runner import ExpiryFlyRunner
    with pytest.raises(RuntimeError):
        ExpiryFlyRunner(None, None, None, None)


# ── real-vs-model comparison ─────────────────────────────────────────────────

def test_model_credit_matches_a_row_priced_by_the_model():
    from research import fly_vs_model as fm
    from research.system_backtest import Contracts, MarketData, bs_price, tick_round
    ch = Contracts(MarketData())
    at, spot, vix = datetime(2026, 10, 22, 10, 30), 75012.0, 14.2
    yrs = ch.trading_years(at, at.date())
    px = lambda k, t: tick_round(bs_price(spot, k, yrs, vix / 100, t))
    legs = [dict(leg="SC", strike=75000, type="CE", side="SELL"),
            dict(leg="SP", strike=75000, type="PE", side="SELL"),
            dict(leg="LC", strike=76000, type="CE", side="BUY"),
            dict(leg="LP", strike=74000, type="PE", side="BUY")]
    expect = round(px(75000, "CE") + px(75000, "PE") - px(76000, "CE") - px(74000, "PE"), 2)
    row = dict(legs=json.dumps(legs), vix_entry=vix, spot_entry=spot,
               entry_time=at.isoformat(), expiry="2026-10-22")
    assert fm.model_credit(ch, row) == expect
    assert fm.model_credit(ch, dict(row, legs=None)) is None
