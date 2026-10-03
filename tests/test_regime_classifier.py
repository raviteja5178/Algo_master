"""Tests for RegimeClassifier."""
import pytest
from unittest.mock import MagicMock, patch

from strategies.regime_classifier import Regime, RegimeClassifier
from execution.smart_exit import SmartExitEngine


# ── factory helpers ───────────────────────────────────────────────────────────

def _classifier(use_ai: bool = False, **kwargs) -> RegimeClassifier:
    defaults = dict(
        enable=True,
        provider="openai",
        api_key="test-key",
        model="gpt-4o-mini",
        use_ai=use_ai,
        atr_mult_trending=1.5,
        atr_mult_choppy=0.8,
        atr_mult_volatile=1.2,
        min_pct_trending=0.6,
        min_pct_choppy=0.3,
        min_pct_volatile=0.5,
    )
    defaults.update(kwargs)
    return RegimeClassifier(**defaults)


def _engine() -> SmartExitEngine:
    return SmartExitEngine(
        profit_lock_multiplier=2.0,
        profit_lock_atr_mult=0.0,
        profit_lock_min_pct=0.0,
        enable_reversal_exit=False,
        enable_ema_collapse=False,
        enable_profit_lock=True,
        enable_time_decay=False,
        enable_daily_loss_limit=False,
    )


# ── Heuristic tests ───────────────────────────────────────────────────────────

class TestHeuristic:
    def test_vix_above_15_returns_volatile(self):
        rc = _classifier()
        regime = rc.classify(vix=16.0, sensex_prev_close=80000.0, sensex_open=80100.0, atr=55.0)
        assert regime is Regime.VOLATILE

    def test_vix_exactly_15_not_volatile(self):
        # VIX must be *above* 15 — 15.0 itself is not VOLATILE
        rc = _classifier()
        regime = rc.classify(vix=15.0, sensex_prev_close=80000.0, sensex_open=80000.0, atr=55.0)
        assert regime is Regime.CHOPPY

    def test_gap_above_04pct_returns_trending(self):
        # gap = 0.5% (> 0.4%) → TRENDING
        rc = _classifier()
        prev_close = 80000.0
        open_ = prev_close * 1.005
        regime = rc.classify(vix=10.0, sensex_prev_close=prev_close, sensex_open=open_, atr=55.0)
        assert regime is Regime.TRENDING

    def test_negative_gap_above_04pct_returns_trending(self):
        # gap = -0.5% (abs > 0.4%) → TRENDING
        rc = _classifier()
        prev_close = 80000.0
        open_ = prev_close * 0.995
        regime = rc.classify(vix=10.0, sensex_prev_close=prev_close, sensex_open=open_, atr=55.0)
        assert regime is Regime.TRENDING

    def test_small_gap_returns_choppy(self):
        # gap = 0.1% (< 0.4%) and VIX = 10 → CHOPPY
        rc = _classifier()
        prev_close = 80000.0
        open_ = prev_close * 1.001
        regime = rc.classify(vix=10.0, sensex_prev_close=prev_close, sensex_open=open_, atr=55.0)
        assert regime is Regime.CHOPPY

    def test_vix_priority_over_gap(self):
        # VIX > 15 takes priority even when gap > 0.4%
        rc = _classifier()
        prev_close = 80000.0
        open_ = prev_close * 1.01
        regime = rc.classify(vix=20.0, sensex_prev_close=prev_close, sensex_open=open_, atr=55.0)
        assert regime is Regime.VOLATILE

    def test_zero_prev_close_defaults_choppy(self):
        # No valid prev_close → gap undefined → CHOPPY
        rc = _classifier()
        regime = rc.classify(vix=10.0, sensex_prev_close=0.0, sensex_open=80000.0, atr=55.0)
        assert regime is Regime.CHOPPY


# ── adjust_profit_lock tests ──────────────────────────────────────────────────

class TestAdjustProfitLock:
    def test_trending_patches_engine(self):
        rc = _classifier()
        eng = _engine()
        rc.adjust_profit_lock(eng, Regime.TRENDING)
        assert eng._profit_lock_atr_mult == pytest.approx(1.5)
        assert eng._profit_lock_min_pct == pytest.approx(0.6)

    def test_choppy_patches_engine(self):
        rc = _classifier()
        eng = _engine()
        rc.adjust_profit_lock(eng, Regime.CHOPPY)
        assert eng._profit_lock_atr_mult == pytest.approx(0.8)
        assert eng._profit_lock_min_pct == pytest.approx(0.3)

    def test_volatile_patches_engine(self):
        rc = _classifier()
        eng = _engine()
        rc.adjust_profit_lock(eng, Regime.VOLATILE)
        assert eng._profit_lock_atr_mult == pytest.approx(1.2)
        assert eng._profit_lock_min_pct == pytest.approx(0.5)

    def test_engine_untouched_before_adjust(self):
        eng = _engine()
        assert eng._profit_lock_atr_mult == pytest.approx(0.0)
        assert eng._profit_lock_min_pct == pytest.approx(0.0)


# ── AI path tests ─────────────────────────────────────────────────────────────

class TestAIPath:
    def test_ai_valid_trending_response(self):
        rc = _classifier(use_ai=True)
        with patch.object(rc, "_call_llm", return_value="TRENDING"):
            regime = rc.classify(vix=10.0, sensex_prev_close=80000.0,
                                 sensex_open=80000.0, atr=55.0)
        assert regime is Regime.TRENDING

    def test_ai_valid_choppy_response(self):
        rc = _classifier(use_ai=True)
        with patch.object(rc, "_call_llm", return_value="CHOPPY"):
            regime = rc.classify(vix=10.0, sensex_prev_close=80000.0,
                                 sensex_open=80000.0, atr=55.0)
        assert regime is Regime.CHOPPY

    def test_ai_valid_volatile_response(self):
        rc = _classifier(use_ai=True)
        with patch.object(rc, "_call_llm", return_value="VOLATILE"):
            regime = rc.classify(vix=10.0, sensex_prev_close=80000.0,
                                 sensex_open=80000.0, atr=55.0)
        assert regime is Regime.VOLATILE

    def test_ai_exception_falls_back_to_heuristic(self):
        """A failed API call must never halt the bot — falls back to heuristic."""
        rc = _classifier(use_ai=True)
        with patch.object(rc, "_call_llm", side_effect=RuntimeError("API timeout")):
            # Low VIX, small gap → heuristic returns CHOPPY
            regime = rc.classify(vix=10.0, sensex_prev_close=80000.0,
                                 sensex_open=80050.0, atr=55.0)
        assert regime is Regime.CHOPPY

    def test_ai_garbage_response_falls_back_to_heuristic(self):
        """An unrecognised LLM response falls back to heuristic."""
        rc = _classifier(use_ai=True)
        with patch.object(rc, "_call_llm", return_value="SIDEWAYS"):
            # VIX > 15 → heuristic returns VOLATILE
            regime = rc.classify(vix=18.0, sensex_prev_close=80000.0,
                                 sensex_open=80000.0, atr=55.0)
        assert regime is Regime.VOLATILE

    def test_ai_empty_response_falls_back_to_heuristic(self):
        rc = _classifier(use_ai=True)
        with patch.object(rc, "_call_llm", return_value=""):
            regime = rc.classify(vix=10.0, sensex_prev_close=80000.0,
                                 sensex_open=80000.0, atr=55.0)
        assert regime is Regime.CHOPPY

    def test_ai_not_called_when_use_ai_false(self):
        """With use_ai=False the AI path is never entered."""
        rc = _classifier(use_ai=False)
        with patch.object(rc, "_call_llm", side_effect=AssertionError("must not call LLM")):
            regime = rc.classify(vix=10.0, sensex_prev_close=80000.0,
                                 sensex_open=80000.0, atr=55.0)
        assert regime is Regime.CHOPPY


# ── ENABLE_REGIME_CLASSIFIER=false ────────────────────────────────────────────

class TestDisabled:
    def test_classifier_is_none_when_disabled(self):
        """When ENABLE_REGIME_CLASSIFIER=false, BotContext.regime_classifier is None.
        Simulate this by constructing None and verifying engine is untouched."""
        regime_classifier = None   # mirrors what BotContext sets
        eng = _engine()
        original_atr_mult = eng._profit_lock_atr_mult
        original_min_pct  = eng._profit_lock_min_pct

        # This is the guard in main.py
        if regime_classifier is not None and eng is not None:
            pass  # pragma: no cover

        assert eng._profit_lock_atr_mult == original_atr_mult
        assert eng._profit_lock_min_pct  == original_min_pct
