# Full-system backtest: 2025-10-01 to 2026-10-16

Run label `pivot_1y`, 258 trading sessions, generated 2026-10-20 15:27.  Overrides: {'ENABLE_EMA_STRATEGY': 'false', 'ENABLE_ORB_STRATEGY': 'false', 'ENABLE_VWAP_STRATEGY': 'false', 'ENABLE_TRB_STRATEGY': 'false', 'ENABLE_MOMENTUM_PHASE': 'false', 'ENABLE_NATR_STRATEGY': 'false', 'ENABLE_PDHL_STRATEGY': 'false', 'ENABLE_OB_STRATEGY': 'false', 'ENABLE_ATR_COPILOT_STRATEGY': 'false', 'ENABLE_PIVOT_STRATEGY': 'true'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 130 |
| Win % | 28.50 |
| Net P&L (Rs) | 25,206 |
| Gross P&L (Rs) | 38,247 |
| Costs (Rs) | 13,041 |
|   of which charges (Rs) | 7,841 |
|   of which slippage (Rs) | 5,200 |
| Avg cost per trade (Rs) | 100 |
| Profit factor | 1.48 |
| Avg trade (Rs) | 194 |
| Avg win (Rs) | 2,108 |
| Avg loss (Rs) | -568 |
| Largest win (Rs) | 7,068 |
| Largest loss (Rs) | -2,226 |
| Max drawdown (Rs) | -10,031 |
| Longest losing streak | 12 |
| Avg hold (min) | 31.90 |


Trades on 92 of 258 sessions; 36% of trading days were green.  Average 10.6 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| PIVOT | CE | 70 | 27.10 | 12,948 | 185 | 1.41 |
| PIVOT | PE | 60 | 30 | 12,258 | 204 | 1.58 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| PIVOT_BE_STOP | 46 | 6.50 | -6,995 | -152 | 0.03 | 24 |
| PIVOT_SL_HIT | 40 | 0 | -43,149 | -1,079 | 0 | 16 |
| PIVOT_TSL_HIT | 29 | 96.60 | 64,241 | 2,215 | 858 | 48 |
| STOP_HIT | 9 | 0 | -2,396 | -266 | 0 | 43 |
| PIVOT_TARGET_T3 | 4 | 100 | 7,347 | 1,837 | inf | 103 |
| EOD_SQUARE_OFF | 2 | 100 | 6,159 | 3,080 | inf | 120 |


### Exit reason by strategy (trade count)

| exit_reason | PIVOT |
|---|---:|
| EOD_SQUARE_OFF | 2 |
| PIVOT_BE_STOP | 46 |
| PIVOT_SL_HIT | 40 |
| PIVOT_TARGET_T3 | 4 |
| PIVOT_TSL_HIT | 29 |
| STOP_HIT | 9 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| BE | 59 | 15.30 | 5,831 | 99 | 1.74 |
| INITIAL | 42 | 0 | -44,866 | -1,068 | 0 |
| T1 | 25 | 96 | 49,772 | 1,991 | 665 |
| T2 | 4 | 100 | 14,470 | 3,617 | inf |


- Trades whose stop moved at least once: 88 of 130 (68%); average 2.0 moves per trade.

- Full initial-stop losses: 42 (32%).

- Of the 66 trades that reached +1R, the exit kept on average 42% of the best index move (median 45%); 45% of them still closed at a net loss.

- Median best move (MFE) 1.02R; 51% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 65 | 29.20 | 18,079 | 278 | 1.67 |
| H2 | 65 | 27.70 | 7,127 | 110 | 1.28 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2025 | 31 | 22.60 | -1,253 | -40 | 0.88 |
| 2026 | 99 | 30.30 | 26,459 | 267 | 1.62 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2025-10 | 10 | 40 | 1,047 | 105 | 1.30 | 1,047 |
| 2025-11 | 16 | 18.80 | 389 | 24 | 1.10 | 1,436 |
| 2025-12 | 5 | 0 | -2,689 | -538 | 0 | -1,253 |
| 2026-01 | 10 | 30 | 4,114 | 411 | 2.32 | 2,861 |
| 2026-02 | 19 | 26.30 | -4,392 | -231 | 0.66 | -1,531 |
| 2026-03 | 3 | 66.70 | 9,941 | 3,314 | 12.87 | 8,410 |
| 2026-04 | 6 | 50 | 9,708 | 1,618 | 4.69 | 18,118 |
| 2026-05 | 10 | 10 | -4,558 | -456 | 0.05 | 13,560 |
| 2026-06 | 15 | 40 | 2,213 | 148 | 1.31 | 15,773 |
| 2026-07 | 8 | 12.50 | -1,179 | -147 | 0.71 | 14,594 |
| 2026-08 | 13 | 23.10 | 247 | 19 | 1.11 | 14,841 |
| 2026-09 | 7 | 42.90 | 3,057 | 437 | 2.60 | 17,898 |
| 2026-10 | 8 | 37.50 | 7,311 | 914 | 3.68 | 25,209 |


69% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 22 | 22.70 | -3,172 | -144 | 0.72 |
| 10:00 | 26 | 34.60 | 7,785 | 299 | 2.09 |
| 11:00 | 21 | 38.10 | 13,536 | 645 | 3.21 |
| 12:00 | 18 | 38.90 | 6,887 | 383 | 2.45 |
| 13:00 | 26 | 30.80 | 12,011 | 462 | 2.02 |
| 14:00 | 17 | 0 | -11,841 | -697 | 0 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Mon | 29 | 31 | 13,471 | 465 | 2.19 |
| Tue | 27 | 33.30 | 11,118 | 412 | 2.47 |
| Wed | 28 | 32.10 | 5,084 | 182 | 1.43 |
| Thu | 26 | 26.90 | 4,630 | 178 | 1.60 |
| Fri | 20 | 15 | -9,096 | -455 | 0.37 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 110 | 29.10 | 22,807 | 207 | 1.48 |
| yes | 20 | 25 | 2,399 | 120 | 1.49 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| CE_PIVOT | 88 |
| PE_PIVOT | 78 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
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
| 2026-02-20 13:10:00 | PIVOT | PE | 575 | 480 | PIVOT_SL_HIT | INITIAL | -2,006 |
| 2026-02-20 12:25:00 | PIVOT | CE | 648 | 562 | PIVOT_SL_HIT | INITIAL | -1,824 |
| 2026-06-05 14:40:00 | PIVOT | PE | 550 | 464 | PIVOT_SL_HIT | INITIAL | -1,816 |
| 2026-02-23 09:50:00 | PIVOT | CE | 463 | 377 | PIVOT_SL_HIT | INITIAL | -1,812 |
| 2026-07-16 14:20:00 | PIVOT | CE | 626 | 541 | PIVOT_SL_HIT | INITIAL | -1,804 |
| 2026-02-02 13:10:00 | PIVOT | CE | 464 | 385 | PIVOT_SL_HIT | INITIAL | -1,669 |
| 2025-10-08 13:50:00 | PIVOT | CE | 208 | 131 | PIVOT_SL_HIT | INITIAL | -1,629 |
| 2026-05-13 13:05:00 | PIVOT | CE | 325 | 252 | PIVOT_SL_HIT | INITIAL | -1,557 |
| 2026-01-30 14:10:00 | PIVOT | CE | 633 | 565 | PIVOT_SL_HIT | INITIAL | -1,462 |


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
| TREND_GATE_STRATEGIES | frozenset({'NATR', 'VWAP', 'TRB', 'EMA'}) |
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
