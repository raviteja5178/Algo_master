# Full-system backtest: 2025-10-01 to 2026-10-16

Run label `orb_nofilters`, 258 trading sessions, generated 2026-10-20 20:03.  Overrides: {'ENABLE_EMA_STRATEGY': 'false', 'ENABLE_ORB_STRATEGY': 'true', 'ENABLE_PIVOT_STRATEGY': 'false', 'ENABLE_VWAP_STRATEGY': 'false', 'ENABLE_TRB_STRATEGY': 'false', 'ENABLE_MOMENTUM_PHASE': 'false', 'ENABLE_NATR_STRATEGY': 'false', 'ENABLE_PDHL_STRATEGY': 'false', 'ENABLE_OB_STRATEGY': 'false', 'ENABLE_ATR_COPILOT_STRATEGY': 'false', 'SMART_ENTRY_MIN_BODY_ATR_RATIO': '0.0', 'MAX_RISK_RUPEES_PER_TRADE': '5000'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 33 |
| Win % | 39.40 |
| Net P&L (Rs) | 658 |
| Gross P&L (Rs) | 3,903 |
| Costs (Rs) | 3,245 |
|   of which charges (Rs) | 1,925 |
|   of which slippage (Rs) | 1,320 |
| Avg cost per trade (Rs) | 98 |
| Profit factor | 1.02 |
| Avg trade (Rs) | 20 |
| Avg win (Rs) | 3,285 |
| Avg loss (Rs) | -2,102 |
| Largest win (Rs) | 6,774 |
| Largest loss (Rs) | -4,120 |
| Max drawdown (Rs) | -15,888 |
| Longest losing streak | 6 |
| Avg hold (min) | 156 |


Trades on 32 of 258 sessions; 41% of trading days were green.  Average 2.7 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| ORB | CE | 16 | 43.80 | 5,798 | 362 | 1.31 |
| ORB | PE | 17 | 35.30 | -5,140 | -302 | 0.78 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| IDX_SL_HIT | 14 | 0 | -34,690 | -2,478 | 0 | 99 |
| IDX_TSL_HIT | 9 | 88.90 | 27,362 | 3,040 | 1,302 | 213 |
| TIME_DECAY | 4 | 25 | -7,081 | -1,770 | 0.01 | 312 |
| IDX_TARGET | 3 | 100 | 14,454 | 4,818 | inf | 68 |
| IDX_BE_STOP | 2 | 0 | -196 | -98 | 0 | 26 |
| EOD_SQUARE_OFF | 1 | 100 | 809 | 809 | inf | 340 |


### Exit reason by strategy (trade count)

| exit_reason | ORB |
|---|---:|
| EOD_SQUARE_OFF | 1 |
| IDX_BE_STOP | 2 |
| IDX_SL_HIT | 14 |
| IDX_TARGET | 3 |
| IDX_TSL_HIT | 9 |
| TIME_DECAY | 4 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| INITIAL | 19 | 10.50 | -40,962 | -2,156 | 0.02 |
| TRAIL | 12 | 91.70 | 41,816 | 3,485 | 1,989 |
| BE | 2 | 0 | -196 | -98 | 0 |


- Trades whose stop moved at least once: 14 of 33 (42%); average 4.9 moves per trade.

- Full initial-stop losses: 19 (58%).

- Of the 14 trades that reached +1R, the exit kept on average 64% of the best index move (median 72%); 21% of them still closed at a net loss.

- Median best move (MFE) 0.78R; 42% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 17 | 35.30 | -7,226 | -425 | 0.70 |
| H2 | 16 | 43.80 | 7,884 | 493 | 1.44 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2025 | 9 | 22.20 | -12,015 | -1,335 | 0.26 |
| 2026 | 24 | 45.80 | 12,673 | 528 | 1.49 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2025-10 | 2 | 50 | -2,124 | -1,062 | 0.03 | -2,124 |
| 2025-11 | 3 | 0 | -8,705 | -2,902 | 0 | -10,829 |
| 2025-12 | 4 | 25 | -1,187 | -297 | 0.78 | -12,016 |
| 2026-01 | 4 | 50 | -2,759 | -690 | 0.59 | -14,775 |
| 2026-02 | 3 | 33.30 | 2,446 | 815 | 3.31 | -12,329 |
| 2026-03 | 1 | 100 | 5,102 | 5,102 | inf | -7,227 |
| 2026-04 | 2 | 50 | 3,946 | 1,973 | 4.41 | -3,281 |
| 2026-05 | 4 | 25 | -4,531 | -1,133 | 0.51 | -7,812 |
| 2026-06 | 1 | 0 | -2,438 | -2,438 | 0 | -10,250 |
| 2026-07 | 3 | 33.30 | 2,312 | 771 | 1.95 | -7,938 |
| 2026-08 | 1 | 100 | 1,461 | 1,461 | inf | -6,477 |
| 2026-09 | 3 | 66.70 | 381 | 127 | 1.14 | -6,096 |
| 2026-10 | 2 | 50 | 6,753 | 3,376 | 322 | 657 |


54% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 33 | 39.40 | 658 | 20 | 1.02 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Tue | 13 | 38.50 | -5,315 | -409 | 0.78 |
| Wed | 5 | 60 | 3,475 | 695 | 1.66 |
| Thu | 8 | 25 | 5,821 | 728 | 2.65 |
| Fri | 7 | 42.90 | -3,324 | -475 | 0.65 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 24 | 41.70 | -10,265 | -428 | 0.73 |
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
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not rising for CE | 7 |
| SMART_ENTRY_BLOCKED_EMA_GAP | 5 |
| ENTRY_BLOCKED_MAX_RISK | 5 |
| SMART_ENTRY_BLOCKED_EMA_GAP_SHRINKING: EMA gap not widening | 3 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not falling for PE | 1 |
| SMART_ENTRY_BLOCKED_COOLDOWN | 1 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-10-13 09:35:00 | ORB | CE | 373 | 718 | IDX_TSL_HIT | TRAIL | 6,774 |
| 2026-04-30 09:40:00 | ORB | PE | 163 | 423 | IDX_TARGET | TRAIL | 5,103 |
| 2026-03-25 09:30:00 | ORB | CE | 188 | 448 | IDX_TARGET | TRAIL | 5,102 |
| 2026-07-17 09:35:00 | ORB | CE | 565 | 808 | IDX_TSL_HIT | TRAIL | 4,752 |
| 2026-05-12 09:30:00 | ORB | PE | 404 | 643 | IDX_TSL_HIT | TRAIL | 4,673 |
| 2025-12-04 09:30:00 | ORB | CE | 127 | 344 | IDX_TARGET | TRAIL | 4,249 |
| 2026-02-24 09:35:00 | ORB | PE | 352 | 533 | IDX_TSL_HIT | TRAIL | 3,504 |
| 2026-01-20 09:30:00 | ORB | PE | 276 | 415 | IDX_TSL_HIT | TRAIL | 2,676 |
| 2026-09-30 09:30:00 | ORB | CE | 238 | 354 | IDX_TSL_HIT | TRAIL | 2,214 |
| 2026-08-19 09:30:00 | ORB | PE | 216 | 294 | IDX_TSL_HIT | TRAIL | 1,461 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2025-11-07 09:40:00 | ORB | PE | 477 | 276 | IDX_SL_HIT | INITIAL | -4,120 |
| 2026-05-19 09:30:00 | ORB | CE | 464 | 270 | TIME_DECAY | INITIAL | -3,976 |
| 2026-01-27 09:30:00 | ORB | PE | 411 | 223 | IDX_SL_HIT | INITIAL | -3,861 |
| 2025-11-11 09:30:00 | ORB | PE | 337 | 175 | IDX_SL_HIT | INITIAL | -3,332 |
| 2026-01-28 09:30:00 | ORB | CE | 294 | 154 | IDX_SL_HIT | INITIAL | -2,904 |
| 2026-05-26 09:40:00 | ORB | CE | 283 | 149 | IDX_SL_HIT | INITIAL | -2,765 |
| 2026-09-29 09:30:00 | ORB | PE | 283 | 156 | IDX_SL_HIT | INITIAL | -2,642 |
| 2025-12-09 09:30:00 | ORB | PE | 273 | 153 | IDX_SL_HIT | INITIAL | -2,494 |
| 2026-05-22 09:35:00 | ORB | CE | 688 | 570 | TIME_DECAY | INITIAL | -2,464 |
| 2026-06-30 09:30:00 | ORB | PE | 310 | 193 | IDX_SL_HIT | INITIAL | -2,438 |


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
