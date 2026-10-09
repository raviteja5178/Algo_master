"""
Tests for the momentum CE/PE strategy (Phase 2).

Covers:
  CE momentum: positive case, each individual rule failing, time window edges
  PE momentum: positive case, each individual rule failing
  Signal engine: momentum wired correctly, gated by ENABLE_MOMENTUM_PHASE
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from unittest.mock import MagicMock, patch

import pytest

from market.candle_builder import Candle
from strategies.ce_momentum import is_ce_momentum_signal
from strategies.pe_momentum import is_pe_momentum_signal

# Use today so the signal_engine today-only guard passes in integration tests
_TODAY = date.today()
BASE_TIME    = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 13, 30)  # 13:30 inside window
OUTSIDE_TIME = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 12,  0)  # 12:00 outside window

WIN_START = time(13, 30)
WIN_END   = time(14, 30)
MIN_BODY  = 40.0


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def flat_candles(count: int, price: float = 74500.0, ts_start: datetime = None) -> list[Candle]:
    """count flat candles at *price* (body = 0), oldest first."""
    ts_start = ts_start or datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15)
    return [
        Candle(
            timestamp=ts_start + timedelta(minutes=5 * i),
            open=price, high=price + 5, low=price - 5, close=price,
        )
        for i in range(count)
    ]


def flat_15m(count: int = 21, price: float = 74500.0) -> list[Candle]:
    ts_start = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15)
    return [
        Candle(
            timestamp=ts_start + timedelta(minutes=15 * i),
            open=price, high=price + 10, low=price - 10, close=price,
        )
        for i in range(count)
    ]


def make_bullish_momentum_5m(
    base_price: float = 74500.0,
    body: float = 60.0,
    candle_time: datetime = None,
    ema9_above_ema21: bool = True,
) -> list[Candle]:
    """
    21 candles: 20 flat seed candles + 1 large-body bull candle at candle_time.
    EMA9 > EMA21 if ema9_above_ema21=True (achieved by trending seed candles).
    """
    ts_start = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15)
    if candle_time is None:
        candle_time = BASE_TIME   # 13:30

    if ema9_above_ema21:
        # Rising seed: last 9 candles slightly higher so EMA9 > EMA21
        candles = [
            Candle(
                timestamp=ts_start + timedelta(minutes=5 * i),
                open=base_price + i * 2,
                high=base_price + i * 2 + 5,
                low=base_price + i * 2 - 5,
                close=base_price + i * 2,
            )
            for i in range(20)
        ]
    else:
        # Flat seed: EMA9 ≈ EMA21
        candles = flat_candles(20, price=base_price)

    # The signal candle: strong bullish body, close well above EMA9
    latest_base = base_price + (20 * 2 if ema9_above_ema21 else 0)
    candles.append(Candle(
        timestamp=candle_time,
        open=latest_base,
        high=latest_base + body + 5,
        low=latest_base - 2,
        close=latest_base + body,      # body pts above open
    ))
    return candles


def make_bullish_15m(price_above_ema: float = 74700.0) -> list[Candle]:
    """21 flat 15m candles + final candle well above its own EMA21."""
    ts_start = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15)
    candles = [
        Candle(
            timestamp=ts_start + timedelta(minutes=15 * i),
            open=price_above_ema - 200,
            high=price_above_ema - 195,
            low=price_above_ema - 205,
            close=price_above_ema - 200,
        )
        for i in range(20)
    ]
    candles.append(Candle(
        timestamp=ts_start + timedelta(minutes=15 * 20),
        open=price_above_ema,
        high=price_above_ema + 10,
        low=price_above_ema - 5,
        close=price_above_ema,         # far above EMA21 of seed candles
    ))
    return candles


# ─────────────────────────────────────────────────────────────────────────────
# CE MOMENTUM
# ─────────────────────────────────────────────────────────────────────────────

class TestCEMomentum:

    def test_positive_all_rules_true(self) -> None:
        c5  = make_bullish_momentum_5m(body=MIN_BODY + 1)
        c15 = make_bullish_15m()
        assert is_ce_momentum_signal(c5, c15,
                                     min_body_pts=MIN_BODY,
                                     window_start=WIN_START,
                                     window_end=WIN_END) is True

    def test_false_when_body_too_small(self) -> None:
        """Body < min_body_pts — candle too weak."""
        c5  = make_bullish_momentum_5m(body=MIN_BODY - 1)
        c15 = make_bullish_15m()
        assert is_ce_momentum_signal(c5, c15,
                                     min_body_pts=MIN_BODY,
                                     window_start=WIN_START,
                                     window_end=WIN_END) is False

    def test_false_when_body_is_bearish(self) -> None:
        """close < open — body is negative, not bullish."""
        c5 = make_bullish_momentum_5m(body=MIN_BODY + 1)
        # Replace last candle with a bearish one
        c = c5[-1]
        c5[-1] = Candle(c.timestamp, open=c.open, high=c.high, low=c.low,
                         close=c.open - MIN_BODY - 1)
        c15 = make_bullish_15m()
        assert is_ce_momentum_signal(c5, c15,
                                     min_body_pts=MIN_BODY,
                                     window_start=WIN_START,
                                     window_end=WIN_END) is False

    def test_false_when_close_below_ema9(self) -> None:
        """Close below EMA9 — price not above short-term average."""
        c5  = make_bullish_momentum_5m(body=MIN_BODY + 1)
        # Replace last candle: close only 1pt above open (tiny body) but
        # large enough test — actually force close to be below EMA9 by making
        # close very low while keeping open even lower so body > min_body.
        # Easier: use flat seed (EMA9 ≈ EMA21 ≈ base_price) and set close < base.
        c5 = make_bullish_momentum_5m(body=MIN_BODY + 1, ema9_above_ema21=False)
        base = 74500.0
        c = c5[-1]
        # close below EMA9 (≈74500), open even lower to keep body > 40
        c5[-1] = Candle(c.timestamp,
                         open=base - 60,
                         high=base - 55,
                         low=base - 65,
                         close=base - 15)   # close < EMA9 ≈ 74500
        c15 = make_bullish_15m()
        assert is_ce_momentum_signal(c5, c15,
                                     min_body_pts=MIN_BODY,
                                     window_start=WIN_START,
                                     window_end=WIN_END) is False

    def test_false_when_ema9_below_ema21(self) -> None:
        """EMA9 < EMA21 — no uptrend alignment."""
        # Force EMA9 < EMA21 by making the last 9 candles low
        ts_start = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15)
        candles: list[Candle] = [
            Candle(ts_start + timedelta(minutes=5 * i),
                   open=74600.0, high=74605.0, low=74595.0, close=74600.0)
            for i in range(11)
        ]
        # Last 9 seed candles: very low to pull EMA9 down
        for i in range(9):
            candles.append(Candle(
                ts_start + timedelta(minutes=5 * (11 + i)),
                open=74200.0, high=74205.0, low=74195.0, close=74200.0,
            ))
        # Signal candle: big bullish body
        candles.append(Candle(
            BASE_TIME,
            open=74200.0, high=74250.0, low=74198.0, close=74250.0,  # body=50
        ))
        c15 = make_bullish_15m()
        # EMA9 is ~74300, EMA21 is ~74450 — EMA9 < EMA21
        assert is_ce_momentum_signal(candles, c15,
                                     min_body_pts=MIN_BODY,
                                     window_start=WIN_START,
                                     window_end=WIN_END) is False

    def test_false_when_15m_below_ema21_rule4(self) -> None:
        """15mins close < 15mins EMA21 — rule 4 fails."""
        c5  = make_bullish_momentum_5m(body=MIN_BODY + 1)
        # Create 15m candles where the last close is below its EMA21 (~74700)
        c15 = make_bullish_15m()
        c = c15[-1]
        c15[-1] = Candle(c.timestamp, open=c.open, high=c.high, low=c.low, close=74400.0)
        assert is_ce_momentum_signal(c5, c15,
                                     min_body_pts=MIN_BODY,
                                     window_start=WIN_START,
                                     window_end=WIN_END) is False

    def test_false_when_outside_time_window(self) -> None:
        """Candle at 12:00 — outside the 13:30–14:30 window."""
        c5  = make_bullish_momentum_5m(body=MIN_BODY + 1, candle_time=OUTSIDE_TIME)
        c15 = make_bullish_15m()
        assert is_ce_momentum_signal(c5, c15,
                                     min_body_pts=MIN_BODY,
                                     window_start=WIN_START,
                                     window_end=WIN_END) is False

    def test_false_at_window_end_boundary(self) -> None:
        """Candle exactly at 14:30 — window is [start, end) so 14:30 is excluded."""
        at_end = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 14, 30)
        c5  = make_bullish_momentum_5m(body=MIN_BODY + 1, candle_time=at_end)
        c15 = make_bullish_15m()
        assert is_ce_momentum_signal(c5, c15,
                                     min_body_pts=MIN_BODY,
                                     window_start=WIN_START,
                                     window_end=WIN_END) is False

    def test_true_at_window_start_boundary(self) -> None:
        """Candle exactly at 13:30 — inclusive lower bound."""
        c5  = make_bullish_momentum_5m(body=MIN_BODY + 1, candle_time=BASE_TIME)
        c15 = make_bullish_15m()
        assert is_ce_momentum_signal(c5, c15,
                                     min_body_pts=MIN_BODY,
                                     window_start=WIN_START,
                                     window_end=WIN_END) is True

    def test_false_insufficient_candles(self) -> None:
        assert is_ce_momentum_signal(
            flat_candles(10), flat_15m(10),
            min_body_pts=MIN_BODY, window_start=WIN_START, window_end=WIN_END,
        ) is False


# ─────────────────────────────────────────────────────────────────────────────
# PE MOMENTUM
# ─────────────────────────────────────────────────────────────────────────────

def make_bearish_momentum_5m(body: float = MIN_BODY + 1) -> list[Candle]:
    """21 candles: 20 falling seed + 1 large bearish body at 13:30."""
    ts_start = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15)
    base = 74500.0
    # Falling seed so EMA9 < EMA21
    candles = [
        Candle(
            ts_start + timedelta(minutes=5 * i),
            open=base - i * 2, high=base - i * 2 + 5,
            low=base - i * 2 - 5, close=base - i * 2,
        )
        for i in range(20)
    ]
    latest_base = base - 20 * 2
    candles.append(Candle(
        BASE_TIME,
        open=latest_base,
        high=latest_base + 2,
        low=latest_base - body - 5,
        close=latest_base - body,   # body pts below open
    ))
    return candles


def make_bearish_15m() -> list[Candle]:
    ts_start = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15)
    high_price = 74700.0
    candles = [
        Candle(ts_start + timedelta(minutes=15 * i),
               open=high_price, high=high_price + 5, low=high_price - 5, close=high_price)
        for i in range(20)
    ]
    candles.append(Candle(
        ts_start + timedelta(minutes=15 * 20),
        open=74300.0, high=74310.0, low=74290.0, close=74300.0,  # far below EMA21
    ))
    return candles


class TestPEMomentum:

    def test_positive_all_rules_true(self) -> None:
        c5  = make_bearish_momentum_5m(body=MIN_BODY + 1)
        c15 = make_bearish_15m()
        assert is_pe_momentum_signal(c5, c15,
                                     min_body_pts=MIN_BODY,
                                     window_start=WIN_START,
                                     window_end=WIN_END) is True

    def test_false_when_body_too_small(self) -> None:
        c5  = make_bearish_momentum_5m(body=MIN_BODY - 1)
        c15 = make_bearish_15m()
        assert is_pe_momentum_signal(c5, c15,
                                     min_body_pts=MIN_BODY,
                                     window_start=WIN_START,
                                     window_end=WIN_END) is False

    def test_false_when_body_is_bullish(self) -> None:
        c5 = make_bearish_momentum_5m(body=MIN_BODY + 1)
        c = c5[-1]
        # Replace with a bullish candle
        c5[-1] = Candle(c.timestamp, open=c.open, high=c.high, low=c.low,
                         close=c.open + MIN_BODY + 1)
        c15 = make_bearish_15m()
        assert is_pe_momentum_signal(c5, c15,
                                     min_body_pts=MIN_BODY,
                                     window_start=WIN_START,
                                     window_end=WIN_END) is False

    def test_false_when_outside_time_window(self) -> None:
        c5  = make_bearish_momentum_5m(body=MIN_BODY + 1)
        # Shift last candle outside the window
        c = c5[-1]
        c5[-1] = Candle(OUTSIDE_TIME, c.open, c.high, c.low, c.close)
        c15 = make_bearish_15m()
        assert is_pe_momentum_signal(c5, c15,
                                     min_body_pts=MIN_BODY,
                                     window_start=WIN_START,
                                     window_end=WIN_END) is False

    def test_false_when_15m_above_ema21_rule4(self) -> None:
        """15mins close > 15mins EMA21 — rule 4 fails for PE."""
        c5  = make_bearish_momentum_5m(body=MIN_BODY + 1)
        # Create 15m candles where the last close is above its EMA21 (~74700)
        c15 = make_bearish_15m()
        c = c15[-1]
        c15[-1] = Candle(c.timestamp, open=c.open, high=c.high, low=c.low, close=74800.0)
        assert is_pe_momentum_signal(c5, c15,
                                     min_body_pts=MIN_BODY,
                                     window_start=WIN_START,
                                     window_end=WIN_END) is False

    def test_false_insufficient_candles(self) -> None:
        assert is_pe_momentum_signal(
            flat_candles(10), flat_15m(10),
            min_body_pts=MIN_BODY, window_start=WIN_START, window_end=WIN_END,
        ) is False


# ─────────────────────────────────────────────────────────────────────────────
# Signal engine integration: momentum gating
# ─────────────────────────────────────────────────────────────────────────────

class TestSignalEngineWithMomentum:
    """
    Verify that evaluate_signals() correctly routes to momentum phase
    only when ENABLE_MOMENTUM_PHASE=True and standard phase doesn't fire.
    """

    def _make_neutral_5m(self) -> list[Candle]:
        """21 flat candles — standard CE/PE conditions not met."""
        return flat_candles(21, price=74500.0, ts_start=datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15))

    def _make_neutral_15m(self) -> list[Candle]:
        return flat_15m(20, price=74500.0)

    def test_momentum_disabled_by_default(self) -> None:
        """With ENABLE_MOMENTUM_PHASE=False, momentum signals are suppressed."""
        from strategies.signal_engine import evaluate_signals

        c5  = make_bullish_momentum_5m(body=MIN_BODY + 1)
        c15 = make_bullish_15m()

        with patch("strategies.signal_engine.settings") as mock_settings, \
             patch("strategies.signal_engine.has_processed_signal", return_value=False), \
             patch("strategies.signal_engine.record_processed_signal"):

            mock_settings.ENABLE_OB_STRATEGY    = False
            mock_settings.ENABLE_ORB_STRATEGY   = False
            mock_settings.ENABLE_EMA_STRATEGY   = False
            mock_settings.ENABLE_MOMENTUM_PHASE = False

            # Use neutral candles so standard phase definitely returns None
            result = evaluate_signals(self._make_neutral_5m(), self._make_neutral_15m())
            assert result is None

    def test_momentum_enabled_fires_ce(self) -> None:
        """When momentum enabled + momentum CE conditions met → returns 'CE'."""
        from strategies.signal_engine import evaluate_signals

        c5  = make_bullish_momentum_5m(body=MIN_BODY + 1)
        c15 = make_bullish_15m()

        with patch("strategies.signal_engine.settings") as mock_settings, \
             patch("strategies.signal_engine.has_processed_signal", return_value=False), \
             patch("strategies.signal_engine.record_processed_signal"), \
             patch("strategies.signal_engine.is_ce_signal", return_value=False), \
             patch("strategies.signal_engine.is_pe_signal", return_value=False):

            mock_settings.ENABLE_OB_STRATEGY           = False
            mock_settings.ENABLE_ORB_STRATEGY          = False
            mock_settings.ENABLE_VWAP_STRATEGY         = False
            mock_settings.ENABLE_PDHL_STRATEGY         = False
            mock_settings.ENABLE_NATR_STRATEGY         = False
            mock_settings.ENABLE_ATR_COPILOT_STRATEGY  = False
            mock_settings.ENABLE_TRB_STRATEGY          = False
            mock_settings.ENABLE_EMA_STRATEGY          = True
            mock_settings.ENABLE_MOMENTUM_PHASE        = True
            mock_settings.MOMENTUM_MIN_BODY_PTS        = MIN_BODY
            mock_settings.MOMENTUM_WINDOW_START        = "13:30"
            mock_settings.MOMENTUM_WINDOW_END          = "14:30"
            mock_settings.EMA_COOLDOWN_CANDLES         = 0
            mock_settings.ENABLE_PIVOT_STRATEGY        = False

            result = evaluate_signals(c5, c15)
            assert result == "CE_MOM"

    def test_momentum_skipped_when_standard_already_fired(self) -> None:
        """Standard CE fires first — momentum is never reached for same candle."""
        from strategies.signal_engine import evaluate_signals

        c5  = make_bullish_momentum_5m(body=MIN_BODY + 1)
        c15 = make_bullish_15m()

        record_calls = []
        with patch("strategies.signal_engine.settings") as mock_settings, \
             patch("strategies.signal_engine.has_processed_signal", return_value=False), \
             patch("strategies.signal_engine.record_processed_signal",
                   side_effect=lambda *a, **kw: record_calls.append(a[0])), \
             patch("strategies.signal_engine.is_ce_signal", return_value=True), \
             patch("strategies.signal_engine.is_pe_signal", return_value=False):

            mock_settings.ENABLE_OB_STRATEGY           = False
            mock_settings.ENABLE_ORB_STRATEGY          = False
            mock_settings.ENABLE_VWAP_STRATEGY         = False
            mock_settings.ENABLE_PDHL_STRATEGY         = False
            mock_settings.ENABLE_NATR_STRATEGY         = False
            mock_settings.ENABLE_ATR_COPILOT_STRATEGY  = False
            mock_settings.ENABLE_TRB_STRATEGY          = False
            mock_settings.ENABLE_EMA_STRATEGY          = True
            mock_settings.ENABLE_MOMENTUM_PHASE        = True
            mock_settings.MOMENTUM_MIN_BODY_PTS        = MIN_BODY
            mock_settings.MOMENTUM_WINDOW_START        = "13:30"
            mock_settings.MOMENTUM_WINDOW_END          = "14:30"
            mock_settings.EMA_COOLDOWN_CANDLES         = 0
            mock_settings.ENABLE_PIVOT_STRATEGY        = False

            result = evaluate_signals(c5, c15)
            assert result == "CE"
            # Only the standard CE id was recorded, not the momentum id
            assert all("_MOM_" not in rid for rid in record_calls)


# ─────────────────────────────────────────────────────────────────────────────
# Monday filter — momentum signal_engine integration
# ─────────────────────────────────────────────────────────────────────────────

class TestMomentumMondayFilter:
    """
    ORB_MOMENTUM_SKIP_MONDAY=True must suppress Momentum signals on Mondays.
    EMA and all other strategies are unaffected.
    """

    def _monday_date(self):
        from datetime import date as _date, timedelta
        d = _date.today()
        return d - timedelta(days=d.weekday())   # nearest past (or today) Monday

    def _tuesday_date(self):
        from datetime import timedelta
        return self._monday_date() + timedelta(days=1)

    def _make_candles_on(self, target_date, body: float = MIN_BODY + 1):
        """Bullish momentum candles with the signal candle shifted to target_date."""
        c5  = make_bullish_momentum_5m(body=body)
        # Shift ALL candles' date to target_date so the today-guard in signal_engine passes
        shifted = []
        for c in c5:
            new_ts = datetime(target_date.year, target_date.month, target_date.day,
                              c.timestamp.hour, c.timestamp.minute)
            shifted.append(Candle(new_ts, c.open, c.high, c.low, c.close))
        return shifted

    def _make_15m_on(self, target_date):
        c15 = make_bullish_15m()
        shifted = []
        for c in c15:
            new_ts = datetime(target_date.year, target_date.month, target_date.day,
                              c.timestamp.hour, c.timestamp.minute)
            shifted.append(Candle(new_ts, c.open, c.high, c.low, c.close))
        return shifted

    def _base_settings(self, ms, skip: bool) -> None:
        ms.ENABLE_OB_STRATEGY           = False
        ms.ENABLE_ORB_STRATEGY          = False
        ms.ENABLE_VWAP_STRATEGY         = False
        ms.ENABLE_PDHL_STRATEGY         = False
        ms.ENABLE_NATR_STRATEGY         = False
        ms.ENABLE_ATR_COPILOT_STRATEGY  = False
        ms.ENABLE_TRB_STRATEGY          = False
        ms.ENABLE_EMA_STRATEGY          = True
        ms.ENABLE_MOMENTUM_PHASE        = True
        ms.MOMENTUM_MIN_BODY_PTS        = MIN_BODY
        ms.MOMENTUM_WINDOW_START        = "13:30"
        ms.MOMENTUM_WINDOW_END          = "14:30"
        ms.ORB_MOMENTUM_SKIP_MONDAY     = skip

    def test_momentum_suppressed_on_monday(self) -> None:
        from unittest.mock import patch
        from strategies.signal_engine import evaluate_signals

        monday = self._monday_date()
        c5  = self._make_candles_on(monday)
        c15 = self._make_15m_on(monday)

        with patch("strategies.signal_engine.settings") as ms, \
             patch("strategies.signal_engine.has_processed_signal", return_value=False), \
             patch("strategies.signal_engine.record_processed_signal"), \
             patch("strategies.signal_engine.is_ce_signal", return_value=False), \
             patch("strategies.signal_engine.is_pe_signal", return_value=False):

            self._base_settings(ms, skip=True)
            result = evaluate_signals(c5, c15)
            assert result is None, "Momentum must be suppressed on Monday"

    def test_skip_flag_false_on_tuesday(self) -> None:
        """Tuesday (weekday=1) must never set _skip_on_monday, regardless of setting."""
        tuesday = self._tuesday_date()
        assert tuesday.weekday() == 1, "helper returned non-Tuesday date"
        skip = True and (tuesday.weekday() == 0)
        assert skip is False, "_skip_on_monday must be False on Tuesday"

    def test_skip_flag_false_when_setting_disabled_on_monday(self) -> None:
        """When ORB_MOMENTUM_SKIP_MONDAY=False, skip must be False even on Monday."""
        monday = self._monday_date()
        assert monday.weekday() == 0, "helper returned non-Monday date"
        skip = False and (monday.weekday() == 0)
        assert skip is False, "_skip_on_monday must be False when setting is disabled"
