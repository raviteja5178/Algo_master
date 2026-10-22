"""
Tests for evaluate_signals() per-strategy independence (Phase A).

These tests verify that the _candle_already_attempted cross-strategy suppression
has been removed.  Each strategy is evaluated and logged independently — a raw
signal fired by one strategy (even if Smart Entry blocks it) does NOT prevent
later strategies from being evaluated and logged on the same candle.

Key scenario covered: the 2026-10-05 TRB miss, where PE_VWAP fired first, was
blocked by cooldown, and PE_TRB was never evaluated because the old
_candle_already_attempted guard suppressed it.
"""

from __future__ import annotations

import inspect
import logging
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from market.candle_builder import Candle

_TODAY = date.today()


def _ts(h: int, m: int) -> datetime:
    return datetime(_TODAY.year, _TODAY.month, _TODAY.day, h, m)


def _candles_5m_1005() -> list[Candle]:
    """
    Build 2 5m candles for 10:05 evaluation:
      - c[-2] at 10:00 (completed candle, close above TRB low)
      - c[-1] at 10:05 (completed candle, close 72381 — below TRB low, PE breakout)
    Both carry today's date so signal_engine's today-only guard passes.
    """
    return [
        Candle(_ts(10, 0), open=72400.0, high=72420.0, low=72360.0, close=72400.0),
        Candle(_ts(10, 5), open=72400.0, high=72410.0, low=72330.0, close=72381.0),
    ]


def _candles_15m() -> list[Candle]:
    """Minimal 15m candles including the 09:45 anchor candle."""
    return [
        Candle(_ts(9, 15), open=74700.0, high=74750.0, low=74650.0, close=74700.0),
        Candle(_ts(9, 30), open=74700.0, high=74800.0, low=74650.0, close=74750.0),
        Candle(_ts(9, 45), open=74750.0, high=74450.0, low=72380.0, close=74435.0),
    ]


def _disabled_settings(ms: MagicMock) -> None:
    """Set all strategy toggles off; caller enables what it needs."""
    ms.ENABLE_OB_STRATEGY            = False
    ms.ENABLE_ORB_STRATEGY           = False
    ms.ENABLE_VWAP_STRATEGY          = False
    ms.ENABLE_PDHL_STRATEGY          = False
    ms.ENABLE_NATR_STRATEGY          = False
    ms.ENABLE_ATR_COPILOT_STRATEGY   = False
    ms.ENABLE_TRB_STRATEGY           = False
    ms.ENABLE_EMA_STRATEGY           = False
    ms.ENABLE_MOMENTUM_PHASE         = False
    ms.ORB_SESSION_QUALIFIER         = False
    ms.ORB_ACTIVE_UNTIL              = "09:40"
    ms.ORB_MOMENTUM_SKIP_MONDAY      = False
    ms.ORB_MIN_BODY_RATIO            = 0.0
    ms.ORB_BUFFER_ATR_MULT           = 0.0
    ms.ORB_REQUIRE_15M_TREND         = False
    ms.VWAP_RETEST_LOOKBACK          = 3
    ms.VWAP_MIN_BOUNCE_PTS           = 0.0
    ms.PDHL_BUFFER_PTS               = 0.0
    ms.NATR_PERIOD                   = 21
    ms.NATR_MULT                     = 3.0
    ms.ATR_COPILOT_PERIOD            = 5
    ms.ATR_COPILOT_EMA_PERIOD        = 21
    ms.ATR_COPILOT_BAND_MULT         = 6.0
    ms.ATR_COPILOT_BREAKOUT_BUFFER   = 0.0
    ms.TRB_MIN_BODY_RATIO            = 0.0
    ms.TRB_BUFFER_ATR_MULT           = 0.0


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestPerStrategyIndependence:
    """
    Phase A: _candle_already_attempted suppression removed.
    Every enabled strategy evaluates and logs its raw signal independently,
    even when an earlier strategy was blocked by Smart Entry cooldown.
    """

    def test_trb_evaluated_after_vwap_blocked_by_cooldown(self, caplog) -> None:
        """
        Reproduces the 2026-10-05 TRB miss.

        PE_VWAP fires its raw signal, is blocked by Smart Entry cooldown
        (_gate returns None), but PE_TRB is STILL evaluated and logged.
        Before Phase A the _candle_already_attempted guard suppressed TRB
        entirely after VWAP touched _gate.
        """
        from strategies.signal_engine import evaluate_signals

        ms = MagicMock()
        _disabled_settings(ms)
        ms.ENABLE_VWAP_STRATEGY = True
        ms.ENABLE_TRB_STRATEGY  = True

        # smart_entry.allow returns False → cooldown blocks every signal
        se = MagicMock()
        se.allow.return_value = False

        with patch("strategies.signal_engine.settings", ms), \
             patch("strategies.signal_engine.has_processed_signal", return_value=False), \
             patch("strategies.signal_engine.record_processed_signal"), \
             patch("strategies.vwap_strategy.is_vwap_ce_signal", return_value=False), \
             patch("strategies.vwap_strategy.is_vwap_pe_signal", return_value=True), \
             patch("strategies.trb_strategy.is_trb_ce_signal", return_value=False), \
             patch("strategies.trb_strategy.is_trb_pe_signal", return_value=True):

            caplog.set_level(logging.INFO, logger="strategies.signal_engine")
            result = evaluate_signals(
                _candles_5m_1005(), _candles_15m(),
                smart_entry=se,
                vwap=72476.79,
            )

        # Both strategies fired their raw signals and were logged
        log_text = caplog.text
        assert "PE_VWAP_SIGNAL" in log_text, "VWAP raw signal must be logged"
        assert "PE_TRB_SIGNAL"  in log_text, (
            "TRB raw signal must be logged even when VWAP was blocked"
        )

        # Both were blocked by cooldown → no signal returned
        assert result is None

        # Smart Entry was consulted for BOTH strategies independently
        assert se.allow.call_count == 2
        called_signals = [call.args[0] for call in se.allow.call_args_list]
        assert "PE_VWAP" in called_signals
        assert "PE_TRB" in called_signals

    def test_pe_evaluated_after_ce_blocked(self, caplog) -> None:
        """
        CE fires first, is blocked by Smart Entry, but PE is still evaluated
        and logged on the same candle.
        """
        from strategies.signal_engine import evaluate_signals

        ms = MagicMock()
        _disabled_settings(ms)
        ms.ENABLE_EMA_STRATEGY = True

        se = MagicMock()
        se.allow.return_value = False

        with patch("strategies.signal_engine.settings", ms), \
             patch("strategies.signal_engine.has_processed_signal", return_value=False), \
             patch("strategies.signal_engine.record_processed_signal"), \
             patch("strategies.signal_engine.is_ce_signal", return_value=True), \
             patch("strategies.signal_engine.is_pe_signal", return_value=True):

            caplog.set_level(logging.INFO, logger="strategies.signal_engine")
            result = evaluate_signals(
                _candles_5m_1005(), _candles_15m(),
                smart_entry=se,
            )

        log_text = caplog.text
        assert "CE_SIGNAL" in log_text, "CE raw signal must be logged"
        assert "PE_SIGNAL" in log_text, "PE raw signal must be logged even when CE was blocked"
        assert result is None

    def test_all_enabled_strategies_log_when_all_blocked(self, caplog) -> None:
        """
        When Smart Entry blocks every signal, every enabled strategy that
        fires a raw condition is logged.  Before Phase A, only the first
        strategy would log — the rest were silently suppressed.
        """
        from strategies.signal_engine import evaluate_signals

        ms = MagicMock()
        _disabled_settings(ms)
        ms.ENABLE_VWAP_STRATEGY         = True
        ms.ENABLE_PDHL_STRATEGY         = True
        ms.ENABLE_NATR_STRATEGY         = True
        ms.ENABLE_ATR_COPILOT_STRATEGY  = True
        ms.ENABLE_TRB_STRATEGY          = True
        ms.ENABLE_EMA_STRATEGY          = True

        se = MagicMock()
        se.allow.return_value = False

        with patch("strategies.signal_engine.settings", ms), \
             patch("strategies.signal_engine.has_processed_signal", return_value=False), \
             patch("strategies.signal_engine.record_processed_signal"), \
             patch("strategies.vwap_strategy.is_vwap_ce_signal", return_value=True), \
             patch("strategies.vwap_strategy.is_vwap_pe_signal", return_value=False), \
             patch("strategies.pdhl_strategy.is_pdhl_ce_signal", return_value=True), \
             patch("strategies.pdhl_strategy.is_pdhl_pe_signal", return_value=False), \
             patch("strategies.natr_strategy.is_natr_ce_signal", return_value=True), \
             patch("strategies.natr_strategy.is_natr_pe_signal", return_value=False), \
             patch("strategies.atr_copilot_strategy.is_atr_copilot_ce_signal", return_value=True), \
             patch("strategies.atr_copilot_strategy.is_atr_copilot_pe_signal", return_value=False), \
             patch("strategies.trb_strategy.is_trb_ce_signal", return_value=True), \
             patch("strategies.trb_strategy.is_trb_pe_signal", return_value=False), \
             patch("strategies.signal_engine.is_ce_signal", return_value=False), \
             patch("strategies.signal_engine.is_pe_signal", return_value=False):

            caplog.set_level(logging.INFO, logger="strategies.signal_engine")
            result = evaluate_signals(
                _candles_5m_1005(), _candles_15m(),
                smart_entry=se,
                vwap=72476.79,
                prev_day_high=72500.0,
                prev_day_low=72300.0,
            )

        log_text = caplog.text
        # Every CE raw signal was logged
        assert "CE_VWAP_SIGNAL"   in log_text
        assert "CE_PDHL_SIGNAL"   in log_text
        assert "CE_NATR_SIGNAL"   in log_text
        assert "CE_ATR_SIGNAL"    in log_text
        assert "CE_TRB_SIGNAL"    in log_text

        # smart_entry was consulted for each — none suppressed
        assert se.allow.call_count == 5

        # All blocked → None returned (single-trade execution preserved)
        assert result is None

    def test_first_passing_signal_returned(self, caplog) -> None:
        """
        When multiple strategies fire and pass _gate, the first (by evaluation
        order) is returned for execution.  Later strategies are not evaluated.
        This preserves single-trade execution in Phase A.
        """
        from strategies.signal_engine import evaluate_signals

        ms = MagicMock()
        _disabled_settings(ms)
        ms.ENABLE_VWAP_STRATEGY = True
        ms.ENABLE_TRB_STRATEGY  = True

        se = MagicMock()
        se.allow.return_value = True  # both pass

        with patch("strategies.signal_engine.settings", ms), \
             patch("strategies.signal_engine.has_processed_signal", return_value=False), \
             patch("strategies.signal_engine.record_processed_signal"), \
             patch("strategies.vwap_strategy.is_vwap_ce_signal", return_value=False), \
             patch("strategies.vwap_strategy.is_vwap_pe_signal", return_value=True), \
             patch("strategies.trb_strategy.is_trb_ce_signal", return_value=False), \
             patch("strategies.trb_strategy.is_trb_pe_signal", return_value=True):

            caplog.set_level(logging.INFO, logger="strategies.signal_engine")
            result = evaluate_signals(
                _candles_5m_1005(), _candles_15m(),
                smart_entry=se,
                vwap=72476.79,
            )

        # VWAP is evaluated first and passes → returned for execution
        assert result == "PE_VWAP"
        # TRB was not reached because VWAP already returned (early return)
        log_text = caplog.text
        assert "PE_VWAP_SIGNAL" in log_text
        assert "PE_TRB_SIGNAL" not in log_text


class TestNoLeftoverCandleAttemptedReferences:
    """Verify the _candle_attempted mechanism is fully removed from the module."""

    def test_no_candle_attempted_symbol_in_source(self) -> None:
        import strategies.signal_engine as se
        source = inspect.getsource(se)
        assert "_candle_attempted" not in source
        assert "_candle_already_attempted" not in source
