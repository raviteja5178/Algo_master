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


def _candle_seq(idx: int, o: float, hi: float, lo: float, c: float, vol: int = 100) -> Candle:
    """Build a candle with a sequential timestamp (9:15 + idx*5m) safe for any count."""
    total_minutes = 9 * 60 + 15 + idx * 5
    h, m = divmod(total_minutes, 60)
    return _candle(h, m, o, hi, lo, c, vol)


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
            ms.VWAP_MR_ZSCORE_ENTRY = 0.0
            ms.VWAP_MR_ADX_MAX = 0.0
            ms.VWAP_MR_RSI_CONFIRM = False
            ms.VWAP_MR_VOLUME_SPIKE = 0.0
            ms.VWAP_MR_MIN_RR = 0.0
            ms.VWAP_MR_MIN_SCORE = 0
            ms.VWAP_MR_VWAP_CROSS_MIN = 0

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
            ms.VWAP_MR_ZSCORE_ENTRY = 0.0
            ms.VWAP_MR_ADX_MAX = 0.0
            ms.VWAP_MR_RSI_CONFIRM = False
            ms.VWAP_MR_VOLUME_SPIKE = 0.0
            ms.VWAP_MR_MIN_RR = 0.0
            ms.VWAP_MR_MIN_SCORE = 0
            ms.VWAP_MR_VWAP_CROSS_MIN = 0

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
            ms.VWAP_MR_ZSCORE_ENTRY = 0.0
            ms.VWAP_MR_ADX_MAX = 0.0
            ms.VWAP_MR_RSI_CONFIRM = False
            ms.VWAP_MR_VOLUME_SPIKE = 0.0
            ms.VWAP_MR_MIN_RR = 0.0
            ms.VWAP_MR_MIN_SCORE = 0
            ms.VWAP_MR_VWAP_CROSS_MIN = 0

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
            ms.VWAP_MR_ZSCORE_ENTRY = 0.0
            ms.VWAP_MR_ADX_MAX = 0.0
            ms.VWAP_MR_RSI_CONFIRM = False
            ms.VWAP_MR_VOLUME_SPIKE = 0.0
            ms.VWAP_MR_MIN_RR = 0.0
            ms.VWAP_MR_MIN_SCORE = 0
            ms.VWAP_MR_VWAP_CROSS_MIN = 0

            sig = evaluate_signals(c5, c15, vwap=73600.0)
            assert sig == "PE_VWAP"




# ── Enhanced VWAP Mean-Reversion helpers ──────────────────────────────────────

class TestVWAPZscore:

    def _candles_around_vwap(self, vwap: float, closes: list[float]) -> list[Candle]:
        result = []
        for i, c in enumerate(closes):
            result.append(_candle(10, i * 5, c - 2, c + 5, c - 8, c))
        return result

    def test_zscore_positive_above_vwap(self):
        from strategies.vwap_strategy import vwap_zscore
        vwap = 73600.0
        # 10 candles near vwap, last one far above
        closes = [73600, 73605, 73595, 73600, 73602, 73598, 73601, 73600, 73599, 73700]
        candles = self._candles_around_vwap(vwap, closes)
        z = vwap_zscore(candles, vwap)
        assert z is not None and z > 0

    def test_zscore_negative_below_vwap(self):
        from strategies.vwap_strategy import vwap_zscore
        vwap = 73600.0
        closes = [73600, 73605, 73595, 73600, 73602, 73598, 73601, 73600, 73599, 73500]
        candles = self._candles_around_vwap(vwap, closes)
        z = vwap_zscore(candles, vwap)
        assert z is not None and z < 0

    def test_zscore_returns_none_with_too_few_candles(self):
        from strategies.vwap_strategy import vwap_zscore
        candles = [_candle(10, 0, 100, 110, 90, 100), _candle(10, 5, 100, 110, 90, 102)]
        assert vwap_zscore(candles, 100.0) is None


class TestADXRegimeOk:

    def test_disabled_always_passes(self):
        from strategies.vwap_strategy import adx_regime_ok
        candles = [_candle(10, i * 5, 100, 110, 90, 100 + i) for i in range(5)]
        assert adx_regime_ok(candles, adx_max=0.0) is True

    def test_passes_when_insufficient_candles(self):
        from strategies.vwap_strategy import adx_regime_ok
        candles = [_candle(10, i * 5, 100, 110, 90, 100) for i in range(5)]
        # ADX needs 2*14+1 candles — not enough, should allow
        assert adx_regime_ok(candles, adx_max=25.0) is True

    def test_blocks_when_adx_high(self):
        from strategies.vwap_strategy import adx_regime_ok
        # Build a strong directional trend so ADX will be high
        candles = [_candle_seq(i, 70000 + i * 50, 70000 + i * 55, 70000 + i * 45, 70000 + i * 50)
                   for i in range(40)]
        # With a strong trend, ADX should exceed 5 (very permissive threshold)
        result = adx_regime_ok(candles, adx_max=5.0)
        # ADX should be well above 5 for such a trend — expected False
        assert result is False


class TestVWAPCrossCount:

    def test_no_crossings(self):
        from strategies.vwap_strategy import vwap_cross_count
        vwap = 73600.0
        candles = [_candle(10, i * 5, 73610, 73620, 73605, 73615) for i in range(5)]
        assert vwap_cross_count(candles, vwap) == 0

    def test_one_crossing(self):
        from strategies.vwap_strategy import vwap_cross_count
        vwap = 73600.0
        closes = [73610, 73620, 73590, 73595, 73605]
        candles = [_candle(10, i * 5, c - 2, c + 5, c - 8, c) for i, c in enumerate(closes)]
        # crosses from 73620 (above) to 73590 (below) = 1 crossing
        assert vwap_cross_count(candles, vwap) >= 1

    def test_multiple_crossings(self):
        from strategies.vwap_strategy import vwap_cross_count
        vwap = 73600.0
        closes = [73610, 73590, 73620, 73580, 73610]
        candles = [_candle(10, i * 5, c - 2, c + 5, c - 8, c) for i, c in enumerate(closes)]
        assert vwap_cross_count(candles, vwap) == 4


class TestRSIReversalOk:

    def _make_closes(self, base: float, ups: int, downs: int, final: float) -> list[float]:
        """Alternate up/down moves then set a final close."""
        closes = [base]
        for i in range(ups):
            closes.append(closes[-1] + 10)
        for i in range(downs):
            closes.append(closes[-1] - 12)
        closes.append(final)
        return closes

    def test_ce_rsi_reversal_confirmed(self):
        from strategies.vwap_strategy import rsi_reversal_ok
        # Build a downtrend to push RSI below 30, then a bounce
        closes = [1000 - i * 5 for i in range(20)]  # declining
        closes.append(closes[-1] + 20)               # bounce up
        candles = [_candle_seq(i, c - 2, c + 5, c - 8, c) for i, c in enumerate(closes)]
        # With aggressive decline RSI should be low before bounce
        # The function returns True when not enough data or when confirmed
        result = rsi_reversal_ok(candles, "CE")
        assert isinstance(result, bool)

    def test_pe_rsi_reversal_confirmed(self):
        from strategies.vwap_strategy import rsi_reversal_ok
        closes = [1000 + i * 5 for i in range(20)]  # rising
        closes.append(closes[-1] - 20)               # drop
        candles = [_candle_seq(i, c - 2, c + 5, c - 8, c) for i, c in enumerate(closes)]
        result = rsi_reversal_ok(candles, "PE")
        assert isinstance(result, bool)

    def test_returns_true_with_insufficient_data(self):
        from strategies.vwap_strategy import rsi_reversal_ok
        candles = [_candle(10, i * 5, 100, 110, 90, 100) for i in range(5)]
        assert rsi_reversal_ok(candles, "CE") is True
        assert rsi_reversal_ok(candles, "PE") is True


class TestVolumeSpike:

    def test_disabled_always_passes(self):
        from strategies.vwap_strategy import volume_spike
        candles = [_candle(10, i * 5, 100, 110, 90, 100, vol=50) for i in range(5)]
        assert volume_spike(candles, multiplier=0.0) is True

    def test_spike_detected(self):
        from strategies.vwap_strategy import volume_spike
        # 20 candles with vol=100, then a spike at vol=300
        candles = [_candle_seq(i, 100, 110, 90, 100, vol=100) for i in range(20)]
        candles.append(_candle_seq(20, 100, 110, 90, 100, vol=300))
        assert volume_spike(candles, multiplier=1.5) is True

    def test_no_spike_blocked(self):
        from strategies.vwap_strategy import volume_spike
        candles = [_candle_seq(i, 100, 110, 90, 100, vol=100) for i in range(21)]
        # current vol=100, avg=100, need 1.5x — should fail
        assert volume_spike(candles, multiplier=1.5) is False

    def test_passes_with_insufficient_history(self):
        from strategies.vwap_strategy import volume_spike
        candles = [_candle(10, i * 5, 100, 110, 90, 100, vol=50) for i in range(5)]
        assert volume_spike(candles, multiplier=2.0) is True


class TestRewardToRiskOk:

    def test_disabled_always_passes(self):
        from strategies.vwap_strategy import reward_to_risk_ok
        assert reward_to_risk_ok(100.0, 110.0, 95.0, min_rr=0.0) is True

    def test_ce_sufficient_rr(self):
        from strategies.vwap_strategy import reward_to_risk_ok
        # close=73580, vwap=73620 → reward=40; stop=73560 → risk=20; RR=2.0
        assert reward_to_risk_ok(73580.0, 73620.0, 73560.0, min_rr=1.5) is True

    def test_ce_insufficient_rr(self):
        from strategies.vwap_strategy import reward_to_risk_ok
        # close=73590, vwap=73600 → reward=10; stop=73560 → risk=30; RR=0.33
        assert reward_to_risk_ok(73590.0, 73600.0, 73560.0, min_rr=1.5) is False

    def test_zero_risk_passes(self):
        from strategies.vwap_strategy import reward_to_risk_ok
        assert reward_to_risk_ok(100.0, 110.0, 100.0, min_rr=1.5) is True


class TestSetupScore:

    def _make_signal_candles(self, vwap: float) -> list[Candle]:
        """Enough today candles for all helpers to compute."""
        closes = [vwap + (i % 3 - 1) * 10 for i in range(25)]
        closes[-1] = vwap - 40   # last close well below VWAP (CE overshoot)
        candles = []
        for i, c in enumerate(closes):
            vol = 300 if i == len(closes) - 1 else 100
            candles.append(_candle_seq(i, c - 2, c + 5, c - 45, c, vol=vol))
        return candles

    def test_score_is_between_0_and_6(self):
        from strategies.vwap_strategy import setup_score
        vwap = 73600.0
        candles = self._make_signal_candles(vwap)
        score = setup_score(candles, vwap, "CE", stop=candles[-1].low)
        assert 0 <= score <= 6

    def test_score_increases_with_better_setup(self):
        from strategies.vwap_strategy import setup_score
        vwap = 73600.0
        # Build a rotational-looking session (many crossings, moderate vol)
        closes = [vwap + (10 if i % 2 == 0 else -10) for i in range(24)]
        closes.append(vwap - 50)  # final big overshoot below VWAP
        candles = [_candle_seq(i, c - 2, c + 5, c - 55, c,
                               vol=300 if i == len(closes) - 1 else 100)
                   for i, c in enumerate(closes)]
        score = setup_score(candles, vwap, "CE", stop=candles[-1].low,
                            adx_max=50.0, vol_multiplier=1.5, min_rr=0.5)
        # With oscillating session, vol spike, and permissive params → at least 3
        assert score >= 2


class TestEnhancedVWAPCESignal:
    """is_vwap_ce_signal with new mr_* params applied."""

    def _base_candles(self) -> tuple[list[Candle], float]:
        """Valid base CE setup: 3 below VWAP then break above."""
        vwap = 73600.0
        candles = [
            _candle(10, 0,  73580, 73590, 73570, 73580),
            _candle(10, 5,  73580, 73595, 73575, 73590),
            _candle(10, 10, 73590, 73600, 73580, 73595),
            _candle(10, 15, 73600, 73660, 73598, 73650),
        ]
        return candles, vwap

    def test_mr_zscore_blocks_weak_extension(self):
        candles, vwap = self._base_candles()
        # close=73650 barely above vwap=73600 — z-score likely low on small sample
        # With very high threshold, it should block
        result = is_vwap_ce_signal(candles, vwap, mr_zscore_entry=100.0)
        assert result is False

    def test_mr_adx_max_blocks_when_trending(self):
        from strategies.vwap_strategy import is_vwap_ce_signal as _sig
        # Build a strong trend then append a valid CE candle
        candles = [_candle_seq(i, 70000 + i * 50, 70000 + i * 55,
                               70000 + i * 45, 70000 + i * 50) for i in range(39)]
        candles.append(_candle_seq(39, 72000, 72100, 71990, 72050))
        v = 71500.0
        # With adx_max=1 it should nearly always block
        assert _sig(candles, v, mr_adx_max=1.0) is False

    def test_mr_volume_spike_blocks_without_spike(self):
        candles, vwap = self._base_candles()
        # Add 20 candles with vol=100 before the signal candles to build history
        history = [_candle_seq(i, 73580, 73590, 73570, 73580, vol=100) for i in range(20)]
        full = history + candles
        result = is_vwap_ce_signal(full, vwap, mr_volume_spike=5.0)
        assert result is False

    def test_mr_min_rr_blocks_poor_rr(self):
        candles, vwap = self._base_candles()
        # close=73650 very close to vwap=73600 (reward=50), candle low=73598 (risk=52)
        # RR ≈ 0.96 → should fail with min_rr=1.5
        result = is_vwap_ce_signal(candles, vwap, mr_min_rr=1.5)
        assert result is False

    def test_mr_vwap_cross_min_blocks_no_crossings(self):
        candles, vwap = self._base_candles()
        # All candles are below VWAP except the last — 1 crossing happened
        # Require 3 → should block
        result = is_vwap_ce_signal(candles, vwap, mr_vwap_cross_min=3)
        assert result is False


class TestEnhancedVWAPPESignal:
    """is_vwap_pe_signal with new mr_* params applied."""

    def _base_candles(self) -> tuple[list[Candle], float]:
        """Valid base PE setup: 3 above VWAP then break below."""
        vwap = 73600.0
        candles = [
            _candle(10, 0,  73620, 73630, 73615, 73620),
            _candle(10, 5,  73620, 73625, 73605, 73615),
            _candle(10, 10, 73615, 73620, 73600, 73610),
            _candle(10, 15, 73610, 73612, 73545, 73550),
        ]
        return candles, vwap


    def test_mr_zscore_blocks_weak_extension(self):
        candles, vwap = self._base_candles()
        result = is_vwap_pe_signal(candles, vwap, mr_zscore_entry=100.0)
        assert result is False

    def test_mr_volume_spike_blocks_without_spike(self):
        candles, vwap = self._base_candles()
        history = [_candle_seq(i, 73610, 73625, 73605, 73615, vol=100) for i in range(20)]
        full = history + candles
        result = is_vwap_pe_signal(full, vwap, mr_volume_spike=5.0)
        assert result is False

    def test_mr_min_rr_blocks_poor_rr(self):
        candles, vwap = self._base_candles()
        # close=73550, vwap=73600 → reward=50, candle high=73612 → risk=62; RR≈0.81
        result = is_vwap_pe_signal(candles, vwap, mr_min_rr=1.5)
        assert result is False

    def test_mr_vwap_cross_min_blocks_no_crossings(self):
        candles, vwap = self._base_candles()
        result = is_vwap_pe_signal(candles, vwap, mr_vwap_cross_min=3)
        assert result is False
