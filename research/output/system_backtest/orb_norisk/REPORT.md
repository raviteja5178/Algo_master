# Full-system backtest: 2025-10-01 to 2026-10-16

Run label `orb_norisk`, 258 trading sessions, generated 2026-10-20 20:03.  Overrides: {'ENABLE_EMA_STRATEGY': 'false', 'ENABLE_ORB_STRATEGY': 'true', 'ENABLE_PIVOT_STRATEGY': 'false', 'ENABLE_VWAP_STRATEGY': 'false', 'ENABLE_TRB_STRATEGY': 'false', 'ENABLE_MOMENTUM_PHASE': 'false', 'ENABLE_NATR_STRATEGY': 'false', 'ENABLE_PDHL_STRATEGY': 'false', 'ENABLE_OB_STRATEGY': 'false', 'ENABLE_ATR_COPILOT_STRATEGY': 'false', 'MAX_RISK_RUPEES_PER_TRADE': '5000'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 24 |
| Win % | 33.30 |
| Net P&L (Rs) | -1,820 |
| Gross P&L (Rs) | 531 |
| Costs (Rs) | 2,351 |
|   of which charges (Rs) | 1,391 |
|   of which slippage (Rs) | 960 |
| Avg cost per trade (Rs) | 98 |
| Profit factor | 0.93 |
| Avg trade (Rs) | -76 |
| Avg win (Rs) | 3,197 |
| Avg loss (Rs) | -1,712 |
| Largest win (Rs) | 6,774 |
| Largest loss (Rs) | -4,120 |
| Max drawdown (Rs) | -14,216 |
| Longest losing streak | 7 |
| Avg hold (min) | 148 |


Trades on 24 of 258 sessions; 33% of trading days were green.  Average 2.0 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| ORB | CE | 11 | 36.40 | 3,720 | 338 | 1.39 |
| ORB | PE | 13 | 30.80 | -5,540 | -426 | 0.69 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| IDX_SL_HIT | 10 | 0 | -23,876 | -2,388 | 0 | 109 |
| IDX_TSL_HIT | 7 | 85.70 | 20,396 | 2,914 | 971 | 201 |
| IDX_BE_STOP | 3 | 0 | -336 | -112 | 0 | 19 |
| TIME_DECAY | 3 | 33.30 | -3,105 | -1,035 | 0.02 | 311 |
| IDX_TARGET | 1 | 100 | 5,102 | 5,102 | inf | 72 |


### Exit reason by strategy (trade count)

| exit_reason | ORB |
|---|---:|
| IDX_BE_STOP | 3 |
| IDX_SL_HIT | 10 |
| IDX_TARGET | 1 |
| IDX_TSL_HIT | 7 |
| TIME_DECAY | 3 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| INITIAL | 13 | 7.70 | -26,982 | -2,076 | 0 |
| TRAIL | 8 | 87.50 | 25,498 | 3,187 | 1,213 |
| BE | 3 | 0 | -336 | -112 | 0 |


- Trades whose stop moved at least once: 11 of 24 (46%); average 5.0 moves per trade.

- Full initial-stop losses: 13 (54%).

- Of the 11 trades that reached +1R, the exit kept on average 52% of the best index move (median 63%); 36% of them still closed at a net loss.

- Median best move (MFE) 0.82R; 46% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 14 | 35.70 | -2,606 | -186 | 0.83 |
| H2 | 10 | 30 | 786 | 79 | 1.06 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2025 | 8 | 12.50 | -14,160 | -1,770 | 0 |
| 2026 | 16 | 43.80 | 12,340 | 771 | 1.94 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2025-10 | 2 | 50 | -2,124 | -1,062 | 0.03 | -2,124 |
| 2025-11 | 3 | 0 | -8,705 | -2,902 | 0 | -10,829 |
| 2025-12 | 3 | 0 | -3,332 | -1,111 | 0 | -14,161 |
| 2026-01 | 2 | 100 | 4,006 | 2,003 | inf | -10,155 |
| 2026-02 | 3 | 33.30 | 2,446 | 815 | 3.31 | -7,709 |
| 2026-03 | 1 | 100 | 5,102 | 5,102 | inf | -2,607 |
| 2026-04 | 1 | 0 | -1,156 | -1,156 | 0 | -3,763 |
| 2026-05 | 3 | 33.30 | -556 | -185 | 0.89 | -4,319 |
| 2026-06 | 1 | 0 | -3,031 | -3,031 | 0 | -7,350 |
| 2026-07 | 1 | 0 | -43 | -43 | 0 | -7,393 |
| 2026-08 | 1 | 100 | 1,461 | 1,461 | inf | -5,932 |
| 2026-09 | 1 | 0 | -2,642 | -2,642 | 0 | -8,574 |
| 2026-10 | 2 | 50 | 6,753 | 3,376 | 322 | -1,821 |


38% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 24 | 33.30 | -1,820 | -76 | 0.93 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Tue | 9 | 44.40 | 3,363 | 374 | 1.24 |
| Wed | 2 | 100 | 6,563 | 3,281 | inf |
| Thu | 7 | 0 | -3,671 | -524 | 0 |
| Fri | 6 | 33.30 | -8,075 | -1,346 | 0.15 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 16 | 43.80 | -3,251 | -203 | 0.86 |
| yes | 8 | 12.50 | 1,431 | 179 | 1.39 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| PE_ORB | 46 |
| CE_ORB | 43 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| SMART_ENTRY_BLOCKED_BODY | 35 |
| ENTRY_BLOCKED_MAX_RISK | 6 |
| SMART_ENTRY_BLOCKED_EMA_GAP | 2 |
| SMART_ENTRY_BLOCKED_EMA_GAP_SHRINKING: EMA gap not widening | 2 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not rising for CE | 1 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not falling for PE | 1 |
| SMART_ENTRY_BLOCKED_COOLDOWN | 1 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-10-13 09:35:00 | ORB | CE | 373 | 718 | IDX_TSL_HIT | TRAIL | 6,774 |
| 2026-03-25 09:30:00 | ORB | CE | 188 | 448 | IDX_TARGET | TRAIL | 5,102 |
| 2026-05-12 09:30:00 | ORB | PE | 404 | 643 | IDX_TSL_HIT | TRAIL | 4,673 |
| 2026-02-24 09:35:00 | ORB | PE | 352 | 533 | IDX_TSL_HIT | TRAIL | 3,504 |
| 2026-01-20 09:30:00 | ORB | PE | 276 | 415 | IDX_TSL_HIT | TRAIL | 2,676 |
| 2026-08-19 09:30:00 | ORB | PE | 216 | 294 | IDX_TSL_HIT | TRAIL | 1,461 |
| 2026-01-02 09:35:00 | ORB | CE | 442 | 514 | IDX_TSL_HIT | TRAIL | 1,330 |
| 2025-10-10 09:35:00 | ORB | CE | 486 | 494 | TIME_DECAY | INITIAL | 56.07 |
| 2026-10-08 09:30:00 | ORB | PE | 131 | 135 | IDX_TSL_HIT | TRAIL | -21.03 |
| 2026-07-02 09:35:00 | ORB | CE | 119 | 122 | IDX_BE_STOP | BE | -42.56 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2025-11-07 09:40:00 | ORB | PE | 477 | 276 | IDX_SL_HIT | INITIAL | -4,120 |
| 2025-11-11 09:30:00 | ORB | PE | 337 | 175 | IDX_SL_HIT | INITIAL | -3,332 |
| 2026-06-30 09:35:00 | ORB | PE | 306 | 159 | IDX_SL_HIT | INITIAL | -3,031 |
| 2026-05-26 09:40:00 | ORB | CE | 283 | 149 | IDX_SL_HIT | INITIAL | -2,765 |
| 2026-09-29 09:30:00 | ORB | PE | 283 | 156 | IDX_SL_HIT | INITIAL | -2,642 |
| 2025-12-09 09:30:00 | ORB | PE | 273 | 153 | IDX_SL_HIT | INITIAL | -2,494 |
| 2026-05-22 09:35:00 | ORB | CE | 688 | 570 | TIME_DECAY | INITIAL | -2,464 |
| 2025-10-31 09:35:00 | ORB | CE | 571 | 468 | IDX_SL_HIT | INITIAL | -2,180 |
| 2025-11-27 09:30:00 | ORB | CE | 121 | 63 | IDX_SL_HIT | INITIAL | -1,253 |
| 2026-04-30 09:30:00 | ORB | PE | 126 | 72.35 | IDX_SL_HIT | INITIAL | -1,156 |


## Configuration tested

| Setting | Value |
|---|---|
| ENABLE_PIVOT_STRATEGY | no |
| ENABLE_ORB_STRATEGY | yes |
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
| MAX_RISK_RUPEES_PER_TRADE | 5,000 |
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
- **Options are modelled, not historical.** Black-Scholes, IV = India VIX (minute), r = 6.5%.  Strike selection, ITM fallback and expiry-day rollover use the bot's own selector on a synthetic chain; weekly expiry calendar [['2000-01-01', 4], ['2025-01-01', 1], ['2025-09-01', 3]] (weekday 0 = Monday), moved to the previous session on holidays.  The model has no volatility smile, no intraday IV crush beyond VIX moves, and VIX (30-day, NIFTY) is a proxy for weekly SENSEX IV — expect real premiums, especially on expiry days, to differ.
- **Fills and costs.** SHADOW-mode paper fills at the modelled premium, then 1.0 option point(s) of slippage per side plus brokerage, STT, exchange, SEBI, stamp duty and GST are deducted per trade.  Quantity is today's lot (20) throughout.
- **Not modelled:** order rejections, partial fills, feed outages, margin limits.


Files: `trades.csv` (one row per trade, with exit reason, stop stage, MFE/MAE and costs), `events.csv` (signals, blocks, stop moves), `run_meta.json` (full settings snapshot).  Re-run: `python -m research.system_backtest`.
