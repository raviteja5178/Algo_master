"""Tests for VWAP calculator and VWAP Retest strategy."""
from __future__ import annotations

from datetime import datetime, date, timedelta
import pytest

from market.candle_builder import Candle
from market.vwap import VWAPCalculator
from strategies.vwap_strategy import is_vwap_ce_signal, is_vwap_pe_signal

_TODAY = date.today()


def _ts(h: int, m: int) -> datetime:
    return datetime(_TODAY.year, _TODAY.month, _TODAY.day, h, m)


def _candle(h: int, m: int, o: float, hi: float, lo: float, c: float, vol: int = 100) -> Candle:
    return Candle(_ts(h, m), open=o, high=hi, low=lo, close=c, volume=vol)


# ── VWAPCalculator ────────────────────────────────────────────────────────────

class TestVWAPCalculator:

    def test_single_candle(self):
        v = VWAPCalculator()
        c = _candle(9, 15, 100, 110, 90, 105, vol=200)
        v.on_candle(c)
        # TP = (110+90+105)/3 = 101.67; VWAP = 101.67*200/200 = 101.67
        assert v.value == pytest.approx((110 + 90 + 105) / 3, rel=1e-4)

    def test_two_candles_weighted(self):
        v = VWAPCalculator()
        c1 = _candle(9, 15, 100, 110, 90, 100, vol=100)
        c2 = _candle(9, 20, 100, 120, 80, 120, vol=300)
        v.on_candle(c1)
        v.on_candle(c2)
        tp1 = (110 + 90 + 100) / 3
        tp2 = (120 + 80 + 120) / 3
        expected = (tp1 * 100 + tp2 * 300) / 400
        assert v.value == pytest.approx(expected, rel=1e-4)

    def test_reset_on_new_day(self):
        v = VWAPCalculator()
        from utils.time_utils import IST
        yesterday = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 10, 0) - timedelta(days=1)
        # Feed a tick for yesterday
        v.on_tick(75000.0, ts=yesterday.replace(tzinfo=IST))
        assert v.value is not None
        # Feed a tick for today — should reset
        today_ts = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 20)
        v.on_tick(74000.0, ts=today_ts.replace(tzinfo=IST))
        # Only today's tick should contribute
        assert v.value == pytest.approx(74000.0, rel=1e-4)

    def test_no_data_returns_none(self):
        v = VWAPCalculator()
        assert v.value is None

    def test_zero_volume_uses_proxy(self):
        v = VWAPCalculator()
        c = _candle(9, 15, 100, 110, 90, 105, vol=0)
        v.on_candle(c)
        # vol=0 → proxy vol=1; should still return a value
        assert v.value is not None


# ── is_vwap_ce_signal ─────────────────────────────────────────────────────────

class TestVWAPCESignal:

    def _make_candles(self, closes: list[float], highs: list[float] | None = None) -> list[Candle]:
        """Build candles with given closes; highs default to close+5."""
        result = []
        for i, c in enumerate(closes):
            h = (highs[i] if highs else c + 5)
            result.append(_candle(10, i * 5, c - 2, h, c - 8, c))
        return result

    def test_ce_signal_success(self):
        vwap = 73600.0
        # last 3 candles: below, below, below VWAP (retest) then current above
        candles = self._make_candles([73580, 73590, 73595, 73650])
        # prev high = 73600, current close = 73650 > prev high 73600
        candles[-2] = _candle(10, 15, 73590, 73600, 73580, 73595)
        candles[-1] = _candle(10, 20, 73600, 73660, 73598, 73650)
        assert is_vwap_ce_signal(candles, vwap, retest_lookback=3) is True

    def test_ce_no_retest(self):
        vwap = 73600.0
        # All previous candles are above VWAP — no retest dip
        candles = self._make_candles([73620, 73630, 73640, 73660])
        candles[-2] = _candle(10, 15, 73630, 73645, 73625, 73640)
        candles[-1] = _candle(10, 20, 73640, 73665, 73638, 73660)
        assert is_vwap_ce_signal(candles, vwap, retest_lookback=3) is False

    def test_ce_current_below_vwap(self):
        vwap = 73600.0
        candles = self._make_candles([73580, 73590, 73595, 73590])
        assert is_vwap_ce_signal(candles, vwap, retest_lookback=3) is False

    def test_ce_no_momentum(self):
        # current close <= previous high — no momentum confirmation
        vwap = 73600.0
        candles = self._make_candles([73580, 73590, 73595, 73610])
        # prev candle high = 73620 (above current close 73610)
        candles[-2] = _candle(10, 15, 73590, 73620, 73580, 73595)
        candles[-1] = _candle(10, 20, 73595, 73615, 73593, 73610)
        assert is_vwap_ce_signal(candles, vwap, retest_lookback=3) is False

    def test_ce_vwap_none(self):
        candles = self._make_candles([73580, 73590, 73595, 73650])
        assert is_vwap_ce_signal(candles, None) is False

    def test_ce_min_bounce_filter(self):
        vwap = 73600.0
        candles = self._make_candles([73580, 73590, 73595, 73605])
        candles[-2] = _candle(10, 15, 73590, 73600, 73580, 73595)
        candles[-1] = _candle(10, 20, 73600, 73610, 73598, 73605)
        # close=73605 — only 5 pts above VWAP; min_bounce=10 should block
        assert is_vwap_ce_signal(candles, vwap, retest_lookback=3, min_bounce_pts=10) is False
        assert is_vwap_ce_signal(candles, vwap, retest_lookback=3, min_bounce_pts=3) is True

    def test_ce_excessive_submerge(self):
        vwap = 73600.0
        # 5 consecutive candles below VWAP before bouncing above
        candles = self._make_candles([73550, 73560, 73570, 73580, 73590, 73650])
        candles[-2] = _candle(10, 25, 73580, 73595, 73575, 73590)
        candles[-1] = _candle(10, 30, 73590, 73660, 73588, 73650)
        # With max_submerged_candles=3, 5 submerged candles should block
        assert is_vwap_ce_signal(candles, vwap, max_submerged_candles=3) is False
        # With max_submerged_candles=0 (disabled) or >= 5, it allows
        assert is_vwap_ce_signal(candles, vwap, max_submerged_candles=0) is True
        assert is_vwap_ce_signal(candles, vwap, max_submerged_candles=5) is True


# ── is_vwap_pe_signal ─────────────────────────────────────────────────────────

class TestVWAPPESignal:

    def _make_candles(self, closes: list[float]) -> list[Candle]:
        result = []
        for i, c in enumerate(closes):
            result.append(_candle(10, i * 5, c + 2, c + 8, c - 5, c))
        return result

    def test_pe_signal_success(self):
        vwap = 73600.0
        candles = self._make_candles([73620, 73615, 73610, 73550])
        candles[-2] = _candle(10, 15, 73615, 73625, 73605, 73610)
        candles[-1] = _candle(10, 20, 73610, 73612, 73545, 73550)
        assert is_vwap_pe_signal(candles, vwap, retest_lookback=3) is True

    def test_pe_no_retest(self):
        vwap = 73600.0
        # All previous candles below VWAP — no pop above VWAP
        candles = self._make_candles([73580, 73570, 73560, 73540])
        assert is_vwap_pe_signal(candles, vwap, retest_lookback=3) is False

    def test_pe_current_above_vwap(self):
        vwap = 73600.0
        candles = self._make_candles([73620, 73615, 73610, 73620])
        assert is_vwap_pe_signal(candles, vwap, retest_lookback=3) is False

    def test_pe_vwap_none(self):
        candles = self._make_candles([73620, 73610, 73605, 73550])
        assert is_vwap_pe_signal(candles, None) is False

    def test_pe_excessive_submerge(self):
        vwap = 73600.0
        # 5 consecutive candles above VWAP before breaking below
        candles = self._make_candles([73650, 73640, 73630, 73620, 73610, 73550])
        candles[-2] = _candle(10, 25, 73620, 73625, 73605, 73610)
        candles[-1] = _candle(10, 30, 73610, 73612, 73545, 73550)
        # With max_submerged_candles=3, 5 emerged candles should block
        assert is_vwap_pe_signal(candles, vwap, max_submerged_candles=3) is False
        # With max_submerged_candles=0 (disabled) or >= 5, it allows
        assert is_vwap_pe_signal(candles, vwap, max_submerged_candles=0) is True
        assert is_vwap_pe_signal(candles, vwap, max_submerged_candles=5) is True


# ── Signal Engine Integration (ENABLE_CE_VWAP / ENABLE_PE_VWAP) ───────────────

class TestVWAPSignalEngineIntegration:

    def _make_bullish_vwap_candles(self) -> tuple[list[Candle], list[Candle]]:
        # 5m candles: 3 below VWAP (73600), last one breaking above
        c5 = [
            _candle(10, 0, 73580, 73590, 73570, 73580),
            _candle(10, 5, 73580, 73595, 73575, 73590),
            _candle(10, 10, 73590, 73600, 73580, 73595),
            _candle(10, 15, 73600, 73660, 73598, 73650),
        ]
        c15 = [
            _candle(10, 0, 73580, 73660, 73570, 73650),
        ]
        return c5, c15

    def _make_bearish_vwap_candles(self) -> tuple[list[Candle], list[Candle]]:
        # 5m candles: 3 above VWAP (73600), last one breaking below
        c5 = [
            _candle(10, 0, 73620, 73630, 73615, 73620),
            _candle(10, 5, 73620, 73625, 73605, 73615),
            _candle(10, 10, 73615, 73620, 73600, 73610),
            _candle(10, 15, 73610, 73612, 73545, 73550),
        ]
        c15 = [
            _candle(10, 0, 73620, 73630, 73545, 73550),
        ]
        return c5, c15

    def test_ce_vwap_disabled_blocks_signal(self):
        from unittest.mock import patch
        from strategies.signal_engine import evaluate_signals

        c5, c15 = self._make_bullish_vwap_candles()
        with patch("strategies.signal_engine.settings") as ms, \
             patch("strategies.signal_engine.has_processed_signal", return_value=False), \
             patch("strategies.signal_engine.claim_signal_atomic", return_value=True), \
             patch("strategies.signal_engine.record_processed_signal"):

            ms.ENABLE_OB_STRATEGY = False
            ms.ENABLE_ORB_STRATEGY = False
            ms.ENABLE_PIVOT_STRATEGY = False
            ms.ENABLE_VWAP_STRATEGY = True
            ms.ENABLE_CE_VWAP = False
            ms.ENABLE_PE_VWAP = True
            ms.ENABLE_PDHL_STRATEGY = False
            ms.ENABLE_NATR_STRATEGY = False
            ms.ENABLE_ATR_COPILOT_STRATEGY = False
            ms.ENABLE_TRB_STRATEGY = False
            ms.ENABLE_EMA_STRATEGY = False
            ms.ENABLE_MOMENTUM_PHASE = False
            ms.ENABLE_VWAP_LEVEL_FILTER = False
            ms.ORB_SESSION_QUALIFIER = False
            ms.MAX_TRADES_PER_SIDE = 0
            ms.VWAP_RETEST_LOOKBACK = 3
            ms.VWAP_MIN_BOUNCE_PTS = 0.0
            ms.VWAP_MAX_SUBMERGED_CANDLES = 3
            ms.VWAP_SLOPE_LOOKBACK = 0
            ms.VWAP_NO_NEW_ENTRY_AFTER = ""

            sig = evaluate_signals(c5, c15, vwap=73600.0)
            assert sig is None

    def test_ce_vwap_enabled_fires_signal(self):
        from unittest.mock import patch
        from strategies.signal_engine import evaluate_signals

        c5, c15 = self._make_bullish_vwap_candles()
        with patch("strategies.signal_engine.settings") as ms, \
             patch("strategies.signal_engine.has_processed_signal", return_value=False), \
             patch("strategies.signal_engine.claim_signal_atomic", return_value=True), \
             patch("strategies.signal_engine.record_processed_signal"):

            ms.ENABLE_OB_STRATEGY = False
            ms.ENABLE_ORB_STRATEGY = False
            ms.ENABLE_PIVOT_STRATEGY = False
            ms.ENABLE_VWAP_STRATEGY = True
            ms.ENABLE_CE_VWAP = True
            ms.ENABLE_PE_VWAP = True
            ms.ENABLE_PDHL_STRATEGY = False
            ms.ENABLE_NATR_STRATEGY = False
            ms.ENABLE_ATR_COPILOT_STRATEGY = False
            ms.ENABLE_TRB_STRATEGY = False
            ms.ENABLE_EMA_STRATEGY = False
            ms.ENABLE_MOMENTUM_PHASE = False
            ms.ENABLE_VWAP_LEVEL_FILTER = False
            ms.ORB_SESSION_QUALIFIER = False
            ms.MAX_TRADES_PER_SIDE = 0
            ms.VWAP_RETEST_LOOKBACK = 3
            ms.VWAP_MIN_BOUNCE_PTS = 0.0
            ms.VWAP_MAX_SUBMERGED_CANDLES = 3
            ms.VWAP_SLOPE_LOOKBACK = 0
            ms.VWAP_NO_NEW_ENTRY_AFTER = ""

            sig = evaluate_signals(c5, c15, vwap=73600.0)
            assert sig == "CE_VWAP"

    def test_pe_vwap_disabled_blocks_signal(self):
        from unittest.mock import patch
        from strategies.signal_engine import evaluate_signals

        c5, c15 = self._make_bearish_vwap_candles()
        with patch("strategies.signal_engine.settings") as ms, \
             patch("strategies.signal_engine.has_processed_signal", return_value=False), \
             patch("strategies.signal_engine.claim_signal_atomic", return_value=True), \
             patch("strategies.signal_engine.record_processed_signal"):

            ms.ENABLE_OB_STRATEGY = False
            ms.ENABLE_ORB_STRATEGY = False
            ms.ENABLE_PIVOT_STRATEGY = False
            ms.ENABLE_VWAP_STRATEGY = True
            ms.ENABLE_CE_VWAP = True
            ms.ENABLE_PE_VWAP = False
            ms.ENABLE_PDHL_STRATEGY = False
            ms.ENABLE_NATR_STRATEGY = False
            ms.ENABLE_ATR_COPILOT_STRATEGY = False
            ms.ENABLE_TRB_STRATEGY = False
            ms.ENABLE_EMA_STRATEGY = False
            ms.ENABLE_MOMENTUM_PHASE = False
            ms.ENABLE_VWAP_LEVEL_FILTER = False
            ms.ORB_SESSION_QUALIFIER = False
            ms.MAX_TRADES_PER_SIDE = 0
            ms.VWAP_RETEST_LOOKBACK = 3
            ms.VWAP_MIN_BOUNCE_PTS = 0.0
            ms.VWAP_MAX_SUBMERGED_CANDLES = 3
            ms.VWAP_SLOPE_LOOKBACK = 0
            ms.VWAP_NO_NEW_ENTRY_AFTER = ""

            sig = evaluate_signals(c5, c15, vwap=73600.0)
            assert sig is None

    def test_pe_vwap_enabled_fires_signal(self):
        from unittest.mock import patch
        from strategies.signal_engine import evaluate_signals

        c5, c15 = self._make_bearish_vwap_candles()
        with patch("strategies.signal_engine.settings") as ms, \
             patch("strategies.signal_engine.has_processed_signal", return_value=False), \
             patch("strategies.signal_engine.claim_signal_atomic", return_value=True), \
             patch("strategies.signal_engine.record_processed_signal"):

            ms.ENABLE_OB_STRATEGY = False
            ms.ENABLE_ORB_STRATEGY = False
            ms.ENABLE_PIVOT_STRATEGY = False
            ms.ENABLE_VWAP_STRATEGY = True
            ms.ENABLE_CE_VWAP = True
            ms.ENABLE_PE_VWAP = True
            ms.ENABLE_PDHL_STRATEGY = False
            ms.ENABLE_NATR_STRATEGY = False
            ms.ENABLE_ATR_COPILOT_STRATEGY = False
            ms.ENABLE_TRB_STRATEGY = False
            ms.ENABLE_EMA_STRATEGY = False
            ms.ENABLE_MOMENTUM_PHASE = False
            ms.ENABLE_VWAP_LEVEL_FILTER = False
            ms.ORB_SESSION_QUALIFIER = False
            ms.MAX_TRADES_PER_SIDE = 0
            ms.VWAP_RETEST_LOOKBACK = 3
            ms.VWAP_MIN_BOUNCE_PTS = 0.0
            ms.VWAP_MAX_SUBMERGED_CANDLES = 3
            ms.VWAP_SLOPE_LOOKBACK = 0
            ms.VWAP_NO_NEW_ENTRY_AFTER = ""

            sig = evaluate_signals(c5, c15, vwap=73600.0)
            assert sig == "PE_VWAP"


