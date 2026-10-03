# Time Range Breakout (TRB) Strategy Implementation Plan

This plan details the design, configuration, and step-by-step implementation for the **Time Range Breakout (TRB)** strategy.

---

## Top-Level Overview
The **TRB Strategy** is an intraday breakout strategy designed for SENSEX option trading. 
* It identifies a specific **15-minute anchor candle (09:45 AM - 10:00 AM IST)**.
* Once the 10:00 AM IST candle is complete, the bot records the **High** and **Low** boundaries of this anchor candle.
* It evaluates completed 5-minute candles strictly after 10:00 AM IST.
* A trade is triggered when a 5-minute candle close **crosses over** one of the boundaries:
  * **CE_TRB:** `c1.close <= High` and `c0.close > High`
  * **PE_TRB:** `c1.close >= Low` and `c0.close < Low`
* To ensure trade quality, the strategy includes optional false-breakout filters (body ratio and ATR breakout buffer).
* It utilizes the bot's existing unified risk engine (`compute_risk_params()`) to handle dynamic stop loss, break-even trailing, target references, and smart exit triggers.

---

## Sub-Tasks

### 1. Configuration & Settings
* **Intent:** Add environment configuration toggles and filter thresholds for the new strategy.
* **Expected Outcomes:** 
  * Settings file `config/settings.py` successfully reads TRB-related variables.
  * `.env.example` lists the new config keys with documentation.
* **Todo List:**
  - [ ] Add the following fields to `config/settings.py` with safe defaults:
    * `ENABLE_TRB_STRATEGY: bool` (default: `False`)
    * `TRB_CANDLE_START_TIME: str` (default: `"09:45"`)
    * `TRB_CANDLE_DURATION_MINS: int` (default: `15`)
    * `TRB_MIN_BODY_RATIO: float` (default: `0.0`)
    * `TRB_BUFFER_ATR_MULT: float` (default: `0.0`)
  - [ ] Update `config/settings.py` validation logic if required.
  - [ ] Append these parameters with explanations to `.env.example`.
* **Relevant Context:** [`config/settings.py`](config/settings.py:122)

---

### 2. TRB Strategy Implementation
* **Intent:** Implement the high/low range extraction and crossover detection logic.
* **Expected Outcomes:** 
  * A new file `strategies/trb_strategy.py` that computes the 9:45-10:00 15m range and checks for valid breakouts on 5m candles.
* **Todo List:**
  - [ ] Create `strategies/trb_strategy.py`.
  - [ ] Implement `get_trb_range(candles_15m)`:
    * Filters today's 15m candles to find the candle starting at `TRB_CANDLE_START_TIME` (default: 09:45 AM).
    * Returns `(high, low)` of that candle.
  - [ ] Implement crossover detection functions:
    * `is_trb_ce_signal(candles_5m, candles_15m, min_body_ratio, buffer_atr_mult)`
    * `is_trb_pe_signal(candles_5m, candles_15m, min_body_ratio, buffer_atr_mult)`
  - [ ] Incorporate ORB-like filters (`_passes_body_filter`, `_passes_buffer_filter`) from `orb_strategy.py`.
  - [ ] Add time guards to block signals before the 10:00 AM anchor candle has completed.
* **Relevant Context:** [`strategies/orb_strategy.py`](strategies/orb_strategy.py:49)

---

### 3. Signal Engine & Orchestrator Integration
* **Intent:** Register TRB in the multi-phase signal engine and display strategy on the web dashboard.
* **Expected Outcomes:**
  * Signal engine evaluates TRB alongside ORB, EMA, and OB.
  * Web dashboard renders the new `CE_TRB` and `PE_TRB` signals correctly with appropriate colors and pills.
* **Todo List:**
  - [ ] Add `"CE_TRB"` and `"PE_TRB"` to `SignalType` literal in `strategies/signal_engine.py`.
  - [ ] In `evaluate_signals()`, add a dedicated TRB evaluation block right after the ORB strategy.
  - [ ] Generate deduplication keys using `_signal_id("CE_TRB", latest_5m_ts)`.
  - [ ] Update `main.py`'s `print_startup_summary()` to include the TRB strategy toggle in the printed summary table.
  - [ ] Update frontend dashboard `parseStrategy(st)` in `ui/templates/index.html` to correctly map `TRB` strategy to a distinct pill style and label (e.g. `TRB` $\rightarrow$ `pill-yellow` or a dedicated style).
* **Relevant Context:** [`strategies/signal_engine.py`](strategies/signal_engine.py:42), [`main.py`](main.py:192), [`ui/templates/index.html`](ui/templates/index.html:902)

---

### 4. Unit Testing
* **Intent:** Ensure absolute robustness and coverage for the new strategy.
* **Expected Outcomes:**
  * Full test coverage for range extraction, crossover triggers, and time-guard restrictions under various market scenarios.
* **Todo List:**
  - [ ] Create `tests/test_trb_strategy.py`.
  - [ ] Write unit tests verifying:
    * Proper extraction of 9:45 AM 15m candle.
    * Inability to trade before 10:00 AM IST.
    * Proper crossover triggering for CE (close crosses high) and PE (close crosses low).
    * Proper execution of the false-breakout filters.
  - [ ] Run `python -m pytest tests/test_trb_strategy.py` to confirm they all pass.
* **Relevant Context:** [`tests/test_orb_strategy.py`](tests/test_orb_strategy.py:1)
