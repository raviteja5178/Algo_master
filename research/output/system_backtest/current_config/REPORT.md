# Full-system backtest: 2024-01-15 to 2026-10-16

Run label `current_config`, 683 trading sessions, generated 2026-10-20 02:20.  Overrides: none (current .env).

## Headline

| Metric | Value |
|---|---:|
| Trades | 473 |
| Win % | 23.30 |
| Net P&L (Rs) | -32,194 |
| Gross P&L (Rs) | 14,860 |
| Costs (Rs) | 47,054 |
|   of which charges (Rs) | 28,134 |
|   of which slippage (Rs) | 18,920 |
| Avg cost per trade (Rs) | 99 |
| Profit factor | 0.86 |
| Avg trade (Rs) | -68 |
| Avg win (Rs) | 1,826 |
| Avg loss (Rs) | -642 |
| Largest win (Rs) | 12,080 |
| Largest loss (Rs) | -2,610 |
| Max drawdown (Rs) | -70,461 |
| Longest losing streak | 24 |
| Avg hold (min) | 29.50 |


Trades on 303 of 683 sessions; 29% of trading days were green.  Average 14.5 trades a month.


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
| current_config | 473 | 14.50 | 23.30 | -32,194 | 0.86 | -68 | -70,461 | 24 | -46,213 | 14,019 | 38 | -53,985 | -15,273 | 37,063 |
| v1_pivot_be_1_5R | 472 | 14.50 | 27.50 | -24,877 | 0.92 | -53 | -72,320 | 18 | -47,957 | 23,080 | 44 | -63,613 | -6,899 | 45,636 |
| v2_no_midday_no_late | 352 | 10.80 | 25 | 9,296 | 1.06 | 26 | -34,537 | 18 | -8,494 | 17,790 | 38 | -28,079 | 2,057 | 35,318 |
| v3_orb_only | 35 | 1.10 | 42.90 | 11,873 | 1.49 | 339 | -8,684 | 5 | -804 | 12,677 | 45 | 1,371 | -1,909 | 12,411 |
| v4_pivot_pe_only | 224 | 6.90 | 21.40 | -20,962 | 0.80 | -94 | -34,932 | 20 | -21,904 | 942 | 35 | -22,517 | -11,368 | 12,923 |


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| EMA | CE | 14 | 42.90 | -3,798 | -271 | 0.40 |
| EMA | PE | 11 | 27.30 | -6,987 | -635 | 0.20 |
| ORB | CE | 15 | 33.30 | -252 | -17 | 0.98 |
| ORB | PE | 20 | 50 | 12,125 | 606 | 2.11 |
| PIVOT | CE | 204 | 20.60 | -12,124 | -59 | 0.87 |
| PIVOT | PE | 209 | 21.10 | -21,158 | -101 | 0.79 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| PIVOT_SL_HIT | 168 | 0 | -163,672 | -974 | 0 | 13 |
| PIVOT_BE_STOP | 155 | 11 | -25,005 | -161 | 0.02 | 24 |
| PIVOT_TSL_HIT | 56 | 96.40 | 115,623 | 2,065 | 1,079 | 50 |
| STOP_HIT | 26 | 3.80 | -10,382 | -399 | 0.01 | 51 |
| IDX_SL_HIT | 14 | 0 | -21,096 | -1,507 | 0 | 25 |
| EOD_SQUARE_OFF | 10 | 80 | 11,492 | 1,149 | 18.72 | 100 |
| EMA_TSL_HIT | 9 | 100 | 4,263 | 474 | inf | 33 |
| IDX_TSL_HIT | 8 | 87.50 | 9,858 | 1,232 | 470 | 130 |
| EMA_SL_HIT | 8 | 0 | -10,433 | -1,304 | 0 | 14 |
| IDX_TARGET | 7 | 100 | 25,889 | 3,698 | inf | 63 |
| PIVOT_TARGET_T3 | 7 | 100 | 32,351 | 4,622 | inf | 63 |
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
| EOD_SQUARE_OFF | 0 | 0 | 10 |
| IDX_BE_STOP | 0 | 3 | 0 |
| IDX_SL_HIT | 0 | 14 | 0 |
| IDX_TARGET | 0 | 7 | 0 |
| IDX_TSL_HIT | 0 | 8 | 0 |
| PIVOT_BE_STOP | 0 | 0 | 155 |
| PIVOT_SL_HIT | 0 | 0 | 168 |
| PIVOT_TARGET_T3 | 0 | 0 | 7 |
| PIVOT_TSL_HIT | 0 | 0 | 56 |
| STOP_HIT | 6 | 3 | 17 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| INITIAL | 207 | 1 | -205,520 | -993 | 0 |
| BE | 182 | 14.80 | 3,856 | 21 | 1.14 |
| T1 | 52 | 96.20 | 96,839 | 1,862 | 904 |
| TRAIL | 24 | 95.80 | 37,941 | 1,581 | 1,805 |
| T2 | 8 | 100 | 34,689 | 4,336 | inf |


- Trades whose stop moved at least once: 266 of 473 (56%); average 1.9 moves per trade.

- Full initial-stop losses: 207 (44%).

- Of the 203 trades that reached +1R, the exit kept on average 36% of the best index move (median 33%); 49% of them still closed at a net loss.

- Median best move (MFE) 0.87R; 43% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 251 | 19.90 | -46,213 | -184 | 0.67 |
| H2 | 222 | 27 | 14,019 | 63 | 1.15 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2024 | 182 | 18.10 | -53,985 | -297 | 0.46 |
| 2025 | 177 | 22 | -15,273 | -86 | 0.82 |
| 2026 | 114 | 33.30 | 37,063 | 325 | 1.79 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2024-01 | 8 | 12.50 | -351 | -44 | 0.86 | -351 |
| 2024-02 | 14 | 42.90 | -18 | -1 | 1 | -369 |
| 2024-03 | 13 | 23.10 | -5,035 | -387 | 0.31 | -5,404 |
| 2024-04 | 12 | 8.30 | -5,113 | -426 | 0.12 | -10,517 |
| 2024-05 | 19 | 10.50 | -13,786 | -726 | 0.14 | -24,303 |
| 2024-06 | 12 | 16.70 | -7,924 | -660 | 0 | -32,227 |
| 2024-07 | 15 | 6.70 | -6,266 | -418 | 0.21 | -38,493 |
| 2024-08 | 13 | 0 | -4,012 | -309 | 0 | -42,505 |
| 2024-09 | 19 | 31.60 | -3,992 | -210 | 0.57 | -46,497 |
| 2024-10 | 23 | 13 | -6,443 | -280 | 0.55 | -52,940 |
| 2024-11 | 15 | 26.70 | 4,656 | 310 | 1.55 | -48,284 |
| 2024-12 | 19 | 21.10 | -5,701 | -300 | 0.52 | -53,985 |
| 2025-01 | 14 | 35.70 | 6,469 | 462 | 1.97 | -47,516 |
| 2025-02 | 16 | 31.20 | 3,153 | 197 | 1.36 | -44,363 |
| 2025-03 | 10 | 20 | 2,847 | 285 | 2.09 | -41,516 |
| 2025-04 | 12 | 25 | 4,932 | 411 | 1.69 | -36,584 |
| 2025-05 | 17 | 11.80 | -9,629 | -566 | 0.20 | -46,213 |
| 2025-06 | 13 | 30.80 | -4,006 | -308 | 0.37 | -50,219 |
| 2025-07 | 20 | 20 | -5,621 | -281 | 0.39 | -55,840 |
| 2025-08 | 25 | 12 | -6,894 | -276 | 0.53 | -62,734 |
| 2025-09 | 16 | 18.80 | -3,961 | -248 | 0.37 | -66,695 |
| 2025-10 | 10 | 40 | 1,047 | 105 | 1.30 | -65,648 |
| 2025-11 | 17 | 17.60 | -864 | -51 | 0.83 | -66,512 |
| 2025-12 | 7 | 14.30 | -2,747 | -392 | 0.03 | -69,259 |
| 2026-01 | 11 | 36.40 | 6,293 | 572 | 3.03 | -62,966 |
| 2026-02 | 21 | 23.80 | -5,450 | -260 | 0.61 | -68,416 |
| 2026-03 | 6 | 50 | 13,599 | 2,267 | 6.96 | -54,817 |
| 2026-04 | 11 | 54.50 | 13,346 | 1,213 | 4 | -41,471 |
| 2026-05 | 10 | 10 | -4,558 | -456 | 0.05 | -46,029 |
| 2026-06 | 15 | 40 | 2,213 | 148 | 1.31 | -43,816 |
| 2026-07 | 10 | 10 | -1,822 | -182 | 0.62 | -45,638 |
| 2026-08 | 15 | 33.30 | 1,593 | 106 | 1.69 | -44,045 |
| 2026-09 | 8 | 50 | 3,985 | 498 | 3.09 | -40,060 |
| 2026-10 | 7 | 42.90 | 7,866 | 1,124 | 4.62 | -32,194 |


38% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 118 | 28 | 5,959 | 50 | 1.08 |
| 10:00 | 95 | 23.20 | -9,609 | -101 | 0.74 |
| 11:00 | 79 | 20.30 | -19,273 | -244 | 0.56 |
| 12:00 | 65 | 24.60 | 7,402 | 114 | 1.29 |
| 13:00 | 64 | 23.40 | 5,456 | 85 | 1.19 |
| 14:00 | 52 | 15.40 | -22,129 | -426 | 0.18 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Mon | 81 | 24.70 | -5,579 | -69 | 0.87 |
| Tue | 113 | 26.50 | 11,630 | 103 | 1.23 |
| Wed | 104 | 21.20 | -19,860 | -191 | 0.63 |
| Thu | 94 | 24.50 | 10,707 | 114 | 1.27 |
| Fri | 80 | 18.80 | -27,226 | -340 | 0.40 |
| Sat | 1 | 0 | -1,866 | -1,866 | 0 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 380 | 23.90 | -45,079 | -119 | 0.76 |
| yes | 93 | 20.40 | 12,885 | 139 | 1.28 |


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
| 2026-03-16 13:55:00 | PIVOT | CE | 596 | 956 | PIVOT_TSL_HIT | T2 | 7,068 |
| 2025-03-03 09:35:00 | PIVOT | PE | 215 | 480 | PIVOT_TSL_HIT | T2 | 5,199 |
| 2026-03-25 09:30:00 | ORB | CE | 188 | 448 | IDX_TARGET | TRAIL | 5,102 |
| 2026-10-14 12:50:00 | PIVOT | PE | 242 | 501 | PIVOT_TSL_HIT | T1 | 5,086 |
| 2026-04-06 11:30:00 | PIVOT | CE | 724 | 974 | PIVOT_TSL_HIT | T1 | 4,883 |
| 2026-04-07 11:15:00 | PIVOT | CE | 574 | 819 | PIVOT_TSL_HIT | T1 | 4,787 |
| 2026-04-30 09:35:00 | ORB | PE | 155 | 397 | IDX_TARGET | TRAIL | 4,753 |
| 2024-11-07 09:35:00 | PIVOT | PE | 268 | 508 | PIVOT_TSL_HIT | T1 | 4,706 |


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
| 2025-02-01 11:35:00 | PIVOT | CE | 457 | 369 | PIVOT_SL_HIT | INITIAL | -1,866 |
| 2024-10-08 10:15:00 | PIVOT | PE | 454 | 368 | PIVOT_SL_HIT | INITIAL | -1,828 |


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
