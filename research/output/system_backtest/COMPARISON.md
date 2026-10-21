# Backtest variant comparison

## Variant comparison

Every variant is the same full-system run (same data, costs and model) with one change.  Changes marked * are backtest-only entry filters — the bot has no setting for them yet.  `H1`/`H2` split the period in half; a real edge should be positive in both.


| Variant | Change |
|---|---|
| current_config | current .env |
| v1_pivot_be_1_5R | PIVOT_BE_TRIGGER_R=1.5 |
| v2_no_midday_no_late | NO_NEW_ENTRY_AFTER=14:00; no entries 11:00-12:00* |
| v3_orb_only | ENABLE_PIVOT_STRATEGY=false; ENABLE_EMA_STRATEGY=false |
| v4_pivot_pe_only | ENABLE_ORB_STRATEGY=false; ENABLE_EMA_STRATEGY=false; skip CE_PIVOT* |



| Variant | Trades | Trades/mo | Win % | Net Rs | PF | Avg Rs | Max DD Rs | Loss streak | H1 Rs | H2 Rs | Green months % | 2024 Rs | 2025 Rs | 2026 Rs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_config | 326 | 10 | 22.40 | -28,574 | 0.83 | -88 | -51,838 | 31 | -23,243 | -5,331 | 38 | -35,428 | -15,962 | 22,816 |
| v1_pivot_be_1_5R | 325 | 10 | 27.70 | -31,894 | 0.85 | -98 | -63,354 | 31 | -31,393 | -501 | 41 | -51,440 | -12,407 | 31,953 |
| v2_no_midday_no_late | 265 | 8.10 | 23 | -5,876 | 0.95 | -22 | -28,402 | 26 | -971 | -4,904 | 47 | -17,581 | -5,864 | 17,570 |
| v3_orb_only | 21 | 0.60 | 52.40 | 5,068 | 1.31 | 241 | -5,553 | 3 | 6,611 | -1,543 | 54 | 5,466 | 24 | -423 |
| v4_pivot_pe_only | 141 | 4.30 | 21.30 | -715 | 0.99 | -5 | -24,798 | 24 | -5,218 | 4,503 | 42 | -10,271 | -8,357 | 17,913 |
