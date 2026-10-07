"""
Deep analysis of SENSEX26O0872900CE — both trades.
Reconstructs SENSEX context, risk params, and post-entry price action.
"""
from __future__ import annotations
from market.historical_data import fetch_historical_candles, SENSEX_TOKEN
from market.candle_builder import Candle
from market.indicators import ema, atr as atr_ind
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

# ── Load SENSEX candles ────────────────────────────────────────────────────────
candles_all = fetch_historical_candles(SENSEX_TOKEN, interval="5minute", days_back=5)

def candles_for_date(d: str) -> list[Candle]:
    return [c for c in candles_all if c.timestamp.date().isoformat() == d]

oct06 = candles_for_date("2026-10-06")
oct07 = candles_for_date("2026-10-07")

def find_candle(candles: list[Candle], hhmm: str) -> Candle | None:
    return next((c for c in candles if c.timestamp.strftime("%H:%M") == hhmm), None)

def context_window(candles: list[Candle], hhmm: str, before: int = 5, after: int = 8) -> list[Candle]:
    idx = next((i for i, c in enumerate(candles) if c.timestamp.strftime("%H:%M") == hhmm), None)
    if idx is None:
        return []
    return candles[max(0, idx - before): idx + after + 1]

SEP = "─" * 76

# ═══════════════════════════════════════════════════════════════════════════════
# TRADE 1 — 2026-10-06  entry 14:05
# ═══════════════════════════════════════════════════════════════════════════════
print(SEP)
print("  TRADE 1  :  SENSEX26O0872900CE  |  2026-10-06  |  SHADOW")
print(SEP)
print("  Entry   : 14:05  @  396.00  (option LTP)")
print("  Exit    : 14:14  @  396.00  (STOP_HIT)  PnL = ₹0  (break-even)")
print("  SL      : 38.25 pts  →  357.75  |  Target: 57.4 pts  →  453.40")
print("  Sensex  : entry=72944.61  sl=72848.99  t1=73088.11")
print("  ATR(14) : 36.0  |  tsl=7.65 pts")
print()

# Signal candle was 14:00 (signal fires at 14:05)
window6 = context_window(oct06, "14:05", before=6, after=8)
print(f"  {'Time':<6}  {'Open':>8}  {'High':>8}  {'Low':>8}  {'Close':>8}  {'Body':>6}  Note")
for c in window6:
    t = c.timestamp.strftime("%H:%M")
    body = abs(c.close - c.open)
    d = "UP" if c.close > c.open else "DN"
    note = ""
    if t == "14:05": note = " <── ENTRY"
    if t == "14:10": note = " ← price action after entry"
    if t == "14:15": note = " ← exit window"
    print(f"  {t:<6}  {c.open:>8.2f}  {c.high:>8.2f}  {c.low:>8.2f}  {c.close:>8.2f}  {body:>6.1f}  [{d}]{note}")

# ── EMA gap at entry ──────────────────────────────────────────────────────────
idx_entry6 = next((i for i, c in enumerate(oct06) if c.timestamp.strftime("%H:%M") == "14:05"), None)
if idx_entry6:
    closes6 = [c.close for c in oct06[:idx_entry6+1]]
    if len(closes6) >= 21:
        e9 = ema(closes6, 9)
        e21 = ema(closes6, 21)
        gap = e9[-1] - e21[-1]
        vel = gap - (e9[-2] - e21[-2]) if len(e9) >= 2 else 0
        print(f"\n  EMA context at entry (14:05):")
        print(f"    EMA9={e9[-1]:.2f}  EMA21={e21[-1]:.2f}  gap={gap:+.2f}  velocity={vel:+.2f}")
        print(f"    Gap direction: {'CE territory (EMA9>EMA21)' if gap > 0 else 'WRONG side — EMA9 below EMA21'}")
    # ATR at entry
    a = atr_ind(oct06[:idx_entry6+1], 14)
    atr_val = next((v for v in reversed(a) if v is not None), None)
    if atr_val:
        print(f"    ATR(14) at entry: {atr_val:.2f}")

# ── Analysis ──────────────────────────────────────────────────────────────────
# What happened after entry — did sensex reach target or SL?
entry6 = find_candle(oct06, "14:05")
after6 = [c for c in oct06 if c.timestamp > entry6.timestamp] if entry6 else []
if after6:
    high_after = max(c.high for c in after6[:8])
    low_after  = min(c.low  for c in after6[:8])
    sensex_entry = 72944.61
    sensex_sl    = 72848.99
    sensex_t1    = 73088.11
    print(f"\n  Post-entry SENSEX (next 8 candles):")
    print(f"    Max high : {high_after:.2f}  (vs T1={sensex_t1:.2f}, distance to T1={sensex_t1-high_after:+.2f})")
    print(f"    Min low  : {low_after:.2f}  (vs SL={sensex_sl:.2f}, distance to SL={low_after-sensex_sl:+.2f})")
    sl_hit = low_after < sensex_sl
    t1_hit = high_after >= sensex_t1
    print(f"    SL hit?  : {'YES ✗' if sl_hit else 'NO ✓'}")
    print(f"    T1 hit?  : {'YES ✓' if t1_hit else 'NO ✗'}")

# ═══════════════════════════════════════════════════════════════════════════════
# TRADE 2 — 2026-10-07  entry 10:55
# ═══════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print("  TRADE 2  :  SENSEX26O0872900CE  |  2026-10-07  |  SHADOW")
print(SEP)
print("  Entry   : 10:55  @  286.25  (option LTP)")
print("  Exit    : 10:55  @  282.65  (STOP_HIT)  PnL = -₹72  (3.6 pts × 20)")
print("  SL      : 20.0 pts  →  266.25  |  Target: 30.0 pts  →  316.25")
print("  Sensex  : entry=72910.55  sl=72860.55  t1=72985.55")
print("  ATR(14) : 90.77  |  tsl=5.0 pts")
print()

window7 = context_window(oct07, "10:55", before=6, after=8)
print(f"  {'Time':<6}  {'Open':>8}  {'High':>8}  {'Low':>8}  {'Close':>8}  {'Body':>6}  Note")
for c in window7:
    t = c.timestamp.strftime("%H:%M")
    body = abs(c.close - c.open)
    d = "UP" if c.close > c.open else "DN"
    note = ""
    if t == "10:55": note = " <── ENTRY + immediate exit (39 sec)"
    if t == "11:00": note = " ← 1st candle after exit"
    print(f"  {t:<6}  {c.open:>8.2f}  {c.high:>8.2f}  {c.low:>8.2f}  {c.close:>8.2f}  {body:>6.1f}  [{d}]{note}")

# ── EMA gap at entry ──────────────────────────────────────────────────────────
idx_entry7 = next((i for i, c in enumerate(oct07) if c.timestamp.strftime("%H:%M") == "10:55"), None)
if idx_entry7 is not None:
    # use full history for warm EMA
    closes7_full = [c.close for c in candles_all[-80: -len(oct07) + idx_entry7 + 1 + len(oct07)]]
    # simpler: use today candles up to entry + previous day
    prev_day = candles_for_date("2026-10-06")
    combo = prev_day + oct07[:idx_entry7+1]
    closes_combo = [c.close for c in combo]
    if len(closes_combo) >= 21:
        e9 = ema(closes_combo, 9)
        e21 = ema(closes_combo, 21)
        gap = e9[-1] - e21[-1]
        vel = gap - (e9[-2] - e21[-2]) if len(e9) >= 2 else 0
        print(f"\n  EMA context at entry (10:55):")
        print(f"    EMA9={e9[-1]:.2f}  EMA21={e21[-1]:.2f}  gap={gap:+.2f}  velocity={vel:+.2f}")
        print(f"    Gap direction: {'CE territory (EMA9>EMA21)' if gap > 0 else 'WRONG side — EMA9 below EMA21'}")
    a7 = atr_ind(combo, 14)
    atr7 = next((v for v in reversed(a7) if v is not None), None)
    if atr7:
        print(f"    ATR(14) at entry: {atr7:.2f}")

# What happened to SENSEX after entry 10:55 on Oct 07
entry7 = find_candle(oct07, "10:55")
after7 = [c for c in oct07 if entry7 and c.timestamp > entry7.timestamp]
if after7:
    high7 = max(c.high for c in after7[:8])
    low7  = min(c.low  for c in after7[:8])
    sensex_entry7 = 72910.55
    sensex_sl7    = 72860.55
    sensex_t1_7   = 72985.55
    print(f"\n  Post-entry SENSEX (next 8 candles):")
    print(f"    Max high : {high7:.2f}  (vs T1={sensex_t1_7:.2f}, distance to T1={sensex_t1_7-high7:+.2f})")
    print(f"    Min low  : {low7:.2f}  (vs SL={sensex_sl7:.2f}, distance to SL={low7-sensex_sl7:+.2f})")
    sl7_hit = low7 < sensex_sl7
    t1_7_hit = high7 >= sensex_t1_7
    print(f"    SL hit?  : {'YES ✗' if sl7_hit else 'NO ✓'}")
    print(f"    T1 hit?  : {'YES ✓' if t1_7_hit else 'NO ✗'}")

# ── KEY ANOMALY: exit in 39 seconds ──────────────────────────────────────────
print()
print("  KEY ANOMALY:")
print("    Entry: 10:55:01  Exit: 10:55:39  →  Trade lasted only 38 seconds")
print("    Entry px: 286.25  Exit px: 282.65  →  -3.60 pts (option lost 1.26%)")
print("    SL was set at 266.25 (20 pts below entry)")
print("    But exit happened at 282.65 — only 3.6 pts below entry, not 20 pts")
print("    → This was NOT a normal SL hit. Possible causes:")
print("      1. Option LTP fell to 282.65 and the TSL triggered at 0 pts gain")
print("      2. MIN_SL_POINTS=20 but TSL trail=5 → stop was at entry-20=266.25, not 282.65")
print("      3. Check: was SL order placed at 266.25 and filled at 282.65 (slippage)?")
print("         OR was the stop ratcheted up to 282.65 before the exit?")

# ── Check if SL was set at MIN_SL (20 pts) or ATR-based (90.77 * mult) ───────
print()
print("  RISK PARAM SANITY CHECK (Trade 2):")
sl_pts = 20.0
atr_val_t2 = 90.77
from config import settings
print(f"    ATR(14)={atr_val_t2}  SPOT_ATR_SL_MULT={settings.SPOT_ATR_SL_MULT}")
atr_sl = atr_val_t2 * settings.SPOT_ATR_SL_MULT
print(f"    ATR-based SL = {atr_val_t2} x {settings.SPOT_ATR_SL_MULT} = {atr_sl:.1f} pts")
print(f"    Actual SL used = {sl_pts} pts  (= MIN_SL_POINTS — ATR calc was overridden by minimum)")
print(f"    This means MIN_SL_POINTS={settings.MIN_SL_POINTS} capped a natural SL of {atr_sl:.1f} pts")
print(f"    At ATR=90.77 the SL should have been {atr_sl:.1f} pts wide, not {sl_pts} pts")
print(f"    The 20-pt SL was too tight for an ATR-90 environment → inevitable stop-out")
