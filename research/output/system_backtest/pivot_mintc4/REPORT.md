# Full-system backtest: 2025-10-01 to 2026-10-16

Run label `pivot_mintc4`, 258 trading sessions, generated 2026-10-20 18:54.  Overrides: {'ENABLE_EMA_STRATEGY': 'false', 'ENABLE_ORB_STRATEGY': 'false', 'ENABLE_VWAP_STRATEGY': 'false', 'ENABLE_TRB_STRATEGY': 'false', 'ENABLE_MOMENTUM_PHASE': 'false', 'ENABLE_NATR_STRATEGY': 'false', 'ENABLE_PDHL_STRATEGY': 'false', 'ENABLE_OB_STRATEGY': 'false', 'ENABLE_ATR_COPILOT_STRATEGY': 'false', 'ENABLE_PIVOT_STRATEGY': 'true', 'PIVOT_MIN_TODAY_CANDLES': '4'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 91 |
| Win % | 34.10 |
| Net P&L (Rs) | 40,025 |
| Gross P&L (Rs) | 49,059 |
| Costs (Rs) | 9,034 |
|   of which charges (Rs) | 5,394 |
|   of which slippage (Rs) | 3,640 |
| Avg cost per trade (Rs) | 99 |
| Profit factor | 2.31 |
| Avg trade (Rs) | 440 |
| Avg win (Rs) | 2,275 |
| Avg loss (Rs) | -508 |
| Largest win (Rs) | 7,068 |
| Largest loss (Rs) | -2,226 |
| Max drawdown (Rs) | -4,514 |
| Longest losing streak | 11 |
| Avg hold (min) | 36.20 |


Trades on 72 of 258 sessions; 40% of trading days were green.  Average 7.4 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| PIVOT | CE | 50 | 30 | 21,704 | 434 | 2.16 |
| PIVOT | PE | 41 | 39 | 18,321 | 447 | 2.54 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| PIVOT_BE_STOP | 32 | 6.20 | -5,526 | -173 | 0.01 | 24 |
| PIVOT_TSL_HIT | 24 | 95.80 | 56,897 | 2,371 | 760 | 54 |
| PIVOT_SL_HIT | 23 | 0 | -22,675 | -986 | 0 | 12 |
| STOP_HIT | 6 | 0 | -2,177 | -363 | 0 | 45 |
| PIVOT_TARGET_T3 | 4 | 100 | 7,347 | 1,837 | inf | 103 |
| EOD_SQUARE_OFF | 2 | 100 | 6,159 | 3,080 | inf | 120 |


### Exit reason by strategy (trade count)

| exit_reason | PIVOT |
|---|---:|
| EOD_SQUARE_OFF | 2 |
| PIVOT_BE_STOP | 32 |
| PIVOT_SL_HIT | 23 |
| PIVOT_TARGET_T3 | 4 |
| PIVOT_TSL_HIT | 24 |
| STOP_HIT | 6 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| BE | 42 | 19 | 7,519 | 179 | 2.24 |
| INITIAL | 25 | 0 | -24,392 | -976 | 0 |
| T1 | 21 | 95.20 | 44,734 | 2,130 | 598 |
| T2 | 3 | 100 | 12,163 | 4,054 | inf |


- Trades whose stop moved at least once: 66 of 91 (73%); average 2.2 moves per trade.

- Full initial-stop losses: 25 (27%).

- Of the 51 trades that reached +1R, the exit kept on average 47% of the best index move (median 57%); 41% of them still closed at a net loss.

- Median best move (MFE) 1.10R; 56% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 47 | 34 | 25,768 | 548 | 2.69 |
| H2 | 44 | 34.10 | 14,257 | 324 | 1.93 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2025 | 22 | 22.70 | -1,258 | -57 | 0.83 |
| 2026 | 69 | 37.70 | 41,283 | 598 | 2.78 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2025-10 | 6 | 50 | -297 | -50 | 0.88 | -297 |
| 2025-11 | 12 | 16.70 | 1,274 | 106 | 1.51 | 977 |
| 2025-12 | 4 | 0 | -2,234 | -559 | 0 | -1,257 |
| 2026-01 | 7 | 42.90 | 6,574 | 939 | 11.19 | 5,317 |
| 2026-02 | 13 | 30.80 | 841 | 65 | 1.13 | 6,158 |
| 2026-03 | 3 | 66.70 | 9,941 | 3,314 | 12.87 | 16,099 |
| 2026-04 | 3 | 100 | 12,338 | 4,113 | inf | 28,437 |
| 2026-05 | 9 | 11.10 | -4,358 | -484 | 0.05 | 24,079 |
| 2026-06 | 10 | 40 | 3,157 | 316 | 1.72 | 27,236 |
| 2026-07 | 5 | 20 | 1,103 | 221 | 2.05 | 28,339 |
| 2026-08 | 7 | 42.90 | 1,425 | 204 | 2.26 | 29,764 |
| 2026-09 | 6 | 33.30 | 2,419 | 403 | 2.27 | 32,183 |
| 2026-10 | 6 | 50 | 7,843 | 1,307 | 4.57 | 40,026 |


77% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 11 | 18.20 | -773 | -70 | 0.88 |
| 10:00 | 23 | 34.80 | 5,632 | 245 | 1.80 |
| 11:00 | 18 | 33.30 | 10,498 | 583 | 2.72 |
| 12:00 | 16 | 43.80 | 8,912 | 557 | 4.26 |
| 13:00 | 23 | 34.80 | 15,755 | 685 | 2.96 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Mon | 21 | 38.10 | 18,235 | 868 | 3.85 |
| Tue | 26 | 34.60 | 10,426 | 401 | 2.40 |
| Wed | 23 | 34.80 | 5,205 | 226 | 1.47 |
| Thu | 21 | 28.60 | 6,159 | 293 | 2.12 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 74 | 36.50 | 37,960 | 513 | 2.46 |
| yes | 17 | 23.50 | 2,065 | 121 | 1.45 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| CE_PIVOT | 56 |
| PE_PIVOT | 44 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| PIVOT_BLOCKED_FRIDAY | 3,774 |
| PIVOT_BLOCKED_TIME | 3,699 |
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
| 2026-01-27 10:40:00 | PIVOT | PE | 381 | 525 | PIVOT_TSL_HIT | T1 | 2,771 |
| 2026-04-30 13:00:00 | PIVOT | CE | 821 | 960 | PIVOT_TSL_HIT | T1 | 2,667 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-06-24 09:50:00 | PIVOT | PE | 233 | 127 | PIVOT_SL_HIT | INITIAL | -2,226 |
| 2026-02-23 09:50:00 | PIVOT | CE | 463 | 377 | PIVOT_SL_HIT | INITIAL | -1,812 |
| 2026-02-02 13:10:00 | PIVOT | CE | 464 | 385 | PIVOT_SL_HIT | INITIAL | -1,669 |
| 2025-10-08 13:50:00 | PIVOT | CE | 208 | 131 | PIVOT_SL_HIT | INITIAL | -1,629 |
| 2026-05-13 13:05:00 | PIVOT | CE | 325 | 252 | PIVOT_SL_HIT | INITIAL | -1,557 |
| 2026-09-15 11:45:00 | PIVOT | CE | 297 | 245 | PIVOT_SL_HIT | INITIAL | -1,145 |
| 2026-02-25 10:20:00 | PIVOT | CE | 262 | 211 | PIVOT_SL_HIT | INITIAL | -1,116 |
| 2026-06-30 10:45:00 | PIVOT | PE | 315 | 266 | PIVOT_SL_HIT | INITIAL | -1,069 |
| 2026-05-06 12:55:00 | PIVOT | PE | 282 | 240 | PIVOT_SL_HIT | INITIAL | -940 |
| 2026-10-01 10:35:00 | PIVOT | CE | 83 | 40.65 | STOP_HIT | INITIAL | -936 |


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
| TREND_GATE_STRATEGIES | frozenset({'TRB', 'EMA', 'VWAP', 'NATR'}) |
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
