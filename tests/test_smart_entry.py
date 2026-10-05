"""
Tests for SmartEntryFilter.

Covers all five filters independently and in combination:
  - Filter 1: candle body / ATR ratio
  - Filter 2: EMA9 slope (rising for CE, falling for PE)
  - Filter 3: post-loss cooldown
  - Filter 4: minimum EMA gap magnitude
  - Filter 5: EMA gap must be widening
"""

from __future__ import annotations

from datetime import datetime, date, timedelta

import pytest

from market.candle_builder import Candle
from strategies.smart_entry import SmartEntryFilter


_TODAY = date.today()


def _ts(h: int, m: int) -> datetime:
    return datetime(_TODAY.year, _TODAY.month, _TODAY.day, h, m)


def _yesterday_ts(i: int) -> datetime:
    d = _TODAY - timedelta(days=1)
    base = datetime(d.year, d.month, d.day, 9, 15)
    return base + timedelta(minutes=i * 5)


def _make_candle(ts: datetime, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(ts, open=open_, high=high, low=low, close=close)


# ─────────────────────────────────────────────────────────────────────────────
# Candle builders
# ─────────────────────────────────────────────────────────────────────────────

def _candles_with_body_and_atr(
    body: float,
    atr_range: float = 20.0,
    direction: str = "CE",
    n_warmup: int = 20,
) -> list[Candle]:
    """
    Build candles that produce ATR ≈ atr_range and a signal candle with
    a specific body.

    Warmup candles alternate between two prices so consecutive closes
    differ by atr_range — ensuring True Range ≈ atr_range on every bar.
    Signal candle today has body=body in the correct direction.
    """
    candles = []
    # Alternate between base and base+atr_range so TR = atr_range each bar
    base = 74000.0
    for i in range(n_warmup):
        price = base if i % 2 == 0 else base + atr_range
        prev  = (base + atr_range) if i % 2 == 0 else base
        candles.append(_make_candle(_yesterday_ts(i),
                                    price, price + 1, price - 1, price))

    if direction == "CE":
        open_ = 74500.0
        close = open_ + body
    else:
        open_ = 74500.0
        close = open_ - body

    candles.append(_make_candle(_ts(9, 25),
                                open_, max(open_, close) + 1, min(open_, close) - 1, close))
    return candles


def _candles_with_ema_slope(rising: bool, n: int = 25) -> list[Candle]:
    """
    Build candles where EMA9 is rising (if rising=True) or falling.
    Use a steadily climbing or declining price series.
    """
    candles = []
    for i in range(n - 1):
        price = 74000.0 + (i if rising else -i)
        candles.append(_make_candle(_yesterday_ts(i),
                                    price, price + 5, price - 5, price))
    # Signal candle today — continues the trend
    last = candles[-1].close
    signal_close = last + (10 if rising else -10)
    candles.append(_make_candle(_ts(9, 25),
                                last, signal_close + 2, last - 2, signal_close))
    return candles


def _candles_with_ema_gap(
    widening: bool,
    side: str = "CE",
    large_gap: bool = True,
    n: int = 30,
) -> list[Candle]:
    """
    Build a candle series with a controlled EMA9/EMA21 gap profile.

    Approach
    --------
    Use a long trending warmup so EMA9 and EMA21 both build a clear gap
    in the desired direction.  Then the signal candle either accelerates
    (gap grows) or decelerates / partially reverses (gap shrinks).

    Parameters
    ----------
    widening  : True  → signal candle accelerates trend (gap grows)
                False → signal candle partially reverses (gap shrinks)
    side      : "CE" → uptrend (EMA9 > EMA21); "PE" → downtrend
    large_gap : True  → warmup step is large (+20 pts/candle) so gap >> 10
                False → warmup step is tiny (+0.1 pts) so gap ≈ 0 pts
    n         : total candles (must be >= 22 for EMA21 to be valid)
    """
    base = 74000.0
    step = 20.0 if large_gap else 0.1
    if side == "PE":
        step = -step

    candles: list[Candle] = []
    for i in range(n - 1):
        price = base + i * step
        candles.append(_make_candle(_yesterday_ts(i),
                                    price, price + 5, price - 5, price))

    # Signal candle: accelerate or decelerate
    last = candles[-1].close
    if widening:
        # Accelerate: price jumps further in trend direction
        delta = +50.0 if side == "CE" else -50.0
    else:
        # Decelerate: price pulls back toward the mean
        delta = -80.0 if side == "CE" else +80.0

    sig_price = last + delta
    candles.append(_make_candle(_ts(9, 25),
                                sig_price, sig_price + 5, sig_price - 5, sig_price))
    return candles


# ─────────────────────────────────────────────────────────────────────────────
# Filter 1 — body / ATR ratio
# ─────────────────────────────────────────────────────────────────────────────

class TestBodyATRFilter:

    def test_allow_when_body_exceeds_threshold(self) -> None:
        # Use body=20 which is comfortably above ATR*0.3 for any realistic ATR
        # built from atr_range=20 alternating candles.
        flt = SmartEntryFilter(min_body_atr_ratio=0.3)
        candles = _candles_with_body_and_atr(body=20, atr_range=20)
        assert flt.allow("CE", candles) is True

    def test_block_when_body_below_threshold(self) -> None:
        # body=1 is always below ATR*0.3 for any realistic warm-up
        flt = SmartEntryFilter(min_body_atr_ratio=0.3)
        candles = _candles_with_body_and_atr(body=1, atr_range=20)
        assert flt.allow("CE", candles) is False

    def test_disabled_at_zero(self) -> None:
        # Even a zero-body candle passes when ratio=0.0
        flt = SmartEntryFilter(min_body_atr_ratio=0.0)
        candles = _candles_with_body_and_atr(body=0, atr_range=20)
        assert flt.allow("CE", candles) is True

    def test_skipped_when_atr_unavailable(self) -> None:
        # Only 5 warmup candles — ATR(14) cannot be computed → filter skips
        flt = SmartEntryFilter(min_body_atr_ratio=0.9)
        candles = _candles_with_body_and_atr(body=1, atr_range=20, n_warmup=5)
        assert flt.allow("CE", candles) is True

    def test_pe_body_direction(self) -> None:
        # PE signal with adequate body (20 pts) passes
        flt = SmartEntryFilter(min_body_atr_ratio=0.3)
        candles = _candles_with_body_and_atr(body=20, atr_range=20, direction="PE")
        assert flt.allow("PE", candles) is True

    def test_ce_orb_prefix_treated_as_ce(self) -> None:
        flt = SmartEntryFilter(min_body_atr_ratio=0.3)
        candles = _candles_with_body_and_atr(body=20, atr_range=20, direction="CE")
        assert flt.allow("CE_ORB", candles) is True


# ─────────────────────────────────────────────────────────────────────────────
# Filter 2 — EMA9 slope
# ─────────────────────────────────────────────────────────────────────────────

class TestEMASlopeFilter:

    def test_ce_passes_when_ema9_rising(self) -> None:
        flt = SmartEntryFilter(require_ema_slope=True)
        candles = _candles_with_ema_slope(rising=True)
        assert flt.allow("CE", candles) is True

    def test_ce_blocked_when_ema9_falling(self) -> None:
        flt = SmartEntryFilter(require_ema_slope=True)
        candles = _candles_with_ema_slope(rising=False)
        assert flt.allow("CE", candles) is False

    def test_pe_passes_when_ema9_falling(self) -> None:
        flt = SmartEntryFilter(require_ema_slope=True)
        candles = _candles_with_ema_slope(rising=False)
        assert flt.allow("PE", candles) is True

    def test_pe_blocked_when_ema9_rising(self) -> None:
        flt = SmartEntryFilter(require_ema_slope=True)
        candles = _candles_with_ema_slope(rising=True)
        assert flt.allow("PE", candles) is False

    def test_disabled_by_default(self) -> None:
        # require_ema_slope=False — rising or falling, always passes
        flt = SmartEntryFilter(require_ema_slope=False)
        candles = _candles_with_ema_slope(rising=False)
        assert flt.allow("CE", candles) is True

    def test_skipped_when_too_few_candles(self) -> None:
        # Only 5 candles — EMA9 needs at least 9; filter skips
        flt = SmartEntryFilter(require_ema_slope=True)
        candles = _candles_with_ema_slope(rising=False, n=5)
        assert flt.allow("CE", candles) is True


# ─────────────────────────────────────────────────────────────────────────────
# Filter 3 — post-loss cooldown
# ─────────────────────────────────────────────────────────────────────────────

class TestCooldownFilter:

    def _base_candles(self) -> list[Candle]:
        return _candles_with_body_and_atr(body=10, atr_range=20)

    def test_no_cooldown_initially(self) -> None:
        flt = SmartEntryFilter(cooldown_candles=2)
        assert flt.allow("CE", self._base_candles()) is True

    def test_cooldown_starts_after_loss(self) -> None:
        flt = SmartEntryFilter(cooldown_candles=2)
        flt.on_trade_closed(-500.0)   # loss
        assert flt.allow("CE", self._base_candles()) is False

    def test_cooldown_expires_after_n_candles(self) -> None:
        flt = SmartEntryFilter(cooldown_candles=2)
        flt.on_trade_closed(-500.0)
        flt.on_candle()   # candle 1
        assert flt.allow("CE", self._base_candles()) is False
        flt.on_candle()   # candle 2 — expires
        assert flt.allow("CE", self._base_candles()) is True

    def test_profit_does_not_start_cooldown(self) -> None:
        flt = SmartEntryFilter(cooldown_candles=2)
        flt.on_trade_closed(+300.0)   # profit
        assert flt.allow("CE", self._base_candles()) is True

    def test_breakeven_does_not_start_cooldown(self) -> None:
        flt = SmartEntryFilter(cooldown_candles=2)
        flt.on_trade_closed(0.0)
        assert flt.allow("CE", self._base_candles()) is True

    def test_disabled_at_zero(self) -> None:
        flt = SmartEntryFilter(cooldown_candles=0)
        flt.on_trade_closed(-9999.0)
        assert flt.allow("CE", self._base_candles()) is True

    def test_consecutive_losses_reset_counter(self) -> None:
        # After 2nd loss the countdown restarts from cooldown_candles
        flt = SmartEntryFilter(cooldown_candles=3)
        flt.on_trade_closed(-100.0)
        flt.on_candle()
        flt.on_trade_closed(-100.0)   # 2nd loss — resets to 3
        flt.on_candle()
        flt.on_candle()
        assert flt.allow("CE", self._base_candles()) is False  # still 1 left
        flt.on_candle()
        assert flt.allow("CE", self._base_candles()) is True

    def test_cooldown_remaining_property(self) -> None:
        flt = SmartEntryFilter(cooldown_candles=3)
        assert flt.cooldown_remaining == 0
        flt.on_trade_closed(-100.0)
        assert flt.cooldown_remaining == 3
        flt.on_candle()
        assert flt.cooldown_remaining == 2


# ─────────────────────────────────────────────────────────────────────────────
# Filter 4 — minimum EMA gap magnitude
# ─────────────────────────────────────────────────────────────────────────────

class TestMinEMAGapFilter:

    def test_ce_passes_when_gap_exceeds_threshold(self) -> None:
        # Strongly trending CE series — EMA9 well above EMA21 → gap >> 10 pts
        flt = SmartEntryFilter(min_ema_gap_pts=10.0)
        candles = _candles_with_ema_gap(widening=True, side="CE", large_gap=True)
        assert flt.allow("CE", candles) is True

    def test_ce_blocked_when_gap_below_threshold(self) -> None:
        # Flat/tiny-step series — EMA9 ≈ EMA21 → gap clearly below 10 pts
        flt = SmartEntryFilter(min_ema_gap_pts=10.0)
        candles = _candles_with_ema_gap(widening=True, side="CE", large_gap=False)
        assert flt.allow("CE", candles) is False

    def test_pe_passes_when_gap_exceeds_threshold(self) -> None:
        # Strongly downtrending series — EMA9 well below EMA21
        flt = SmartEntryFilter(min_ema_gap_pts=10.0)
        candles = _candles_with_ema_gap(widening=True, side="PE", large_gap=True)
        assert flt.allow("PE", candles) is True

    def test_pe_blocked_when_gap_below_threshold(self) -> None:
        # Flat series with positive gap (wrong direction for PE) → blocked
        flt = SmartEntryFilter(min_ema_gap_pts=10.0)
        candles = _candles_with_ema_gap(widening=True, side="CE", large_gap=False)
        assert flt.allow("PE", candles) is False

    def test_disabled_at_zero(self) -> None:
        flt = SmartEntryFilter(min_ema_gap_pts=0.0)
        candles = _candles_with_ema_gap(widening=True, side="CE", large_gap=False)
        assert flt.allow("CE", candles) is True

    def test_skipped_when_too_few_candles(self) -> None:
        # Fewer than 21 candles → filter skips (fail-open)
        flt = SmartEntryFilter(min_ema_gap_pts=10.0)
        candles = _candles_with_ema_gap(widening=True, side="CE", large_gap=False, n=10)
        assert flt.allow("CE", candles) is True


# ─────────────────────────────────────────────────────────────────────────────
# Filter 5 — EMA gap widening
# ─────────────────────────────────────────────────────────────────────────────

class TestEMAGapWideningFilter:

    def test_ce_passes_when_gap_growing(self) -> None:
        # Signal candle accelerates CE trend — gap grows
        flt = SmartEntryFilter(require_ema_gap_widening=True)
        candles = _candles_with_ema_gap(widening=True, side="CE")
        assert flt.allow("CE", candles) is True

    def test_ce_blocked_when_gap_shrinking(self) -> None:
        # Signal candle decelerates CE trend — gap shrinks → blocked
        flt = SmartEntryFilter(require_ema_gap_widening=True)
        candles = _candles_with_ema_gap(widening=False, side="CE")
        assert flt.allow("CE", candles) is False

    def test_pe_passes_when_gap_growing_negative(self) -> None:
        # Signal candle accelerates PE downtrend — gap grows (more negative)
        flt = SmartEntryFilter(require_ema_gap_widening=True)
        candles = _candles_with_ema_gap(widening=True, side="PE")
        assert flt.allow("PE", candles) is True

    def test_pe_blocked_when_gap_shrinking(self) -> None:
        # Signal candle decelerates PE trend — gap shrinks → blocked
        flt = SmartEntryFilter(require_ema_gap_widening=True)
        candles = _candles_with_ema_gap(widening=False, side="PE")
        assert flt.allow("PE", candles) is False

    def test_disabled_by_default(self) -> None:
        flt = SmartEntryFilter(require_ema_gap_widening=False)
        candles = _candles_with_ema_gap(widening=False, side="CE")
        assert flt.allow("CE", candles) is True

    def test_skipped_when_too_few_candles(self) -> None:
        flt = SmartEntryFilter(require_ema_gap_widening=True)
        candles = _candles_with_ema_gap(widening=False, side="CE", n=10)
        assert flt.allow("CE", candles) is True


# ─────────────────────────────────────────────────────────────────────────────
# All five filters combined
# ─────────────────────────────────────────────────────────────────────────────

class TestFiltersComposed:

    def test_all_pass(self) -> None:
        flt = SmartEntryFilter(
            min_body_atr_ratio=0.3,
            require_ema_slope=True,
            cooldown_candles=2,
        )
        candles = _candles_with_ema_slope(rising=True, n=25)
        # Make sure ATR warmup exists — replace yesterday candles with fixed-range ones
        for i in range(20):
            candles[i] = _make_candle(_yesterday_ts(i),
                                      74000, 74020, 74000, 74010)
        assert flt.allow("CE", candles) is True

    def test_body_blocks_even_when_slope_ok_and_no_cooldown(self) -> None:
        flt = SmartEntryFilter(
            min_body_atr_ratio=0.9,   # very high threshold
            require_ema_slope=True,
            cooldown_candles=0,
        )
        candles = _candles_with_body_and_atr(body=2, atr_range=20)   # tiny body
        assert flt.allow("CE", candles) is False

    def test_cooldown_blocks_even_when_other_filters_pass(self) -> None:
        flt = SmartEntryFilter(
            min_body_atr_ratio=0.0,
            require_ema_slope=False,
            cooldown_candles=3,
        )
        flt.on_trade_closed(-100.0)
        candles = _candles_with_body_and_atr(body=10, atr_range=20)
        assert flt.allow("CE", candles) is False

    def test_all_five_filters_pass(self) -> None:
        # Strongly trending CE series: body ok, EMA9 rising, no cooldown,
        # gap large and growing.
        flt = SmartEntryFilter(
            min_body_atr_ratio=0.1,
            require_ema_slope=True,
            cooldown_candles=2,
            min_ema_gap_pts=5.0,
            require_ema_gap_widening=True,
        )
        # Build a strongly trending rising series with accelerating signal candle
        candles = _candles_with_ema_gap(widening=True, side="CE", large_gap=True, n=30)
        # Replace the signal candle with a large-body version
        last = candles[-1]
        candles[-1] = _make_candle(last.timestamp, last.open - 50, last.high, last.low, last.close + 50)
        assert flt.allow("CE", candles) is True

    def test_filter4_blocks_even_when_filters_1_2_3_pass(self) -> None:
        flt = SmartEntryFilter(
            min_body_atr_ratio=0.0,
            require_ema_slope=False,
            cooldown_candles=0,
            min_ema_gap_pts=10.0,
        )
        # Flat/tiny series → EMA gap << 10 pts → filter 4 blocks
        candles = _candles_with_ema_gap(widening=True, side="CE", large_gap=False)
        assert flt.allow("CE", candles) is False

    def test_filter5_blocks_even_when_filters_1_2_3_4_pass(self) -> None:
        flt = SmartEntryFilter(
            min_body_atr_ratio=0.0,
            require_ema_slope=False,
            cooldown_candles=0,
            min_ema_gap_pts=5.0,
            require_ema_gap_widening=True,
        )
        # Gap is large enough for filter 4 but shrinking → filter 5 blocks
        candles = _candles_with_ema_gap(widening=False, side="CE", large_gap=True)
        assert flt.allow("CE", candles) is False


# ─────────────────────────────────────────────────────────────────────────────
# Filter 6 — 15m trend alignment
# ─────────────────────────────────────────────────────────────────────────────

class TestFilter6_15mTrend:
    """Filter 6: 15m close must be above 15m EMA21 for CE, below for PE."""

    def _make_15m_candles(self, close_above_ema: bool, n: int = 25) -> list[Candle]:
        """Build 25 15m candles. Last candle closes above or below EMA21."""
        base = 74000.0
        candles = []
        for i in range(n):
            ts = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15) + timedelta(minutes=i * 15)
            # Steady series so EMA21 ≈ base
            c = base + 0.1 * i  # gently rising → EMA21 ≈ base
            candles.append(_make_candle(ts, c, c + 5, c - 5, c))
        # Overwrite last candle to be clearly above or below
        last = candles[-1]
        final_close = base + 100.0 if close_above_ema else base - 100.0
        candles[-1] = _make_candle(last.timestamp, last.open, last.high, last.low, final_close)
        return candles

    def _basic_ce_candles(self) -> list[Candle]:
        """Minimal 5m candles that satisfy no other filter (all disabled)."""
        ts_base = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 11, 0)
        candles = []
        for i in range(25):
            ts = ts_base + timedelta(minutes=i * 5)
            candles.append(_make_candle(ts, 74000, 74050, 73950, 74020))
        return candles

    def test_ce_allowed_when_15m_above_ema21(self) -> None:
        flt = SmartEntryFilter(require_15m_trend=True)
        candles_15m = self._make_15m_candles(close_above_ema=True)
        assert flt.allow("CE", self._basic_ce_candles(), candles_15m=candles_15m) is True

    def test_ce_blocked_when_15m_below_ema21(self) -> None:
        flt = SmartEntryFilter(require_15m_trend=True)
        candles_15m = self._make_15m_candles(close_above_ema=False)
        assert flt.allow("CE", self._basic_ce_candles(), candles_15m=candles_15m) is False

    def test_pe_allowed_when_15m_below_ema21(self) -> None:
        flt = SmartEntryFilter(require_15m_trend=True)
        candles_15m = self._make_15m_candles(close_above_ema=False)
        assert flt.allow("PE", self._basic_ce_candles(), candles_15m=candles_15m) is True

    def test_pe_blocked_when_15m_above_ema21(self) -> None:
        flt = SmartEntryFilter(require_15m_trend=True)
        candles_15m = self._make_15m_candles(close_above_ema=True)
        assert flt.allow("PE", self._basic_ce_candles(), candles_15m=candles_15m) is False

    def test_skipped_when_candles_15m_is_none(self) -> None:
        """Filter must fail-open when no 15m data is available."""
        flt = SmartEntryFilter(require_15m_trend=True)
        assert flt.allow("CE", self._basic_ce_candles(), candles_15m=None) is True

    def test_skipped_when_fewer_than_21_candles(self) -> None:
        """Filter skipped when < 21 15m candles — not enough to compute EMA21."""
        flt = SmartEntryFilter(require_15m_trend=True)
        short = self._make_15m_candles(close_above_ema=False, n=20)
        # CE would normally be blocked (15m bearish), but should pass because < 21 candles
        assert flt.allow("CE", self._basic_ce_candles(), candles_15m=short) is True

    def test_disabled_by_default(self) -> None:
        """Filter 6 is OFF by default — no 15m data should not affect outcome."""
        flt = SmartEntryFilter()  # require_15m_trend=False
        candles_15m = self._make_15m_candles(close_above_ema=False)
        # CE with bearish 15m — should still pass because filter is off
        assert flt.allow("CE", self._basic_ce_candles(), candles_15m=candles_15m) is True

    def test_ce_orb_prefix_treated_as_ce(self) -> None:
        """CE_ORB direction string should match as CE side."""
        flt = SmartEntryFilter(require_15m_trend=True)
        candles_15m = self._make_15m_candles(close_above_ema=True)
        assert flt.allow("CE_ORB", self._basic_ce_candles(), candles_15m=candles_15m) is True

    def test_pe_trb_prefix_treated_as_pe(self) -> None:
        """PE_TRB direction string should match as PE side."""
        flt = SmartEntryFilter(require_15m_trend=True)
        candles_15m = self._make_15m_candles(close_above_ema=False)
        assert flt.allow("PE_TRB", self._basic_ce_candles(), candles_15m=candles_15m) is True


# ─────────────────────────────────────────────────────────────────────────────
# Bounce-exempt strategy bypass (Filters 1, 4 & 5)
# ─────────────────────────────────────────────────────────────────────────────

class TestBounceExemptStrategies:
    """
    VWAP and NATR signals must bypass Filters 1 (body/ATR), 4 (min EMA gap),
    and 5 (EMA gap widening) because bounce setups have flat EMAs by definition.
    """

    def _flat_candles(self, n: int = 30) -> list[Candle]:
        """Candles with tiny bodies and near-zero EMA gap (flat/noise zone)."""
        base = 72000.0
        candles = []
        for i in range(n):
            ts = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15) + timedelta(minutes=i * 5)
            # All candles close at base ± 1 — body = 1, ATR ≈ 1, EMA gap ≈ 0
            c = base + (1.0 if i % 2 == 0 else -1.0)
            candles.append(_make_candle(ts, base, base + 2, base - 2, c))
        return candles

    def test_vwap_bypasses_body_filter(self) -> None:
        """CE_VWAP must pass even when body << ATR threshold."""
        flt = SmartEntryFilter(min_body_atr_ratio=0.5, bounce_exempt_strategies={"VWAP", "NATR"})
        candles = _candles_with_body_and_atr(body=1, atr_range=20)  # body/ATR = 0.05 << 0.5
        assert flt.allow("CE_VWAP", candles) is True

    def test_natr_bypasses_body_filter(self) -> None:
        """PE_NATR must pass even when body << ATR threshold."""
        flt = SmartEntryFilter(min_body_atr_ratio=0.5, bounce_exempt_strategies={"VWAP", "NATR"})
        candles = _candles_with_body_and_atr(body=1, atr_range=20, direction="PE")
        assert flt.allow("PE_NATR", candles) is True

    def test_non_exempt_strategy_still_blocked_by_body(self) -> None:
        """CE_EMA (not in exempt set) must still be blocked by body filter."""
        flt = SmartEntryFilter(min_body_atr_ratio=0.5, bounce_exempt_strategies={"VWAP", "NATR"})
        candles = _candles_with_body_and_atr(body=1, atr_range=20)
        assert flt.allow("CE_EMA", candles) is False

    def test_vwap_bypasses_ema_gap_filter(self) -> None:
        """CE_VWAP must pass even when EMA gap is flat/negative (noise zone)."""
        flt = SmartEntryFilter(min_ema_gap_pts=10.0, bounce_exempt_strategies={"VWAP", "NATR"})
        candles = _candles_with_ema_gap(widening=True, side="CE", large_gap=False)
        # EMA gap is small → CE_EMA would be blocked, CE_VWAP must pass
        assert flt.allow("CE_VWAP", candles) is True

    def test_vwap_bypasses_ema_gap_widening_filter(self) -> None:
        """CE_VWAP must pass even when EMA gap is shrinking."""
        flt = SmartEntryFilter(require_ema_gap_widening=True, bounce_exempt_strategies={"VWAP", "NATR"})
        candles = _candles_with_ema_gap(widening=False, side="CE")
        assert flt.allow("CE_VWAP", candles) is True

    def test_non_exempt_still_blocked_by_ema_gap(self) -> None:
        """CE_EMA (not exempt) must still be blocked by EMA gap filter."""
        flt = SmartEntryFilter(min_ema_gap_pts=10.0, bounce_exempt_strategies={"VWAP", "NATR"})
        candles = _candles_with_ema_gap(widening=True, side="CE", large_gap=False)
        assert flt.allow("CE_EMA", candles) is False

    def test_empty_exempt_set_disables_bypass(self) -> None:
        """When bounce_exempt_strategies=set(), no strategy gets the bypass."""
        flt = SmartEntryFilter(min_body_atr_ratio=0.5, bounce_exempt_strategies=set())
        candles = _candles_with_body_and_atr(body=1, atr_range=20)
        # CE_VWAP should be blocked when exemption is explicitly disabled
        assert flt.allow("CE_VWAP", candles) is False

    def test_default_exempt_set_includes_vwap_and_natr(self) -> None:
        """Default SmartEntryFilter exempt set is VWAP and NATR (body bypass)."""
        flt = SmartEntryFilter(min_body_atr_ratio=0.5)  # no bounce_exempt_strategies → default
        candles = _candles_with_body_and_atr(body=1, atr_range=20)
        assert flt.allow("CE_VWAP", candles) is True
        assert flt.allow("PE_NATR", candles) is True
        # EMA/ORB are NOT in default exempt set
        assert flt.allow("CE_EMA", candles) is False
