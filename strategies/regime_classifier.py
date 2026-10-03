"""
AI Day-Regime Classifier
========================
Classifies the current trading day as TRENDING, CHOPPY, or VOLATILE once at
bot startup (before the first candle).

Heuristic path (always available, no external dependencies):
  - VIX > 15              → VOLATILE
  - |gap%| > 0.4%         → TRENDING
  - otherwise             → CHOPPY

AI path (opt-in via REGIME_USE_AI=true):
  - Builds a one-line prompt and calls the configured LLM.
  - Any failure (network, bad response, invalid value) silently falls back to
    the heuristic — a failed API call MUST NOT halt the bot.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

from utils.logging_config import log_event

if TYPE_CHECKING:
    from execution.smart_exit import SmartExitEngine

logger = logging.getLogger(__name__)


class Regime(Enum):
    TRENDING = "TRENDING"
    CHOPPY   = "CHOPPY"
    VOLATILE = "VOLATILE"


_VALID_REGIMES = {r.value for r in Regime}


class RegimeClassifier:
    """
    Once per trading day, classify the market regime and optionally patch the
    profit-lock parameters of a SmartExitEngine.
    """

    def __init__(
        self,
        enable: bool,
        provider: str,
        api_key: str,
        model: str,
        atr_mult_trending: float,
        atr_mult_choppy: float,
        atr_mult_volatile: float,
        min_pct_trending: float,
        min_pct_choppy: float,
        min_pct_volatile: float,
        use_ai: bool = False,
        ollama_host: str = "http://localhost:11434",
    ) -> None:
        self._enable = enable
        self._provider = provider.lower()
        self._api_key = api_key
        self._model = model
        self._use_ai = use_ai
        self._ollama_host = ollama_host.rstrip("/")

        self._atr_mult = {
            Regime.TRENDING: atr_mult_trending,
            Regime.CHOPPY:   atr_mult_choppy,
            Regime.VOLATILE: atr_mult_volatile,
        }
        self._min_pct = {
            Regime.TRENDING: min_pct_trending,
            Regime.CHOPPY:   min_pct_choppy,
            Regime.VOLATILE: min_pct_volatile,
        }

    # ── Heuristic (always available) ──────────────────────────────────────────

    def _heuristic(
        self,
        vix: float,
        sensex_prev_close: float,
        sensex_open: float,
    ) -> Regime:
        if vix > 15:
            return Regime.VOLATILE
        if sensex_prev_close > 0:
            gap_pct = abs(sensex_open - sensex_prev_close) / sensex_prev_close
            if gap_pct > 0.004:
                return Regime.TRENDING
        return Regime.CHOPPY

    # ── AI path (optional) ────────────────────────────────────────────────────

    def _call_llm(self, vix: float, prev_close: float, open_: float, atr: float) -> str:
        prompt = (
            f"SENSEX day classification. VIX={vix}, prev_close={prev_close}, "
            f"open={open_}, ATR14={atr}. "
            "Reply with exactly one word: TRENDING, CHOPPY, or VOLATILE."
        )
        if self._provider == "watsonx":
            from ibm_watsonx_ai.foundation_models import ModelInference  # type: ignore[import]
            model = ModelInference(model_id=self._model, credentials={"apikey": self._api_key})
            response = model.generate_text(prompt)
            return str(response).strip().upper()
        elif self._provider == "ollama":
            from openai import OpenAI  # type: ignore[import]
            client = OpenAI(
                api_key="ollama",
                base_url=f"{self._ollama_host}/v1",
            )
            resp = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=5,
                temperature=0,
            )
            return resp.choices[0].message.content.strip().upper()
        else:
            # default: openai
            from openai import OpenAI  # type: ignore[import]
            client = OpenAI(api_key=self._api_key)
            resp = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=5,
                temperature=0,
            )
            return resp.choices[0].message.content.strip().upper()

    # ── Public interface ──────────────────────────────────────────────────────

    def classify(
        self,
        vix: float,
        sensex_prev_close: float,
        sensex_open: float,
        atr: float,
    ) -> Regime:
        """Return the day's regime. Fails safely — always returns a valid Regime."""
        fallback = self._heuristic(vix, sensex_prev_close, sensex_open)

        if not self._use_ai:
            # Log the heuristic inputs so the operator can see why this regime was chosen.
            gap_pct = (
                abs(sensex_open - sensex_prev_close) / sensex_prev_close * 100
                if sensex_prev_close > 0 else 0.0
            )
            log_event(
                logger, "REGIME_HEURISTIC",
                regime=fallback.value,
                vix=round(vix, 2),
                gap_pct=round(gap_pct, 3),
                sensex_prev_close=sensex_prev_close,
                sensex_open=sensex_open,
                atr=round(atr, 2),
            )
            return fallback

        try:
            raw = self._call_llm(vix, sensex_prev_close, sensex_open, atr)
            if raw not in _VALID_REGIMES:
                log_event(logger, "REGIME_AI_INVALID_RESPONSE", raw=raw, fallback=fallback.value)
                return fallback
            return Regime(raw)
        except Exception as exc:
            # AI failed — log the heuristic inputs alongside the error so the
            # operator can see exactly what drove the fallback regime choice.
            gap_pct = (
                abs(sensex_open - sensex_prev_close) / sensex_prev_close * 100
                if sensex_prev_close > 0 else 0.0
            )
            log_event(
                logger, "REGIME_AI_FAILED",
                error=str(exc),
                fallback=fallback.value,
                vix=round(vix, 2),
                gap_pct=round(gap_pct, 3),
                sensex_prev_close=sensex_prev_close,
                sensex_open=sensex_open,
            )
            return fallback

    def adjust_profit_lock(self, engine: SmartExitEngine, regime: Regime) -> None:
        """Patch the engine's profit-lock parameters for today's regime."""
        engine._profit_lock_atr_mult = self._atr_mult[regime]
        engine._profit_lock_min_pct  = self._min_pct[regime]
