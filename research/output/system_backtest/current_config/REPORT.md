# Full-system backtest: 2024-01-15 to 2026-10-16

Run label `current_config`, 683 trading sessions, generated 2026-10-20 20:32.  Overrides: none (current .env).

## Headline

| Metric | Value |
|---|---:|
| Trades | 326 |
| Win % | 22.40 |
| Net P&L (Rs) | -28,574 |
| Gross P&L (Rs) | 4,274 |
| Costs (Rs) | 32,848 |
|   of which charges (Rs) | 19,808 |
|   of which slippage (Rs) | 13,040 |
| Avg cost per trade (Rs) | 101 |
| Profit factor | 0.83 |
| Avg trade (Rs) | -88 |
| Avg win (Rs) | 1,919 |
| Avg loss (Rs) | -667 |
| Largest win (Rs) | 10,514 |
| Largest loss (Rs) | -2,743 |
| Max drawdown (Rs) | -51,838 |
| Longest losing streak | 31 |
| Avg hold (min) | 34.60 |


Trades on 232 of 683 sessions; 30% of trading days were green.  Average 10.0 trades a month.


![equity](equity.svg)


## Variant comparison

Every variant is the same full-system run (same data, costs and model) with one change.  Changes marked * are backtest-only entry filters — the bot has no setting for them yet.  `H1`/`H2` split the period in half; a real edge should be positive in both.


| Variant | Change |
|---|---|
| current_config | current .env |
| v1_pivot_be_1_5R | PIVOT_BE_TRIGGER_R=1.5 |
| v2_no_midday_no_late | NO_NEW_ENTRY_AFTER=14:00; no entries 11:00-12:00* |
| v3_orb_only | ENABLE_PIVOT_STRATEGY=false; ENABLE_EMA_STRATEGY=false |
| v4_pivot_pe_only | ENABLE_ORB_STRATEGY=false; ENABLE_EMA_STRATEGY=false; skip CE_PIVOT* |



| Variant | Trades | Trades/mo | Win % | Net Rs | PF | Avg Rs | Max DD Rs | Loss streak | H1 Rs | H2 Rs | Green months % | 2024 Rs | 2025 Rs | 2026 Rs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_config | 326 | 10 | 22.40 | -28,574 | 0.83 | -88 | -51,838 | 31 | -23,243 | -5,331 | 38 | -35,428 | -15,962 | 22,816 |
| v1_pivot_be_1_5R | 325 | 10 | 27.70 | -31,894 | 0.85 | -98 | -63,354 | 31 | -31,393 | -501 | 41 | -51,440 | -12,407 | 31,953 |
| v2_no_midday_no_late | 265 | 8.10 | 23 | -5,876 | 0.95 | -22 | -28,402 | 26 | -971 | -4,904 | 47 | -17,581 | -5,864 | 17,570 |
| v3_orb_only | 21 | 0.60 | 52.40 | 5,068 | 1.31 | 241 | -5,553 | 3 | 6,611 | -1,543 | 54 | 5,466 | 24 | -423 |
| v4_pivot_pe_only | 141 | 4.30 | 21.30 | -715 | 0.99 | -5 | -24,798 | 24 | -5,218 | 4,503 | 42 | -10,271 | -8,357 | 17,913 |


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| EMA | CE | 14 | 42.90 | -4,812 | -344 | 0.35 |
| EMA | PE | 11 | 27.30 | -8,399 | -764 | 0.15 |
| ORB | CE | 8 | 62.50 | 173 | 22 | 1.03 |
| ORB | PE | 13 | 46.20 | 4,895 | 377 | 1.46 |
| PIVOT | CE | 144 | 16.70 | -19,842 | -138 | 0.72 |
| PIVOT | PE | 136 | 21.30 | -589 | -4 | 0.99 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| PIVOT_SL_HIT | 111 | 0 | -112,516 | -1,014 | 0 | 14 |
| PIVOT_BE_STOP | 87 | 4.60 | -16,093 | -185 | 0 | 19 |
| PIVOT_TSL_HIT | 43 | 95.30 | 82,104 | 1,909 | 395 | 57 |
| STOP_HIT | 40 | 10 | -11,380 | -284 | 0.12 | 73 |
| EMA_SL_HIT | 9 | 0 | -12,455 | -1,384 | 0 | 13 |
| IDX_TSL_HIT | 8 | 100 | 11,849 | 1,481 | inf | 122 |
| IDX_SL_HIT | 6 | 0 | -10,390 | -1,732 | 0 | 51 |
| PIVOT_TARGET_T3 | 6 | 100 | 26,264 | 4,377 | inf | 52 |
| EMA_TSL_HIT | 6 | 100 | 2,686 | 448 | inf | 25 |
| EMA_TIME_STOP | 3 | 0 | -1,126 | -375 | 0 | 30 |
| EOD_SQUARE_OFF | 3 | 66.70 | 4,495 | 1,498 | 5.04 | 182 |
| EMA_COLLAPSE | 2 | 0 | -1,684 | -842 | 0 | 78 |
| IDX_TARGET | 2 | 100 | 9,672 | 4,836 | inf | 33 |


### Exit reason by strategy (trade count)

| exit_reason | EMA | ORB | PIVOT |
|---|---:|---:|---:|
| EMA_COLLAPSE | 2 | 0 | 0 |
| EMA_SL_HIT | 9 | 0 | 0 |
| EMA_TIME_STOP | 3 | 0 | 0 |
| EMA_TSL_HIT | 6 | 0 | 0 |
| EOD_SQUARE_OFF | 0 | 0 | 3 |
| IDX_SL_HIT | 0 | 6 | 0 |
| IDX_TARGET | 0 | 2 | 0 |
| IDX_TSL_HIT | 0 | 8 | 0 |
| PIVOT_BE_STOP | 0 | 0 | 87 |
| PIVOT_SL_HIT | 0 | 0 | 111 |
| PIVOT_TARGET_T3 | 0 | 0 | 6 |
| PIVOT_TSL_HIT | 0 | 0 | 43 |
| STOP_HIT | 5 | 5 | 30 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| INITIAL | 138 | 0 | -148,657 | -1,077 | 0 |
| BE | 123 | 8.10 | 234 | 2 | 1.01 |
| T1 | 40 | 95 | 72,369 | 1,809 | 349 |
| TRAIL | 20 | 100 | 25,826 | 1,291 | inf |
| T2 | 5 | 100 | 21,654 | 4,331 | inf |


- Trades whose stop moved at least once: 188 of 326 (58%); average 2.2 moves per trade.

- Full initial-stop losses: 138 (42%).

- Of the 143 trades that reached +1R, the exit kept on average 41% of the best index move (median 40%); 50% of them still closed at a net loss.

- Median best move (MFE) 0.90R; 44% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 171 | 18.10 | -23,243 | -136 | 0.75 |
| H2 | 155 | 27.10 | -5,331 | -34 | 0.93 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2024 | 128 | 16.40 | -35,428 | -277 | 0.51 |
| 2025 | 118 | 19.50 | -15,962 | -135 | 0.74 |
| 2026 | 80 | 36.20 | 22,816 | 285 | 1.66 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2024-01 | 7 | 0 | -3,137 | -448 | 0 | -3,137 |
| 2024-02 | 10 | 40 | 3,025 | 303 | 2.90 | -112 |
| 2024-03 | 11 | 18.20 | -6,335 | -576 | 0.18 | -6,447 |
| 2024-04 | 4 | 25 | -1,947 | -487 | 0.25 | -8,394 |
| 2024-05 | 9 | 0 | -6,033 | -670 | 0 | -14,427 |
| 2024-06 | 9 | 0 | -6,894 | -766 | 0 | -21,321 |
| 2024-07 | 13 | 7.70 | -7,310 | -562 | 0.16 | -28,631 |
| 2024-08 | 9 | 0 | -2,950 | -328 | 0 | -31,581 |
| 2024-09 | 13 | 30.80 | -753 | -58 | 0.87 | -32,334 |
| 2024-10 | 21 | 9.50 | -9,854 | -469 | 0.29 | -42,188 |
| 2024-11 | 9 | 33.30 | 6,320 | 702 | 2.17 | -35,868 |
| 2024-12 | 13 | 30.80 | 439 | 34 | 1.05 | -35,429 |
| 2025-01 | 5 | 40 | 7,237 | 1,447 | 5.09 | -28,192 |
| 2025-02 | 13 | 30.80 | 485 | 37 | 1.07 | -27,707 |
| 2025-03 | 8 | 12.50 | 2,186 | 273 | 1.80 | -25,521 |
| 2025-04 | 9 | 22.20 | 6,402 | 711 | 2.56 | -19,119 |
| 2025-05 | 8 | 12.50 | -4,125 | -516 | 0.35 | -23,244 |
| 2025-06 | 10 | 20 | -4,870 | -487 | 0.17 | -28,114 |
| 2025-07 | 13 | 15.40 | -5,609 | -431 | 0.30 | -33,723 |
| 2025-08 | 18 | 11.10 | -9,652 | -536 | 0.24 | -43,375 |
| 2025-09 | 10 | 10 | -4,562 | -456 | 0.12 | -47,937 |
| 2025-10 | 6 | 50 | -786 | -131 | 0.71 | -48,723 |
| 2025-11 | 12 | 8.30 | -1,894 | -158 | 0.32 | -50,617 |
| 2025-12 | 6 | 33.30 | -774 | -129 | 0.67 | -51,391 |
| 2026-01 | 8 | 50 | 7,944 | 993 | 11.82 | -43,447 |
| 2026-02 | 15 | 26.70 | -2,430 | -162 | 0.73 | -45,877 |
| 2026-03 | 5 | 20 | -105 | -21 | 0.97 | -45,982 |
| 2026-04 | 6 | 83.30 | 11,141 | 1,857 | 10.64 | -34,841 |
| 2026-05 | 9 | 11.10 | -4,966 | -552 | 0.04 | -39,807 |
| 2026-06 | 10 | 40 | 2,174 | 217 | 1.48 | -37,633 |
| 2026-07 | 7 | 14.30 | -2,127 | -304 | 0.49 | -39,760 |
| 2026-08 | 8 | 37.50 | 1,379 | 172 | 1.92 | -38,381 |
| 2026-09 | 7 | 42.90 | 2,772 | 396 | 2.32 | -35,609 |
| 2026-10 | 5 | 60 | 7,032 | 1,406 | 3.93 | -28,577 |


38% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 66 | 31.80 | 6,419 | 97 | 1.15 |
| 10:00 | 81 | 21 | -17,678 | -218 | 0.52 |
| 11:00 | 67 | 19.40 | -23,400 | -349 | 0.43 |
| 12:00 | 58 | 20.70 | 4,704 | 81 | 1.19 |
| 13:00 | 54 | 18.50 | 1,381 | 26 | 1.06 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Mon | 63 | 20.60 | -6,201 | -98 | 0.80 |
| Tue | 95 | 28.40 | 10,266 | 108 | 1.24 |
| Wed | 82 | 15.90 | -25,902 | -316 | 0.46 |
| Thu | 78 | 20.50 | -10,644 | -136 | 0.75 |
| Fri | 7 | 57.10 | 5,801 | 829 | 3.06 |
| Sat | 1 | 0 | -1,894 | -1,894 | 0 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 271 | 22.10 | -38,651 | -143 | 0.72 |
| yes | 55 | 23.60 | 10,077 | 183 | 1.35 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| CE | 517 |
| PE | 442 |
| CE_PIVOT | 157 |
| PE_PIVOT | 143 |
| PE_ORB | 127 |
| CE_ORB | 94 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| PIVOT_BLOCKED_FRIDAY | 9,735 |
| PIVOT_BLOCKED_TIME | 9,495 |
| SMART_ENTRY_BLOCKED_EMA_GAP_SHRINKING: EMA gap not widening | 281 |
| SMART_ENTRY_BLOCKED_BODY | 218 |
| TREND_GATE_BLOCKED: against daily trend (UP) | 217 |
| TREND_GATE_BLOCKED: against daily trend (DOWN) | 179 |
| EMA_ENTRY_BLOCKED: room # < #R (#) | 95 |
| ENTRY_BLOCKED_MAX_RISK | 91 |
| SMART_ENTRY_BLOCKED_EMA_GAP | 16 |
| EMA_ENTRY_BLOCKED: option premium # <= option #m EMA# # | 7 |
| EMA_ENTRY_BLOCKED: risk # > max # | 6 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not falling for PE | 5 |
| GLOBAL_SIDE_CAP_BLOCKED: global PE cap reached (#/# trades today) | 1 |
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
| 2026-04-06 11:30:00 | PIVOT | CE | 837 | 1,070 | PIVOT_TSL_HIT | T1 | 4,541 |
| 2024-11-07 09:35:00 | PIVOT | PE | 338 | 563 | PIVOT_TSL_HIT | T1 | 4,394 |
| 2024-11-12 12:00:00 | PIVOT | PE | 391 | 616 | PIVOT_TSL_HIT | T1 | 4,389 |
| 2026-04-07 11:15:00 | PIVOT | CE | 680 | 898 | PIVOT_TSL_HIT | T1 | 4,238 |
| 2026-02-02 13:50:00 | PIVOT | CE | 508 | 695 | EOD_SQUARE_OFF | BE | 3,627 |


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
| 2024-09-12 11:10:00 | PIVOT | CE | 305 | 214 | PIVOT_SL_HIT | INITIAL | -1,912 |
| 2025-02-01 11:35:00 | PIVOT | CE | 512 | 423 | PIVOT_SL_HIT | INITIAL | -1,894 |


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
| TREND_GATE_STRATEGIES | frozenset({'VWAP', 'NATR', 'EMA', 'TRB'}) |
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
