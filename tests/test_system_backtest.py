"""
Guards for the full-system backtest harness (research/system_backtest.py):
no look-ahead, option model sanity, expiry calendar, cost formula.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta

import pandas as pd
import pytest

from research import system_backtest as sb
from research.backtest_report import charges


@pytest.fixture()
def md(tmp_path, monkeypatch):
    """Three sessions of synthetic 1-minute data (Mon 2025-09-01 .. Wed 09-03)."""
    rows, vix = [], []
    for day in (date(2025, 9, 1), date(2025, 9, 2), date(2025, 9, 3)):
        t = datetime.combine(day, time(9, 15))
        px = 80000.0
        while t.time() < time(15, 30):
            rows.append((t, px, px + 5, px - 5, px + 1))
            vix.append((t, 12.0, 12.0, 12.0, 12.0))
            px += 1
            t += timedelta(minutes=1)
    cols = ["timestamp", "open", "high", "low", "close"]
    m1 = tmp_path / "m1.csv"
    pd.DataFrame(rows, columns=cols).to_csv(m1, index=False)
    v = tmp_path / "vix.csv"
    pd.DataFrame(vix, columns=cols).to_csv(v, index=False)
    d = tmp_path / "d.csv"
    pd.DataFrame([(date(2025, 8, 29), 1, 2, 0.5, 1.5), (date(2025, 9, 1), 1, 2, 0.5, 1.5)],
                 columns=["date", "open", "high", "low", "close"]).to_csv(d, index=False)
    monkeypatch.setattr(sb, "MINUTE_CSV", m1)
    monkeypatch.setattr(sb, "VIX_CSV", v)
    monkeypatch.setattr(sb, "DAILY_CSV", d)
    return sb.MarketData()


def test_completed_never_returns_a_forming_bar(md):
    now = datetime(2025, 9, 2, 10, 2, 30)
    frm, to = datetime(2025, 9, 2, 9, 0), datetime(2025, 9, 2, 15, 30)
    bars5 = md.completed("5minute", frm, to, now)
    assert bars5[-1]["date"] == datetime(2025, 9, 2, 9, 55)      # 10:00 bar still forming
    assert all(b["date"] + timedelta(minutes=5) <= now for b in bars5)
    bars1 = md.completed("minute", frm, to, now)
    assert bars1[-1]["date"] == datetime(2025, 9, 2, 10, 1)


def test_daily_bar_only_after_session_close(md):
    to = datetime(2025, 9, 1, 23, 59)
    during = md.completed("day", datetime(2025, 8, 1), to, datetime(2025, 9, 1, 12, 0))
    after = md.completed("day", datetime(2025, 8, 1), to, datetime(2025, 9, 1, 15, 31))
    assert [b["date"].date() for b in during] == [date(2025, 8, 29)]
    assert [b["date"].date() for b in after] == [date(2025, 8, 29), date(2025, 9, 1)]


def test_resampled_bars_match_minutes(md):
    b = md.bars["5minute"]
    i = b["start"].index(datetime(2025, 9, 1, 9, 15))
    r = b["recs"][i]
    assert (r["open"], r["close"]) == (80000.0, 80005.0)
    assert (r["high"], r["low"]) == (80009.0, 79995.0)


def test_bs_put_call_parity_and_intrinsic_floor():
    s, k, yrs, vol, r = 80000.0, 80100.0, 3 / 365, 0.13, sb.RISK_FREE
    ce, pe = sb.bs_price(s, k, yrs, vol, "CE"), sb.bs_price(s, k, yrs, vol, "PE")
    assert ce - pe == pytest.approx(s - k * math.exp(-r * yrs), abs=0.01)
    assert sb.bs_price(80500, 80000, 0.0, 0.13, "CE") == 500
    assert sb.bs_price(79500, 80000, 0.0, 0.13, "CE") == 0
    # ATM weekly premium in a sensible range (a few hundred points)
    assert 150 < sb.bs_price(80000, 80000, 3 / 365, 0.13, "CE") < 600


def test_expiry_calendar_follows_schedule(md):
    ch = sb.Contracts(md)
    assert ch.expiry_weekday(date(2024, 6, 3)) == 4          # Friday era
    assert ch.expiry_weekday(date(2025, 3, 3)) == 1          # Tuesday era
    assert ch.expiry_weekday(date(2025, 9, 2)) == 3          # Thursday era
    assert ch.expiries_from(date(2025, 9, 2), 2) == [date(2025, 9, 4), date(2025, 9, 11)]


def test_premium_decays_toward_expiry(md):
    ch = sb.Contracts(md)
    c = ch.contract(date(2025, 9, 4), 80000, "CE")
    early = ch.premium(c, 80000, datetime(2025, 9, 1, 10, 0))
    late = ch.premium(c, 80000, datetime(2025, 9, 3, 15, 0))
    assert early > late > 0


def test_fake_datetime_reads_the_simulated_clock():
    from utils.time_utils import IST
    sb._CLOCK[:] = [IST.localize(datetime(2025, 9, 2, 11, 7))]
    assert sb.FakeDatetime.now(IST).hour == 11
    assert sb.FakeDatetime.now().minute == 7
    assert isinstance(datetime(2020, 1, 1), sb.FakeDatetime)


def test_charges_post_oct_2024():
    # Rs 300 -> 330, qty 20: STT 0.1% of 6600 = 6.6; brokerage 40; exchange 0.0325% of 12600
    c = charges(300, 330, 20, date(2025, 1, 2))
    exch = 12600 * 0.000325
    sebi = 12600 * 10 / 1e7
    expected = 40 + 6.6 + exch + sebi + 6000 * 0.00003 + 0.18 * (40 + exch + sebi)
    assert c == pytest.approx(expected, abs=0.01)
    assert charges(300, 330, 20, date(2024, 9, 1)) < c      # lower STT before Oct 2024
