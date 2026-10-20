# Full-system backtest: 2024-01-15 to 2026-10-16

Run label `v2_no_midday_no_late`, 683 trading sessions, generated 2026-10-20 02:19.  Overrides: {'NO_NEW_ENTRY_AFTER': '14:00'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 352 |
| Win % | 25 |
| Net P&L (Rs) | 9,296 |
| Gross P&L (Rs) | 44,298 |
| Costs (Rs) | 35,002 |
|   of which charges (Rs) | 20,922 |
|   of which slippage (Rs) | 14,080 |
| Avg cost per trade (Rs) | 99 |
| Profit factor | 1.06 |
| Avg trade (Rs) | 26 |
| Avg win (Rs) | 1,983 |
| Avg loss (Rs) | -626 |
| Largest win (Rs) | 12,080 |
| Largest loss (Rs) | -2,610 |
| Max drawdown (Rs) | -34,537 |
| Longest losing streak | 18 |
| Avg hold (min) | 31.60 |


Trades on 247 of 683 sessions; 31% of trading days were green.  Average 10.8 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| EMA | CE | 7 | 42.90 | -1,266 | -181 | 0.57 |
| EMA | PE | 1 | 0 | -1,742 | -1,742 | 0 |
| ORB | CE | 15 | 33.30 | -252 | -17 | 0.98 |
| ORB | PE | 20 | 50 | 12,125 | 606 | 2.11 |
| PIVOT | CE | 158 | 20.90 | -4,906 | -31 | 0.93 |
| PIVOT | PE | 151 | 24.50 | 5,338 | 35 | 1.08 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| PIVOT_BE_STOP | 121 | 12.40 | -20,834 | -172 | 0.02 | 23 |
| PIVOT_SL_HIT | 115 | 0 | -111,787 | -972 | 0 | 13 |
| PIVOT_TSL_HIT | 49 | 95.90 | 99,685 | 2,034 | 931 | 48 |
| STOP_HIT | 19 | 5.30 | -5,932 | -312 | 0.02 | 66 |
| IDX_SL_HIT | 14 | 0 | -21,096 | -1,507 | 0 | 25 |
| IDX_TSL_HIT | 8 | 87.50 | 9,858 | 1,232 | 470 | 130 |
| IDX_TARGET | 7 | 100 | 25,889 | 3,698 | inf | 63 |
| PIVOT_TARGET_T3 | 5 | 100 | 28,380 | 5,676 | inf | 60 |
| EOD_SQUARE_OFF | 4 | 75 | 7,877 | 1,969 | 16.03 | 200 |
| EMA_TSL_HIT | 3 | 100 | 1,675 | 558 | inf | 46 |
| IDX_BE_STOP | 3 | 0 | -336 | -112 | 0 | 19 |
| EMA_SL_HIT | 3 | 0 | -3,925 | -1,308 | 0 | 16 |
| EMA_TIME_STOP | 1 | 0 | -158 | -158 | 0 | 30 |


### Exit reason by strategy (trade count)

| exit_reason | EMA | ORB | PIVOT |
|---|---:|---:|---:|
| EMA_SL_HIT | 3 | 0 | 0 |
| EMA_TIME_STOP | 1 | 0 | 0 |
| EMA_TSL_HIT | 3 | 0 | 0 |
| EOD_SQUARE_OFF | 0 | 0 | 4 |
| IDX_BE_STOP | 0 | 3 | 0 |
| IDX_SL_HIT | 0 | 14 | 0 |
| IDX_TARGET | 0 | 7 | 0 |
| IDX_TSL_HIT | 0 | 8 | 0 |
| PIVOT_BE_STOP | 0 | 0 | 121 |
| PIVOT_SL_HIT | 0 | 0 | 115 |
| PIVOT_TARGET_T3 | 0 | 0 | 5 |
| PIVOT_TSL_HIT | 0 | 0 | 49 |
| STOP_HIT | 1 | 3 | 15 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| BE | 144 | 15.30 | 3,207 | 22 | 1.14 |
| INITIAL | 139 | 0 | -142,394 | -1,024 | 0 |
| T1 | 44 | 95.50 | 79,826 | 1,814 | 746 |
| TRAIL | 18 | 94.40 | 35,353 | 1,964 | 1,682 |
| T2 | 7 | 100 | 33,304 | 4,758 | inf |


- Trades whose stop moved at least once: 213 of 352 (61%); average 2.2 moves per trade.

- Full initial-stop losses: 139 (39%).

- Of the 165 trades that reached +1R, the exit kept on average 35% of the best index move (median 29%); 50% of them still closed at a net loss.

- Median best move (MFE) 0.95R; 47% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 194 | 22.70 | -8,494 | -44 | 0.91 |
| H2 | 158 | 27.80 | 17,790 | 113 | 1.26 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2024 | 141 | 19.90 | -28,079 | -199 | 0.62 |
| 2025 | 127 | 23.60 | 2,057 | 16 | 1.03 |
| 2026 | 84 | 35.70 | 35,318 | 420 | 2.12 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2024-01 | 7 | 14.30 | -255 | -36 | 0.90 | -255 |
| 2024-02 | 10 | 40 | -2,070 | -207 | 0.56 | -2,325 |
| 2024-03 | 9 | 22.20 | -2,198 | -244 | 0.50 | -4,523 |
| 2024-04 | 8 | 12.50 | -516 | -64 | 0.82 | -5,039 |
| 2024-05 | 12 | 8.30 | -8,304 | -692 | 0.21 | -13,343 |
| 2024-06 | 11 | 18.20 | -6,907 | -628 | 0 | -20,250 |
| 2024-07 | 13 | 7.70 | -5,767 | -444 | 0.22 | -26,017 |
| 2024-08 | 11 | 0 | -2,587 | -235 | 0 | -28,604 |
| 2024-09 | 13 | 38.50 | -386 | -30 | 0.93 | -28,990 |
| 2024-10 | 20 | 15 | -2,067 | -103 | 0.79 | -31,057 |
| 2024-11 | 14 | 28.60 | 5,269 | 376 | 1.67 | -25,788 |
| 2024-12 | 13 | 30.80 | -2,292 | -176 | 0.73 | -28,080 |
| 2025-01 | 12 | 33.30 | 6,866 | 572 | 2.31 | -21,214 |
| 2025-02 | 11 | 45.50 | 8,563 | 778 | 3.54 | -12,651 |
| 2025-03 | 7 | 28.60 | 4,374 | 625 | 5.07 | -8,277 |
| 2025-04 | 11 | 27.30 | 5,659 | 514 | 1.88 | -2,618 |
| 2025-05 | 12 | 16.70 | -5,877 | -490 | 0.29 | -8,495 |
| 2025-06 | 8 | 12.50 | -3,439 | -430 | 0.15 | -11,934 |
| 2025-07 | 13 | 23.10 | -4,470 | -344 | 0.38 | -16,404 |
| 2025-08 | 20 | 15 | -4,271 | -214 | 0.65 | -20,675 |
| 2025-09 | 11 | 9.10 | -4,070 | -370 | 0.16 | -24,745 |
| 2025-10 | 7 | 57.10 | 2,229 | 318 | 1.95 | -22,516 |
| 2025-11 | 12 | 16.70 | -2,154 | -180 | 0.43 | -24,670 |
| 2025-12 | 3 | 0 | -1,353 | -451 | 0 | -26,023 |
| 2026-01 | 9 | 44.40 | 7,790 | 866 | 5.84 | -18,233 |
| 2026-02 | 16 | 18.80 | -5,993 | -375 | 0.47 | -24,226 |
| 2026-03 | 4 | 75 | 15,042 | 3,761 | 18.96 | -9,184 |
| 2026-04 | 7 | 42.90 | 4,178 | 597 | 2.10 | -5,006 |
| 2026-05 | 7 | 14.30 | -3,337 | -477 | 0.07 | -8,343 |
| 2026-06 | 10 | 50 | 4,184 | 418 | 2.20 | -4,159 |
| 2026-07 | 9 | 11.10 | -17 | -2 | 0.99 | -4,176 |
| 2026-08 | 10 | 40 | 1,169 | 117 | 1.87 | -3,007 |
| 2026-09 | 6 | 50 | 3,598 | 600 | 3.63 | 591 |
| 2026-10 | 6 | 50 | 8,704 | 1,451 | 7.53 | 9,295 |


38% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 118 | 28 | 5,959 | 50 | 1.08 |
| 10:00 | 95 | 23.20 | -9,609 | -101 | 0.74 |
| 12:00 | 70 | 24.30 | 6,479 | 93 | 1.24 |
| 13:00 | 69 | 23.20 | 6,467 | 94 | 1.22 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Mon | 58 | 27.60 | -520 | -9 | 0.98 |
| Tue | 82 | 29.30 | 18,348 | 224 | 1.53 |
| Wed | 83 | 21.70 | -13,308 | -160 | 0.70 |
| Thu | 72 | 25 | 17,892 | 249 | 1.66 |
| Fri | 57 | 21.10 | -13,116 | -230 | 0.56 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 278 | 25.50 | -9,346 | -34 | 0.93 |
| yes | 74 | 23 | 18,642 | 252 | 1.52 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| CE | 516 |
| PE | 442 |
| PE_PIVOT | 253 |
| CE_PIVOT | 246 |
| PE_ORB | 127 |
| CE_ORB | 94 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| SMART_ENTRY_BLOCKED_EMA_GAP_SHRINKING: EMA gap not widening | 281 |
| SMART_ENTRY_BLOCKED_BODY | 218 |
| TREND_GATE_BLOCKED: against daily trend (UP) | 217 |
| TREND_GATE_BLOCKED: against daily trend (DOWN) | 178 |
| BACKTEST_FILTER_BLOCKED: entry window #:#-#:# blocked | 121 |
| ENTRY_BLOCKED_MAX_RISK | 70 |
| EMA_ENTRY_BLOCKED: room # < #R (#) | 53 |
| SMART_ENTRY_BLOCKED_EMA_GAP | 16 |
| EMA_ENTRY_BLOCKED: option premium # <= option #m EMA# # | 15 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not falling for PE | 5 |
| EMA_ENTRY_BLOCKED: risk # > max # | 3 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not rising for CE | 1 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2025-04-08 12:00:00 | PIVOT | CE | 103 | 712 | PIVOT_TARGET_T3 | BE | 12,080 |
| 2025-01-21 09:45:00 | PIVOT | PE | 133 | 655 | PIVOT_TARGET_T3 | T2 | 10,332 |
| 2026-03-16 13:55:00 | PIVOT | CE | 596 | 956 | PIVOT_TSL_HIT | T2 | 7,068 |
| 2025-03-03 09:35:00 | PIVOT | PE | 215 | 480 | PIVOT_TSL_HIT | T2 | 5,199 |
| 2026-03-25 09:30:00 | ORB | CE | 188 | 448 | IDX_TARGET | TRAIL | 5,102 |
| 2026-10-14 12:50:00 | PIVOT | PE | 242 | 501 | PIVOT_TSL_HIT | T1 | 5,086 |
| 2026-04-30 09:35:00 | ORB | PE | 155 | 397 | IDX_TARGET | TRAIL | 4,753 |
| 2024-11-07 09:35:00 | PIVOT | PE | 268 | 508 | PIVOT_TSL_HIT | T1 | 4,706 |
| 2024-11-12 12:00:00 | PIVOT | PE | 340 | 573 | PIVOT_TSL_HIT | T1 | 4,550 |
| 2025-02-13 09:30:00 | PIVOT | CE | 610 | 827 | PIVOT_TSL_HIT | T1 | 4,214 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2024-11-06 09:50:00 | PIVOT | CE | 407 | 282 | PIVOT_SL_HIT | INITIAL | -2,610 |
| 2024-12-04 10:35:00 | PIVOT | CE | 370 | 260 | PIVOT_SL_HIT | INITIAL | -2,291 |
| 2026-06-24 09:50:00 | PIVOT | PE | 233 | 127 | PIVOT_SL_HIT | INITIAL | -2,226 |
| 2024-05-31 09:35:00 | ORB | CE | 199 | 93.40 | IDX_SL_HIT | INITIAL | -2,203 |
| 2025-04-29 09:35:00 | ORB | CE | 146 | 43.70 | IDX_SL_HIT | INITIAL | -2,146 |
| 2024-06-20 09:40:00 | ORB | PE | 260 | 162 | IDX_SL_HIT | INITIAL | -2,045 |
| 2026-02-20 13:10:00 | PIVOT | PE | 575 | 480 | PIVOT_SL_HIT | INITIAL | -2,006 |
| 2024-05-24 09:30:00 | ORB | CE | 183 | 87.85 | IDX_SL_HIT | INITIAL | -1,989 |
| 2024-10-08 10:15:00 | PIVOT | PE | 454 | 368 | PIVOT_SL_HIT | INITIAL | -1,828 |
| 2026-02-20 12:25:00 | PIVOT | CE | 648 | 562 | PIVOT_SL_HIT | INITIAL | -1,824 |


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
- **Options are modelled, not historical.** Black-Scholes, IV = India VIX (minute), r = 6.5%.  Strike selection, ITM fallback and expiry-day rollover use the bot's own selector on a synthetic chain; weekly expiry calendar [['2000-01-01', 4], ['2025-01-01', 1], ['2025-09-01', 3]] (weekday 0 = Monday), moved to the previous session on holidays.  The model has no volatility smile, no intraday IV crush beyond VIX moves, and VIX (30-day, NIFTY) is a proxy for weekly SENSEX IV — expect real premiums, especially on expiry days, to differ.
- **Fills and costs.** SHADOW-mode paper fills at the modelled premium, then 1.0 option point(s) of slippage per side plus brokerage, STT, exchange, SEBI, stamp duty and GST are deducted per trade.  Quantity is today's lot (20) throughout.
- **Not modelled:** order rejections, partial fills, feed outages, margin limits.


Files: `trades.csv` (one row per trade, with exit reason, stop stage, MFE/MAE and costs), `events.csv` (signals, blocks, stop moves), `run_meta.json` (full settings snapshot).  Re-run: `python -m research.system_backtest`.
