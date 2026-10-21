# Full-system backtest: 2025-10-01 to 2026-10-16

Run label `full_sys_monday_enabled`, 258 trading sessions, generated 2026-10-20 21:14.  Overrides: {'ORB_MOMENTUM_SKIP_MONDAY': 'false'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 103 |
| Win % | 46.60 |
| Net P&L (Rs) | 12,519 |
| Gross P&L (Rs) | 22,907 |
| Costs (Rs) | 10,388 |
|   of which charges (Rs) | 6,268 |
|   of which slippage (Rs) | 4,120 |
| Avg cost per trade (Rs) | 101 |
| Profit factor | 1.30 |
| Avg trade (Rs) | 122 |
| Avg win (Rs) | 1,135 |
| Avg loss (Rs) | -763 |
| Largest win (Rs) | 4,870 |
| Largest loss (Rs) | -2,704 |
| Max drawdown (Rs) | -9,383 |
| Longest losing streak | 5 |
| Avg hold (min) | 36.30 |


Trades on 81 of 258 sessions; 47% of trading days were green.  Average 8.4 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| EMA | CE | 5 | 60 | -669 | -134 | 0.68 |
| EMA | PE | 4 | 50 | -1,690 | -423 | 0.35 |
| ORB | CE | 4 | 25 | -4,493 | -1,123 | 0.21 |
| ORB | PE | 2 | 50 | -503 | -252 | 0.81 |
| PIVOT | CE | 49 | 40.80 | 5,889 | 120 | 1.32 |
| PIVOT | PE | 39 | 53.80 | 13,987 | 359 | 2.37 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| PIVOT_BE_STOP | 34 | 47.10 | -1,977 | -58 | 0.43 | 20 |
| PIVOT_SL_HIT | 24 | 0 | -25,192 | -1,050 | 0 | 15 |
| PIVOT_TSL_HIT | 20 | 95 | 40,449 | 2,022 | 460 | 52 |
| STOP_HIT | 12 | 41.70 | -3,818 | -318 | 0.21 | 55 |
| IDX_SL_HIT | 3 | 0 | -5,808 | -1,936 | 0 | 50 |
| EMA_TSL_HIT | 3 | 100 | 1,364 | 455 | inf | 27 |
| EOD_SQUARE_OFF | 2 | 100 | 5,608 | 2,804 | inf | 120 |
| IDX_TSL_HIT | 2 | 100 | 3,419 | 1,710 | inf | 196 |
| EMA_COLLAPSE | 1 | 0 | -890 | -890 | 0 | 90 |
| EMA_SL_HIT | 1 | 0 | -1,695 | -1,695 | 0 | 6 |
| PIVOT_TARGET_T3 | 1 | 100 | 1,058 | 1,058 | inf | 54 |


### Exit reason by strategy (trade count)

| exit_reason | EMA | ORB | PIVOT |
|---|---:|---:|---:|
| EMA_COLLAPSE | 1 | 0 | 0 |
| EMA_SL_HIT | 1 | 0 | 0 |
| EMA_TSL_HIT | 3 | 0 | 0 |
| EOD_SQUARE_OFF | 0 | 0 | 2 |
| IDX_SL_HIT | 0 | 3 | 0 |
| IDX_TSL_HIT | 0 | 2 | 0 |
| PIVOT_BE_STOP | 0 | 0 | 34 |
| PIVOT_SL_HIT | 0 | 0 | 24 |
| PIVOT_TARGET_T3 | 0 | 0 | 1 |
| PIVOT_TSL_HIT | 0 | 0 | 20 |
| STOP_HIT | 4 | 1 | 7 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| BE | 44 | 50 | 4,619 | 105 | 2.29 |
| INITIAL | 32 | 0 | -38,291 | -1,197 | 0 |
| T1 | 18 | 94.40 | 35,617 | 1,979 | 405 |
| TRAIL | 7 | 100 | 5,743 | 820 | inf |
| T2 | 2 | 100 | 4,831 | 2,416 | inf |


- Trades whose stop moved at least once: 71 of 103 (69%); average 2.5 moves per trade.

- Full initial-stop losses: 32 (31%).

- Of the 49 trades that reached +1R, the exit kept on average 50% of the best index move (median 48%); 24% of them still closed at a net loss.

- Median best move (MFE) 0.97R; 48% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 53 | 43.40 | 8,479 | 160 | 1.42 |
| H2 | 50 | 50 | 4,040 | 81 | 1.19 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2025 | 25 | 40 | -8,897 | -356 | 0.11 |
| 2026 | 78 | 48.70 | 21,417 | 275 | 1.67 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2025-10 | 8 | 37.50 | -5,352 | -669 | 0.08 | -5,352 |
| 2025-11 | 12 | 41.70 | -1,564 | -130 | 0.24 | -6,916 |
| 2025-12 | 5 | 40 | -1,982 | -396 | 0.05 | -8,898 |
| 2026-01 | 8 | 62.50 | 8,219 | 1,027 | 16.06 | -679 |
| 2026-02 | 13 | 38.50 | -400 | -31 | 0.94 | -1,079 |
| 2026-03 | 5 | 20 | 778 | 156 | 1.29 | -301 |
| 2026-04 | 6 | 83.30 | 11,141 | 1,857 | 10.64 | 10,840 |
| 2026-05 | 10 | 20 | -6,769 | -677 | 0.04 | 4,071 |
| 2026-06 | 10 | 60 | -377 | -38 | 0.94 | 3,694 |
| 2026-07 | 6 | 50 | 354 | 59 | 1.19 | 4,048 |
| 2026-08 | 8 | 50 | 1,628 | 204 | 2.23 | 5,676 |
| 2026-09 | 7 | 57.10 | -188 | -27 | 0.90 | 5,488 |
| 2026-10 | 5 | 60 | 7,032 | 1,406 | 3.93 | 12,520 |


46% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 16 | 31.20 | -6,040 | -377 | 0.60 |
| 10:00 | 25 | 64 | 4,071 | 163 | 1.59 |
| 11:00 | 24 | 37.50 | 4,088 | 170 | 1.42 |
| 12:00 | 15 | 53.30 | 4,977 | 332 | 2.68 |
| 13:00 | 23 | 43.50 | 5,423 | 236 | 1.74 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Mon | 21 | 42.90 | 7,140 | 340 | 2.06 |
| Tue | 28 | 64.30 | 5,449 | 195 | 1.55 |
| Wed | 27 | 37 | 2,969 | 110 | 1.22 |
| Thu | 24 | 37.50 | -2,556 | -106 | 0.74 |
| Fri | 3 | 66.70 | -482 | -161 | 0.75 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 83 | 49.40 | 18,874 | 227 | 1.57 |
| yes | 20 | 35 | -6,354 | -318 | 0.27 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| CE | 210 |
| PE | 186 |
| CE_PIVOT | 55 |
| PE_PIVOT | 44 |
| CE_ORB | 41 |
| PE_ORB | 40 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| PIVOT_BLOCKED_FRIDAY | 3,756 |
| PIVOT_BLOCKED_TIME | 3,699 |
| ORB_BLOCKED_THURSDAY | 300 |
| SMART_ENTRY_BLOCKED_EMA_GAP_SHRINKING: EMA gap not widening | 121 |
| TREND_GATE_BLOCKED: against daily trend (UP) | 93 |
| TREND_GATE_BLOCKED: against daily trend (DOWN) | 83 |
| ENTRY_BLOCKED_MAX_RISK | 65 |
| SMART_ENTRY_BLOCKED_BODY | 52 |
| EMA_ENTRY_BLOCKED: room # < #R (#) | 26 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not rising for CE | 6 |
| EMA_ENTRY_BLOCKED: option premium # <= option #m EMA# # | 3 |
| SMART_ENTRY_BLOCKED_EMA_GAP | 3 |
| EMA_ENTRY_BLOCKED: risk # > max # | 3 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-10-14 12:50:00 | PIVOT | PE | 282 | 531 | PIVOT_TSL_HIT | T1 | 4,870 |
| 2026-04-06 11:30:00 | PIVOT | CE | 837 | 1,070 | PIVOT_TSL_HIT | T1 | 4,541 |
| 2026-04-07 11:15:00 | PIVOT | CE | 680 | 898 | PIVOT_TSL_HIT | T1 | 4,238 |
| 2026-02-02 13:50:00 | PIVOT | CE | 508 | 695 | EOD_SQUARE_OFF | BE | 3,627 |
| 2026-03-11 09:35:00 | PIVOT | PE | 446 | 626 | PIVOT_TSL_HIT | T2 | 3,484 |
| 2026-06-24 10:15:00 | PIVOT | CE | 323 | 462 | PIVOT_TSL_HIT | T1 | 2,680 |
| 2026-01-27 10:40:00 | PIVOT | PE | 445 | 584 | PIVOT_TSL_HIT | T1 | 2,673 |
| 2026-01-14 13:20:00 | PIVOT | PE | 481 | 615 | PIVOT_TSL_HIT | T1 | 2,587 |
| 2026-10-12 10:40:00 | PIVOT | PE | 426 | 560 | PIVOT_TSL_HIT | T1 | 2,583 |
| 2026-04-30 13:00:00 | PIVOT | CE | 760 | 894 | PIVOT_TSL_HIT | T1 | 2,558 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-06-30 09:30:00 | ORB | PE | 370 | 240 | IDX_SL_HIT | INITIAL | -2,704 |
| 2026-05-26 09:30:00 | ORB | CE | 375 | 249 | STOP_HIT | INITIAL | -2,608 |
| 2026-06-24 09:50:00 | PIVOT | PE | 293 | 180 | PIVOT_SL_HIT | INITIAL | -2,359 |
| 2025-10-31 09:40:00 | ORB | CE | 563 | 470 | IDX_SL_HIT | INITIAL | -1,951 |
| 2026-02-23 09:50:00 | PIVOT | CE | 546 | 454 | PIVOT_SL_HIT | INITIAL | -1,944 |
| 2026-02-02 13:10:00 | PIVOT | CE | 527 | 447 | PIVOT_SL_HIT | INITIAL | -1,696 |
| 2026-03-12 11:50:00 | EMA | PE | 244 | 164 | EMA_SL_HIT | INITIAL | -1,695 |
| 2025-10-08 13:50:00 | PIVOT | CE | 240 | 160 | PIVOT_SL_HIT | INITIAL | -1,694 |
| 2026-05-13 13:05:00 | PIVOT | CE | 385 | 309 | PIVOT_SL_HIT | INITIAL | -1,617 |
| 2026-10-01 10:35:00 | PIVOT | CE | 158 | 87.70 | PIVOT_SL_HIT | INITIAL | -1,506 |


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
| TREND_GATE_STRATEGIES | frozenset({'NATR', 'VWAP', 'EMA', 'TRB'}) |
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
