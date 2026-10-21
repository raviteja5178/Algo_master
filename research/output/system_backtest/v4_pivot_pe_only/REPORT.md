# Full-system backtest: 2024-01-15 to 2026-10-16

Run label `v4_pivot_pe_only`, 683 trading sessions, generated 2026-10-20 20:27.  Overrides: {'ENABLE_ORB_STRATEGY': 'false', 'ENABLE_EMA_STRATEGY': 'false'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 141 |
| Win % | 21.30 |
| Net P&L (Rs) | -715 |
| Gross P&L (Rs) | 13,429 |
| Costs (Rs) | 14,144 |
|   of which charges (Rs) | 8,504 |
|   of which slippage (Rs) | 5,640 |
| Avg cost per trade (Rs) | 100 |
| Profit factor | 0.99 |
| Avg trade (Rs) | -5 |
| Avg win (Rs) | 2,194 |
| Avg loss (Rs) | -600 |
| Largest win (Rs) | 8,867 |
| Largest loss (Rs) | -2,359 |
| Max drawdown (Rs) | -24,798 |
| Longest losing streak | 24 |
| Avg hold (min) | 24.20 |


Trades on 112 of 683 sessions; 25% of trading days were green.  Average 4.3 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| PIVOT | PE | 141 | 21.30 | -715 | -5 | 0.99 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| PIVOT_SL_HIT | 58 | 0 | -55,935 | -964 | 0 | 12 |
| PIVOT_BE_STOP | 46 | 8.70 | -9,036 | -196 | 0.01 | 17 |
| PIVOT_TSL_HIT | 22 | 100 | 51,124 | 2,324 | inf | 39 |
| STOP_HIT | 11 | 0 | -1,513 | -138 | 0 | 78 |
| PIVOT_TARGET_T3 | 4 | 100 | 14,645 | 3,661 | inf | 47 |


### Exit reason by strategy (trade count)

| exit_reason | PIVOT |
|---|---:|
| PIVOT_BE_STOP | 46 |
| PIVOT_SL_HIT | 58 |
| PIVOT_TARGET_T3 | 4 |
| PIVOT_TSL_HIT | 22 |
| STOP_HIT | 11 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| BE | 59 | 10.20 | -7,822 | -133 | 0.26 |
| INITIAL | 58 | 0 | -55,935 | -964 | 0 |
| T1 | 19 | 100 | 41,389 | 2,178 | inf |
| T2 | 5 | 100 | 21,654 | 4,331 | inf |


- Trades whose stop moved at least once: 83 of 141 (59%); average 1.9 moves per trade.

- Full initial-stop losses: 58 (41%).

- Of the 57 trades that reached +1R, the exit kept on average 40% of the best index move (median 40%); 51% of them still closed at a net loss.

- Median best move (MFE) 0.87R; 40% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 79 | 16.50 | -5,218 | -66 | 0.87 |
| H2 | 62 | 27.40 | 4,503 | 73 | 1.17 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2024 | 56 | 16.10 | -10,271 | -183 | 0.63 |
| 2025 | 51 | 13.70 | -8,357 | -164 | 0.70 |
| 2026 | 34 | 41.20 | 17,913 | 527 | 2.69 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2024-01 | 3 | 0 | -1,667 | -556 | 0 | -1,667 |
| 2024-02 | 4 | 25 | -1,200 | -300 | 0.01 | -2,867 |
| 2024-03 | 4 | 25 | -3,277 | -819 | 0.01 | -6,144 |
| 2024-04 | 2 | 0 | -1,972 | -986 | 0 | -8,116 |
| 2024-05 | 7 | 0 | -4,932 | -705 | 0 | -13,048 |
| 2024-06 | 1 | 0 | -279 | -279 | 0 | -13,327 |
| 2024-07 | 4 | 0 | -2,334 | -583 | 0 | -15,661 |
| 2024-08 | 5 | 0 | -1,466 | -293 | 0 | -17,127 |
| 2024-09 | 4 | 25 | 2,627 | 657 | 7.19 | -14,500 |
| 2024-10 | 11 | 9.10 | -6,687 | -608 | 0.13 | -21,187 |
| 2024-11 | 6 | 50 | 10,914 | 1,819 | 14.40 | -10,273 |
| 2024-12 | 5 | 40 | 0 | 0 | 1 | -10,273 |
| 2025-01 | 2 | 50 | 8,459 | 4,229 | 21.72 | -1,814 |
| 2025-02 | 4 | 25 | 2,628 | 657 | 4.58 | 814 |
| 2025-03 | 3 | 33.30 | 3,561 | 1,187 | 3.65 | 4,375 |
| 2025-04 | 8 | 12.50 | -4,427 | -553 | 0 | -52 |
| 2025-05 | 6 | 0 | -5,169 | -861 | 0 | -5,221 |
| 2025-06 | 4 | 0 | -2,211 | -553 | 0 | -7,432 |
| 2025-07 | 4 | 25 | -1,262 | -316 | 0.45 | -8,694 |
| 2025-08 | 8 | 12.50 | -4,278 | -535 | 0.29 | -12,972 |
| 2025-09 | 5 | 0 | -3,587 | -717 | 0 | -16,559 |
| 2025-10 | 1 | 100 | 26 | 26 | inf | -16,533 |
| 2025-11 | 4 | 0 | -995 | -249 | 0 | -17,528 |
| 2025-12 | 2 | 0 | -1,102 | -551 | 0 | -18,630 |
| 2026-01 | 6 | 50 | 6,478 | 1,080 | 15.39 | -12,152 |
| 2026-02 | 7 | 28.60 | 21 | 3 | 1.01 | -12,131 |
| 2026-03 | 1 | 100 | 3,484 | 3,484 | inf | -8,647 |
| 2026-05 | 5 | 20 | -2,063 | -413 | 0.10 | -10,710 |
| 2026-06 | 5 | 20 | -3,880 | -776 | 0.13 | -14,590 |
| 2026-07 | 2 | 50 | 1,400 | 700 | 3.21 | -13,190 |
| 2026-08 | 4 | 50 | 2,246 | 562 | 15.04 | -10,944 |
| 2026-09 | 2 | 50 | 2,774 | 1,387 | 5.70 | -8,170 |
| 2026-10 | 2 | 100 | 7,452 | 3,726 | inf | -718 |


39% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 25 | 32 | 13,248 | 530 | 2 |
| 10:00 | 38 | 18.40 | -8,845 | -233 | 0.51 |
| 11:00 | 22 | 9.10 | -11,101 | -505 | 0.21 |
| 12:00 | 31 | 22.60 | 235 | 8 | 1.02 |
| 13:00 | 25 | 24 | 5,748 | 230 | 1.70 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Mon | 21 | 19 | -4,972 | -237 | 0.65 |
| Tue | 46 | 28.30 | 12,252 | 266 | 1.76 |
| Wed | 43 | 16.30 | -6,783 | -158 | 0.68 |
| Thu | 31 | 19.40 | -1,212 | -39 | 0.92 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 122 | 21.30 | -9,800 | -80 | 0.84 |
| yes | 19 | 21.10 | 9,085 | 478 | 2.51 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| CE_PIVOT | 163 |
| PE_PIVOT | 146 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| PIVOT_BLOCKED_FRIDAY | 9,768 |
| PIVOT_BLOCKED_TIME | 9,765 |
| BACKTEST_FILTER_BLOCKED: signal CE_PIVOT skipped | 163 |
| ENTRY_BLOCKED_MAX_RISK | 2 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2025-01-21 09:45:00 | PIVOT | PE | 233 | 682 | PIVOT_TARGET_T3 | T2 | 8,867 |
| 2025-03-03 09:35:00 | PIVOT | PE | 274 | 524 | PIVOT_TSL_HIT | T2 | 4,904 |
| 2026-10-14 12:50:00 | PIVOT | PE | 282 | 531 | PIVOT_TSL_HIT | T1 | 4,870 |
| 2024-11-07 09:35:00 | PIVOT | PE | 338 | 563 | PIVOT_TSL_HIT | T1 | 4,394 |
| 2024-11-12 12:00:00 | PIVOT | PE | 391 | 616 | PIVOT_TSL_HIT | T1 | 4,389 |
| 2026-03-11 09:35:00 | PIVOT | PE | 446 | 626 | PIVOT_TSL_HIT | T2 | 3,484 |
| 2026-09-15 13:10:00 | PIVOT | PE | 328 | 501 | PIVOT_TSL_HIT | T1 | 3,364 |
| 2025-02-13 13:10:00 | PIVOT | PE | 481 | 655 | PIVOT_TSL_HIT | T1 | 3,363 |
| 2024-09-18 13:25:00 | PIVOT | PE | 366 | 524 | PIVOT_TARGET_T3 | T2 | 3,051 |
| 2024-11-14 10:20:00 | PIVOT | PE | 189 | 341 | PIVOT_TSL_HIT | T1 | 2,946 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-06-24 09:50:00 | PIVOT | PE | 293 | 180 | PIVOT_SL_HIT | INITIAL | -2,359 |
| 2024-05-06 10:00:00 | PIVOT | PE | 564 | 474 | PIVOT_SL_HIT | INITIAL | -1,891 |
| 2024-10-08 10:15:00 | PIVOT | PE | 522 | 433 | PIVOT_SL_HIT | INITIAL | -1,869 |
| 2024-05-06 11:25:00 | PIVOT | PE | 557 | 475 | PIVOT_SL_HIT | INITIAL | -1,731 |
| 2024-03-12 11:45:00 | PIVOT | PE | 394 | 316 | PIVOT_SL_HIT | INITIAL | -1,661 |
| 2025-05-21 12:55:00 | PIVOT | PE | 711 | 636 | PIVOT_SL_HIT | INITIAL | -1,625 |
| 2024-10-10 09:45:00 | PIVOT | PE | 316 | 241 | PIVOT_SL_HIT | INITIAL | -1,596 |
| 2025-09-03 12:55:00 | PIVOT | PE | 220 | 149 | PIVOT_SL_HIT | INITIAL | -1,510 |
| 2024-10-01 11:15:00 | PIVOT | PE | 395 | 325 | PIVOT_SL_HIT | INITIAL | -1,501 |
| 2025-04-02 13:00:00 | PIVOT | PE | 523 | 455 | PIVOT_SL_HIT | INITIAL | -1,468 |


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
- **Options are modelled, not historical.** Black-Scholes in trading time (weeknight = 176 min, weekend = 609 min), IV = India VIX (minute), r = 6.5%.  Strike selection, ITM fallback and expiry-day rollover use the bot's own selector on a synthetic chain; weekly expiry calendar [['2000-01-01', 4], ['2025-01-01', 1], ['2025-09-01', 3]] (weekday 0 = Monday), moved to the previous session on holidays.  The model has no volatility smile, no intraday IV crush beyond VIX moves, and VIX (30-day, NIFTY) is a proxy for weekly SENSEX IV — expect real premiums, especially on expiry days, to differ.
- **Fills and costs.** SHADOW-mode paper fills at the modelled premium, then 1.0 option point(s) of slippage per side plus brokerage, STT, exchange, SEBI, stamp duty and GST are deducted per trade.  Quantity is today's lot (20) throughout.
- **Not modelled:** order rejections, partial fills, feed outages, margin limits.


Files: `trades.csv` (one row per trade, with exit reason, stop stage, MFE/MAE and costs), `events.csv` (signals, blocks, stop moves), `run_meta.json` (full settings snapshot).  Re-run: `python -m research.system_backtest`.
