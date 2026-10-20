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
| current_config | 473 | 14.50 | 23.30 | -32,194 | 0.86 | -68 | -70,461 | 24 | -46,213 | 14,019 | 38 | -53,985 | -15,273 | 37,063 |
| v1_pivot_be_1_5R | 472 | 14.50 | 27.50 | -24,877 | 0.92 | -53 | -72,320 | 18 | -47,957 | 23,080 | 44 | -63,613 | -6,899 | 45,636 |
| v2_no_midday_no_late | 352 | 10.80 | 25 | 9,296 | 1.06 | 26 | -34,537 | 18 | -8,494 | 17,790 | 38 | -28,079 | 2,057 | 35,318 |
| v3_orb_only | 35 | 1.10 | 42.90 | 11,873 | 1.49 | 339 | -8,684 | 5 | -804 | 12,677 | 45 | 1,371 | -1,909 | 12,411 |
| v4_pivot_pe_only | 224 | 6.90 | 21.40 | -20,962 | 0.80 | -94 | -34,932 | 20 | -21,904 | 942 | 35 | -22,517 | -11,368 | 12,923 |
