# Full-system backtest: 2024-01-15 to 2026-10-16

Run label `v3_orb_only`, 683 trading sessions, generated 2026-10-20 20:28.  Overrides: {'ENABLE_PIVOT_STRATEGY': 'false', 'ENABLE_EMA_STRATEGY': 'false'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 21 |
| Win % | 52.40 |
| Net P&L (Rs) | 5,068 |
| Gross P&L (Rs) | 7,119 |
| Costs (Rs) | 2,051 |
|   of which charges (Rs) | 1,211 |
|   of which slippage (Rs) | 840 |
| Avg cost per trade (Rs) | 98 |
| Profit factor | 1.31 |
| Avg trade (Rs) | 241 |
| Avg win (Rs) | 1,970 |
| Avg loss (Rs) | -1,660 |
| Largest win (Rs) | 6,637 |
| Largest loss (Rs) | -2,288 |
| Max drawdown (Rs) | -5,553 |
| Longest losing streak | 3 |
| Avg hold (min) | 103 |


Trades on 21 of 683 sessions; 52% of trading days were green.  Average 0.6 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| ORB | CE | 8 | 62.50 | 173 | 22 | 1.03 |
| ORB | PE | 13 | 46.20 | 4,895 | 377 | 1.46 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| IDX_TSL_HIT | 8 | 100 | 11,849 | 1,481 | inf | 122 |
| IDX_SL_HIT | 6 | 0 | -10,390 | -1,732 | 0 | 51 |
| STOP_HIT | 5 | 20 | -6,064 | -1,213 | 0.02 | 162 |
| IDX_TARGET | 2 | 100 | 9,672 | 4,836 | inf | 33 |


### Exit reason by strategy (trade count)

| exit_reason | ORB |
|---|---:|
| IDX_SL_HIT | 6 |
| IDX_TARGET | 2 |
| IDX_TSL_HIT | 8 |
| STOP_HIT | 5 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| TRAIL | 11 | 100 | 21,672 | 1,970 | inf |
| INITIAL | 9 | 0 | -16,543 | -1,838 | 0 |
| BE | 1 | 0 | -62 | -62 | 0 |


- Trades whose stop moved at least once: 12 of 21 (57%); average 8.8 moves per trade.

- Full initial-stop losses: 9 (43%).

- Of the 12 trades that reached +1R, the exit kept on average 61% of the best index move (median 61%); 8% of them still closed at a net loss.

- Median best move (MFE) 1.14R; 57% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 9 | 55.60 | 6,611 | 735 | 1.98 |
| H2 | 12 | 50 | -1,543 | -129 | 0.84 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2024 | 6 | 50 | 5,466 | 911 | 1.98 |
| 2025 | 10 | 60 | 24 | 2 | 1 |
| 2026 | 5 | 40 | -423 | -85 | 0.89 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2024-03 | 1 | 100 | 1,348 | 1,348 | inf | 1,348 |
| 2024-06 | 1 | 0 | -2,240 | -2,240 | 0 | -892 |
| 2024-07 | 2 | 0 | -3,313 | -1,657 | 0 | -4,205 |
| 2024-10 | 1 | 100 | 3,035 | 3,035 | inf | -1,170 |
| 2024-12 | 1 | 100 | 6,637 | 6,637 | inf | 5,467 |
| 2025-02 | 3 | 66.70 | 1,145 | 382 | 1.98 | 6,612 |
| 2025-07 | 3 | 33.30 | -2,550 | -850 | 0.36 | 4,062 |
| 2025-08 | 2 | 50 | -766 | -383 | 0.63 | 3,296 |
| 2025-09 | 1 | 100 | 637 | 637 | inf | 3,933 |
| 2025-12 | 1 | 100 | 1,559 | 1,559 | inf | 5,492 |
| 2026-01 | 2 | 100 | 3,419 | 1,710 | inf | 8,911 |
| 2026-02 | 2 | 0 | -1,844 | -922 | 0 | 7,067 |
| 2026-07 | 1 | 0 | -1,997 | -1,997 | 0 | 5,070 |


54% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 21 | 52.40 | 5,068 | 241 | 1.31 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Tue | 6 | 66.70 | -66 | -11 | 0.99 |
| Wed | 2 | 0 | -3,286 | -1,643 | 0 |
| Thu | 10 | 50 | 2,257 | 226 | 1.31 |
| Fri | 3 | 66.70 | 6,162 | 2,054 | 4.64 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 10 | 60 | 3,963 | 396 | 1.59 |
| yes | 11 | 45.50 | 1,105 | 100 | 1.11 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| PE_ORB | 127 |
| CE_ORB | 94 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| ENTRY_BLOCKED_MAX_RISK | 87 |
| SMART_ENTRY_BLOCKED_BODY | 81 |
| SMART_ENTRY_BLOCKED_EMA_GAP_SHRINKING: EMA gap not widening | 8 |
| SMART_ENTRY_BLOCKED_EMA_GAP | 7 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not falling for PE | 5 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not rising for CE | 1 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2024-12-13 09:30:00 | ORB | PE | 185 | 522 | IDX_TARGET | TRAIL | 6,637 |
| 2024-10-17 09:35:00 | ORB | PE | 287 | 443 | IDX_TARGET | TRAIL | 3,035 |
| 2026-01-20 09:30:00 | ORB | PE | 331 | 447 | IDX_TSL_HIT | TRAIL | 2,201 |
| 2025-02-06 09:30:00 | ORB | PE | 516 | 629 | IDX_TSL_HIT | TRAIL | 2,166 |
| 2025-12-04 09:35:00 | ORB | CE | 163 | 246 | IDX_TSL_HIT | TRAIL | 1,559 |
| 2025-07-10 09:35:00 | ORB | PE | 428 | 504 | IDX_TSL_HIT | TRAIL | 1,404 |
| 2024-03-28 09:40:00 | ORB | CE | 163 | 235 | IDX_TSL_HIT | TRAIL | 1,348 |
| 2025-08-12 09:30:00 | ORB | CE | 193 | 264 | IDX_TSL_HIT | TRAIL | 1,317 |
| 2026-01-02 09:35:00 | ORB | CE | 457 | 523 | IDX_TSL_HIT | TRAIL | 1,219 |
| 2025-09-16 09:35:00 | ORB | CE | 338 | 375 | IDX_TSL_HIT | TRAIL | 637 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2025-07-08 09:30:00 | ORB | CE | 197 | 86.75 | STOP_HIT | INITIAL | -2,288 |
| 2024-06-20 09:40:00 | ORB | PE | 321 | 214 | IDX_SL_HIT | INITIAL | -2,240 |
| 2025-08-26 09:35:00 | ORB | PE | 199 | 99 | STOP_HIT | INITIAL | -2,083 |
| 2026-07-02 09:40:00 | ORB | CE | 192 | 97.20 | IDX_SL_HIT | INITIAL | -1,997 |
| 2026-02-12 09:30:00 | ORB | PE | 160 | 75.80 | STOP_HIT | INITIAL | -1,783 |
| 2024-07-05 09:30:00 | ORB | PE | 168 | 88.05 | IDX_SL_HIT | INITIAL | -1,693 |
| 2025-07-16 09:35:00 | ORB | PE | 480 | 402 | IDX_SL_HIT | INITIAL | -1,666 |
| 2024-07-24 09:35:00 | ORB | CE | 386 | 309 | IDX_SL_HIT | INITIAL | -1,620 |
| 2025-02-27 09:40:00 | ORB | PE | 470 | 416 | IDX_SL_HIT | INITIAL | -1,173 |
| 2026-02-05 09:40:00 | ORB | PE | 180 | 182 | STOP_HIT | BE | -61.72 |


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
