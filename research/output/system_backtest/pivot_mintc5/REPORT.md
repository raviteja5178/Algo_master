# Full-system backtest: 2025-10-01 to 2026-10-16

Run label `pivot_mintc5`, 258 trading sessions, generated 2026-10-20 18:54.  Overrides: {'ENABLE_EMA_STRATEGY': 'false', 'ENABLE_ORB_STRATEGY': 'false', 'ENABLE_VWAP_STRATEGY': 'false', 'ENABLE_TRB_STRATEGY': 'false', 'ENABLE_MOMENTUM_PHASE': 'false', 'ENABLE_NATR_STRATEGY': 'false', 'ENABLE_PDHL_STRATEGY': 'false', 'ENABLE_OB_STRATEGY': 'false', 'ENABLE_ATR_COPILOT_STRATEGY': 'false', 'ENABLE_PIVOT_STRATEGY': 'true', 'PIVOT_MIN_TODAY_CANDLES': '5'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 85 |
| Win % | 34.10 |
| Net P&L (Rs) | 35,435 |
| Gross P&L (Rs) | 43,877 |
| Costs (Rs) | 8,442 |
|   of which charges (Rs) | 5,042 |
|   of which slippage (Rs) | 3,400 |
| Avg cost per trade (Rs) | 99 |
| Profit factor | 2.21 |
| Avg trade (Rs) | 417 |
| Avg win (Rs) | 2,230 |
| Avg loss (Rs) | -522 |
| Largest win (Rs) | 7,068 |
| Largest loss (Rs) | -2,226 |
| Max drawdown (Rs) | -4,514 |
| Longest losing streak | 11 |
| Avg hold (min) | 36.30 |


Trades on 66 of 258 sessions; 41% of trading days were green.  Average 6.9 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| PIVOT | CE | 46 | 32.60 | 22,976 | 499 | 2.32 |
| PIVOT | PE | 39 | 35.90 | 12,459 | 319 | 2.05 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| PIVOT_BE_STOP | 31 | 6.50 | -5,104 | -165 | 0.01 | 23 |
| PIVOT_SL_HIT | 22 | 0 | -22,016 | -1,001 | 0 | 13 |
| PIVOT_TSL_HIT | 21 | 100 | 51,110 | 2,434 | inf | 57 |
| STOP_HIT | 5 | 0 | -2,060 | -412 | 0 | 46 |
| PIVOT_TARGET_T3 | 4 | 100 | 7,347 | 1,837 | inf | 103 |
| EOD_SQUARE_OFF | 2 | 100 | 6,159 | 3,080 | inf | 120 |


### Exit reason by strategy (trade count)

| exit_reason | PIVOT |
|---|---:|
| EOD_SQUARE_OFF | 2 |
| PIVOT_BE_STOP | 31 |
| PIVOT_SL_HIT | 22 |
| PIVOT_TARGET_T3 | 4 |
| PIVOT_TSL_HIT | 21 |
| STOP_HIT | 5 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| BE | 40 | 20 | 8,058 | 201 | 2.46 |
| INITIAL | 24 | 0 | -23,733 | -989 | 0 |
| T1 | 19 | 100 | 42,657 | 2,245 | inf |
| T2 | 2 | 100 | 8,454 | 4,227 | inf |


- Trades whose stop moved at least once: 61 of 85 (72%); average 2.1 moves per trade.

- Full initial-stop losses: 24 (28%).

- Of the 47 trades that reached +1R, the exit kept on average 47% of the best index move (median 57%); 40% of them still closed at a net loss.

- Median best move (MFE) 1.10R; 55% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 45 | 33.30 | 22,717 | 505 | 2.56 |
| H2 | 40 | 35 | 12,718 | 318 | 1.87 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2025 | 21 | 23.80 | -599 | -29 | 0.91 |
| 2026 | 64 | 37.50 | 36,034 | 563 | 2.60 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2025-10 | 5 | 60 | 362 | 72 | 1.19 | 362 |
| 2025-11 | 12 | 16.70 | 1,274 | 106 | 1.51 | 1,636 |
| 2025-12 | 4 | 0 | -2,234 | -559 | 0 | -598 |
| 2026-01 | 7 | 42.90 | 6,574 | 939 | 11.19 | 5,976 |
| 2026-02 | 13 | 30.80 | 841 | 65 | 1.13 | 6,817 |
| 2026-03 | 2 | 50 | 6,231 | 3,115 | 8.44 | 13,048 |
| 2026-04 | 3 | 100 | 12,338 | 4,113 | inf | 25,386 |
| 2026-05 | 9 | 11.10 | -4,358 | -484 | 0.05 | 21,028 |
| 2026-06 | 10 | 40 | 3,157 | 316 | 1.72 | 24,185 |
| 2026-07 | 3 | 0 | -932 | -311 | 0 | 23,253 |
| 2026-08 | 6 | 50 | 1,500 | 250 | 2.42 | 24,753 |
| 2026-09 | 6 | 33.30 | 2,419 | 403 | 2.27 | 27,172 |
| 2026-10 | 5 | 60 | 8,264 | 1,653 | 5.66 | 35,436 |


77% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 5 | 0 | -5,362 | -1,072 | 0 |
| 10:00 | 23 | 34.80 | 5,632 | 245 | 1.80 |
| 11:00 | 18 | 33.30 | 10,498 | 583 | 2.72 |
| 12:00 | 16 | 43.80 | 8,912 | 557 | 4.26 |
| 13:00 | 23 | 34.80 | 15,755 | 685 | 2.96 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Mon | 20 | 40 | 18,310 | 915 | 3.89 |
| Tue | 24 | 33.30 | 8,695 | 362 | 2.24 |
| Wed | 21 | 33.30 | 2,155 | 103 | 1.21 |
| Thu | 20 | 30 | 6,276 | 314 | 2.17 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 69 | 36.20 | 33,253 | 482 | 2.34 |
| yes | 16 | 25 | 2,182 | 136 | 1.49 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| CE_PIVOT | 52 |
| PE_PIVOT | 42 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| PIVOT_BLOCKED_FRIDAY | 3,774 |
| PIVOT_BLOCKED_TIME | 3,699 |
| ENTRY_BLOCKED_MAX_RISK | 3 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-03-16 13:55:00 | PIVOT | CE | 596 | 956 | PIVOT_TSL_HIT | T2 | 7,068 |
| 2026-10-14 12:50:00 | PIVOT | PE | 242 | 501 | PIVOT_TSL_HIT | T1 | 5,086 |
| 2026-04-06 11:30:00 | PIVOT | CE | 724 | 974 | PIVOT_TSL_HIT | T1 | 4,883 |
| 2026-04-07 11:15:00 | PIVOT | CE | 574 | 819 | PIVOT_TSL_HIT | T1 | 4,787 |
| 2026-02-02 13:50:00 | PIVOT | CE | 449 | 648 | EOD_SQUARE_OFF | BE | 3,861 |
| 2026-09-15 13:10:00 | PIVOT | PE | 290 | 472 | PIVOT_TSL_HIT | T1 | 3,529 |
| 2026-06-24 10:15:00 | PIVOT | CE | 257 | 413 | PIVOT_TSL_HIT | T1 | 3,026 |
| 2026-01-27 10:40:00 | PIVOT | PE | 381 | 525 | PIVOT_TSL_HIT | T1 | 2,771 |
| 2026-04-30 13:00:00 | PIVOT | CE | 821 | 960 | PIVOT_TSL_HIT | T1 | 2,667 |
| 2025-11-20 11:35:00 | PIVOT | CE | 66.45 | 204 | PIVOT_TARGET_T3 | BE | 2,665 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-06-24 09:50:00 | PIVOT | PE | 233 | 127 | PIVOT_SL_HIT | INITIAL | -2,226 |
| 2026-02-23 09:50:00 | PIVOT | CE | 463 | 377 | PIVOT_SL_HIT | INITIAL | -1,812 |
| 2026-02-02 13:10:00 | PIVOT | CE | 464 | 385 | PIVOT_SL_HIT | INITIAL | -1,669 |
| 2025-10-08 13:50:00 | PIVOT | CE | 208 | 131 | PIVOT_SL_HIT | INITIAL | -1,629 |
| 2026-05-13 13:05:00 | PIVOT | CE | 325 | 252 | PIVOT_SL_HIT | INITIAL | -1,557 |
| 2026-09-15 11:45:00 | PIVOT | CE | 297 | 245 | PIVOT_SL_HIT | INITIAL | -1,145 |
| 2026-02-25 10:20:00 | PIVOT | CE | 262 | 211 | PIVOT_SL_HIT | INITIAL | -1,116 |
| 2026-06-30 10:45:00 | PIVOT | PE | 315 | 266 | PIVOT_SL_HIT | INITIAL | -1,069 |
| 2026-05-06 12:55:00 | PIVOT | PE | 282 | 240 | PIVOT_SL_HIT | INITIAL | -940 |
| 2026-10-01 10:35:00 | PIVOT | CE | 83 | 40.65 | STOP_HIT | INITIAL | -936 |


## Configuration tested

| Setting | Value |
|---|---|
| ENABLE_PIVOT_STRATEGY | yes |
| ENABLE_ORB_STRATEGY | no |
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
| TREND_GATE_STRATEGIES | frozenset({'VWAP', 'EMA', 'NATR', 'TRB'}) |
| GENERIC_INDEX_EXITS | yes |
| PIVOT_BE_TRIGGER_R | 0.75 |
| PIVOT_BE_BUFFER_PTS | 12 |
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
- **Options are modelled, not historical.** Black-Scholes, IV = India VIX (minute), r = 6.5%.  Strike selection, ITM fallback and expiry-day rollover use the bot's own selector on a synthetic chain; weekly expiry calendar [['2000-01-01', 4], ['2025-01-01', 1], ['2025-09-01', 3]] (weekday 0 = Monday), moved to the previous session on holidays.  The model has no volatility smile, no intraday IV crush beyond VIX moves, and VIX (30-day, NIFTY) is a proxy for weekly SENSEX IV — expect real premiums, especially on expiry days, to differ.
- **Fills and costs.** SHADOW-mode paper fills at the modelled premium, then 1.0 option point(s) of slippage per side plus brokerage, STT, exchange, SEBI, stamp duty and GST are deducted per trade.  Quantity is today's lot (20) throughout.
- **Not modelled:** order rejections, partial fills, feed outages, margin limits.


Files: `trades.csv` (one row per trade, with exit reason, stop stage, MFE/MAE and costs), `events.csv` (signals, blocks, stop moves), `run_meta.json` (full settings snapshot).  Re-run: `python -m research.system_backtest`.
