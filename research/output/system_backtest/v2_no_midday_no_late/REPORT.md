# Full-system backtest: 2024-01-15 to 2026-10-16

Run label `v2_no_midday_no_late`, 683 trading sessions, generated 2026-10-20 20:29.  Overrides: {'NO_NEW_ENTRY_AFTER': '14:00'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 265 |
| Win % | 23 |
| Net P&L (Rs) | -5,876 |
| Gross P&L (Rs) | 20,884 |
| Costs (Rs) | 26,760 |
|   of which charges (Rs) | 16,160 |
|   of which slippage (Rs) | 10,600 |
| Avg cost per trade (Rs) | 101 |
| Profit factor | 0.95 |
| Avg trade (Rs) | -22 |
| Avg win (Rs) | 2,025 |
| Avg loss (Rs) | -634 |
| Largest win (Rs) | 10,514 |
| Largest loss (Rs) | -2,743 |
| Max drawdown (Rs) | -28,402 |
| Longest losing streak | 26 |
| Avg hold (min) | 36 |


Trades on 196 of 683 sessions; 30% of trading days were green.  Average 8.1 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| EMA | CE | 7 | 42.90 | -1,831 | -262 | 0.48 |
| EMA | PE | 1 | 0 | -1,783 | -1,783 | 0 |
| ORB | CE | 8 | 62.50 | 173 | 22 | 1.03 |
| ORB | PE | 13 | 46.20 | 4,895 | 377 | 1.46 |
| PIVOT | CE | 120 | 16.70 | -17,346 | -145 | 0.69 |
| PIVOT | PE | 116 | 23.30 | 10,017 | 86 | 1.20 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| PIVOT_SL_HIT | 88 | 0 | -88,794 | -1,009 | 0 | 14 |
| PIVOT_BE_STOP | 76 | 5.30 | -13,961 | -184 | 0 | 18 |
| PIVOT_TSL_HIT | 38 | 94.70 | 69,326 | 1,824 | 334 | 52 |
| STOP_HIT | 34 | 8.80 | -9,157 | -269 | 0.13 | 79 |
| IDX_TSL_HIT | 8 | 100 | 11,849 | 1,481 | inf | 122 |
| IDX_SL_HIT | 6 | 0 | -10,390 | -1,732 | 0 | 51 |
| PIVOT_TARGET_T3 | 5 | 100 | 24,972 | 4,994 | inf | 60 |
| EMA_SL_HIT | 3 | 0 | -4,119 | -1,373 | 0 | 16 |
| EOD_SQUARE_OFF | 3 | 66.70 | 4,495 | 1,498 | 5.04 | 182 |
| IDX_TARGET | 2 | 100 | 9,672 | 4,836 | inf | 33 |
| EMA_TSL_HIT | 1 | 100 | 469 | 469 | inf | 18 |
| EMA_TIME_STOP | 1 | 0 | -239 | -239 | 0 | 30 |


### Exit reason by strategy (trade count)

| exit_reason | EMA | ORB | PIVOT |
|---|---:|---:|---:|
| EMA_SL_HIT | 3 | 0 | 0 |
| EMA_TIME_STOP | 1 | 0 | 0 |
| EMA_TSL_HIT | 1 | 0 | 0 |
| EOD_SQUARE_OFF | 0 | 0 | 3 |
| IDX_SL_HIT | 0 | 6 | 0 |
| IDX_TARGET | 0 | 2 | 0 |
| IDX_TSL_HIT | 0 | 8 | 0 |
| PIVOT_BE_STOP | 0 | 0 | 76 |
| PIVOT_SL_HIT | 0 | 0 | 88 |
| PIVOT_TARGET_T3 | 0 | 0 | 5 |
| PIVOT_TSL_HIT | 0 | 0 | 38 |
| STOP_HIT | 3 | 5 | 26 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| BE | 108 | 8.30 | 1,272 | 12 | 1.07 |
| INITIAL | 103 | 0 | -111,750 | -1,085 | 0 |
| T1 | 36 | 94.40 | 60,938 | 1,693 | 294 |
| TRAIL | 14 | 100 | 23,358 | 1,668 | inf |
| T2 | 4 | 100 | 20,306 | 5,076 | inf |


- Trades whose stop moved at least once: 162 of 265 (61%); average 2.4 moves per trade.

- Full initial-stop losses: 103 (39%).

- Of the 125 trades that reached +1R, the exit kept on average 39% of the best index move (median 35%); 53% of them still closed at a net loss.

- Median best move (MFE) 0.96R; 47% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 139 | 19.40 | -971 | -7 | 0.99 |
| H2 | 126 | 27 | -4,904 | -39 | 0.92 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2024 | 102 | 16.70 | -17,581 | -172 | 0.66 |
| 2025 | 98 | 21.40 | -5,864 | -60 | 0.88 |
| 2026 | 65 | 35.40 | 17,570 | 270 | 1.66 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2024-01 | 6 | 0 | -3,000 | -500 | 0 | -3,000 |
| 2024-02 | 6 | 33.30 | 1,008 | 168 | 1.83 | -1,992 |
| 2024-03 | 8 | 25 | -3,279 | -410 | 0.30 | -5,271 |
| 2024-04 | 1 | 0 | -1,227 | -1,227 | 0 | -6,498 |
| 2024-05 | 7 | 0 | -3,627 | -518 | 0 | -10,125 |
| 2024-06 | 6 | 0 | -3,945 | -657 | 0 | -14,070 |
| 2024-07 | 13 | 7.70 | -7,310 | -562 | 0.16 | -21,380 |
| 2024-08 | 7 | 0 | -1,289 | -184 | 0 | -22,669 |
| 2024-09 | 10 | 30 | 1,747 | 175 | 1.60 | -20,922 |
| 2024-10 | 18 | 11.10 | -5,263 | -292 | 0.44 | -26,185 |
| 2024-11 | 9 | 33.30 | 6,320 | 702 | 2.17 | -19,865 |
| 2024-12 | 11 | 36.40 | 2,282 | 207 | 1.34 | -17,583 |
| 2025-01 | 5 | 40 | 7,237 | 1,447 | 5.09 | -10,346 |
| 2025-02 | 10 | 40 | 3,634 | 363 | 2.04 | -6,712 |
| 2025-03 | 6 | 16.70 | 3,210 | 535 | 2.90 | -3,502 |
| 2025-04 | 9 | 22.20 | 6,402 | 711 | 2.56 | 2,900 |
| 2025-05 | 7 | 14.30 | -3,874 | -553 | 0.36 | -974 |
| 2025-06 | 8 | 12.50 | -3,724 | -465 | 0.12 | -4,698 |
| 2025-07 | 12 | 16.70 | -5,166 | -430 | 0.32 | -9,864 |
| 2025-08 | 15 | 13.30 | -8,189 | -546 | 0.27 | -18,053 |
| 2025-09 | 9 | 11.10 | -4,073 | -453 | 0.14 | -22,126 |
| 2025-10 | 5 | 60 | -428 | -86 | 0.82 | -22,554 |
| 2025-11 | 9 | 11.10 | -1,164 | -129 | 0.43 | -23,718 |
| 2025-12 | 3 | 33.30 | 269 | 90 | 1.21 | -23,449 |
| 2026-01 | 8 | 50 | 7,944 | 993 | 11.82 | -15,505 |
| 2026-02 | 14 | 21.40 | -3,977 | -284 | 0.56 | -19,482 |
| 2026-03 | 3 | 33.30 | 2,480 | 827 | 3.47 | -17,002 |
| 2026-04 | 2 | 100 | 3,267 | 1,634 | inf | -13,735 |
| 2026-05 | 6 | 16.70 | -3,676 | -613 | 0.06 | -17,411 |
| 2026-06 | 9 | 44.40 | 3,097 | 344 | 1.86 | -14,314 |
| 2026-07 | 7 | 14.30 | -2,127 | -304 | 0.49 | -16,441 |
| 2026-08 | 7 | 28.60 | 32 | 5 | 1.02 | -16,409 |
| 2026-09 | 5 | 40 | 2,602 | 520 | 2.84 | -13,807 |
| 2026-10 | 4 | 75 | 7,928 | 1,982 | 6.26 | -5,879 |


47% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 66 | 31.80 | 6,419 | 97 | 1.15 |
| 10:00 | 81 | 21 | -17,678 | -218 | 0.52 |
| 12:00 | 62 | 21 | 4,537 | 73 | 1.18 |
| 13:00 | 56 | 17.90 | 846 | 15 | 1.04 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Mon | 51 | 21.60 | -5,227 | -102 | 0.79 |
| Tue | 75 | 28 | 12,956 | 173 | 1.41 |
| Wed | 72 | 16.70 | -20,941 | -291 | 0.50 |
| Thu | 63 | 22.20 | 666 | 11 | 1.02 |
| Fri | 4 | 75 | 6,669 | 1,667 | 4.94 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 222 | 22.10 | -20,702 | -93 | 0.81 |
| yes | 43 | 27.90 | 14,826 | 345 | 1.67 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| CE | 517 |
| PE | 442 |
| CE_PIVOT | 161 |
| PE_PIVOT | 146 |
| PE_ORB | 127 |
| CE_ORB | 94 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| PIVOT_BLOCKED_FRIDAY | 9,737 |
| PIVOT_BLOCKED_TIME | 9,693 |
| SMART_ENTRY_BLOCKED_EMA_GAP_SHRINKING: EMA gap not widening | 281 |
| SMART_ENTRY_BLOCKED_BODY | 218 |
| TREND_GATE_BLOCKED: against daily trend (UP) | 217 |
| TREND_GATE_BLOCKED: against daily trend (DOWN) | 179 |
| BACKTEST_FILTER_BLOCKED: entry window #:#-#:# blocked | 109 |
| ENTRY_BLOCKED_MAX_RISK | 89 |
| EMA_ENTRY_BLOCKED: room # < #R (#) | 62 |
| SMART_ENTRY_BLOCKED_EMA_GAP | 16 |
| EMA_ENTRY_BLOCKED: option premium # <= option #m EMA# # | 6 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not falling for PE | 5 |
| EMA_ENTRY_BLOCKED: risk # > max # | 4 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not rising for CE | 1 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2025-04-08 12:00:00 | PIVOT | CE | 201 | 732 | PIVOT_TARGET_T3 | BE | 10,514 |
| 2025-01-21 09:45:00 | PIVOT | PE | 233 | 682 | PIVOT_TARGET_T3 | T2 | 8,867 |
| 2024-12-13 09:30:00 | ORB | PE | 185 | 522 | IDX_TARGET | TRAIL | 6,637 |
| 2025-03-03 09:35:00 | PIVOT | PE | 274 | 524 | PIVOT_TSL_HIT | T2 | 4,904 |
| 2026-10-14 12:50:00 | PIVOT | PE | 282 | 531 | PIVOT_TSL_HIT | T1 | 4,870 |
| 2024-11-07 09:35:00 | PIVOT | PE | 338 | 563 | PIVOT_TSL_HIT | T1 | 4,394 |
| 2024-11-12 12:00:00 | PIVOT | PE | 391 | 616 | PIVOT_TSL_HIT | T1 | 4,389 |
| 2026-02-02 13:50:00 | PIVOT | CE | 508 | 695 | EOD_SQUARE_OFF | BE | 3,627 |
| 2026-03-11 09:35:00 | PIVOT | PE | 446 | 626 | PIVOT_TSL_HIT | T2 | 3,484 |
| 2026-09-15 13:10:00 | PIVOT | PE | 328 | 501 | PIVOT_TSL_HIT | T1 | 3,364 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2024-11-06 09:50:00 | PIVOT | CE | 488 | 356 | PIVOT_SL_HIT | INITIAL | -2,743 |
| 2024-12-04 10:35:00 | PIVOT | CE | 442 | 321 | PIVOT_SL_HIT | INITIAL | -2,519 |
| 2026-06-24 09:50:00 | PIVOT | PE | 293 | 180 | PIVOT_SL_HIT | INITIAL | -2,359 |
| 2025-07-08 09:30:00 | ORB | CE | 197 | 86.75 | STOP_HIT | INITIAL | -2,288 |
| 2024-06-20 09:40:00 | ORB | PE | 321 | 214 | IDX_SL_HIT | INITIAL | -2,240 |
| 2025-08-26 09:35:00 | ORB | PE | 199 | 99 | STOP_HIT | INITIAL | -2,083 |
| 2026-07-02 09:40:00 | ORB | CE | 192 | 97.20 | IDX_SL_HIT | INITIAL | -1,997 |
| 2026-02-23 09:50:00 | PIVOT | CE | 546 | 454 | PIVOT_SL_HIT | INITIAL | -1,944 |
| 2024-05-06 10:00:00 | PIVOT | PE | 564 | 474 | PIVOT_SL_HIT | INITIAL | -1,891 |
| 2024-10-08 10:15:00 | PIVOT | PE | 522 | 433 | PIVOT_SL_HIT | INITIAL | -1,869 |


## Configuration tested

| Setting | Value |
|---|---|
| ENABLE_PIVOT_STRATEGY | yes |
| ENABLE_ORB_STRATEGY | yes |
| ENABLE_EMA_STRATEGY | yes |
| ENABLE_VWAP_STRATEGY | no |
| ENABLE_TRB_STRATEGY | no |
| ENABLE_MOMENTUM_PHASE | no |
| ENABLE_NATR_STRATEGY | no |
| ENABLE_PDHL_STRATEGY | no |
| ENABLE_OB_STRATEGY | no |
| ENABLE_ATR_COPILOT_STRATEGY | no |
| QUANTITY | 20 |
| FORCE_EXIT_TIME | 15:10 |
| NO_NEW_ENTRY_AFTER | 14:00 |
| MAX_TRADES_PER_SIDE | 3 |
| ENABLE_DAILY_LOSS_LIMIT | yes |
| DAILY_LOSS_LIMIT_RUPEES | 5,000 |
| MAX_RISK_RUPEES_PER_TRADE | 2,000 |
| TREND_GATE_15M | yes |
| TREND_GATE_DAILY | yes |
| TREND_GATE_STRATEGIES | frozenset({'TRB', 'NATR', 'VWAP', 'EMA'}) |
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
- **Options are modelled, not historical.** Black-Scholes in trading time (weeknight = 176 min, weekend = 609 min), IV = India VIX (minute), r = 6.5%.  Strike selection, ITM fallback and expiry-day rollover use the bot's own selector on a synthetic chain; weekly expiry calendar [['2000-01-01', 4], ['2025-01-01', 1], ['2025-09-01', 3]] (weekday 0 = Monday), moved to the previous session on holidays.  The model has no volatility smile, no intraday IV crush beyond VIX moves, and VIX (30-day, NIFTY) is a proxy for weekly SENSEX IV — expect real premiums, especially on expiry days, to differ.
- **Fills and costs.** SHADOW-mode paper fills at the modelled premium, then 1.0 option point(s) of slippage per side plus brokerage, STT, exchange, SEBI, stamp duty and GST are deducted per trade.  Quantity is today's lot (20) throughout.
- **Not modelled:** order rejections, partial fills, feed outages, margin limits.


Files: `trades.csv` (one row per trade, with exit reason, stop stage, MFE/MAE and costs), `events.csv` (signals, blocks, stop moves), `run_meta.json` (full settings snapshot).  Re-run: `python -m research.system_backtest`.
