# Full-system backtest: 2024-01-15 to 2026-10-16

Run label `v4_pivot_pe_only`, 683 trading sessions, generated 2026-10-20 02:18.  Overrides: {'ENABLE_ORB_STRATEGY': 'false', 'ENABLE_EMA_STRATEGY': 'false'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 224 |
| Win % | 21.40 |
| Net P&L (Rs) | -20,962 |
| Gross P&L (Rs) | 1,326 |
| Costs (Rs) | 22,288 |
|   of which charges (Rs) | 13,328 |
|   of which slippage (Rs) | 8,960 |
| Avg cost per trade (Rs) | 100 |
| Profit factor | 0.80 |
| Avg trade (Rs) | -94 |
| Avg win (Rs) | 1,782 |
| Avg loss (Rs) | -605 |
| Largest win (Rs) | 10,332 |
| Largest loss (Rs) | -2,226 |
| Max drawdown (Rs) | -34,932 |
| Longest losing streak | 20 |
| Avg hold (min) | 22.60 |


Trades on 170 of 683 sessions; 25% of trading days were green.  Average 6.9 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| PIVOT | PE | 224 | 21.40 | -20,962 | -94 | 0.80 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| PIVOT_SL_HIT | 97 | 0 | -92,076 | -949 | 0 | 12 |
| PIVOT_BE_STOP | 83 | 14.50 | -13,274 | -160 | 0.03 | 22 |
| PIVOT_TSL_HIT | 27 | 100 | 63,427 | 2,349 | inf | 40 |
| STOP_HIT | 7 | 0 | -618 | -88 | 0 | 76 |
| EOD_SQUARE_OFF | 6 | 83.30 | 5,153 | 859 | 42.43 | 42 |
| PIVOT_TARGET_T3 | 4 | 100 | 16,425 | 4,106 | inf | 47 |


### Exit reason by strategy (trade count)

| exit_reason | PIVOT |
|---|---:|
| EOD_SQUARE_OFF | 6 |
| PIVOT_BE_STOP | 83 |
| PIVOT_SL_HIT | 97 |
| PIVOT_TARGET_T3 | 4 |
| PIVOT_TSL_HIT | 27 |
| STOP_HIT | 7 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| INITIAL | 99 | 1 | -91,973 | -929 | 0 |
| BE | 95 | 17.90 | -7,326 | -77 | 0.49 |
| T1 | 24 | 100 | 52,291 | 2,179 | inf |
| T2 | 6 | 100 | 26,045 | 4,341 | inf |


- Trades whose stop moved at least once: 125 of 224 (56%); average 1.5 moves per trade.

- Full initial-stop losses: 99 (44%).

- Of the 90 trades that reached +1R, the exit kept on average 32% of the best index move (median 30%); 52% of them still closed at a net loss.

- Median best move (MFE) 0.81R; 40% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 125 | 18.40 | -21,904 | -175 | 0.66 |
| H2 | 99 | 25.30 | 942 | 10 | 1.02 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2024 | 88 | 18.20 | -22,517 | -256 | 0.49 |
| 2025 | 86 | 18.60 | -11,368 | -132 | 0.74 |
| 2026 | 50 | 32 | 12,923 | 258 | 1.71 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2024-01 | 4 | 0 | -1,269 | -317 | 0 | -1,269 |
| 2024-02 | 6 | 50 | -2,155 | -359 | 0.01 | -3,424 |
| 2024-03 | 7 | 28.60 | -4,306 | -615 | 0.01 | -7,730 |
| 2024-04 | 6 | 16.70 | 72 | 12 | 1.03 | -7,658 |
| 2024-05 | 11 | 9.10 | -7,868 | -715 | 0.02 | -15,526 |
| 2024-06 | 4 | 0 | -3,148 | -787 | 0 | -18,674 |
| 2024-07 | 6 | 0 | -2,614 | -436 | 0 | -21,288 |
| 2024-08 | 6 | 0 | -1,798 | -300 | 0 | -23,086 |
| 2024-09 | 8 | 25 | -410 | -51 | 0.88 | -23,496 |
| 2024-10 | 11 | 9.10 | -6,234 | -567 | 0.15 | -29,730 |
| 2024-11 | 9 | 44.40 | 10,345 | 1,149 | 4.74 | -19,385 |
| 2024-12 | 10 | 20 | -3,133 | -313 | 0.35 | -22,518 |
| 2025-01 | 8 | 25 | 8,476 | 1,060 | 3.27 | -14,042 |
| 2025-02 | 5 | 20 | 1,215 | 243 | 1.55 | -12,827 |
| 2025-03 | 4 | 50 | 4,627 | 1,157 | 4.51 | -8,200 |
| 2025-04 | 10 | 20 | -5,330 | -533 | 0.01 | -13,530 |
| 2025-05 | 10 | 0 | -8,376 | -838 | 0 | -21,906 |
| 2025-06 | 7 | 28.60 | -1,538 | -220 | 0.44 | -23,444 |
| 2025-07 | 10 | 20 | -2,434 | -243 | 0.45 | -25,878 |
| 2025-08 | 12 | 16.70 | -3,294 | -274 | 0.57 | -29,172 |
| 2025-09 | 9 | 11.10 | -3,577 | -397 | 0.29 | -32,749 |
| 2025-10 | 4 | 50 | 1,443 | 361 | 2.61 | -31,306 |
| 2025-11 | 5 | 0 | -1,513 | -303 | 0 | -32,819 |
| 2025-12 | 2 | 0 | -1,068 | -534 | 0 | -33,887 |
| 2026-01 | 7 | 42.90 | 6,786 | 969 | 16.64 | -27,101 |
| 2026-02 | 10 | 20 | -2,750 | -275 | 0.46 | -29,851 |
| 2026-03 | 1 | 100 | 3,710 | 3,710 | inf | -26,141 |
| 2026-04 | 1 | 0 | -1,419 | -1,419 | 0 | -27,560 |
| 2026-05 | 6 | 16.70 | -2,117 | -353 | 0.10 | -29,677 |
| 2026-06 | 8 | 25 | -5,361 | -670 | 0.12 | -35,038 |
| 2026-07 | 2 | 50 | 2,326 | 1,163 | 4.69 | -32,712 |
| 2026-08 | 9 | 33.30 | 1,594 | 177 | 2.65 | -31,118 |
| 2026-09 | 2 | 50 | 2,946 | 1,473 | 6.05 | -28,172 |
| 2026-10 | 4 | 50 | 7,208 | 1,802 | 14.56 | -20,964 |


35% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 50 | 24 | 6,113 | 122 | 1.23 |
| 10:00 | 41 | 22 | -4,344 | -106 | 0.74 |
| 11:00 | 27 | 7.40 | -12,836 | -475 | 0.20 |
| 12:00 | 35 | 25.70 | 160 | 5 | 1.01 |
| 13:00 | 32 | 28.10 | 5,252 | 164 | 1.39 |
| 14:00 | 39 | 17.90 | -15,308 | -393 | 0.22 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Mon | 34 | 23.50 | -9,549 | -281 | 0.55 |
| Tue | 58 | 25.90 | 9,031 | 156 | 1.40 |
| Wed | 57 | 15.80 | -13,149 | -231 | 0.55 |
| Thu | 42 | 23.80 | 249 | 6 | 1.01 |
| Fri | 33 | 18.20 | -7,544 | -229 | 0.55 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 194 | 22.20 | -28,576 | -147 | 0.70 |
| yes | 30 | 16.70 | 7,614 | 254 | 1.74 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| PE_PIVOT | 258 |
| CE_PIVOT | 253 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| BACKTEST_FILTER_BLOCKED: signal CE_PIVOT skipped | 252 |
| ENTRY_BLOCKED_MAX_RISK | 2 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2025-01-21 09:45:00 | PIVOT | PE | 133 | 655 | PIVOT_TARGET_T3 | T2 | 10,332 |
| 2025-03-03 09:35:00 | PIVOT | PE | 215 | 480 | PIVOT_TSL_HIT | T2 | 5,199 |
| 2026-10-14 12:50:00 | PIVOT | PE | 242 | 501 | PIVOT_TSL_HIT | T1 | 5,086 |
| 2024-11-07 09:35:00 | PIVOT | PE | 268 | 508 | PIVOT_TSL_HIT | T1 | 4,706 |
| 2024-11-12 12:00:00 | PIVOT | PE | 340 | 573 | PIVOT_TSL_HIT | T1 | 4,550 |
| 2026-03-11 09:35:00 | PIVOT | PE | 359 | 550 | PIVOT_TSL_HIT | T2 | 3,710 |
| 2024-11-14 10:20:00 | PIVOT | PE | 103 | 289 | PIVOT_TSL_HIT | T1 | 3,624 |
| 2026-09-15 13:10:00 | PIVOT | PE | 290 | 472 | PIVOT_TSL_HIT | T1 | 3,529 |
| 2025-02-13 13:10:00 | PIVOT | PE | 490 | 665 | PIVOT_TSL_HIT | T1 | 3,406 |
| 2024-09-18 13:25:00 | PIVOT | PE | 324 | 485 | PIVOT_TARGET_T3 | T2 | 3,113 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-06-24 09:50:00 | PIVOT | PE | 233 | 127 | PIVOT_SL_HIT | INITIAL | -2,226 |
| 2025-05-21 14:05:00 | PIVOT | PE | 709 | 609 | PIVOT_SL_HIT | INITIAL | -2,101 |
| 2026-02-20 13:10:00 | PIVOT | PE | 575 | 480 | PIVOT_SL_HIT | INITIAL | -2,006 |
| 2024-10-08 10:15:00 | PIVOT | PE | 454 | 368 | PIVOT_SL_HIT | INITIAL | -1,828 |
| 2026-06-05 14:40:00 | PIVOT | PE | 550 | 464 | PIVOT_SL_HIT | INITIAL | -1,816 |
| 2024-05-06 10:00:00 | PIVOT | PE | 492 | 407 | PIVOT_SL_HIT | INITIAL | -1,797 |
| 2024-05-10 11:00:00 | PIVOT | PE | 145 | 65.50 | PIVOT_SL_HIT | INITIAL | -1,681 |
| 2024-06-05 09:30:00 | PIVOT | PE | 476 | 398 | PIVOT_BE_STOP | BE | -1,678 |
| 2024-05-06 11:25:00 | PIVOT | PE | 492 | 414 | PIVOT_SL_HIT | INITIAL | -1,655 |
| 2024-12-02 09:30:00 | PIVOT | PE | 482 | 406 | PIVOT_SL_HIT | INITIAL | -1,627 |


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
| TREND_GATE_STRATEGIES | frozenset({'TRB', 'VWAP', 'EMA', 'NATR'}) |
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
