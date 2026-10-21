# Full-system backtest: 2025-10-01 to 2026-10-16

Run label `orb_nobody`, 258 trading sessions, generated 2026-10-20 20:03.  Overrides: {'ENABLE_EMA_STRATEGY': 'false', 'ENABLE_ORB_STRATEGY': 'true', 'ENABLE_PIVOT_STRATEGY': 'false', 'ENABLE_VWAP_STRATEGY': 'false', 'ENABLE_TRB_STRATEGY': 'false', 'ENABLE_MOMENTUM_PHASE': 'false', 'ENABLE_NATR_STRATEGY': 'false', 'ENABLE_PDHL_STRATEGY': 'false', 'ENABLE_OB_STRATEGY': 'false', 'ENABLE_ATR_COPILOT_STRATEGY': 'false', 'SMART_ENTRY_MIN_BODY_ATR_RATIO': '0.0'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 14 |
| Win % | 42.90 |
| Net P&L (Rs) | 11,408 |
| Gross P&L (Rs) | 12,752 |
| Costs (Rs) | 1,344 |
|   of which charges (Rs) | 784 |
|   of which slippage (Rs) | 560 |
| Avg cost per trade (Rs) | 96 |
| Profit factor | 2.45 |
| Avg trade (Rs) | 815 |
| Avg win (Rs) | 3,215 |
| Avg loss (Rs) | -985 |
| Largest win (Rs) | 5,103 |
| Largest loss (Rs) | -2,438 |
| Max drawdown (Rs) | -2,481 |
| Longest losing streak | 2 |
| Avg hold (min) | 70.60 |


Trades on 13 of 258 sessions; 46% of trading days were green.  Average 1.1 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| ORB | CE | 6 | 50 | 7,474 | 1,246 | 3.33 |
| ORB | PE | 8 | 37.50 | 3,934 | 492 | 1.84 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| IDX_SL_HIT | 5 | 0 | -7,663 | -1,533 | 0 | 34 |
| IDX_TSL_HIT | 4 | 75 | 4,814 | 1,203 | 230 | 140 |
| IDX_TARGET | 3 | 100 | 14,454 | 4,818 | inf | 68 |
| IDX_BE_STOP | 2 | 0 | -196 | -98 | 0 | 26 |


### Exit reason by strategy (trade count)

| exit_reason | ORB |
|---|---:|
| IDX_BE_STOP | 2 |
| IDX_SL_HIT | 5 |
| IDX_TARGET | 3 |
| IDX_TSL_HIT | 4 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| TRAIL | 7 | 85.70 | 19,267 | 2,752 | 917 |
| INITIAL | 5 | 0 | -7,663 | -1,533 | 0 |
| BE | 2 | 0 | -196 | -98 | 0 |


- Trades whose stop moved at least once: 9 of 14 (64%); average 7.3 moves per trade.

- Full initial-stop losses: 5 (36%).

- Of the 9 trades that reached +1R, the exit kept on average 58% of the best index move (median 57%); 33% of them still closed at a net loss.

- Median best move (MFE) 1.19R; 64% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 8 | 50 | 9,134 | 1,142 | 3.16 |
| H2 | 6 | 33.30 | 2,274 | 379 | 1.62 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2025 | 3 | 33.30 | 1,084 | 361 | 1.34 |
| 2026 | 11 | 45.50 | 10,323 | 938 | 3.19 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2025-10 | 1 | 0 | -1,912 | -1,912 | 0 | -1,912 |
| 2025-11 | 1 | 0 | -1,253 | -1,253 | 0 | -3,165 |
| 2025-12 | 1 | 100 | 4,249 | 4,249 | inf | 1,084 |
| 2026-01 | 2 | 100 | 4,006 | 2,003 | inf | 5,090 |
| 2026-02 | 2 | 0 | -1,058 | -529 | 0 | 4,032 |
| 2026-03 | 1 | 100 | 5,102 | 5,102 | inf | 9,134 |
| 2026-04 | 2 | 50 | 3,946 | 1,973 | 4.41 | 13,080 |
| 2026-06 | 1 | 0 | -2,438 | -2,438 | 0 | 10,642 |
| 2026-07 | 1 | 0 | -43 | -43 | 0 | 10,599 |
| 2026-08 | 1 | 100 | 829 | 829 | inf | 11,428 |
| 2026-10 | 1 | 0 | -21 | -21 | 0 | 11,407 |


45% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 14 | 42.90 | 11,408 | 815 | 2.45 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Tue | 2 | 50 | 238 | 119 | 1.10 |
| Wed | 2 | 100 | 5,931 | 2,965 | inf |
| Thu | 8 | 25 | 5,821 | 728 | 2.65 |
| Fri | 2 | 50 | -582 | -291 | 0.70 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 5 | 60 | 485 | 97 | 1.11 |
| yes | 9 | 33.30 | 10,923 | 1,214 | 4.09 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| PE_ORB | 46 |
| CE_ORB | 43 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| ENTRY_BLOCKED_MAX_RISK | 43 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not rising for CE | 7 |
| SMART_ENTRY_BLOCKED_EMA_GAP | 5 |
| SMART_ENTRY_BLOCKED_EMA_GAP_SHRINKING: EMA gap not widening | 3 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not falling for PE | 1 |
| SMART_ENTRY_BLOCKED_COOLDOWN | 1 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-04-30 09:40:00 | ORB | PE | 163 | 423 | IDX_TARGET | TRAIL | 5,103 |
| 2026-03-25 09:30:00 | ORB | CE | 188 | 448 | IDX_TARGET | TRAIL | 5,102 |
| 2025-12-04 09:30:00 | ORB | CE | 127 | 344 | IDX_TARGET | TRAIL | 4,249 |
| 2026-01-20 09:30:00 | ORB | PE | 276 | 415 | IDX_TSL_HIT | TRAIL | 2,676 |
| 2026-01-02 09:35:00 | ORB | CE | 442 | 514 | IDX_TSL_HIT | TRAIL | 1,330 |
| 2026-08-19 09:40:00 | ORB | PE | 188 | 235 | IDX_TSL_HIT | TRAIL | 829 |
| 2026-10-08 09:30:00 | ORB | PE | 131 | 135 | IDX_TSL_HIT | TRAIL | -21.03 |
| 2026-07-02 09:35:00 | ORB | CE | 119 | 122 | IDX_BE_STOP | BE | -42.56 |
| 2026-02-05 09:40:00 | ORB | PE | 101 | 97.95 | IDX_BE_STOP | BE | -154 |
| 2026-02-12 09:30:00 | ORB | PE | 84.90 | 44.15 | IDX_SL_HIT | INITIAL | -904 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-06-30 09:30:00 | ORB | PE | 310 | 193 | IDX_SL_HIT | INITIAL | -2,438 |
| 2025-10-31 09:40:00 | ORB | CE | 558 | 468 | IDX_SL_HIT | INITIAL | -1,912 |
| 2025-11-27 09:30:00 | ORB | CE | 121 | 63 | IDX_SL_HIT | INITIAL | -1,253 |
| 2026-04-30 09:30:00 | ORB | PE | 126 | 72.35 | IDX_SL_HIT | INITIAL | -1,156 |
| 2026-02-12 09:30:00 | ORB | PE | 84.90 | 44.15 | IDX_SL_HIT | INITIAL | -904 |
| 2026-02-05 09:40:00 | ORB | PE | 101 | 97.95 | IDX_BE_STOP | BE | -154 |
| 2026-07-02 09:35:00 | ORB | CE | 119 | 122 | IDX_BE_STOP | BE | -42.56 |
| 2026-10-08 09:30:00 | ORB | PE | 131 | 135 | IDX_TSL_HIT | TRAIL | -21.03 |
| 2026-08-19 09:40:00 | ORB | PE | 188 | 235 | IDX_TSL_HIT | TRAIL | 829 |
| 2026-01-02 09:35:00 | ORB | CE | 442 | 514 | IDX_TSL_HIT | TRAIL | 1,330 |


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
| TREND_GATE_STRATEGIES | frozenset({'EMA', 'VWAP', 'TRB', 'NATR'}) |
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
