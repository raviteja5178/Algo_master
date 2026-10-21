# Full-system backtest: 2025-10-01 to 2026-10-16

Run label `orb_monday_enabled`, 258 trading sessions, generated 2026-10-20 21:10.  Overrides: {'ENABLE_EMA_STRATEGY': 'false', 'ENABLE_ORB_STRATEGY': 'true', 'ENABLE_PIVOT_STRATEGY': 'false', 'ENABLE_VWAP_STRATEGY': 'false', 'ENABLE_TRB_STRATEGY': 'false', 'ENABLE_MOMENTUM_PHASE': 'false', 'ENABLE_NATR_STRATEGY': 'false', 'ENABLE_PDHL_STRATEGY': 'false', 'ENABLE_OB_STRATEGY': 'false', 'ENABLE_ATR_COPILOT_STRATEGY': 'false', 'ORB_MOMENTUM_SKIP_MONDAY': 'false'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 6 |
| Win % | 33.30 |
| Net P&L (Rs) | -4,997 |
| Gross P&L (Rs) | -4,395 |
| Costs (Rs) | 602 |
|   of which charges (Rs) | 362 |
|   of which slippage (Rs) | 240 |
| Avg cost per trade (Rs) | 100 |
| Profit factor | 0.41 |
| Avg trade (Rs) | -833 |
| Avg win (Rs) | 1,710 |
| Avg loss (Rs) | -2,104 |
| Largest win (Rs) | 2,201 |
| Largest loss (Rs) | -2,704 |
| Max drawdown (Rs) | -5,312 |
| Longest losing streak | 2 |
| Avg hold (min) | 121 |


Trades on 6 of 258 sessions; 33% of trading days were green.  Average 0.5 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| ORB | CE | 4 | 25 | -4,493 | -1,123 | 0.21 |
| ORB | PE | 2 | 50 | -503 | -252 | 0.81 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| IDX_SL_HIT | 3 | 0 | -5,808 | -1,936 | 0 | 50 |
| IDX_TSL_HIT | 2 | 100 | 3,419 | 1,710 | inf | 196 |
| STOP_HIT | 1 | 0 | -2,608 | -2,608 | 0 | 186 |


### Exit reason by strategy (trade count)

| exit_reason | ORB |
|---|---:|
| IDX_SL_HIT | 3 |
| IDX_TSL_HIT | 2 |
| STOP_HIT | 1 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| INITIAL | 4 | 0 | -8,416 | -2,104 | 0 |
| TRAIL | 2 | 100 | 3,419 | 1,710 | inf |


- Trades whose stop moved at least once: 2 of 6 (33%); average 8.7 moves per trade.

- Full initial-stop losses: 4 (67%).

- Of the 2 trades that reached +1R, the exit kept on average 65% of the best index move (median 65%); 0% of them still closed at a net loss.

- Median best move (MFE) 0.92R; 33% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 4 | 50 | 315 | 79 | 1.10 |
| H2 | 2 | 0 | -5,312 | -2,656 | 0 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2025 | 2 | 0 | -3,104 | -1,552 | 0 |
| 2026 | 4 | 50 | -1,893 | -473 | 0.64 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2025-10 | 2 | 0 | -3,104 | -1,552 | 0 | -3,104 |
| 2026-01 | 2 | 100 | 3,419 | 1,710 | inf | 315 |
| 2026-05 | 1 | 0 | -2,608 | -2,608 | 0 | -2,293 |
| 2026-06 | 1 | 0 | -2,704 | -2,704 | 0 | -4,997 |


25% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 6 | 33.30 | -4,997 | -833 | 0.41 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Tue | 3 | 33.30 | -3,111 | -1,037 | 0.41 |
| Wed | 1 | 0 | -1,153 | -1,153 | 0 |
| Fri | 2 | 50 | -732 | -366 | 0.62 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 6 | 33.30 | -4,997 | -833 | 0.41 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| CE_ORB | 41 |
| PE_ORB | 40 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| ORB_BLOCKED_THURSDAY | 300 |
| ENTRY_BLOCKED_MAX_RISK | 62 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not rising for CE | 6 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-01-20 09:30:00 | ORB | PE | 331 | 447 | IDX_TSL_HIT | TRAIL | 2,201 |
| 2026-01-02 09:35:00 | ORB | CE | 457 | 523 | IDX_TSL_HIT | TRAIL | 1,219 |
| 2025-10-08 09:40:00 | ORB | CE | 253 | 200 | IDX_SL_HIT | INITIAL | -1,153 |
| 2025-10-31 09:40:00 | ORB | CE | 563 | 470 | IDX_SL_HIT | INITIAL | -1,951 |
| 2026-05-26 09:30:00 | ORB | CE | 375 | 249 | STOP_HIT | INITIAL | -2,608 |
| 2026-06-30 09:30:00 | ORB | PE | 370 | 240 | IDX_SL_HIT | INITIAL | -2,704 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-06-30 09:30:00 | ORB | PE | 370 | 240 | IDX_SL_HIT | INITIAL | -2,704 |
| 2026-05-26 09:30:00 | ORB | CE | 375 | 249 | STOP_HIT | INITIAL | -2,608 |
| 2025-10-31 09:40:00 | ORB | CE | 563 | 470 | IDX_SL_HIT | INITIAL | -1,951 |
| 2025-10-08 09:40:00 | ORB | CE | 253 | 200 | IDX_SL_HIT | INITIAL | -1,153 |
| 2026-01-02 09:35:00 | ORB | CE | 457 | 523 | IDX_TSL_HIT | TRAIL | 1,219 |
| 2026-01-20 09:30:00 | ORB | PE | 331 | 447 | IDX_TSL_HIT | TRAIL | 2,201 |


## Configuration tested

| Setting | Value |
|---|---|
| ENABLE_PIVOT_STRATEGY | no |
| ENABLE_ORB_STRATEGY | yes |
| ENABLE_EMA_STRATEGY | no |
| ENABLE_VWAP_STRATEGY | no |
| ENABLE_TRB_STRATEGY | no |
| ENABLE_MOMENTUM_PHASE | no |
| ENABLE_NATR_STRATEGY | no |
| ENABLE_PDHL_STRATEGY | no |
| ENABLE_OB_STRATEGY | no |
| ENABLE_ATR_COPILOT_STRATEGY | no |
| QUANTITY | 20 |
| FORCE_EXIT_TIME | 15:10 |
| NO_NEW_ENTRY_AFTER | 15:00 |
| MAX_TRADES_PER_SIDE | 3 |
| ENABLE_DAILY_LOSS_LIMIT | yes |
| DAILY_LOSS_LIMIT_RUPEES | 5,000 |
| MAX_RISK_RUPEES_PER_TRADE | 2,000 |
| TREND_GATE_15M | yes |
| TREND_GATE_DAILY | yes |
| TREND_GATE_STRATEGIES | frozenset({'TRB', 'VWAP', 'EMA', 'NATR'}) |
| GENERIC_INDEX_EXITS | yes |
| PIVOT_BE_TRIGGER_R | 0.75 |
| PIVOT_BE_BUFFER_PTS | 25 |
| PIVOT_TRAIL_ATR_MULT | 1 |
| PIVOT_T2_TRAIL_ATR_MULT | 0.75 |
| PIVOT_MAX_TRADES_PER_DAY | 3 |
| PIVOT_OPTION_DELTA | 0.40 |
| EMA_NO_NEW_ENTRY_AFTER | 12:00 |
| EMA_TRAIL_ATR_MULT | 1 |
| EMA_BE_TRIGGER_R | 1 |
| BE_TRIGGER_RR | 1 |
| GENERIC_TRAIL_ATR_MULT | 2 |
| MAX_SL_PCT | 0.50 |
| ATM_DELTA | 0.50 |
| EXPIRY_DAY_ROLLOVER_TIME | 12:30 |
| ENABLE_SMART_EXIT | yes |


## How this backtest works

- **Production code, not a re-implementation.** Each session runs `main.BotContext`, `main.bootstrap_session`, the live tick handler, `execute_entry`, the Pivot / EMA / Index trade managers (SL, break-even, T1/T2 locks, chandelier trailing stop, targets), smart exits, the paper-broker SL backstop and `main._run_eod_exit`.  Signal de-duplication, daily caps, cooldowns, the trend gates, the rupee-risk cap and the daily loss limit all run from the bot's own SQLite tables.
- **No look-ahead.** The simulated Kite API only returns bars that had completed by the simulated time; signals fire on the first tick after a 5-minute candle closes, as live.
- **Price path.** Each 1-minute SENSEX bar is replayed as four ticks (up bar O,L,H,C; down bar O,H,L,C).  Intra-minute order beyond that is unknown.
- **Options are modelled, not historical.** Black-Scholes in trading time (weeknight = 176 min, weekend = 609 min), IV = India VIX (minute), r = 6.5%.  Strike selection, ITM fallback and expiry-day rollover use the bot's own selector on a synthetic chain; weekly expiry calendar [['2000-01-01', 4], ['2025-01-01', 1], ['2025-09-01', 3]] (weekday 0 = Monday), moved to the previous session on holidays.  The model has no volatility smile, no intraday IV crush beyond VIX moves, and VIX (30-day, NIFTY) is a proxy for weekly SENSEX IV — expect real premiums, especially on expiry days, to differ.
- **Fills and costs.** SHADOW-mode paper fills at the modelled premium, then 1.0 option point(s) of slippage per side plus brokerage, STT, exchange, SEBI, stamp duty and GST are deducted per trade.  Quantity is today's lot (20) throughout.
- **Not modelled:** order rejections, partial fills, feed outages, margin limits.


Files: `trades.csv` (one row per trade, with exit reason, stop stage, MFE/MAE and costs), `events.csv` (signals, blocks, stop moves), `run_meta.json` (full settings snapshot).  Re-run: `python -m research.system_backtest`.
