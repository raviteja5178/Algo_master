# Full-system backtest: 2024-01-15 to 2026-10-16

Run label `v1_pivot_be_1_5R`, 683 trading sessions, generated 2026-10-20 02:19.  Overrides: {'PIVOT_BE_TRIGGER_R': '1.5'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 472 |
| Win % | 27.50 |
| Net P&L (Rs) | -24,877 |
| Gross P&L (Rs) | 22,087 |
| Costs (Rs) | 46,964 |
|   of which charges (Rs) | 28,084 |
|   of which slippage (Rs) | 18,880 |
| Avg cost per trade (Rs) | 99 |
| Profit factor | 0.92 |
| Avg trade (Rs) | -53 |
| Avg win (Rs) | 2,084 |
| Avg loss (Rs) | -865 |
| Largest win (Rs) | 12,080 |
| Largest loss (Rs) | -2,658 |
| Max drawdown (Rs) | -72,320 |
| Longest losing streak | 18 |
| Avg hold (min) | 40.50 |


Trades on 303 of 683 sessions; 35% of trading days were green.  Average 14.5 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| EMA | CE | 14 | 42.90 | -3,798 | -271 | 0.40 |
| EMA | PE | 11 | 27.30 | -6,987 | -635 | 0.20 |
| ORB | CE | 15 | 33.30 | -252 | -17 | 0.98 |
| ORB | PE | 20 | 50 | 12,125 | 606 | 2.11 |
| PIVOT | CE | 204 | 27 | -22,598 | -111 | 0.83 |
| PIVOT | PE | 208 | 24.50 | -3,367 | -16 | 0.97 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| PIVOT_SL_HIT | 233 | 0 | -229,698 | -986 | 0 | 22 |
| PIVOT_TSL_HIT | 81 | 96.30 | 170,045 | 2,099 | 165 | 58 |
| PIVOT_BE_STOP | 47 | 10.60 | -11,729 | -250 | 0.01 | 39 |
| STOP_HIT | 33 | 3 | -18,279 | -554 | 0.01 | 77 |
| EOD_SQUARE_OFF | 18 | 77.80 | 14,911 | 828 | 7.96 | 109 |
| IDX_SL_HIT | 14 | 0 | -21,096 | -1,507 | 0 | 25 |
| EMA_TSL_HIT | 9 | 100 | 4,263 | 474 | inf | 33 |
| PIVOT_TARGET_T3 | 9 | 100 | 42,475 | 4,719 | inf | 66 |
| IDX_TSL_HIT | 8 | 87.50 | 9,858 | 1,232 | 470 | 130 |
| EMA_SL_HIT | 8 | 0 | -10,433 | -1,304 | 0 | 14 |
| IDX_TARGET | 7 | 100 | 25,889 | 3,698 | inf | 63 |
| IDX_BE_STOP | 3 | 0 | -336 | -112 | 0 | 19 |
| EMA_TIME_STOP | 1 | 0 | -158 | -158 | 0 | 30 |
| EMA_COLLAPSE | 1 | 0 | -589 | -589 | 0 | 90 |


### Exit reason by strategy (trade count)

| exit_reason | EMA | ORB | PIVOT |
|---|---:|---:|---:|
| EMA_COLLAPSE | 1 | 0 | 0 |
| EMA_SL_HIT | 8 | 0 | 0 |
| EMA_TIME_STOP | 1 | 0 | 0 |
| EMA_TSL_HIT | 9 | 0 | 0 |
| EOD_SQUARE_OFF | 0 | 0 | 18 |
| IDX_BE_STOP | 0 | 3 | 0 |
| IDX_SL_HIT | 0 | 14 | 0 |
| IDX_TARGET | 0 | 7 | 0 |
| IDX_TSL_HIT | 0 | 8 | 0 |
| PIVOT_BE_STOP | 0 | 0 | 47 |
| PIVOT_SL_HIT | 0 | 0 | 233 |
| PIVOT_TARGET_T3 | 0 | 0 | 9 |
| PIVOT_TSL_HIT | 0 | 0 | 81 |
| STOP_HIT | 6 | 3 | 24 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| INITIAL | 287 | 2.80 | -277,367 | -966 | 0.01 |
| BE | 75 | 21.30 | 23,446 | 313 | 2.70 |
| T1 | 74 | 95.90 | 137,651 | 1,860 | 134 |
| TRAIL | 24 | 95.80 | 37,941 | 1,581 | 1,805 |
| T2 | 12 | 100 | 53,453 | 4,454 | inf |


- Trades whose stop moved at least once: 185 of 472 (39%); average 2.1 moves per trade.

- Full initial-stop losses: 287 (61%).

- Of the 237 trades that reached +1R, the exit kept on average 23% of the best index move (median 36%); 46% of them still closed at a net loss.

- Median best move (MFE) 1.02R; 50% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 251 | 21.10 | -47,957 | -191 | 0.73 |
| H2 | 221 | 34.80 | 23,080 | 104 | 1.19 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2024 | 182 | 19.20 | -63,613 | -350 | 0.53 |
| 2025 | 177 | 26 | -6,899 | -39 | 0.93 |
| 2026 | 113 | 43.40 | 45,636 | 404 | 1.75 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2024-01 | 8 | 12.50 | -2,192 | -274 | 0.51 | -2,192 |
| 2024-02 | 14 | 28.60 | -2,315 | -165 | 0.70 | -4,507 |
| 2024-03 | 13 | 7.70 | -8,666 | -667 | 0.20 | -13,173 |
| 2024-04 | 12 | 25 | 1,876 | 156 | 1.30 | -11,297 |
| 2024-05 | 19 | 10.50 | -17,112 | -901 | 0.12 | -28,409 |
| 2024-06 | 12 | 16.70 | -8,433 | -703 | 0.15 | -36,842 |
| 2024-07 | 15 | 13.30 | -7,969 | -531 | 0.31 | -44,811 |
| 2024-08 | 13 | 0 | -8,290 | -638 | 0 | -53,101 |
| 2024-09 | 19 | 31.60 | -3,495 | -184 | 0.67 | -56,596 |
| 2024-10 | 23 | 17.40 | -8,093 | -352 | 0.60 | -64,689 |
| 2024-11 | 15 | 40 | 10,047 | 670 | 2 | -54,642 |
| 2024-12 | 19 | 21.10 | -8,972 | -472 | 0.41 | -63,614 |
| 2025-01 | 14 | 28.60 | 5,835 | 417 | 1.80 | -57,779 |
| 2025-02 | 16 | 37.50 | 4,045 | 253 | 1.43 | -53,734 |
| 2025-03 | 10 | 40 | 4,658 | 466 | 2.23 | -49,076 |
| 2025-04 | 12 | 8.30 | 3,768 | 314 | 1.45 | -45,308 |
| 2025-05 | 17 | 17.60 | -2,650 | -156 | 0.79 | -47,958 |
| 2025-06 | 13 | 38.50 | -2,988 | -230 | 0.53 | -50,946 |
| 2025-07 | 20 | 25 | -6,901 | -345 | 0.34 | -57,847 |
| 2025-08 | 25 | 16 | -8,511 | -340 | 0.55 | -66,358 |
| 2025-09 | 16 | 37.50 | 2,107 | 132 | 1.28 | -64,251 |
| 2025-10 | 10 | 40 | 615 | 61 | 1.14 | -63,636 |
| 2025-11 | 17 | 17.60 | -3,586 | -211 | 0.55 | -67,222 |
| 2025-12 | 7 | 14.30 | -3,292 | -470 | 0.02 | -70,514 |
| 2026-01 | 10 | 50 | 7,485 | 748 | 2.59 | -63,029 |
| 2026-02 | 21 | 33.30 | -361 | -17 | 0.98 | -63,390 |
| 2026-03 | 6 | 66.70 | 16,766 | 2,794 | 12.62 | -46,624 |
| 2026-04 | 11 | 54.50 | 12,313 | 1,119 | 3.25 | -34,311 |
| 2026-05 | 10 | 20 | -8,591 | -859 | 0.15 | -42,902 |
| 2026-06 | 15 | 40 | 4,805 | 320 | 1.54 | -38,097 |
| 2026-07 | 10 | 40 | 706 | 71 | 1.13 | -37,391 |
| 2026-08 | 15 | 40 | -1,097 | -73 | 0.81 | -38,488 |
| 2026-09 | 8 | 62.50 | 5,129 | 641 | 3 | -33,359 |
| 2026-10 | 7 | 57.10 | 8,481 | 1,212 | 5.73 | -24,878 |


44% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 118 | 32.20 | 17,295 | 147 | 1.21 |
| 10:00 | 95 | 25.30 | -12,026 | -127 | 0.78 |
| 11:00 | 79 | 25.30 | -19,513 | -247 | 0.64 |
| 12:00 | 65 | 30.80 | 10,410 | 160 | 1.30 |
| 13:00 | 63 | 28.60 | 4,435 | 70 | 1.12 |
| 14:00 | 52 | 19.20 | -25,478 | -490 | 0.23 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Mon | 81 | 27.20 | -8,300 | -102 | 0.85 |
| Tue | 113 | 29.20 | 11,065 | 98 | 1.17 |
| Wed | 103 | 29.10 | -10,653 | -103 | 0.83 |
| Thu | 94 | 29.80 | 11,331 | 121 | 1.21 |
| Fri | 80 | 21.20 | -26,454 | -331 | 0.53 |
| Sat | 1 | 0 | -1,866 | -1,866 | 0 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 379 | 27.20 | -52,489 | -138 | 0.78 |
| yes | 93 | 29 | 27,612 | 297 | 1.51 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| CE | 516 |
| PE | 442 |
| PE_PIVOT | 242 |
| CE_PIVOT | 240 |
| PE_ORB | 127 |
| CE_ORB | 94 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| SMART_ENTRY_BLOCKED_EMA_GAP_SHRINKING: EMA gap not widening | 281 |
| SMART_ENTRY_BLOCKED_BODY | 218 |
| TREND_GATE_BLOCKED: against daily trend (UP) | 217 |
| TREND_GATE_BLOCKED: against daily trend (DOWN) | 178 |
| EMA_ENTRY_BLOCKED: room # < #R (#) | 88 |
| ENTRY_BLOCKED_MAX_RISK | 72 |
| SMART_ENTRY_BLOCKED_EMA_GAP | 16 |
| EMA_ENTRY_BLOCKED: option premium # <= option #m EMA# # | 15 |
| EMA_ENTRY_BLOCKED: risk # > max # | 5 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not falling for PE | 5 |
| GLOBAL_SIDE_CAP_BLOCKED: global PE cap reached (#/# trades today) | 1 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not rising for CE | 1 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2025-04-08 12:00:00 | PIVOT | CE | 103 | 712 | PIVOT_TARGET_T3 | BE | 12,080 |
| 2025-01-21 09:45:00 | PIVOT | PE | 133 | 655 | PIVOT_TARGET_T3 | T2 | 10,332 |
| 2025-05-13 11:55:00 | PIVOT | PE | 120 | 496 | PIVOT_TSL_HIT | T1 | 7,409 |
| 2026-03-16 13:55:00 | PIVOT | CE | 596 | 956 | PIVOT_TSL_HIT | T2 | 7,068 |
| 2025-03-03 09:35:00 | PIVOT | PE | 215 | 480 | PIVOT_TSL_HIT | T2 | 5,199 |
| 2024-04-12 09:35:00 | PIVOT | PE | 74.10 | 336 | PIVOT_TARGET_T3 | T2 | 5,153 |
| 2026-03-25 09:30:00 | ORB | CE | 188 | 448 | IDX_TARGET | TRAIL | 5,102 |
| 2026-10-14 12:50:00 | PIVOT | PE | 242 | 501 | PIVOT_TSL_HIT | T1 | 5,086 |
| 2024-11-13 12:10:00 | PIVOT | PE | 234 | 487 | PIVOT_TARGET_T3 | BE | 4,970 |
| 2026-04-06 11:30:00 | PIVOT | CE | 724 | 974 | PIVOT_TSL_HIT | T1 | 4,883 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2024-12-23 09:50:00 | PIVOT | CE | 525 | 398 | PIVOT_SL_HIT | INITIAL | -2,658 |
| 2024-11-06 09:50:00 | PIVOT | CE | 407 | 282 | PIVOT_SL_HIT | INITIAL | -2,610 |
| 2024-11-28 09:55:00 | PIVOT | CE | 270 | 151 | PIVOT_SL_HIT | INITIAL | -2,477 |
| 2024-12-04 10:35:00 | PIVOT | CE | 370 | 260 | PIVOT_SL_HIT | INITIAL | -2,291 |
| 2026-06-24 09:50:00 | PIVOT | PE | 233 | 127 | PIVOT_SL_HIT | INITIAL | -2,226 |
| 2024-05-31 09:35:00 | ORB | CE | 199 | 93.40 | IDX_SL_HIT | INITIAL | -2,203 |
| 2024-10-28 12:10:00 | PIVOT | CE | 475 | 371 | PIVOT_SL_HIT | INITIAL | -2,182 |
| 2025-04-29 09:35:00 | ORB | CE | 146 | 43.70 | IDX_SL_HIT | INITIAL | -2,146 |
| 2024-06-20 09:40:00 | ORB | PE | 260 | 162 | IDX_SL_HIT | INITIAL | -2,045 |
| 2026-02-20 13:10:00 | PIVOT | PE | 575 | 480 | PIVOT_SL_HIT | INITIAL | -2,006 |


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
| NO_NEW_ENTRY_AFTER | 15:00 |
| MAX_TRADES_PER_SIDE | 3 |
| ENABLE_DAILY_LOSS_LIMIT | yes |
| DAILY_LOSS_LIMIT_RUPEES | 5,000 |
| MAX_RISK_RUPEES_PER_TRADE | 2,000 |
| TREND_GATE_15M | yes |
| TREND_GATE_DAILY | yes |
| TREND_GATE_STRATEGIES | frozenset({'EMA', 'NATR', 'VWAP', 'TRB'}) |
| GENERIC_INDEX_EXITS | yes |
| PIVOT_BE_TRIGGER_R | 1.50 |
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
