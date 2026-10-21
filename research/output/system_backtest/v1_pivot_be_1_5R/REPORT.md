# Full-system backtest: 2024-01-15 to 2026-10-16

Run label `v1_pivot_be_1_5R`, 683 trading sessions, generated 2026-10-20 20:30.  Overrides: {'PIVOT_BE_TRIGGER_R': '1.5'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 325 |
| Win % | 27.70 |
| Net P&L (Rs) | -31,894 |
| Gross P&L (Rs) | 851 |
| Costs (Rs) | 32,745 |
|   of which charges (Rs) | 19,745 |
|   of which slippage (Rs) | 13,000 |
| Avg cost per trade (Rs) | 101 |
| Profit factor | 0.85 |
| Avg trade (Rs) | -98 |
| Avg win (Rs) | 2,078 |
| Avg loss (Rs) | -932 |
| Largest win (Rs) | 10,514 |
| Largest loss (Rs) | -2,988 |
| Max drawdown (Rs) | -63,354 |
| Longest losing streak | 31 |
| Avg hold (min) | 46.20 |


Trades on 232 of 683 sessions; 37% of trading days were green.  Average 10.0 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| EMA | CE | 14 | 42.90 | -4,812 | -344 | 0.35 |
| EMA | PE | 11 | 27.30 | -8,399 | -764 | 0.15 |
| ORB | CE | 8 | 62.50 | 173 | 22 | 1.03 |
| ORB | PE | 13 | 46.20 | 4,895 | 377 | 1.46 |
| PIVOT | CE | 144 | 25 | -24,894 | -173 | 0.76 |
| PIVOT | PE | 135 | 25.20 | 1,143 | 8 | 1.01 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| PIVOT_SL_HIT | 156 | 0 | -165,557 | -1,061 | 0 | 23 |
| PIVOT_TSL_HIT | 60 | 96.70 | 119,957 | 1,999 | 577 | 62 |
| STOP_HIT | 39 | 10.30 | -19,409 | -498 | 0.08 | 88 |
| PIVOT_BE_STOP | 18 | 0 | -4,530 | -252 | 0 | 31 |
| EMA_SL_HIT | 9 | 0 | -12,455 | -1,384 | 0 | 13 |
| PIVOT_TARGET_T3 | 9 | 100 | 33,722 | 3,747 | inf | 77 |
| IDX_TSL_HIT | 8 | 100 | 11,849 | 1,481 | inf | 122 |
| EOD_SQUARE_OFF | 7 | 42.90 | 5,371 | 767 | 3.74 | 161 |
| EMA_TSL_HIT | 6 | 100 | 2,686 | 448 | inf | 25 |
| IDX_SL_HIT | 6 | 0 | -10,390 | -1,732 | 0 | 51 |
| EMA_TIME_STOP | 3 | 0 | -1,126 | -375 | 0 | 30 |
| EMA_COLLAPSE | 2 | 0 | -1,684 | -842 | 0 | 78 |
| IDX_TARGET | 2 | 100 | 9,672 | 4,836 | inf | 33 |


### Exit reason by strategy (trade count)

| exit_reason | EMA | ORB | PIVOT |
|---|---:|---:|---:|
| EMA_COLLAPSE | 2 | 0 | 0 |
| EMA_SL_HIT | 9 | 0 | 0 |
| EMA_TIME_STOP | 3 | 0 | 0 |
| EMA_TSL_HIT | 6 | 0 | 0 |
| EOD_SQUARE_OFF | 0 | 0 | 7 |
| IDX_SL_HIT | 0 | 6 | 0 |
| IDX_TARGET | 0 | 2 | 0 |
| IDX_TSL_HIT | 0 | 8 | 0 |
| PIVOT_BE_STOP | 0 | 0 | 18 |
| PIVOT_SL_HIT | 0 | 0 | 156 |
| PIVOT_TARGET_T3 | 0 | 0 | 9 |
| PIVOT_TSL_HIT | 0 | 0 | 60 |
| STOP_HIT | 5 | 5 | 29 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| INITIAL | 194 | 1 | -208,760 | -1,076 | 0.01 |
| T1 | 54 | 96.30 | 95,600 | 1,770 | 460 |
| BE | 49 | 16.30 | 19,166 | 391 | 3.52 |
| TRAIL | 20 | 100 | 25,826 | 1,291 | inf |
| T2 | 8 | 100 | 36,274 | 4,534 | inf |


- Trades whose stop moved at least once: 131 of 325 (40%); average 2.4 moves per trade.

- Full initial-stop losses: 194 (60%).

- Of the 171 trades that reached +1R, the exit kept on average 26% of the best index move (median 44%); 47% of them still closed at a net loss.

- Median best move (MFE) 1.09R; 53% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 171 | 21.10 | -31,393 | -184 | 0.75 |
| H2 | 154 | 35.10 | -501 | -3 | 0.99 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2024 | 128 | 18.80 | -51,440 | -402 | 0.50 |
| 2025 | 118 | 23.70 | -12,407 | -105 | 0.83 |
| 2026 | 79 | 48.10 | 31,953 | 404 | 1.74 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2024-01 | 7 | 0 | -4,318 | -617 | 0 | -4,318 |
| 2024-02 | 10 | 30 | 620 | 62 | 1.16 | -3,698 |
| 2024-03 | 11 | 9.10 | -9,052 | -823 | 0.13 | -12,750 |
| 2024-04 | 4 | 25 | -1,947 | -487 | 0.25 | -14,697 |
| 2024-05 | 9 | 0 | -8,969 | -997 | 0 | -23,666 |
| 2024-06 | 9 | 0 | -9,032 | -1,004 | 0 | -32,698 |
| 2024-07 | 13 | 7.70 | -9,591 | -738 | 0.13 | -42,289 |
| 2024-08 | 9 | 0 | -5,948 | -661 | 0 | -48,237 |
| 2024-09 | 13 | 38.50 | -69 | -5 | 0.99 | -48,306 |
| 2024-10 | 21 | 19 | -11,489 | -547 | 0.45 | -59,795 |
| 2024-11 | 9 | 55.60 | 10,637 | 1,182 | 2.43 | -49,158 |
| 2024-12 | 13 | 30.80 | -2,282 | -176 | 0.80 | -51,440 |
| 2025-01 | 5 | 40 | 7,237 | 1,447 | 5.09 | -44,203 |
| 2025-02 | 13 | 38.50 | 1,467 | 113 | 1.21 | -42,736 |
| 2025-03 | 8 | 25 | 3,985 | 498 | 2.05 | -38,751 |
| 2025-04 | 9 | 11.10 | 5,612 | 624 | 2.15 | -33,139 |
| 2025-05 | 8 | 25 | 1,745 | 218 | 1.29 | -31,394 |
| 2025-06 | 10 | 30 | -3,882 | -388 | 0.34 | -35,276 |
| 2025-07 | 13 | 15.40 | -6,732 | -518 | 0.27 | -42,008 |
| 2025-08 | 18 | 16.70 | -10,411 | -578 | 0.33 | -52,419 |
| 2025-09 | 10 | 10 | -6,159 | -616 | 0.09 | -58,578 |
| 2025-10 | 6 | 50 | -1,369 | -228 | 0.64 | -59,947 |
| 2025-11 | 12 | 16.70 | -2,569 | -214 | 0.52 | -62,516 |
| 2025-12 | 6 | 33.30 | -1,333 | -222 | 0.54 | -63,849 |
| 2026-01 | 7 | 85.70 | 10,130 | 1,447 | 7.18 | -53,719 |
| 2026-02 | 15 | 33.30 | -1,210 | -81 | 0.89 | -54,929 |
| 2026-03 | 5 | 60 | 9,764 | 1,953 | 4.78 | -45,165 |
| 2026-04 | 6 | 83.30 | 11,141 | 1,857 | 10.64 | -34,024 |
| 2026-05 | 9 | 22.20 | -9,408 | -1,045 | 0.09 | -43,432 |
| 2026-06 | 10 | 40 | 1,503 | 150 | 1.29 | -41,929 |
| 2026-07 | 7 | 42.90 | -1,101 | -157 | 0.71 | -43,030 |
| 2026-08 | 8 | 37.50 | 522 | 65 | 1.22 | -42,508 |
| 2026-09 | 7 | 57.10 | 3,581 | 512 | 2.29 | -38,927 |
| 2026-10 | 5 | 60 | 7,032 | 1,406 | 3.93 | -31,895 |


41% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 66 | 33.30 | -156 | -2 | 1 |
| 10:00 | 81 | 27.20 | -14,733 | -182 | 0.70 |
| 11:00 | 67 | 25.40 | -23,855 | -356 | 0.53 |
| 12:00 | 58 | 24.10 | 49 | 1 | 1 |
| 13:00 | 53 | 28.30 | 6,801 | 128 | 1.22 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Mon | 63 | 27 | -8,393 | -133 | 0.82 |
| Tue | 95 | 30.50 | 5,670 | 60 | 1.10 |
| Wed | 81 | 19.80 | -26,927 | -332 | 0.54 |
| Thu | 78 | 30.80 | -6,150 | -79 | 0.88 |
| Fri | 7 | 57.10 | 5,801 | 829 | 3.06 |
| Sat | 1 | 0 | -1,894 | -1,894 | 0 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 270 | 25.20 | -56,328 | -209 | 0.70 |
| yes | 55 | 40 | 24,434 | 444 | 1.79 |


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
| ENTRY_BLOCKED_MAX_RISK | 90 |
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
| 2026-03-16 13:55:00 | PIVOT | CE | 675 | 1,025 | PIVOT_TSL_HIT | T2 | 6,894 |
| 2024-12-13 09:30:00 | ORB | PE | 185 | 522 | IDX_TARGET | TRAIL | 6,637 |
| 2025-05-13 11:55:00 | PIVOT | PE | 214 | 500 | PIVOT_TSL_HIT | T1 | 5,619 |
| 2025-03-03 09:35:00 | PIVOT | PE | 274 | 524 | PIVOT_TSL_HIT | T2 | 4,904 |
| 2026-10-14 12:50:00 | PIVOT | PE | 282 | 531 | PIVOT_TSL_HIT | T1 | 4,870 |
| 2026-04-06 11:30:00 | PIVOT | CE | 837 | 1,070 | PIVOT_TSL_HIT | T1 | 4,541 |
| 2024-11-13 12:10:00 | PIVOT | PE | 285 | 515 | PIVOT_TARGET_T3 | BE | 4,500 |
| 2024-11-07 09:35:00 | PIVOT | PE | 338 | 563 | PIVOT_TSL_HIT | T1 | 4,394 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2024-12-23 09:50:00 | PIVOT | CE | 594 | 450 | PIVOT_SL_HIT | INITIAL | -2,988 |
| 2024-11-06 09:50:00 | PIVOT | CE | 488 | 356 | PIVOT_SL_HIT | INITIAL | -2,743 |
| 2024-11-28 09:55:00 | PIVOT | CE | 346 | 216 | PIVOT_SL_HIT | INITIAL | -2,707 |
| 2024-12-04 10:35:00 | PIVOT | CE | 442 | 321 | PIVOT_SL_HIT | INITIAL | -2,519 |
| 2024-10-28 12:10:00 | PIVOT | CE | 543 | 427 | PIVOT_SL_HIT | INITIAL | -2,423 |
| 2026-05-14 12:20:00 | PIVOT | CE | 204 | 88.25 | STOP_HIT | INITIAL | -2,397 |
| 2026-06-24 09:50:00 | PIVOT | PE | 293 | 180 | PIVOT_SL_HIT | INITIAL | -2,359 |
| 2024-10-08 10:40:00 | PIVOT | CE | 539 | 428 | PIVOT_SL_HIT | INITIAL | -2,318 |
| 2025-07-08 09:30:00 | ORB | CE | 197 | 86.75 | STOP_HIT | INITIAL | -2,288 |
| 2024-06-20 09:40:00 | ORB | PE | 321 | 214 | IDX_SL_HIT | INITIAL | -2,240 |


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
| TREND_GATE_STRATEGIES | frozenset({'EMA', 'NATR', 'TRB', 'VWAP'}) |
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
- **Options are modelled, not historical.** Black-Scholes in trading time (weeknight = 176 min, weekend = 609 min), IV = India VIX (minute), r = 6.5%.  Strike selection, ITM fallback and expiry-day rollover use the bot's own selector on a synthetic chain; weekly expiry calendar [['2000-01-01', 4], ['2025-01-01', 1], ['2025-09-01', 3]] (weekday 0 = Monday), moved to the previous session on holidays.  The model has no volatility smile, no intraday IV crush beyond VIX moves, and VIX (30-day, NIFTY) is a proxy for weekly SENSEX IV — expect real premiums, especially on expiry days, to differ.
- **Fills and costs.** SHADOW-mode paper fills at the modelled premium, then 1.0 option point(s) of slippage per side plus brokerage, STT, exchange, SEBI, stamp duty and GST are deducted per trade.  Quantity is today's lot (20) throughout.
- **Not modelled:** order rejections, partial fills, feed outages, margin limits.


Files: `trades.csv` (one row per trade, with exit reason, stop stage, MFE/MAE and costs), `events.csv` (signals, blocks, stop moves), `run_meta.json` (full settings snapshot).  Re-run: `python -m research.system_backtest`.
