# Full-system backtest: 2024-01-15 to 2026-10-16

Run label `v3_orb_only`, 683 trading sessions, generated 2026-10-20 02:18.  Overrides: {'ENABLE_PIVOT_STRATEGY': 'false', 'ENABLE_EMA_STRATEGY': 'false'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 35 |
| Win % | 42.90 |
| Net P&L (Rs) | 11,873 |
| Gross P&L (Rs) | 15,187 |
| Costs (Rs) | 3,314 |
|   of which charges (Rs) | 1,914 |
|   of which slippage (Rs) | 1,400 |
| Avg cost per trade (Rs) | 95 |
| Profit factor | 1.49 |
| Avg trade (Rs) | 339 |
| Avg win (Rs) | 2,394 |
| Avg loss (Rs) | -1,202 |
| Largest win (Rs) | 5,102 |
| Largest loss (Rs) | -2,203 |
| Max drawdown (Rs) | -8,684 |
| Longest losing streak | 5 |
| Avg hold (min) | 60.70 |


Trades on 33 of 683 sessions; 45% of trading days were green.  Average 1.1 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| ORB | CE | 15 | 33.30 | -252 | -17 | 0.98 |
| ORB | PE | 20 | 50 | 12,125 | 606 | 2.11 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| IDX_SL_HIT | 14 | 0 | -21,096 | -1,507 | 0 | 25 |
| IDX_TSL_HIT | 8 | 87.50 | 9,858 | 1,232 | 470 | 130 |
| IDX_TARGET | 7 | 100 | 25,889 | 3,698 | inf | 63 |
| IDX_BE_STOP | 3 | 0 | -336 | -112 | 0 | 19 |
| STOP_HIT | 3 | 33.30 | -2,442 | -814 | 0.06 | 82 |


### Exit reason by strategy (trade count)

| exit_reason | ORB |
|---|---:|
| IDX_BE_STOP | 3 |
| IDX_SL_HIT | 14 |
| IDX_TARGET | 7 |
| IDX_TSL_HIT | 8 |
| STOP_HIT | 3 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| INITIAL | 16 | 0 | -23,683 | -1,480 | 0 |
| TRAIL | 15 | 93.30 | 33,678 | 2,245 | 1,602 |
| BE | 4 | 25 | 1,878 | 469 | 6.58 |


- Trades whose stop moved at least once: 19 of 35 (54%); average 6.7 moves per trade.

- Full initial-stop losses: 16 (46%).

- Of the 19 trades that reached +1R, the exit kept on average 61% of the best index move (median 65%); 21% of them still closed at a net loss.

- Median best move (MFE) 1.04R; 54% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 17 | 41.20 | -804 | -47 | 0.95 |
| H2 | 18 | 44.40 | 12,677 | 704 | 2.63 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2024 | 11 | 36.40 | 1,371 | 125 | 1.12 |
| 2025 | 14 | 42.90 | -1,909 | -136 | 0.82 |
| 2026 | 10 | 50 | 12,411 | 1,241 | 6.45 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2024-02 | 2 | 0 | -2,547 | -1,273 | 0 | -2,547 |
| 2024-03 | 1 | 100 | 2,214 | 2,214 | inf | -333 |
| 2024-05 | 2 | 0 | -4,192 | -2,096 | 0 | -4,525 |
| 2024-06 | 1 | 0 | -2,045 | -2,045 | 0 | -6,570 |
| 2024-07 | 2 | 0 | -2,447 | -1,223 | 0 | -9,017 |
| 2024-10 | 2 | 100 | 6,734 | 3,367 | inf | -2,283 |
| 2024-12 | 1 | 100 | 3,653 | 3,653 | inf | 1,370 |
| 2025-02 | 3 | 66.70 | 1,534 | 511 | 2.32 | 2,904 |
| 2025-04 | 1 | 0 | -2,146 | -2,146 | 0 | 758 |
| 2025-05 | 2 | 50 | -1,562 | -781 | 0.09 | -804 |
| 2025-07 | 3 | 33.30 | -1,118 | -373 | 0.59 | -1,922 |
| 2025-08 | 2 | 50 | 2,027 | 1,014 | 2.44 | 105 |
| 2025-09 | 1 | 100 | 750 | 750 | inf | 855 |
| 2025-11 | 1 | 0 | -1,253 | -1,253 | 0 | -398 |
| 2025-12 | 1 | 0 | -140 | -140 | 0 | -538 |
| 2026-01 | 2 | 100 | 4,006 | 2,003 | inf | 3,468 |
| 2026-02 | 2 | 0 | -1,058 | -529 | 0 | 2,410 |
| 2026-03 | 1 | 100 | 5,102 | 5,102 | inf | 7,512 |
| 2026-04 | 2 | 50 | 3,596 | 1,798 | 4.11 | 11,108 |
| 2026-07 | 1 | 0 | -43 | -43 | 0 | 11,065 |
| 2026-08 | 1 | 100 | 829 | 829 | inf | 11,894 |
| 2026-10 | 1 | 0 | -21 | -21 | 0 | 11,873 |


45% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 35 | 42.90 | 11,873 | 339 | 1.49 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Tue | 9 | 55.60 | 911 | 101 | 1.14 |
| Wed | 4 | 50 | 2,816 | 704 | 1.90 |
| Thu | 15 | 40 | 10,768 | 718 | 2.57 |
| Fri | 7 | 28.60 | -2,622 | -375 | 0.66 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 11 | 63.60 | 6,356 | 578 | 2.01 |
| yes | 24 | 33.30 | 5,517 | 230 | 1.31 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| PE_ORB | 127 |
| CE_ORB | 94 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| SMART_ENTRY_BLOCKED_BODY | 81 |
| ENTRY_BLOCKED_MAX_RISK | 68 |
| SMART_ENTRY_BLOCKED_EMA_GAP_SHRINKING: EMA gap not widening | 8 |
| SMART_ENTRY_BLOCKED_EMA_GAP | 7 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not falling for PE | 5 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not rising for CE | 1 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-03-25 09:30:00 | ORB | CE | 188 | 448 | IDX_TARGET | TRAIL | 5,102 |
| 2026-04-30 09:35:00 | ORB | PE | 155 | 397 | IDX_TARGET | TRAIL | 4,753 |
| 2024-12-13 09:30:00 | ORB | PE | 98.25 | 286 | IDX_TARGET | TRAIL | 3,653 |
| 2024-10-31 09:30:00 | ORB | PE | 137 | 321 | IDX_TARGET | TRAIL | 3,586 |
| 2025-08-12 09:30:00 | ORB | CE | 108 | 285 | IDX_TARGET | TRAIL | 3,434 |
| 2024-10-17 09:35:00 | ORB | PE | 225 | 387 | IDX_TARGET | TRAIL | 3,148 |
| 2026-01-20 09:30:00 | ORB | PE | 276 | 415 | IDX_TSL_HIT | TRAIL | 2,676 |
| 2025-02-06 09:30:00 | ORB | PE | 509 | 632 | IDX_TSL_HIT | TRAIL | 2,351 |
| 2024-03-28 09:40:00 | ORB | CE | 85.15 | 200 | IDX_TARGET | BE | 2,214 |
| 2025-07-10 09:35:00 | ORB | PE | 423 | 508 | IDX_TSL_HIT | TRAIL | 1,596 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2024-05-31 09:35:00 | ORB | CE | 199 | 93.40 | IDX_SL_HIT | INITIAL | -2,203 |
| 2025-04-29 09:35:00 | ORB | CE | 146 | 43.70 | IDX_SL_HIT | INITIAL | -2,146 |
| 2024-06-20 09:40:00 | ORB | PE | 260 | 162 | IDX_SL_HIT | INITIAL | -2,045 |
| 2024-05-24 09:30:00 | ORB | CE | 183 | 87.85 | IDX_SL_HIT | INITIAL | -1,989 |
| 2025-05-13 09:35:00 | ORB | PE | 157 | 75.70 | IDX_SL_HIT | INITIAL | -1,708 |
| 2024-07-24 09:35:00 | ORB | CE | 317 | 242 | IDX_SL_HIT | INITIAL | -1,581 |
| 2025-07-16 09:35:00 | ORB | PE | 468 | 397 | IDX_SL_HIT | INITIAL | -1,534 |
| 2025-08-26 09:35:00 | ORB | PE | 122 | 56.15 | STOP_HIT | INITIAL | -1,407 |
| 2024-02-02 09:40:00 | ORB | CE | 129 | 67.45 | IDX_SL_HIT | INITIAL | -1,324 |
| 2025-11-27 09:30:00 | ORB | CE | 121 | 63 | IDX_SL_HIT | INITIAL | -1,253 |


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
| TREND_GATE_STRATEGIES | frozenset({'NATR', 'TRB', 'EMA', 'VWAP'}) |
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
