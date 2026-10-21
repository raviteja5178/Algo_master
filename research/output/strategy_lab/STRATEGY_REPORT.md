# SENSEX intraday strategy research

Data: SENSEX 1-minute bars and India VIX, Jan 2024 – Oct 2026.  Generated 2026-10-20 20:23.  Re-run: `python -m research.strategy_lab`, `python -m research.strategy_lab --robustness`, `python -m research.strategy_lab --report`.

> Research output from a backtest, not investment advice.  Every number below depends on the option-price model described under *Risks*.

## What the market data says

- **Options have been priced above realised movement.** Median India VIX 13.8 vs 20-day realised SENSEX volatility 10.9: buyers pay for more movement than usually arrives; that gap is the seller's edge.
- **Morning direction does not predict the afternoon.** First-hour move vs rest-of-day move: correlation 0.02; same direction on only 53% of days.
- **Volatility is U-shaped.** The 09:15 half-hour moves about 2.5x more than any midday half-hour; 11:15–13:45 is the quietest stretch.
- **43% of daily variance happens overnight** (weeknight ≈ 176 trading minutes, weekend ≈ 609), so an intraday option buyer pays the day's time decay but only sees about 57% of the day's movement.

## Strategy families tested

Parameters were chosen on **in-sample** days (to 2025-06-30) and judged on the **out-of-sample** days after it, which played no part in the choice.  Same data, option model, costs (brokerage, STT, exchange, SEBI, stamp, GST per leg) and 1 point of slippage per leg per side throughout.


| Family | Setups | Positive in-sample | Positive out-of-sample | Positive in both | Best out-of-sample PF |
|---|---:|---:|---:|---:|---:|
| ICONDOR | 32 | 7 | 13 | 5 | 1.43 |
| IFLY | 32 | 12 | 24 | 12 | 1.67 |
| ORB | 24 | 3 | 4 | 0 | 1.18 |


- **ORB** = buy ATM CE/PE on an opening-range breakout (15/30-minute range; fixed 1.5R/2R target or break-even + trailing stop).
- **IFLY** = sell an ATM straddle and buy wings either side (iron butterfly), intraday.
- **ICONDOR** = sell a 400-point OTM strangle with wings (iron condor), intraday.


### Best three per family (picked in-sample, then judged out-of-sample)

| strategy | IS n | IS net | IS pf | OOS n | OOS net | OOS pf | OOS max dd |
|---|---:|---:|---:|---:|---:|---:|---:|
| IFLY entry=10:30 dist=0 wing=1000 stop_x=0.5 take_x=0.0 expiry_only=True | 76 | 40,031 | 1.29 | 68 | 49,433 | 1.55 | -17,548 |
| IFLY entry=10:30 dist=0 wing=500 stop_x=1.0 take_x=0.0 expiry_only=True | 76 | 29,872 | 1.32 | 68 | 16,926 | 1.22 | -18,739 |
| IFLY entry=10:30 dist=0 wing=500 stop_x=0.5 take_x=0.0 expiry_only=True | 76 | 25,484 | 1.27 | 68 | 19,924 | 1.27 | -16,200 |
| ICONDOR entry=10:30 dist=400 wing=1000 stop_x=0.5 take_x=0.0 expiry_only=True | 76 | 25,355 | 1.43 | 68 | -895 | 0.98 | -9,057 |
| ICONDOR entry=10:30 dist=400 wing=500 stop_x=0.5 take_x=0.0 expiry_only=True | 76 | 23,902 | 1.49 | 68 | 4,415 | 1.11 | -5,103 |
| ORB or_min=15 exit_mode=trail target_r=0.0 last_entry=10:30 max_risk_atr=0.4 | 188 | 15,382 | 1.06 | 115 | -4,314 | 0.97 | -36,480 |
| ICONDOR entry=09:45 dist=400 wing=1000 stop_x=0.5 take_x=0.0 expiry_only=True | 76 | 14,533 | 1.20 | 68 | 10,774 | 1.20 | -8,055 |
| ORB or_min=30 exit_mode=trail target_r=0.0 last_entry=10:30 max_risk_atr=0.7 | 224 | 8,162 | 1.02 | 181 | -77,841 | 0.73 | -93,842 |
| ORB or_min=15 exit_mode=trail target_r=0.0 last_entry=10:30 max_risk_atr=0.7 | 289 | 5,249 | 1.01 | 240 | -82,697 | 0.79 | -115,922 |


## Recommended strategy: expiry-day intraday iron butterfly

| Rule | Value |
|---|---|
| Days | SENSEX weekly expiry day only (0 days to expiry) |
| Entry | 10:30: buy CE and PE 1000 points from ATM first, then sell the ATM CE and ATM PE |
| Size | 1 lot (20) per leg |
| Stop | close all four legs if the cost to buy the position back rises 50% above the credit received |
| Exit | otherwise close everything at 15:10 |
| Max loss | capped by the wings: (wing − credit) × 20 |


| Period | n | trades_mo | win% | net | avg | pf | max_dd | worst | green_mo% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| All | 144 | 4.20 | 61.80 | 89,464 | 621 | 1.39 | -23,553 | -6,375 | 71 |
| In-sample | 76 | 4.20 | 57.90 | 40,031 | 527 | 1.29 | -23,553 | -6,375 | 61 |
| Out-of-sample | 68 | 4.20 | 66.20 | 49,433 | 727 | 1.55 | -17,548 | -6,342 | 81 |


### By year

| Year | Trades | Net Rs |
|---|---:|---:|
| 2024 | 50 | 33,696 |
| 2025 | 52 | 25,042 |
| 2026 | 42 | 30,726 |


### Exits

| Exit | Trades | Avg Rs | Net Rs |
|---|---:|---:|---:|
| STOP | 49 | -4,533 | -222,134 |
| TIME | 95 | 3,280 | 311,598 |


## Stress tests

Each row changes one thing and re-runs every expiry day.


| Test | Value | Net Rs | PF | Max DD Rs | In-sample Rs | Out-of-sample Rs |
|---|---|---:|---:|---:|---:|---:|
| As specified | - | 89,464 | 1.39 | -23,553 | 40,031 | 49,433 |
| Slippage per leg per side (pts) | 1.50 | 77,944 | 1.34 | -24,513 | 33,951 | 43,993 |
| Slippage per leg per side (pts) | 2 | 66,424 | 1.28 | -25,473 | 27,871 | 38,553 |
| Slippage per leg per side (pts) | 3 | 43,384 | 1.18 | -27,393 | 15,711 | 27,673 |
| Option prices: model IV × | 0.80 | -37,597 | 0.85 | -59,575 | -10,195 | -27,402 |
| Option prices: model IV × | 0.90 | 44,681 | 1.20 | -24,117 | 23,262 | 21,419 |
| Option prices: model IV × | 1.10 | 156,300 | 1.73 | -19,422 | 76,914 | 79,386 |
| Entry time | 10:00 | 72,221 | 1.29 | -26,071 | 24,634 | 47,587 |
| Entry time | 11:00 | 118,330 | 1.60 | -18,351 | 80,019 | 38,311 |
| Entry time | 11:30 | 97,407 | 1.51 | -15,829 | 68,961 | 28,445 |
| Wing width (pts) | 700 | 70,200 | 1.34 | -21,481 | 33,341 | 36,859 |
| Wing width (pts) | 1,500 | 101,253 | 1.44 | -23,401 | 46,520 | 54,733 |
| Stop at loss of credit × | 0.30 | 123,020 | 1.70 | -15,815 | 70,992 | 52,028 |
| Stop at loss of credit × | 0.75 | 76,323 | 1.30 | -26,740 | 36,561 | 39,762 |


**The test that matters:** the edge is options being priced above the movement that follows.  With real expiry-day premiums 10% below the model it still makes money; 20% below and it loses.  Measuring real premiums comes before any capital.


## Why not the current buying strategies

Under the same model and costs, every opening-range-breakout buying setup failed out-of-sample, and the bot's current configuration (Pivot + ORB + EMA buying) loses over the period — see `research/output/system_backtest/current_config/REPORT.md`.  Buying options intraday means paying the day's time decay while much of the variance happens overnight; none of the tested buying rules overcame that.


## Risks and what the model cannot see

- **Option prices are modelled** (Black-Scholes, IV = India VIX, trading-time decay calibrated on SENSEX's own overnight/intraday variance split).  No volatility smile, no 0DTE-specific IV, no bid/ask spread beyond the slippage figure.
- **Event days** (budget, RBI policy, election results, global shocks) can move SENSEX 1,000+ points; the wings cap each loss, but a run of them hurts.
- **Execution**: four legs must fill together.  Buy the wings before selling the ATM legs and use limit orders; a partial fill can leave a naked short option.
- **Margin**: a hedged iron fly needs far less margin than naked selling; check the exact figure in Zerodha's basket margin calculator.
- **Expiry calendar**: SENSEX weeklies moved Friday → Tuesday (Jan 2025) → Thursday (Sep 2025).  A future change moves the trading day.
- **The bot cannot trade this yet**: it only places single-leg buy orders.


## Plan before trading it

1. **Verify premiums (2–4 expiry days, no orders):** record the real 10:30 ATM straddle and 1000-point wing prices from Kite and compare with the model.  Proceed only if the real credit is at least ~90% of the model's.
2. **Paper-trade the rules** for 8+ expiry days on real quotes, including the 4-leg fill sequence.
3. **Go live with 1 lot**: wings mandatory, the stop automated, a daily loss cap, and no trading on scheduled event days.
