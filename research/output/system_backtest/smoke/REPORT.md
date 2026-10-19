# Full-system backtest: 2026-09-01 to 2026-09-30

Run label `smoke`, 21 trading sessions, generated 2026-10-20 02:05.  Overrides: none (current .env).

## Headline

| Metric | Value |
|---|---:|
| Trades | 8.00 |
| Win % | 50.00 |
| Net P&L (Rs) | 3,985 |
| Gross P&L (Rs) | 4,748 |
| Costs (Rs) | 763 |
| Profit factor | 3.09 |
| Avg trade (Rs) | 498 |
| Avg win (Rs) | 1,473 |
| Avg loss (Rs) | -477 |
| Largest win (Rs) | 3,529 |
| Largest loss (Rs) | -1,145 |
| Max drawdown (Rs) | -1,145 |
| Longest losing streak | 3.00 |
| Avg hold (min) | 34.30 |


Trades on 5 of 21 sessions; 80% of trading days were green.  Average 8.0 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| EMA | PE | 1 | 100 | 928 | 928 | inf |
| PIVOT | CE | 5 | 40.00 | 111 | 22.00 | 1.08 |
| PIVOT | PE | 2 | 50.00 | 2,946 | 1,473 | 6.05 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| PIVOT_TSL_HIT | 3 | 100 | 4,966 | 1,655 | inf | 54.00 |
| PIVOT_BE_STOP | 2 | 0.00 | -180 | -90.00 | 0.00 | 6.00 |
| PIVOT_SL_HIT | 2 | 0.00 | -1,729 | -864 | 0.00 | 39.00 |
| EMA_TSL_HIT | 1 | 100 | 928 | 928 | inf | 24.00 |


### Exit reason by strategy (trade count)

| exit_reason | EMA | PIVOT |
|---|---:|---:|
| EMA_TSL_HIT | 1 | 0 |
| PIVOT_BE_STOP | 0 | 2 |
| PIVOT_SL_HIT | 0 | 2 |
| PIVOT_TSL_HIT | 0 | 3 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| T1 | 3 | 100 | 4,966 | 1,655 | inf |
| BE | 2 | 0.00 | -180 | -90.00 | 0.00 |
| nan | 2 | 0.00 | -1,729 | -864 | 0.00 |
| TRAIL | 1 | 100 | 928 | 928 | inf |


- Trades whose stop moved at least once: 6 of 8 (75%); average 4.0 moves per trade.

- Full initial-stop losses: 0 (0%).

- Profit capture: on average the exit kept -27% of the best index move seen during the trade (median 37%).

- Median best move (MFE) 1.75R; 62% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 3 | 66.70 | 3,312 | 1,104 | 3.89 |
| H2 | 5 | 40.00 | 673 | 135 | 1.88 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| 2,026 | 8 | 50.00 | 3,985 | 498 | 3.09 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2026-09 | 8 | 50.00 | 3,985 | 498 | 3.09 | 3,985 |


100% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 1 | 100 | 638 | 638 | inf |
| 10:00 | 3 | 33.30 | 74.00 | 25.00 | 1.10 |
| 11:00 | 3 | 33.30 | -256 | -85.00 | 0.78 |
| 13:00 | 1 | 100 | 3,529 | 3,529 | inf |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Tue | 4 | 25.00 | 1,659 | 415 | 1.89 |
| Wed | 2 | 100 | 1,726 | 863 | inf |
| Thu | 2 | 50.00 | 599 | 300 | 16.59 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| 0 | 6 | 50.00 | 3,385 | 564 | 2.81 |
| 1 | 2 | 50.00 | 599 | 300 | 16.59 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| PE | 24 |
| CE_PIVOT | 8 |
| PE_ORB | 5 |
| CE | 2 |
| PE_PIVOT | 2 |
| CE_ORB | 1 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| SMART_ENTRY_BLOCKED_EMA_GAP_SHRINKING: EMA gap not widening | 18 |
| SMART_ENTRY_BLOCKED_BODY | 7 |
| ENTRY_BLOCKED_MAX_RISK | 3 |
| TREND_GATE_BLOCKED: against daily trend (DOWN) | 2 |
| EMA_ENTRY_BLOCKED: room # < #R (#) | 1 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-09-15 13:10:00 | PIVOT | PE | 290 | 472 | PIVOT_TSL_HIT | T1 | 3,529 |
| 2026-09-09 11:50:00 | EMA | PE | 209 | 261 | EMA_TSL_HIT | TRAIL | 928 |
| 2026-09-23 10:30:00 | PIVOT | CE | 166 | 211 | PIVOT_TSL_HIT | T1 | 799 |
| 2026-09-17 09:30:00 | PIVOT | CE | 81.20 | 118 | PIVOT_TSL_HIT | T1 | 638 |
| 2026-09-17 11:30:00 | PIVOT | CE | 88.35 | 90.95 | PIVOT_BE_STOP | BE | -38.45 |
| 2026-09-22 10:05:00 | PIVOT | CE | 268 | 266 | PIVOT_BE_STOP | BE | -142 |
| 2026-09-22 10:55:00 | PIVOT | PE | 242 | 218 | PIVOT_SL_HIT | nan | -583 |
| 2026-09-15 11:45:00 | PIVOT | CE | 297 | 245 | PIVOT_SL_HIT | nan | -1,145 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-09-15 11:45:00 | PIVOT | CE | 297 | 245 | PIVOT_SL_HIT | nan | -1,145 |
| 2026-09-22 10:55:00 | PIVOT | PE | 242 | 218 | PIVOT_SL_HIT | nan | -583 |
| 2026-09-22 10:05:00 | PIVOT | CE | 268 | 266 | PIVOT_BE_STOP | BE | -142 |
| 2026-09-17 11:30:00 | PIVOT | CE | 88.35 | 90.95 | PIVOT_BE_STOP | BE | -38.45 |
| 2026-09-17 09:30:00 | PIVOT | CE | 81.20 | 118 | PIVOT_TSL_HIT | T1 | 638 |
| 2026-09-23 10:30:00 | PIVOT | CE | 166 | 211 | PIVOT_TSL_HIT | T1 | 799 |
| 2026-09-09 11:50:00 | EMA | PE | 209 | 261 | EMA_TSL_HIT | TRAIL | 928 |
| 2026-09-15 13:10:00 | PIVOT | PE | 290 | 472 | PIVOT_TSL_HIT | T1 | 3,529 |


## Configuration tested

| Setting | Value |
|---|---|
| ENABLE_PIVOT_STRATEGY | 1 |
| ENABLE_ORB_STRATEGY | 1 |
| ENABLE_EMA_STRATEGY | 1 |
| ENABLE_VWAP_STRATEGY | 0 |
| ENABLE_TRB_STRATEGY | 0 |
| ENABLE_MOMENTUM_PHASE | 0 |
| ENABLE_NATR_STRATEGY | 0 |
| ENABLE_PDHL_STRATEGY | 0 |
| ENABLE_OB_STRATEGY | 0 |
| ENABLE_ATR_COPILOT_STRATEGY | 0 |
| QUANTITY | 20 |
| FORCE_EXIT_TIME | 15:10 |
| NO_NEW_ENTRY_AFTER | 15:00 |
| MAX_TRADES_PER_SIDE | 3 |
| ENABLE_DAILY_LOSS_LIMIT | 1 |
| DAILY_LOSS_LIMIT_RUPEES | 5,000 |
| MAX_RISK_RUPEES_PER_TRADE | 2,000 |
| TREND_GATE_15M | 1 |
| TREND_GATE_DAILY | 1 |
| TREND_GATE_STRATEGIES | frozenset({'TRB', 'NATR', 'EMA', 'VWAP'}) |
| GENERIC_INDEX_EXITS | 1 |
| PIVOT_BE_TRIGGER_R | 0.75 |
| PIVOT_BE_BUFFER_PTS | 12.00 |
| PIVOT_TRAIL_ATR_MULT | 1.00 |
| PIVOT_T2_TRAIL_ATR_MULT | 0.75 |
| PIVOT_MAX_TRADES_PER_DAY | 3 |
| PIVOT_OPTION_DELTA | 0.40 |
| EMA_NO_NEW_ENTRY_AFTER | 12:00 |
| EMA_TRAIL_ATR_MULT | 1.00 |
| EMA_BE_TRIGGER_R | 1.00 |
| BE_TRIGGER_RR | 1.00 |
| GENERIC_TRAIL_ATR_MULT | 2.00 |
| MAX_SL_PCT | 0.50 |
| ATM_DELTA | 0.50 |
| EXPIRY_DAY_ROLLOVER_TIME | 12:30 |
| ENABLE_SMART_EXIT | 1 |


## How this backtest works

- **Production code, not a re-implementation.** Each session runs `main.BotContext`, `main.bootstrap_session`, the live tick handler, `execute_entry`, the Pivot / EMA / Index trade managers (SL, break-even, T1/T2 locks, chandelier trailing stop, targets), smart exits, the paper-broker SL backstop and `main._run_eod_exit`.  Signal de-duplication, daily caps, cooldowns, the trend gates, the rupee-risk cap and the daily loss limit all run from the bot's own SQLite tables.
- **No look-ahead.** The simulated Kite API only returns bars that had completed by the simulated time; signals fire on the first tick after a 5-minute candle closes, as live.
- **Price path.** Each 1-minute SENSEX bar is replayed as four ticks (up bar O,L,H,C; down bar O,H,L,C).  Intra-minute order beyond that is unknown.
- **Options are modelled, not historical.** Black-Scholes, IV = India VIX (minute), r = 6.5%.  Strike selection, ITM fallback and expiry-day rollover use the bot's own selector on a synthetic chain; weekly expiry calendar [['2000-01-01', 4], ['2025-01-01', 1], ['2025-09-01', 3]] (weekday 0 = Monday), moved to the previous session on holidays.  The model has no volatility smile, no intraday IV crush beyond VIX moves, and VIX (30-day, NIFTY) is a proxy for weekly SENSEX IV — expect real premiums, especially on expiry days, to differ.
- **Fills and costs.** SHADOW-mode paper fills at the modelled premium, then 1.0 option point(s) of slippage per side plus brokerage, STT, exchange, SEBI, stamp duty and GST are deducted per trade.  Quantity is today's lot (20) throughout.
- **Not modelled:** order rejections, partial fills, feed outages, margin limits.


Files: `trades.csv` (one row per trade, with exit reason, stop stage, MFE/MAE and costs), `events.csv` (signals, blocks, stop moves), `run_meta.json` (full settings snapshot).  Re-run: `python -m research.system_backtest`.
