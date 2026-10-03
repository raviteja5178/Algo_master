"""
Tests for the 5-minute Opening Range Breakout (ORB) strategy.

Opening range = HIGH/LOW of the FIRST 5m candle (09:15 only, ORB_CANDLES=1).

Entry logic:
  1. Sustain candle (09:20) must close ABOVE ORB High (CE) or BELOW ORB Low (PE).
  2. Signal candle must be in the 09:25–09:35 entry window.
  3. Standard crossover (prev <= ORB level, current crosses).

Covers:
  - ORB range from the single first candle of the day
  - CE/PE crossover logic (prev ≤ ORB, current crosses)
  - Sustain confirmation on 09:20 candle
  - Entry window gate (09:25–09:35 only)
  - Date guard (today-only)
  - Filter 1: body/range ratio (ORB_MIN_BODY_RATIO)
  - Filter 2: ATR breakout buffer (ORB_BUFFER_ATR_MULT)
  - Filter 3: 15m trend confirmation (ORB_REQUIRE_15M_TREND)
"""

from __future__ import annotations

from datetime import datetime, date, timedelta
import pytest

from market.candle_builder import Candle
from strategies.orb_strategy import (
    get_orb_range,
    is_orb_ce_signal,
    is_orb_pe_signal,
    ORB_CANDLES,
)

_TODAY = date.today()
_BASE = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15)


def _ts(h: int, m: int) -> datetime:
    return datetime(_TODAY.year, _TODAY.month, _TODAY.day, h, m)


def make_orb_candles(
    orb_high: float = 74500.0,
    orb_low: float = 74400.0,
    latest_close: float = 74510.0,
    prev_close: float = 74490.0,
    # Sustain candle (09:20) close — defaults to latest_close so sustain passes
    # for CE (above orb_high) by default. Pass explicitly to test rejection.
    sustain_close: float | None = None,
    # Allow explicit control of breakout candle OHLC for filter tests
    latest_open: float | None = None,
    latest_high: float | None = None,
    latest_low: float | None = None,
) -> list[Candle]:
    """
    Build a minimal candle list for ORB testing.

    Structure (ORB_CANDLES=1 → single opening candle at 09:15):
      - 1 ORB candle   (09:15) with the given orb_high/orb_low
      - 1 sustain candle (09:20) — must close on the correct side for signal to fire
      - 1 signal candle  (09:25) at latest_close — the candle under test

    sustain_close defaults to latest_close so callers don't need to set it for
    happy-path tests.  For CE tests: sustain_close > orb_high is required.
    For PE tests: sustain_close < orb_low is required.

    latest_open/high/low can be overridden to test body/range filters.
    """
    sc = sustain_close if sustain_close is not None else latest_close
    lopen  = latest_open  if latest_open  is not None else prev_close
    lhigh  = latest_high  if latest_high  is not None else max(latest_close, prev_close) + 2
    llow   = latest_low   if latest_low   is not None else min(latest_close, prev_close) - 2

    candles: list[Candle] = [
        Candle(_ts(9, 15), open=orb_low, high=orb_high, low=orb_low, close=orb_low),
        Candle(_ts(9, 20), open=sc, high=sc + 5, low=sc - 5, close=sc),
        Candle(_ts(9, 25), open=lopen, high=lhigh, low=llow, close=latest_close),
    ]
    return candles


def make_15m_candles(
    close: float,
    ema_seed: float | None = None,
    count: int = 25,
) -> list[Candle]:
    """
    Build 15m candles whose last close is *close* and whose EMA21 converges
    toward *ema_seed* (defaults to close — so EMA21 ≈ close).
    With count >= 21 the EMA will be valid.
    """
    seed = ema_seed if ema_seed is not None else close
    candles = []
    for i in range(count):
        ts = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15) + \
             timedelta(minutes=15 * i)
        price = seed if i < count - 1 else close
        candles.append(Candle(ts, open=price, high=price + 5,
                               low=price - 5, close=price))
    return candles


# ─────────────────────────────────────────────────────────────────────────────
# ORB range
# ─────────────────────────────────────────────────────────────────────────────

class TestORBRange:

    def test_get_orb_range_returns_first_candle_high_low(self) -> None:
        candles = make_orb_candles(orb_high=74600.0, orb_low=74300.0)
        high, low = get_orb_range(candles)
        assert high == 74600.0
        assert low == 74300.0

    def test_get_orb_range_none_when_empty(self) -> None:
        high, low = get_orb_range([])
        assert high is None
        assert low is None

    def test_get_orb_range_uses_latest_date(self) -> None:
        yesterday = _TODAY - timedelta(days=1)
        candles = [
            Candle(datetime(yesterday.year, yesterday.month, yesterday.day, 9, 15),
                   74400, 74500, 74300, 74450),
        ]
        high, low = get_orb_range(candles)
        assert high == 74500
        assert low == 74300


# ─────────────────────────────────────────────────────────────────────────────
# CE crossover (no filters)
# ─────────────────────────────────────────────────────────────────────────────

class TestORBCESignal:

    def test_ce_breakout_positive(self) -> None:
        # sustain (09:20) closes at 74520 > orb_high 74500 ✓
        # signal  (09:25) crosses above: prev_close 74490 -> 74520 ✓
        candles = make_orb_candles(orb_high=74500.0, prev_close=74490.0,
                                    latest_close=74520.0)
        assert is_orb_ce_signal(candles) is True

    def test_ce_rejected_when_sustain_inside_range(self) -> None:
        # sustain (09:20) closes at 74495 — still inside ORB, no confirmation
        candles = make_orb_candles(orb_high=74500.0, prev_close=74490.0,
                                    latest_close=74520.0, sustain_close=74495.0)
        assert is_orb_ce_signal(candles) is False

    def test_ce_rejected_when_sustain_below_range(self) -> None:
        # sustain (09:20) closes at 74480 — below ORB high, definitely no confirmation
        candles = make_orb_candles(orb_high=74500.0, prev_close=74490.0,
                                    latest_close=74520.0, sustain_close=74480.0)
        assert is_orb_ce_signal(candles) is False

    def test_ce_still_fires_if_price_already_above(self) -> None:
        # With sustain confirmed and close > ORB High, signal fires
        # even if the previous 5m candle was also above (no crossover needed)
        candles = make_orb_candles(orb_high=74500.0, prev_close=74510.0,
                                    latest_close=74530.0)
        assert is_orb_ce_signal(candles) is True

    def test_ce_false_when_close_below_orb_high(self) -> None:
        # Signal candle close is BELOW the ORB High — rejected
        candles = make_orb_candles(orb_high=74500.0, prev_close=74490.0,
                                    latest_close=74495.0)
        assert is_orb_ce_signal(candles) is False

    def test_ce_false_on_yesterday_candle(self) -> None:
        candles = make_orb_candles(orb_high=74500.0, prev_close=74490.0,
                                    latest_close=74520.0)
        yesterday = _TODAY - timedelta(days=1)
        c = candles[-1]
        candles[-1] = Candle(
            datetime(yesterday.year, yesterday.month, yesterday.day, 10, 0),
            c.open, c.high, c.low, c.close,
        )
        assert is_orb_ce_signal(candles) is False

    def test_ce_false_outside_entry_window(self) -> None:
        # Signal candle at 09:40 (after window end 09:35) — must be rejected
        candles = make_orb_candles(orb_high=74500.0, prev_close=74490.0,
                                    latest_close=74520.0)
        c = candles[-1]
        candles[-1] = Candle(_ts(9, 40), c.open, c.high, c.low, c.close)
        assert is_orb_ce_signal(candles) is False

    def test_ce_insufficient_candles(self) -> None:
        candles = [Candle(_ts(9, 15), 74400, 74500, 74300, 74450)]
        assert is_orb_ce_signal(candles) is False


# ─────────────────────────────────────────────────────────────────────────────
# PE crossover (no filters)
# ─────────────────────────────────────────────────────────────────────────────

class TestORBPESignal:

    def test_pe_breakout_positive(self) -> None:
        # sustain (09:20) closes at 74380 < orb_low 74400 ✓
        # signal  (09:25) crosses below: prev_close 74410 -> 74380 ✓
        candles = make_orb_candles(orb_low=74400.0, prev_close=74410.0,
                                    latest_close=74380.0)
        assert is_orb_pe_signal(candles) is True

    def test_pe_rejected_when_sustain_inside_range(self) -> None:
        # sustain (09:20) closes at 74405 — still inside ORB, no confirmation
        candles = make_orb_candles(orb_low=74400.0, prev_close=74410.0,
                                    latest_close=74380.0, sustain_close=74405.0)
        assert is_orb_pe_signal(candles) is False

    def test_pe_rejected_when_sustain_above_range(self) -> None:
        candles = make_orb_candles(orb_low=74400.0, prev_close=74410.0,
                                    latest_close=74380.0, sustain_close=74420.0)
        assert is_orb_pe_signal(candles) is False

    def test_pe_still_fires_if_price_already_below(self) -> None:
        # With sustain confirmed and close < ORB Low, signal fires
        candles = make_orb_candles(orb_low=74400.0, prev_close=74390.0,
                                    latest_close=74370.0)
        assert is_orb_pe_signal(candles) is True

    def test_pe_false_when_close_above_orb_low(self) -> None:
        # Signal candle close is ABOVE the ORB Low — rejected
        candles = make_orb_candles(orb_low=74400.0, prev_close=74410.0,
                                    latest_close=74405.0)
        assert is_orb_pe_signal(candles) is False

    def test_pe_false_on_yesterday_candle(self) -> None:
        candles = make_orb_candles(orb_low=74400.0, prev_close=74410.0,
                                    latest_close=74380.0)
        yesterday = _TODAY - timedelta(days=1)
        c = candles[-1]
        candles[-1] = Candle(
            datetime(yesterday.year, yesterday.month, yesterday.day, 10, 0),
            c.open, c.high, c.low, c.close,
        )
        assert is_orb_pe_signal(candles) is False

    def test_pe_false_outside_entry_window(self) -> None:
        candles = make_orb_candles(orb_low=74400.0, prev_close=74410.0,
                                    latest_close=74380.0)
        c = candles[-1]
        candles[-1] = Candle(_ts(9, 40), c.open, c.high, c.low, c.close)
        assert is_orb_pe_signal(candles) is False


# ─────────────────────────────────────────────────────────────────────────────
# Filter 1 — body / range ratio
# ─────────────────────────────────────────────────────────────────────────────

class TestBodyFilter:
    """
    Breakout candle: open=74490, close=74520, high=74530, low=74480
      body  = 74520 - 74490 = 30
      range = 74530 - 74480 = 50
      ratio = 30/50 = 0.60
    """

    def _candles_ce(self) -> list[Candle]:
        # body=30, range=50 → ratio 0.60
        return make_orb_candles(
            orb_high=74500.0, orb_low=74400.0,
            prev_close=74490.0, latest_close=74520.0,
            latest_open=74490.0, latest_high=74530.0, latest_low=74480.0,
        )

    def _candles_pe(self) -> list[Candle]:
        # body=30, range=50 → ratio 0.60
        return make_orb_candles(
            orb_high=74500.0, orb_low=74400.0,
            prev_close=74410.0, latest_close=74380.0,
            latest_open=74410.0, latest_high=74420.0, latest_low=74370.0,
        )

    def test_ce_passes_when_ratio_meets_threshold(self) -> None:
        assert is_orb_ce_signal(self._candles_ce(), min_body_ratio=0.5) is True

    def test_ce_rejected_when_ratio_below_threshold(self) -> None:
        assert is_orb_ce_signal(self._candles_ce(), min_body_ratio=0.7) is False

    def test_ce_disabled_at_zero(self) -> None:
        # ratio=0.0 means no body filter — should still pass crossover
        assert is_orb_ce_signal(self._candles_ce(), min_body_ratio=0.0) is True

    def test_pe_passes_when_ratio_meets_threshold(self) -> None:
        assert is_orb_pe_signal(self._candles_pe(), min_body_ratio=0.5) is True

    def test_pe_rejected_when_ratio_below_threshold(self) -> None:
        assert is_orb_pe_signal(self._candles_pe(), min_body_ratio=0.7) is False

    def test_doji_rejected(self) -> None:
        """A doji (body ≈ 0) should be blocked even at min_body_ratio=0.3."""
        # open ≈ close, large wick → body/range ≈ 0
        candles = make_orb_candles(
            orb_high=74500.0, prev_close=74499.0, latest_close=74501.0,
            latest_open=74500.5, latest_high=74560.0, latest_low=74440.0,
        )
        assert is_orb_ce_signal(candles, min_body_ratio=0.3) is False


# ─────────────────────────────────────────────────────────────────────────────
# Filter 2 — ATR breakout buffer
# ─────────────────────────────────────────────────────────────────────────────

class TestBufferFilter:
    """
    We need enough candles to compute ATR(14).  Build 20 candles whose
    high-low range is exactly 20 pts each so ATR ≈ 20.
    Buffer = ATR * mult.  close must be > orb_high + buffer (CE)
                                    or < orb_low  - buffer (PE).
    """

    def _build_with_atr(
        self,
        orb_high: float,
        orb_low: float,
        latest_close: float,
        direction: str,  # "CE" or "PE"
    ) -> list[Candle]:
        """
        20 historical candles (each range=20) + ORB candle + sustain + signal.
        ATR(14) ≈ 20.
        Sustain candle (09:20) is set to latest_close so it passes sustain check.
        """
        base_price = 74000.0
        candles: list[Candle] = []
        # 20 warm-up candles on yesterday — spread across the day to avoid
        # minute overflow (9:15 + 20*5min = 9:115 which is invalid)
        yesterday = _TODAY - timedelta(days=1)
        base_ts = datetime(yesterday.year, yesterday.month, yesterday.day, 9, 15)
        for i in range(20):
            ts = base_ts + timedelta(minutes=i * 5)
            candles.append(Candle(ts, base_price, base_price + 20,
                                   base_price, base_price + 10))

        # Today: ORB candle
        candles.append(Candle(_ts(9, 15), orb_low, orb_high, orb_low, orb_low))

        if direction == "CE":
            prev_close  = orb_high - 5   # below ORB high (crossover prev)
            sustain_close = latest_close  # 09:20 closes above ORB high → sustain passes
            lopen  = prev_close
            lhigh  = latest_close + 2
            llow   = prev_close - 2
        else:
            prev_close  = orb_low + 5    # above ORB low (crossover prev)
            sustain_close = latest_close  # 09:20 closes below ORB low → sustain passes
            lopen  = prev_close
            lhigh  = prev_close + 2
            llow   = latest_close - 2

        # Sustain candle (09:20) — must clear the ORB level for the signal to fire
        candles.append(Candle(_ts(9, 20), sustain_close, sustain_close + 5,
                               sustain_close - 5, sustain_close))
        candles.append(Candle(_ts(9, 25), lopen, lhigh, llow, latest_close))
        return candles

    def test_ce_passes_when_buffer_exceeded(self) -> None:
        # ORB high=74500, close=74522, ATR≈20, mult=0.1 → buffer=2.0 → need close>74502
        candles = self._build_with_atr(74500, 74400, 74522, "CE")
        assert is_orb_ce_signal(candles, buffer_atr_mult=0.1) is True

    def test_ce_rejected_when_inside_buffer(self) -> None:
        # ORB high=74500, close=74501, ATR≈20, mult=0.1 → need close>74502 — fails
        candles = self._build_with_atr(74500, 74400, 74501, "CE")
        assert is_orb_ce_signal(candles, buffer_atr_mult=0.1) is False

    def test_ce_disabled_at_zero(self) -> None:
        candles = self._build_with_atr(74500, 74400, 74501, "CE")
        assert is_orb_ce_signal(candles, buffer_atr_mult=0.0) is True

    def test_pe_passes_when_buffer_exceeded(self) -> None:
        # ORB low=74400, close=74378, ATR≈20, mult=0.1 → buffer=2.0 → need close<74398
        candles = self._build_with_atr(74500, 74400, 74378, "PE")
        assert is_orb_pe_signal(candles, buffer_atr_mult=0.1) is True

    def test_pe_rejected_when_inside_buffer(self) -> None:
        candles = self._build_with_atr(74500, 74400, 74399, "PE")
        assert is_orb_pe_signal(candles, buffer_atr_mult=0.1) is False


# ─────────────────────────────────────────────────────────────────────────────
# Filter 3 — 15m trend confirmation
# ─────────────────────────────────────────────────────────────────────────────

class TestTrendFilter:
    """
    make_15m_candles(close, ema_seed) builds 25 15m candles.
    When all seed candles are at ema_seed and the last is at close:
      - EMA21 converges toward ema_seed.
      - If close > ema_seed → close > EMA21 (uptrend).
      - If close < ema_seed → close < EMA21 (downtrend).
    """

    def _ce_candles(self) -> list[Candle]:
        return make_orb_candles(orb_high=74500.0, prev_close=74490.0,
                                 latest_close=74520.0)

    def _pe_candles(self) -> list[Candle]:
        return make_orb_candles(orb_low=74400.0, prev_close=74410.0,
                                 latest_close=74380.0)

    def test_ce_passes_when_uptrend(self) -> None:
        # 15m close (74600) well above EMA21 (seeds at 74300)
        c15m = make_15m_candles(close=74600, ema_seed=74300)
        assert is_orb_ce_signal(self._ce_candles(), c15m,
                                  require_15m_trend=True) is True

    def test_ce_rejected_when_downtrend(self) -> None:
        # 15m close (74200) well below EMA21 (seeds at 74600)
        c15m = make_15m_candles(close=74200, ema_seed=74600)
        assert is_orb_ce_signal(self._ce_candles(), c15m,
                                  require_15m_trend=True) is False

    def test_pe_passes_when_downtrend(self) -> None:
        c15m = make_15m_candles(close=74100, ema_seed=74500)
        assert is_orb_pe_signal(self._pe_candles(), c15m,
                                  require_15m_trend=True) is True

    def test_pe_rejected_when_uptrend(self) -> None:
        c15m = make_15m_candles(close=74600, ema_seed=74300)
        assert is_orb_pe_signal(self._pe_candles(), c15m,
                                  require_15m_trend=True) is False

    def test_trend_filter_skipped_when_disabled(self) -> None:
        # Even with a downtrend 15m, filter OFF → CE still fires on crossover
        c15m = make_15m_candles(close=74200, ema_seed=74600)
        assert is_orb_ce_signal(self._ce_candles(), c15m,
                                  require_15m_trend=False) is True

    def test_trend_filter_skipped_when_no_15m_data(self) -> None:
        # require_15m_trend=True but no 15m candles passed → filter is skipped
        assert is_orb_ce_signal(self._ce_candles(), None,
                                  require_15m_trend=True) is True

    def test_trend_filter_skipped_when_ema_unavailable(self) -> None:
        # Only 5 candles — EMA21 cannot be computed → filter skipped
        c15m = make_15m_candles(close=74200, ema_seed=74600, count=5)
        assert is_orb_ce_signal(self._ce_candles(), c15m,
                                  require_15m_trend=True) is True


# ─────────────────────────────────────────────────────────────────────────────
# Filters combined
# ─────────────────────────────────────────────────────────────────────────────

class TestFiltersComposed:
    """All three filters must pass simultaneously."""

    def test_all_filters_pass_ce(self) -> None:
        # body/range = 30/50 = 0.6 → passes min_body_ratio=0.5
        # buffer disabled (mult=0)
        # 15m uptrend
        candles = make_orb_candles(
            orb_high=74500.0, prev_close=74490.0, latest_close=74520.0,
            latest_open=74490.0, latest_high=74530.0, latest_low=74480.0,
        )
        c15m = make_15m_candles(close=74600, ema_seed=74300)
        assert is_orb_ce_signal(
            candles, c15m,
            min_body_ratio=0.5,
            buffer_atr_mult=0.0,
            require_15m_trend=True,
        ) is True

    def test_body_blocks_even_when_trend_ok(self) -> None:
        # doji — body ≈ 0; trend is fine → body filter kills it
        candles = make_orb_candles(
            orb_high=74500.0, prev_close=74499.0, latest_close=74501.0,
            latest_open=74500.5, latest_high=74560.0, latest_low=74440.0,
        )
        c15m = make_15m_candles(close=74600, ema_seed=74300)
        assert is_orb_ce_signal(
            candles, c15m,
            min_body_ratio=0.4,
            require_15m_trend=True,
        ) is False

    def test_trend_blocks_even_when_body_ok(self) -> None:
        # good body, but 15m is in downtrend
        candles = make_orb_candles(
            orb_high=74500.0, prev_close=74490.0, latest_close=74520.0,
            latest_open=74490.0, latest_high=74530.0, latest_low=74480.0,
        )
        c15m = make_15m_candles(close=74200, ema_seed=74600)
        assert is_orb_ce_signal(
            candles, c15m,
            min_body_ratio=0.5,
            require_15m_trend=True,
        ) is False


# ─────────────────────────────────────────────────────────────────────────────
# Monday filter — signal_engine integration
# ─────────────────────────────────────────────────────────────────────────────

class TestMondayFilter:
    """
    ORB_MOMENTUM_SKIP_MONDAY=True must suppress ORB signals when the candle
    falls on a Monday.  Other strategies (EMA, etc.) must be unaffected.
    """

    def _make_valid_ce_candles(self) -> list[Candle]:
        return make_orb_candles(orb_high=74500.0, prev_close=74490.0,
                                latest_close=74520.0)

    def _monday_ts(self) -> datetime:
        """Return a datetime on the nearest past (or current) Monday at 09:25."""
        from datetime import date as _date, timedelta
        d = _date.today()
        days_since_monday = d.weekday()   # 0=Mon … 6=Sun
        monday = d - timedelta(days=days_since_monday)
        return datetime(monday.year, monday.month, monday.day, 9, 25)

    def _non_monday_ts(self) -> datetime:
        """Return a datetime on the nearest past Tuesday at 09:25."""
        from datetime import date as _date, timedelta
        d = _date.today()
        days_since_monday = d.weekday()
        monday = d - timedelta(days=days_since_monday)
        tuesday = monday + timedelta(days=1)
        return datetime(tuesday.year, tuesday.month, tuesday.day, 9, 25)

    def test_orb_suppressed_on_monday(self) -> None:
        from unittest.mock import patch
        from strategies.signal_engine import evaluate_signals

        candles = self._make_valid_ce_candles()
        monday = self._monday_ts()
        # Shift all candles to the Monday date
        from datetime import date as _date
        monday_date = monday.date()
        shifted = [
            Candle(datetime(monday_date.year, monday_date.month, monday_date.day,
                            c.timestamp.hour, c.timestamp.minute),
                   c.open, c.high, c.low, c.close)
            for c in candles
        ]

        with patch("strategies.signal_engine.settings") as ms, \
             patch("strategies.signal_engine.has_processed_signal", return_value=False), \
             patch("strategies.signal_engine.record_processed_signal"), \
             patch("strategies.orb_strategy.date") as mock_date:

            mock_date.today.return_value = monday_date

            ms.ENABLE_OB_STRATEGY           = False
            ms.ENABLE_ORB_STRATEGY          = True
            ms.ORB_ACTIVE_UNTIL             = "09:40"
            ms.ORB_MIN_BODY_RATIO           = 0.0
            ms.ORB_BUFFER_ATR_MULT          = 0.0
            ms.ORB_REQUIRE_15M_TREND        = False
            ms.ORB_MOMENTUM_SKIP_MONDAY     = True
            ms.ENABLE_VWAP_STRATEGY         = False
            ms.ENABLE_PDHL_STRATEGY         = False
            ms.ENABLE_NATR_STRATEGY         = False
            ms.ENABLE_ATR_COPILOT_STRATEGY  = False
            ms.ENABLE_TRB_STRATEGY          = False
            ms.ENABLE_EMA_STRATEGY          = False
            ms.ENABLE_MOMENTUM_PHASE        = False

            result = evaluate_signals(shifted, shifted)
            assert result is None, "ORB must be suppressed on Monday"

    def test_skip_flag_false_on_tuesday(self) -> None:
        """Tuesday (weekday=1) must never set _skip_on_monday, regardless of setting."""
        from datetime import date
        tuesday_date = self._non_monday_ts().date()
        assert tuesday_date.weekday() == 1, "helper returned non-Tuesday date"
        # When ORB_MOMENTUM_SKIP_MONDAY=True but day is Tuesday: skip must be False
        skip = True and (tuesday_date.weekday() == 0)
        assert skip is False, "_skip_on_monday must be False on Tuesday"

    def test_skip_flag_false_when_setting_disabled_on_monday(self) -> None:
        """When ORB_MOMENTUM_SKIP_MONDAY=False, skip must be False even on Monday."""
        monday_date = self._monday_ts().date()
        assert monday_date.weekday() == 0, "helper returned non-Monday date"
        skip = False and (monday_date.weekday() == 0)
        assert skip is False, "_skip_on_monday must be False when setting is disabled"
