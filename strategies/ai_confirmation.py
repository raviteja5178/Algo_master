"""
AI Entry Confirmation Filter
============================
Optional quality gate that sits between the rule-based signal engine and
order execution.  When enabled (ENABLE_AI_CONFIRMATION=true), every signal
that passes the rule-based strategies is validated by an LLM before the bot
places an order.

How it works
------------
1. A rule fires (e.g. CE_ORB).
2. AIConfirmationFilter.confirm() is called with the last 10 candles,
   EMA values, ATR, regime, time-of-day, and signal type.
3. The LLM returns a JSON object: {"score": 7, "action": "BUY", "reason": "..."}
4. If score >= threshold (default 6) AND action == "BUY" (CE) or "SELL" (PE),
   the signal is allowed through.  Otherwise it is blocked.
5. Any LLM error (network, timeout, bad JSON) silently falls back to ALLOW
   so the rule-based bot continues working uninterrupted.

Exit suggestion
---------------
confirm_exit() is called on every candle close when a position is open.
If the LLM says action="EXIT" with score >= exit_threshold, it returns the
reason string which main.py treats like any other smart-exit reason.
Falls back to None (no exit) on any error.

Prompt design principles
------------------------
- Single-turn, ≤ 150 tokens prompt.  Response capped at 60 tokens.
- Structured JSON output enforced via response_format (OpenAI) or prompt
  instruction (watsonx).
- Temperature = 0 for deterministic scoring.
- Prompt includes ONLY numeric market context — no news, no sentiment.
  The LLM acts as a pattern-recognition engine over candle data.

Supported providers
-------------------
  "openai"  — OpenAI API (paid).  Requires AI_CONFIRMATION_API_KEY.
              Models: gpt-4o-mini (recommended), gpt-4o, gpt-3.5-turbo.

  "watsonx" — IBM watsonx.ai (paid/trial).  Requires AI_CONFIRMATION_API_KEY.
              Models: ibm/granite-3-8b-instruct, meta-llama/llama-3-3-70b-instruct.

  "ollama"  — Ollama local inference (FREE, runs on your own machine).
              No API key needed.  Requires Ollama running on localhost.
              Install: https://ollama.com/download
              Pull a model first: ollama pull llama3.2   (or mistral, phi3, gemma2)
              Then set:
                AI_CONFIRMATION_PROVIDER=ollama
                AI_CONFIRMATION_MODEL=llama3.2
                AI_CONFIRMATION_OLLAMA_HOST=http://localhost:11434  (optional)
              Ollama exposes an OpenAI-compatible API — no extra dependencies.
              Recommended models for speed vs quality on SENSEX scalping:
                llama3.2     — fast, good JSON discipline  (recommended)
                mistral      — slightly slower, better reasoning
                phi3:mini    — very fast, minimal RAM usage
                gemma2:2b    — ultra-light, good for low-spec machines
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from typing import NamedTuple

from market.candle_builder import Candle
from utils.logging_config import log_event

logger = logging.getLogger(__name__)

_CANDLE_WINDOW = 10   # number of recent candles sent to the LLM


class AIVerdict(NamedTuple):
    allowed: bool
    score: int        # 1-10
    action: str       # "BUY" | "SELL" | "SKIP" | "EXIT" | "HOLD"
    reason: str


class AIConfirmationFilter:
    """
    LLM-backed entry and exit confirmation.

    Parameters
    ----------
    provider        : "openai", "watsonx", or "ollama"
    api_key         : LLM API key
    model           : model name (e.g. "gpt-4o-mini")
    entry_threshold : minimum score (1-10) to allow an entry   (default 6)
    exit_threshold  : minimum score (1-10) to suggest an exit  (default 7)
    timeout_secs    : HTTP timeout for each LLM call           (default 8)
    """

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        entry_threshold: int = 6,
        exit_threshold: int = 7,
        timeout_secs: float = 8.0,
        ollama_host: str = "http://localhost:11434",
    ) -> None:
        self._provider = provider.lower()
        self._api_key = api_key
        self._model = model
        self._entry_thresh = entry_threshold
        self._exit_thresh = exit_threshold
        self._timeout = timeout_secs
        self._ollama_host = ollama_host.rstrip("/")

    # ── Prompt builders ────────────────────────────────────────────────────────

    def _entry_prompt(
        self,
        signal: str,
        candles: Sequence[Candle],
        ema9: float | None,
        ema21: float | None,
        atr: float | None,
        regime: str,
        vwap: float | None,
        option_day_low: float | None = None,
        option_day_high: float | None = None,
        option_ltp: float | None = None,
    ) -> str:
        direction = "CALL (bullish)" if signal.startswith("CE") else "PUT (bearish)"
        rows = []
        for c in candles[-_CANDLE_WINDOW:]:
            rows.append(f"  {c.timestamp.strftime('%H:%M')} O={c.open:.1f} H={c.high:.1f} L={c.low:.1f} C={c.close:.1f}")
        candle_block = "\n".join(rows)
        _atr_s  = f"{atr:.1f}"  if atr  else "n/a"
        _e9_s   = f"{ema9:.1f}" if ema9 else "n/a"
        _e21_s  = f"{ema21:.1f}" if ema21 else "n/a"
        _vwap_s = f"{vwap:.1f}" if vwap else "n/a"

        # Option premium extension context — helps the LLM detect stale/exhausted moves.
        _prem_ctx = ""
        if option_ltp and option_day_low and option_day_low > 0:
            _ext_pct = (option_ltp - option_day_low) / option_day_low * 100
            _day_high_s = f"{option_day_high:.1f}" if option_day_high else "n/a"
            _prem_ctx = (
                f"Option LTP={option_ltp:.1f} "
                f"(day low={option_day_low:.1f}, day high={_day_high_s}, "
                f"premium up {_ext_pct:.0f}% from day low). "
            )
        elif option_ltp:
            _prem_ctx = f"Option LTP={option_ltp:.1f}. "

        return (
            f"SENSEX options scalping bot. Signal: {signal} ({direction}).\n"
            f"Regime: {regime}. ATR14={_atr_s}. "
            f"EMA9={_e9_s} EMA21={_e21_s}. "
            f"VWAP={_vwap_s}.\n"
            f"{_prem_ctx}"
            f"Last {min(_CANDLE_WINDOW, len(candles))} 5-min candles (IST):\n{candle_block}\n"
            "Score this entry 1-10 (10=excellent) based on price action, EMA alignment, and momentum. "
            "Reply ONLY with JSON: "
            '{"score":<int>,"action":"BUY"|"SKIP","reason":"<15 words max>"}'
        )

    def _exit_prompt(
        self,
        signal: str,
        candles: Sequence[Candle],
        entry_price: float,
        option_ltp: float,
        unrealised_pnl_pts: float,
        ema9: float | None,
        ema21: float | None,
        atr: float | None,
    ) -> str:
        direction = "CALL" if signal.startswith("CE") else "PUT"
        rows = []
        for c in candles[-_CANDLE_WINDOW:]:
            rows.append(f"  {c.timestamp.strftime('%H:%M')} O={c.open:.1f} H={c.high:.1f} L={c.low:.1f} C={c.close:.1f}")
        candle_block = "\n".join(rows)
        _e9_s  = f"{ema9:.1f}"  if ema9  else "n/a"
        _e21_s = f"{ema21:.1f}" if ema21 else "n/a"
        _atr_s = f"{atr:.1f}"   if atr   else "n/a"
        return (
            f"Open {direction} position. Entry={entry_price:.1f} LTP={option_ltp:.1f} "
            f"PnL={unrealised_pnl_pts:+.1f}pts. "
            f"EMA9={_e9_s} EMA21={_e21_s}. "
            f"ATR14={_atr_s}.\n"
            f"Last {min(_CANDLE_WINDOW, len(candles))} 5-min candles:\n{candle_block}\n"
            "Should we EXIT now or HOLD? Score urgency 1-10 (10=exit immediately). "
            "Reply ONLY with JSON: "
            '{"score":<int>,"action":"EXIT"|"HOLD","reason":"<15 words max>"}'
        )

    # ── LLM call ───────────────────────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> dict:
        if self._provider == "watsonx":
            from ibm_watsonx_ai.foundation_models import ModelInference  # type: ignore
            model = ModelInference(
                model_id=self._model,
                credentials={"apikey": self._api_key},
            )
            raw = model.generate_text(prompt)
        elif self._provider == "ollama":
            # Ollama exposes an OpenAI-compatible /v1 endpoint — reuse the
            # openai client with a custom base_url; no extra package needed.
            from openai import OpenAI  # type: ignore
            client = OpenAI(
                api_key="ollama",            # Ollama ignores the key value
                base_url=f"{self._ollama_host}/v1",
                timeout=self._timeout,
            )
            resp = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0,
            )
            raw = resp.choices[0].message.content
        else:
            # default: openai
            from openai import OpenAI  # type: ignore
            client = OpenAI(api_key=self._api_key, timeout=self._timeout)
            resp = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0,
            )
            raw = resp.choices[0].message.content

        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    # ── Public API ─────────────────────────────────────────────────────────────

    def confirm(
        self,
        signal: str,
        candles_5m: Sequence[Candle],
        ema9: float | None = None,
        ema21: float | None = None,
        atr: float | None = None,
        regime: str = "UNKNOWN",
        vwap: float | None = None,
        option_day_low: float | None = None,
        option_day_high: float | None = None,
        option_ltp: float | None = None,
    ) -> AIVerdict:
        """
        Validate an entry signal. Returns AIVerdict(allowed=True) on any error
        so the bot always falls back to rule-based behaviour.

        option_day_low / option_day_high / option_ltp — optional intraday premium
        context.  When provided the LLM prompt will include the premium extension %
        so the model can penalise late/exhausted entries (e.g. option already up
        136% from day low — the T8 / Rs.331 peak scenario).
        """
        try:
            prompt = self._entry_prompt(
                signal, candles_5m, ema9, ema21, atr, regime, vwap,
                option_day_low=option_day_low,
                option_day_high=option_day_high,
                option_ltp=option_ltp,
            )
            result = self._call_llm(prompt)
            score = int(result.get("score", 5))
            action = str(result.get("action", "SKIP")).upper()
            reason = str(result.get("reason", ""))
            allowed = score >= self._entry_thresh and action == "BUY"
            verdict = AIVerdict(allowed=allowed, score=score, action=action, reason=reason)
            log_event(logger, "AI_ENTRY_VERDICT",
                      signal=signal, score=score, action=action,
                      allowed=allowed, reason=reason)
            return verdict
        except Exception as exc:
            log_event(logger, "AI_ENTRY_FAILED", signal=signal, error=str(exc), fallback="ALLOW")
            return AIVerdict(allowed=True, score=-1, action="ALLOW", reason="llm_error_fallback")

    def confirm_exit(
        self,
        signal: str,
        candles_5m: Sequence[Candle],
        entry_price: float,
        option_ltp: float,
        unrealised_pnl_pts: float,
        ema9: float | None = None,
        ema21: float | None = None,
        atr: float | None = None,
    ) -> str | None:
        """
        Ask the LLM whether the current position should be exited now.
        Returns an exit reason string if EXIT is recommended, else None.
        Returns None on any error (never forces an exit due to LLM failure).
        """
        try:
            prompt = self._exit_prompt(
                signal, candles_5m, entry_price, option_ltp,
                unrealised_pnl_pts, ema9, ema21, atr,
            )
            result = self._call_llm(prompt)
            score = int(result.get("score", 0))
            action = str(result.get("action", "HOLD")).upper()
            reason = str(result.get("reason", ""))
            if score >= self._exit_thresh and action == "EXIT":
                log_event(logger, "AI_EXIT_VERDICT",
                          signal=signal, score=score, reason=reason)
                return f"AI_EXIT(score={score}: {reason})"
            return None
        except Exception as exc:
            log_event(logger, "AI_EXIT_FAILED", signal=signal, error=str(exc))
            return None
