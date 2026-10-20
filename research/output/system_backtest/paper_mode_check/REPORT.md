# Full-system backtest: 2026-01-01 to 2026-10-16

Run label `paper_mode_check`, 196 trading sessions, generated 2026-10-20 02:26.  Overrides: none (current .env).

## Headline

| Metric | Value |
|---|---:|
| Trades | 106 |
| Win % | 17 |
| Net P&L (Rs) | -244,853 |
| Gross P&L (Rs) | 62,312 |
| Costs (Rs) | 307,165 |
|   of which charges (Rs) | 302,925 |
|   of which slippage (Rs) | 4,240 |
| Avg cost per trade (Rs) | 2,898 |
| Profit factor | 0.19 |
| Avg trade (Rs) | -2,310 |
| Avg win (Rs) | 3,227 |
| Avg loss (Rs) | -3,443 |
| Largest win (Rs) | 9,819 |
| Largest loss (Rs) | -7,836 |
| Max drawdown (Rs) | -249,201 |
| Longest losing streak | 20 |
| Avg hold (min) | 36.10 |


Trades on 75 of 196 sessions; 17% of trading days were green.  Average 11.4 trades a month.


![equity](equity.svg)


## By strategy and side

| strategy | side | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---|---:|---:|---:|---:|---:|
| EMA | CE | 5 | 0 | -15,724 | -3,145 | 0 |
| EMA | PE | 4 | 0 | -11,442 | -2,860 | 0 |
| ORB | CE | 1 | 0 | -520 | -520 | 0 |
| ORB | PE | 2 | 50 | -559 | -279 | 0.81 |
| PIVOT | CE | 47 | 19.10 | -107,156 | -2,280 | 0.24 |
| PIVOT | PE | 47 | 17 | -109,452 | -2,329 | 0.16 |


## Exit reasons

Every exit carries the reason recorded by the bot itself (`trades.exit_reason`).


| exit_reason | Trades | Win % | Net Rs | Avg Rs | PF | Avg hold min |
|---|---:|---:|---:|---:|---:|---:|
| PIVOT_BE_STOP | 37 | 0 | -109,807 | -2,968 | 0 | 26 |
| PIVOT_SL_HIT | 29 | 0 | -150,182 | -5,179 | 0 | 20 |
| PIVOT_TSL_HIT | 25 | 60 | 37,650 | 1,506 | 4.20 | 49 |
| EMA_TSL_HIT | 5 | 0 | -7,039 | -1,408 | 0 | 26 |
| EOD_SQUARE_OFF | 2 | 100 | 6,294 | 3,147 | inf | 120 |
| EMA_SL_HIT | 2 | 0 | -12,500 | -6,250 | 0 | 14 |
| IDX_TSL_HIT | 2 | 50 | 1,869 | 935 | 4.59 | 196 |
| EMA_TIME_STOP | 1 | 0 | -3,998 | -3,998 | 0 | 30 |
| EMA_COLLAPSE | 1 | 0 | -3,629 | -3,629 | 0 | 90 |
| IDX_BE_STOP | 1 | 0 | -2,948 | -2,948 | 0 | 92 |
| PIVOT_TARGET_T3 | 1 | 0 | -563 | -563 | 0 | 54 |


### Exit reason by strategy (trade count)

| exit_reason | EMA | ORB | PIVOT |
|---|---:|---:|---:|
| EMA_COLLAPSE | 1 | 0 | 0 |
| EMA_SL_HIT | 2 | 0 | 0 |
| EMA_TIME_STOP | 1 | 0 | 0 |
| EMA_TSL_HIT | 5 | 0 | 0 |
| EOD_SQUARE_OFF | 0 | 0 | 2 |
| IDX_BE_STOP | 0 | 1 | 0 |
| IDX_TSL_HIT | 0 | 2 | 0 |
| PIVOT_BE_STOP | 0 | 0 | 37 |
| PIVOT_SL_HIT | 0 | 0 | 29 |
| PIVOT_TARGET_T3 | 0 | 0 | 1 |
| PIVOT_TSL_HIT | 0 | 0 | 25 |


## Stop-loss and trailing-stop behaviour

`stage_at_exit` is the furthest stop stage reached: INITIAL = the original SL, BE = moved to break-even, T1/T2 = Pivot profit locks, TRAIL = chandelier trailing stop.  `sl_moves` counts broker stop modifications.


| stage_at_exit | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| BE | 41 | 4.90 | -107,025 | -2,610 | 0.06 |
| INITIAL | 33 | 0 | -170,309 | -5,161 | 0 |
| T1 | 22 | 59.10 | 24,476 | 1,113 | 3.11 |
| TRAIL | 7 | 14.30 | -5,169 | -738 | 0.32 |
| T2 | 3 | 66.70 | 13,174 | 4,391 | 100 |


- Trades whose stop moved at least once: 73 of 106 (69%); average 2.9 moves per trade.

- Full initial-stop losses: 33 (31%).

- Of the 56 trades that reached +1R, the exit kept on average 44% of the best index move (median 53%); 68% of them still closed at a net loss.

- Median best move (MFE) 1.02R; 53% of trades reached +1R at some point.


## Stability

### First half vs second half of the period

| half | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| H1 | 52 | 19.20 | -120,584 | -2,319 | 0.25 |
| H2 | 54 | 14.80 | -124,269 | -2,301 | 0.13 |


### By year

| year | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 2026 | 106 | 17 | -244,853 | -2,310 | 0.19 |


### By month

| month | Trades | Win % | Net Rs | Avg Rs | PF | Cumulative Rs |
|---|---:|---:|---:|---:|---:|---:|
| 2026-01 | 11 | 27.30 | -20,191 | -1,836 | 0.25 | -20,191 |
| 2026-02 | 19 | 10.50 | -61,797 | -3,252 | 0.07 | -81,988 |
| 2026-03 | 5 | 40 | -674 | -135 | 0.95 | -82,662 |
| 2026-04 | 9 | 33.30 | -7,505 | -834 | 0.68 | -90,167 |
| 2026-05 | 10 | 0 | -32,809 | -3,281 | 0 | -122,976 |
| 2026-06 | 14 | 21.40 | -39,132 | -2,795 | 0.07 | -162,108 |
| 2026-07 | 9 | 11.10 | -27,874 | -3,097 | 0.08 | -189,982 |
| 2026-08 | 14 | 0 | -36,620 | -2,616 | 0 | -226,602 |
| 2026-09 | 8 | 12.50 | -13,827 | -1,728 | 0.19 | -240,429 |
| 2026-10 | 7 | 42.90 | -4,424 | -632 | 0.68 | -244,853 |


0% of months were profitable.


## Timing

### Entry hour

| entry_hour | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| 09:00 | 18 | 16.70 | -47,333 | -2,630 | 0.15 |
| 10:00 | 19 | 10.50 | -50,743 | -2,671 | 0.08 |
| 11:00 | 21 | 19 | -33,611 | -1,601 | 0.30 |
| 12:00 | 15 | 20 | -32,907 | -2,194 | 0.18 |
| 13:00 | 22 | 27.30 | -34,228 | -1,556 | 0.41 |
| 14:00 | 11 | 0 | -46,031 | -4,185 | 0 |


### Weekday

| weekday | Trades | Win % | Net Rs | Avg Rs | PF |
|---|---:|---:|---:|---:|---:|
| Mon | 19 | 26.30 | -26,212 | -1,380 | 0.49 |
| Tue | 19 | 26.30 | -23,964 | -1,261 | 0.41 |
| Wed | 24 | 12.50 | -58,907 | -2,454 | 0.16 |
| Thu | 27 | 14.80 | -75,425 | -2,794 | 0.05 |
| Fri | 17 | 5.90 | -60,345 | -3,550 | 0.01 |


### Expiry day vs other days

| expiry_day | Trades | Win % | Net Rs | Avg Rs | PF |
|---:|---:|---:|---:|---:|---:|
| no | 86 | 18.60 | -185,311 | -2,155 | 0.24 |
| yes | 20 | 10 | -59,542 | -2,977 | 0 |


## Signal funnel

Raw signals are strategy conditions that fired on a closed candle; most are removed by the entry gates below before any order.


| Signal | Raw signals |
|---|---:|
| CE | 154 |
| PE | 136 |
| PE_PIVOT | 65 |
| CE_PIVOT | 63 |
| PE_ORB | 36 |
| CE_ORB | 27 |


### Top reasons signals were blocked

| Block (event: reason) | Count |
|---|---:|
| SMART_ENTRY_BLOCKED_EMA_GAP_SHRINKING: EMA gap not widening | 99 |
| TREND_GATE_BLOCKED: against daily trend (DOWN) | 71 |
| SMART_ENTRY_BLOCKED_BODY | 68 |
| TREND_GATE_BLOCKED: against daily trend (UP) | 46 |
| ENTRY_BLOCKED_MAX_RISK | 30 |
| EMA_ENTRY_BLOCKED: room # < #R (#) | 19 |
| SMART_ENTRY_BLOCKED_EMA_GAP | 2 |
| EMA_ENTRY_BLOCKED: risk # > max # | 2 |
| SMART_ENTRY_BLOCKED_SLOPE: EMA# not falling for PE | 1 |


## Best and worst trades

### Best 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-03-16 13:55:00 | PIVOT | CE | 74,556 | 75,186 | PIVOT_TSL_HIT | T2 | 9,819 |
| 2026-04-06 11:30:00 | PIVOT | CE | 72,987 | 73,457 | PIVOT_TSL_HIT | T1 | 6,680 |
| 2026-04-07 11:15:00 | PIVOT | CE | 73,758 | 74,226 | PIVOT_TSL_HIT | T1 | 6,600 |
| 2026-10-14 12:50:00 | PIVOT | PE | 73,067 | 73,464 | PIVOT_TSL_HIT | T1 | 5,221 |
| 2026-02-02 13:50:00 | PIVOT | CE | 81,296 | 81,669 | EOD_SQUARE_OFF | BE | 4,430 |
| 2026-03-11 09:35:00 | PIVOT | PE | 78,054 | 78,374 | PIVOT_TSL_HIT | T2 | 3,488 |
| 2026-09-15 13:10:00 | PIVOT | PE | 74,571 | 74,875 | PIVOT_TSL_HIT | T1 | 3,293 |
| 2026-07-14 09:30:00 | PIVOT | PE | 77,359 | 77,631 | PIVOT_TSL_HIT | T1 | 2,560 |
| 2026-01-20 09:30:00 | ORB | PE | 82,946 | 83,219 | IDX_TSL_HIT | TRAIL | 2,389 |
| 2026-04-30 13:00:00 | PIVOT | CE | 76,767 | 77,029 | PIVOT_TSL_HIT | T1 | 2,380 |


### Worst 10

| entry_dt | strategy | side | entry_price | exit_price | exit_reason | stage_at_exit | net_pnl |
|---|---|---|---:|---:|---|---|---:|
| 2026-06-24 09:50:00 | PIVOT | PE | 76,314 | 76,063 | PIVOT_SL_HIT | INITIAL | -7,836 |
| 2026-02-20 12:25:00 | PIVOT | CE | 83,083 | 82,889 | PIVOT_SL_HIT | INITIAL | -6,951 |
| 2026-02-20 13:10:00 | PIVOT | PE | 82,800 | 82,612 | PIVOT_SL_HIT | INITIAL | -6,811 |
| 2026-04-16 11:05:00 | EMA | CE | 78,463 | 78,294 | EMA_SL_HIT | INITIAL | -6,278 |
| 2026-02-02 13:10:00 | PIVOT | CE | 81,313 | 81,152 | PIVOT_SL_HIT | INITIAL | -6,238 |
| 2026-03-12 11:50:00 | EMA | PE | 76,285 | 76,116 | EMA_SL_HIT | INITIAL | -6,222 |
| 2026-07-16 14:20:00 | PIVOT | CE | 77,345 | 77,180 | PIVOT_SL_HIT | INITIAL | -6,169 |
| 2026-02-23 09:50:00 | PIVOT | CE | 83,379 | 83,225 | PIVOT_SL_HIT | INITIAL | -6,156 |
| 2026-05-13 13:05:00 | PIVOT | CE | 75,102 | 74,946 | PIVOT_SL_HIT | INITIAL | -5,908 |
| 2026-06-05 14:40:00 | PIVOT | PE | 74,144 | 73,988 | PIVOT_SL_HIT | INITIAL | -5,862 |


## Configuration tested

| Setting | Value |
|---|---|
| ENABLE_PIVOT_STRATEGY | yes |
| ENABLE_ORB_STRATEGY | yes |
| ENABLE_EMA_STRATEGY | yes |
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
| TREND_GATE_STRATEGIES | frozenset({'VWAP', 'TRB', 'NATR', 'EMA'}) |
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
