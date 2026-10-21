# Full-system backtest: 2025-10-01 to 2026-10-16

Run label `pivot_latest`, 258 trading sessions, generated 2026-10-20 18:20.  Overrides: {'ENABLE_EMA_STRATEGY': 'false', 'ENABLE_ORB_STRATEGY': 'false', 'ENABLE_VWAP_STRATEGY': 'false', 'ENABLE_TRB_STRATEGY': 'false', 'ENABLE_MOMENTUM_PHASE': 'false', 'ENABLE_NATR_STRATEGY': 'false', 'ENABLE_PDHL_STRATEGY': 'false', 'ENABLE_OB_STRATEGY': 'false', 'ENABLE_ATR_COPILOT_STRATEGY': 'false', 'ENABLE_PIVOT_STRATEGY': 'true'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 100 |
| Win % | 34 |
| Net P&L (Rs) | 39,109 |
| Gross P&L (Rs) | 49,016 |
| Costs (Rs) | 9,907 |
|   of which charges (Rs) | 5,907 |
|   of which slippage (Rs) | 4,000 |
| Avg cost per trade (Rs) | 99 |
| Profit factor | 2.17 |
| Avg trade (Rs) | 391 |
| Avg win (Rs) | 2,137 |
| Avg loss (Rs) | -508 |
| Largest win (Rs) | 7,068 |
| Largest loss (Rs) | -2,226 |
| Max drawdown (Rs) | -4,514 |
| Longest losing streak | 8 |
| Avg hold (min) | 34.80 |


Trades on 78 of 258 sessions; 41% of trading days were green.  Average 8.1 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| PIVOT | CE | 55 | 30.90 | 20,535 | 373 | 1.98 |
| PIVOT | PE | 45 | 37.80 | 18,574 | 413 | 2.48 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| PIVOT_BE_STOP | 37 | 8.10 | -6,339 | -171 | 0.03 | 25 |
| PIVOT_TSL_HIT | 26 | 96.20 | 58,884 | 2,265 | 787 | 51 |
| PIVOT_SL_HIT | 25 | 0 | -24,764 | -991 | 0 | 12 |
| STOP_HIT | 6 | 0 | -2,177 | -363 | 0 | 45 |
| PIVOT_TARGET_T3 | 4 | 100 | 7,347 | 1,837 | inf | 103 |
| EOD_SQUARE_OFF | 2 | 100 | 6,159 | 3,080 | inf | 120 |


### Exit reason by strategy (trade count)

| exit_reason | PIVOT |
|---|---:|
| EOD_SQUARE_OFF | 2 |
| PIVOT_BE_STOP | 37 |
| PIVOT_SL_HIT | 25 |
| PIVOT_TARGET_T3 | 4 |
| PIVOT_TSL_HIT | 26 |
| STOP_HIT | 6 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| BE | 47 | 19.10 | 6,706 | 143 | 1.96 |
| INITIAL | 27 | 0 | -26,481 | -981 | 0 |
| T1 | 23 | 95.70 | 46,721 | 2,031 | 624 |
| T2 | 3 | 100 | 12,163 | 4,054 | inf |


- Trades whose stop moved at least once: 73 of 100 (73%); average 2.2 moves per trade.

- Full initial-stop losses: 27 (27%).

- Of the 56 trades that reached +1R, the exit kept on average 43% of the best index move (median 49%); 41% of them still closed at a net loss.

- Median best move (MFE) 1.10R; 56% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 49 | 34.70 | 25,348 | 517 | 2.56 |
| H2 | 51 | 33.30 | 13,761 | 270 | 1.79 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2025 | 23 | 26.10 | -714 | -31 | 0.90 |
| 2026 | 77 | 36.40 | 39,823 | 517 | 2.52 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2025-10 | 6 | 50 | -297 | -50 | 0.88 | -297 |
| 2025-11 | 13 | 23.10 | 1,817 | 140 | 1.73 | 1,520 |
| 2025-12 | 4 | 0 | -2,234 | -559 | 0 | -714 |
| 2026-01 | 8 | 37.50 | 5,611 | 701 | 4.49 | 4,897 |
| 2026-02 | 13 | 30.80 | 841 | 65 | 1.13 | 5,738 |
| 2026-03 | 3 | 66.70 | 9,941 | 3,314 | 12.87 | 15,679 |
| 2026-04 | 4 | 75 | 11,212 | 2,803 | 10.96 | 26,891 |
| 2026-05 | 9 | 11.10 | -4,358 | -484 | 0.05 | 22,533 |
| 2026-06 | 11 | 45.50 | 3,286 | 299 | 1.75 | 25,819 |
| 2026-07 | 6 | 16.70 | 1,646 | 274 | 2.26 | 27,465 |
| 2026-08 | 8 | 37.50 | 1,277 | 160 | 1.99 | 28,742 |
| 2026-09 | 7 | 42.90 | 3,057 | 437 | 2.60 | 31,799 |
| 2026-10 | 8 | 37.50 | 7,311 | 914 | 3.68 | 39,110 |


77% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 20 | 25 | -1,688 | -84 | 0.83 |
| 10:00 | 23 | 34.80 | 5,632 | 245 | 1.80 |
| 11:00 | 18 | 33.30 | 10,498 | 583 | 2.72 |
| 12:00 | 16 | 43.80 | 8,912 | 557 | 4.26 |
| 13:00 | 23 | 34.80 | 15,755 | 685 | 2.96 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Mon | 24 | 37.50 | 16,274 | 678 | 2.92 |
| Tue | 26 | 34.60 | 11,231 | 432 | 2.51 |
| Wed | 26 | 34.60 | 5,110 | 197 | 1.43 |
| Thu | 24 | 29.20 | 6,493 | 271 | 2.12 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 80 | 36.20 | 36,710 | 459 | 2.28 |
| yes | 20 | 25 | 2,399 | 120 | 1.49 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| CE_PIVOT | 61 |
| PE_PIVOT | 49 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| PIVOT_BLOCKED_FRIDAY | 3,774 |
| PIVOT_BLOCKED_TIME | 3,681 |
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
| 2026-03-11 09:35:00 | PIVOT | PE | 359 | 550 | PIVOT_TSL_HIT | T2 | 3,710 |
| 2026-09-15 13:10:00 | PIVOT | PE | 290 | 472 | PIVOT_TSL_HIT | T1 | 3,529 |
| 2026-06-24 10:15:00 | PIVOT | CE | 257 | 413 | PIVOT_TSL_HIT | T1 | 3,026 |
| 2026-07-14 09:30:00 | PIVOT | PE | 336 | 489 | PIVOT_TSL_HIT | T1 | 2,957 |
| 2026-01-27 10:40:00 | PIVOT | PE | 381 | 525 | PIVOT_TSL_HIT | T1 | 2,771 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-06-24 09:50:00 | PIVOT | PE | 233 | 127 | PIVOT_SL_HIT | INITIAL | -2,226 |
| 2026-02-23 09:50:00 | PIVOT | CE | 463 | 377 | PIVOT_SL_HIT | INITIAL | -1,812 |
| 2026-02-02 13:10:00 | PIVOT | CE | 464 | 385 | PIVOT_SL_HIT | INITIAL | -1,669 |
| 2025-10-08 13:50:00 | PIVOT | CE | 208 | 131 | PIVOT_SL_HIT | INITIAL | -1,629 |
| 2026-05-13 13:05:00 | PIVOT | CE | 325 | 252 | PIVOT_SL_HIT | INITIAL | -1,557 |
| 2026-09-15 11:45:00 | PIVOT | CE | 297 | 245 | PIVOT_SL_HIT | INITIAL | -1,145 |
| 2026-04-27 09:30:00 | PIVOT | CE | 579 | 528 | PIVOT_SL_HIT | INITIAL | -1,126 |
| 2026-02-25 10:20:00 | PIVOT | CE | 262 | 211 | PIVOT_SL_HIT | INITIAL | -1,116 |
| 2026-06-30 10:45:00 | PIVOT | PE | 315 | 266 | PIVOT_SL_HIT | INITIAL | -1,069 |
| 2026-01-05 09:30:00 | PIVOT | CE | 366 | 323 | PIVOT_SL_HIT | INITIAL | -963 |


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
| TREND_GATE_STRATEGIES | frozenset({'VWAP', 'EMA', 'TRB', 'NATR'}) |
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
