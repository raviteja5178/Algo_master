"""
Tests for SmartEntryFilter Filter 7 — option premium extension guard.
"""

from datetime import date
from unittest.mock import patch

import pytest

from strategies.smart_entry import SmartEntryFilter


# ── helpers ──────────────────────────────────────────────────────────────────

def _filter(max_pct: float) -> SmartEntryFilter:
    return SmartEntryFilter(max_premium_extension_pct=max_pct)


# ── notify_option_ltp ─────────────────────────────────────────────────────────

def test_first_ltp_recorded():
    f = _filter(1.5)
    f.notify_option_ltp("SENSEX26O0173000CE", 140.0)
    stored_date, stored_ltp = f._first_ltp["SENSEX26O0173000CE"]
    assert stored_ltp == 140.0
    assert stored_date == date.today()


def test_first_ltp_not_overwritten_same_day():
    f = _filter(1.5)
    f.notify_option_ltp("SENSEX26O0173000CE", 140.0)
    f.notify_option_ltp("SENSEX26O0173000CE", 250.0)  # second call same day
    _, stored_ltp = f._first_ltp["SENSEX26O0173000CE"]
    assert stored_ltp == 140.0, "First-seen LTP must not be overwritten on same day"


def test_first_ltp_ignores_zero_or_negative():
    f = _filter(1.5)
    f.notify_option_ltp("SENSEX26O0173000CE", 0.0)
    f.notify_option_ltp("SENSEX26O0173000CE", -5.0)
    assert "SENSEX26O0173000CE" not in f._first_ltp


def test_first_ltp_refreshes_next_day():
    f = _filter(1.5)
    yesterday = date.fromordinal(date.today().toordinal() - 1)
    f._first_ltp["SENSEX26O0173000CE"] = (yesterday, 140.0)
    f.notify_option_ltp("SENSEX26O0173000CE", 250.0)
    stored_date, stored_ltp = f._first_ltp["SENSEX26O0173000CE"]
    assert stored_date == date.today()
    assert stored_ltp == 250.0, "Stale previous-day entry must be replaced"


# ── allow() with empty candles (late-gate path) ───────────────────────────────

def test_disabled_filter_always_allows():
    """max_premium_extension_pct=0 means filter is off — must never block."""
    f = _filter(0.0)
    f.notify_option_ltp("SYM", 140.0)
    assert f.allow("CE", [], option_ltp=500.0, tradingsymbol="SYM") is True


def test_allows_when_below_threshold():
    """140 → 331 = +136%.  Threshold 150% → should ALLOW."""
    f = _filter(1.5)
    f.notify_option_ltp("SYM", 140.0)
    assert f.allow("CE", [], option_ltp=331.0, tradingsymbol="SYM") is True


def test_blocks_when_above_threshold():
    """140 → 360 = +157%.  Threshold 150% → should BLOCK."""
    f = _filter(1.5)
    f.notify_option_ltp("SYM", 140.0)
    assert f.allow("CE", [], option_ltp=360.0, tradingsymbol="SYM") is False


def test_blocks_exactly_at_threshold():
    """Extension == threshold: 140 * (1 + 1.5) = 350 exactly.  Must BLOCK (extension > threshold is the test)."""
    f = _filter(1.5)
    f.notify_option_ltp("SYM", 140.0)
    # 350/140 - 1 = 1.5  → not strictly greater → ALLOW
    assert f.allow("CE", [], option_ltp=350.0, tradingsymbol="SYM") is True


def test_blocks_one_tick_above_threshold():
    """350.05 / 140 - 1 = 1.5003...  → strictly > 1.5 → BLOCK."""
    f = _filter(1.5)
    f.notify_option_ltp("SYM", 140.0)
    assert f.allow("CE", [], option_ltp=350.05, tradingsymbol="SYM") is False


def test_allows_when_no_first_ltp_recorded():
    """If notify_option_ltp was never called, filter must fail-open."""
    f = _filter(1.5)
    assert f.allow("CE", [], option_ltp=500.0, tradingsymbol="SYM") is True


def test_allows_when_option_ltp_is_none():
    f = _filter(1.5)
    f.notify_option_ltp("SYM", 140.0)
    assert f.allow("CE", [], option_ltp=None, tradingsymbol="SYM") is True


def test_allows_when_tradingsymbol_is_none():
    f = _filter(1.5)
    f.notify_option_ltp("SYM", 140.0)
    assert f.allow("CE", [], option_ltp=500.0, tradingsymbol=None) is True


def test_pe_signal_also_blocked():
    """Filter applies equally to PE signals."""
    f = _filter(1.5)
    f.notify_option_ltp("SYM_PE", 140.0)
    assert f.allow("PE", [], option_ltp=360.0, tradingsymbol="SYM_PE") is False


def test_pe_signal_allowed_within_threshold():
    f = _filter(1.5)
    f.notify_option_ltp("SYM_PE", 200.0)
    # 350/200 - 1 = 0.75 < 1.5 → ALLOW
    assert f.allow("PE", [], option_ltp=350.0, tradingsymbol="SYM_PE") is True


def test_stale_previous_day_entry_is_skipped():
    """If stored entry is from yesterday, filter treats first_ltp as unknown → fail-open."""
    f = _filter(1.5)
    yesterday = date.fromordinal(date.today().toordinal() - 1)
    f._first_ltp["SYM"] = (yesterday, 140.0)
    # Stale — should fail-open even though extension would have been blocked
    assert f.allow("CE", [], option_ltp=500.0, tradingsymbol="SYM") is True


# ── _highest_ltp tracking ─────────────────────────────────────────────────────

def test_highest_ltp_tracked_on_first_call():
    f = _filter(1.5)
    f.notify_option_ltp("SYM", 140.0)
    stored_date, stored_high = f._highest_ltp["SYM"]
    assert stored_high == 140.0
    assert stored_date == date.today()


def test_highest_ltp_updated_on_higher_price():
    f = _filter(1.5)
    f.notify_option_ltp("SYM", 140.0)
    f.notify_option_ltp("SYM", 280.0)
    _, high = f._highest_ltp["SYM"]
    assert high == 280.0


def test_highest_ltp_not_updated_on_lower_price():
    f = _filter(1.5)
    f.notify_option_ltp("SYM", 280.0)
    f.notify_option_ltp("SYM", 200.0)  # lower — should not overwrite
    _, high = f._highest_ltp["SYM"]
    assert high == 280.0


# ── get_premium_context ────────────────────────────────────────────────────────

def test_get_premium_context_returns_none_when_unknown():
    f = _filter(1.5)
    day_low, day_high = f.get_premium_context("UNKNOWN_SYM")
    assert day_low is None
    assert day_high is None


def test_get_premium_context_returns_correct_values():
    f = _filter(1.5)
    f.notify_option_ltp("SYM", 140.0)
    f.notify_option_ltp("SYM", 200.0)
    f.notify_option_ltp("SYM", 180.0)  # lower — first stays 140, high stays 200
    day_low, day_high = f.get_premium_context("SYM")
    assert day_low == 140.0
    assert day_high == 200.0


def test_get_premium_context_stale_day_returns_none():
    f = _filter(1.5)
    yesterday = date.fromordinal(date.today().toordinal() - 1)
    f._first_ltp["SYM"] = (yesterday, 140.0)
    f._highest_ltp["SYM"] = (yesterday, 300.0)
    day_low, day_high = f.get_premium_context("SYM")
    assert day_low is None
    assert day_high is None


# ── default PCT=1.0 blocks the Sep 30 T8 scenario ─────────────────────────────

def test_default_pct_blocks_sep30_t8():
    """Default PCT=1.0 must block the Rs.140 → Rs.331 = +136% peak entry."""
    f = SmartEntryFilter(max_premium_extension_pct=1.0)
    f.notify_option_ltp("SENSEX26O0173000CE", 140.0)
    # +136% > 100% → BLOCK
    assert f.allow("CE", [], option_ltp=331.0, tradingsymbol="SENSEX26O0173000CE") is False


def test_default_pct_allows_moderate_extension():
    """100% or less from day low should still be allowed."""
    f = SmartEntryFilter(max_premium_extension_pct=1.0)
    f.notify_option_ltp("SYM", 200.0)
    # 200*2 = 400 exactly — not strictly > → ALLOW
    assert f.allow("CE", [], option_ltp=400.0, tradingsymbol="SYM") is True
    # 399 < 400 → also ALLOW
    assert f.allow("CE", [], option_ltp=399.0, tradingsymbol="SYM") is True


def test_default_pct_blocks_just_above_100pct():
    """200 → 401 = +100.5% > 100% → BLOCK."""
    f = SmartEntryFilter(max_premium_extension_pct=1.0)
    f.notify_option_ltp("SYM", 200.0)
    assert f.allow("CE", [], option_ltp=401.0, tradingsymbol="SYM") is False
