# Full-system backtest: 2025-10-01 to 2026-10-16

Run label `orb_latest`, 258 trading sessions, generated 2026-10-20 19:19.  Overrides: {'ENABLE_EMA_STRATEGY': 'false', 'ENABLE_ORB_STRATEGY': 'true', 'ENABLE_PIVOT_STRATEGY': 'false', 'ENABLE_VWAP_STRATEGY': 'false', 'ENABLE_TRB_STRATEGY': 'false', 'ENABLE_MOMENTUM_PHASE': 'false', 'ENABLE_NATR_STRATEGY': 'false', 'ENABLE_PDHL_STRATEGY': 'false', 'ENABLE_OB_STRATEGY': 'false', 'ENABLE_ATR_COPILOT_STRATEGY': 'false'}.

## Headline

| Metric | Value |
|---|---:|
| Trades | 11 |
| Win % | 36.40 |
| Net P&L (Rs) | 6,266 |
| Gross P&L (Rs) | 7,302 |
| Costs (Rs) | 1,036 |
|   of which charges (Rs) | 596 |
|   of which slippage (Rs) | 440 |
| Avg cost per trade (Rs) | 94 |
| Profit factor | 2.71 |
| Avg trade (Rs) | 570 |
| Avg win (Rs) | 2,484 |
| Avg loss (Rs) | -524 |
| Largest win (Rs) | 5,102 |
| Largest loss (Rs) | -1,253 |
| Max drawdown (Rs) | -1,199 |
| Longest losing streak | 2 |
| Avg hold (min) | 65.90 |


Trades on 11 of 258 sessions; 36% of trading days were green.  Average 0.9 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| ORB | CE | 5 | 40 | 4,996 | 999 | 4.48 |
| ORB | PE | 6 | 33.30 | 1,270 | 212 | 1.57 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| IDX_TSL_HIT | 4 | 75 | 4,814 | 1,203 | 230 | 140 |
| IDX_BE_STOP | 3 | 0 | -336 | -112 | 0 | 19 |
| IDX_SL_HIT | 3 | 0 | -3,313 | -1,104 | 0 | 11 |
| IDX_TARGET | 1 | 100 | 5,102 | 5,102 | inf | 72 |


### Exit reason by strategy (trade count)

| exit_reason | ORB |
|---|---:|
| IDX_BE_STOP | 3 |
| IDX_SL_HIT | 3 |
| IDX_TARGET | 1 |
| IDX_TSL_HIT | 4 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| TRAIL | 5 | 80 | 9,915 | 1,983 | 472 |
| BE | 3 | 0 | -336 | -112 | 0 |
| INITIAL | 3 | 0 | -3,313 | -1,104 | 0 |


- Trades whose stop moved at least once: 8 of 11 (73%); average 7.0 moves per trade.

- Full initial-stop losses: 3 (27%).

- Of the 8 trades that reached +1R, the exit kept on average 42% of the best index move (median 40%); 50% of them still closed at a net loss.

- Median best move (MFE) 1.11R; 73% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 8 | 37.50 | 5,501 | 688 | 2.52 |
| H2 | 3 | 33.30 | 765 | 255 | 13.03 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2025 | 2 | 0 | -1,393 | -697 | 0 |
| 2026 | 9 | 44.40 | 7,659 | 851 | 4.36 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2025-11 | 1 | 0 | -1,253 | -1,253 | 0 | -1,253 |
| 2025-12 | 1 | 0 | -140 | -140 | 0 | -1,393 |
| 2026-01 | 2 | 100 | 4,006 | 2,003 | inf | 2,613 |
| 2026-02 | 2 | 0 | -1,058 | -529 | 0 | 1,555 |
| 2026-03 | 1 | 100 | 5,102 | 5,102 | inf | 6,657 |
| 2026-04 | 1 | 0 | -1,156 | -1,156 | 0 | 5,501 |
| 2026-07 | 1 | 0 | -43 | -43 | 0 | 5,458 |
| 2026-08 | 1 | 100 | 829 | 829 | inf | 6,287 |
| 2026-10 | 1 | 0 | -21 | -21 | 0 | 6,266 |


33% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 11 | 36.40 | 6,266 | 570 | 2.71 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Tue | 1 | 100 | 2,676 | 2,676 | inf |
| Wed | 2 | 100 | 5,931 | 2,965 | inf |
| Thu | 7 | 0 | -3,671 | -524 | 0 |
| Fri | 1 | 100 | 1,330 | 1,330 | inf |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 3 | 100 | 4,835 | 1,612 | inf |
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
| ENTRY_BLOCKED_MAX_RISK | 29 |
| SMART_ENTRY_BLOCKED_EMA_GAP | 2 |
| SMART_ENTRY_BLOCKED_EMA_GAP_SHRINKING: EMA gap not widening | 2 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not rising for CE | 1 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not falling for PE | 1 |
| SMART_ENTRY_BLOCKED_COOLDOWN | 1 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-03-25 09:30:00 | ORB | CE | 188 | 448 | IDX_TARGET | TRAIL | 5,102 |
| 2026-01-20 09:30:00 | ORB | PE | 276 | 415 | IDX_TSL_HIT | TRAIL | 2,676 |
| 2026-01-02 09:35:00 | ORB | CE | 442 | 514 | IDX_TSL_HIT | TRAIL | 1,330 |
| 2026-08-19 09:40:00 | ORB | PE | 188 | 235 | IDX_TSL_HIT | TRAIL | 829 |
| 2026-10-08 09:30:00 | ORB | PE | 131 | 135 | IDX_TSL_HIT | TRAIL | -21.03 |
| 2026-07-02 09:35:00 | ORB | CE | 119 | 122 | IDX_BE_STOP | BE | -42.56 |
| 2025-12-04 09:35:00 | ORB | CE | 83.15 | 80.65 | IDX_BE_STOP | BE | -140 |
| 2026-02-05 09:40:00 | ORB | PE | 101 | 97.95 | IDX_BE_STOP | BE | -154 |
| 2026-02-12 09:30:00 | ORB | PE | 84.90 | 44.15 | IDX_SL_HIT | INITIAL | -904 |
| 2026-04-30 09:30:00 | ORB | PE | 126 | 72.35 | IDX_SL_HIT | INITIAL | -1,156 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2025-11-27 09:30:00 | ORB | CE | 121 | 63 | IDX_SL_HIT | INITIAL | -1,253 |
| 2026-04-30 09:30:00 | ORB | PE | 126 | 72.35 | IDX_SL_HIT | INITIAL | -1,156 |
| 2026-02-12 09:30:00 | ORB | PE | 84.90 | 44.15 | IDX_SL_HIT | INITIAL | -904 |
| 2026-02-05 09:40:00 | ORB | PE | 101 | 97.95 | IDX_BE_STOP | BE | -154 |
| 2025-12-04 09:35:00 | ORB | CE | 83.15 | 80.65 | IDX_BE_STOP | BE | -140 |
| 2026-07-02 09:35:00 | ORB | CE | 119 | 122 | IDX_BE_STOP | BE | -42.56 |
| 2026-10-08 09:30:00 | ORB | PE | 131 | 135 | IDX_TSL_HIT | TRAIL | -21.03 |
| 2026-08-19 09:40:00 | ORB | PE | 188 | 235 | IDX_TSL_HIT | TRAIL | 829 |
| 2026-01-02 09:35:00 | ORB | CE | 442 | 514 | IDX_TSL_HIT | TRAIL | 1,330 |
| 2026-01-20 09:30:00 | ORB | PE | 276 | 415 | IDX_TSL_HIT | TRAIL | 2,676 |


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
| TREND_GATE_STRATEGIES | frozenset({'VWAP', 'EMA', 'NATR', 'TRB'}) |
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
