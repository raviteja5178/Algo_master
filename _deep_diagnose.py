"""
Deep diagnosis: replay today's candles to explain exactly why
no PE entry was taken. Uses bot's own Candle + indicator types.
"""
import json, sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Use bot's own types ───────────────────────────────────────────────────────
from market.candle_builder import Candle
from market.indicators import ema as calc_ema, atr_at

today = date.today()

# ── Load state ────────────────────────────────────────────────────────────────
state = json.loads(Path(".bot_state.json").read_text())
print(f"Current LTP : {state.get('ltp')}")
print(f"Bot state   : {state.get('bot_state')}")
print()

# ── Rebuild Candle objects ────────────────────────────────────────────────────
def make_candle(d):
    return Candle(
        timestamp=datetime.fromisoformat(d["t"]),
        open=d["o"], high=d["h"], low=d["l"], close=d["c"],
        volume=d.get("v", 0),
    )

all_candles   = [make_candle(d) for d in state.get("candles_5m", [])]
today_candles = [c for c in all_candles if c.timestamp.date() == today]

print(f"Total 5m candles : {len(all_candles)}")
print(f"Today 5m candles : {len(today_candles)}")
print()

# ── Today's candle table ──────────────────────────────────────────────────────
print("TODAY'S 5m CANDLES:")
print(f"  {'Time':>6}  {'Open':>8}  {'High':>8}  {'Low':>8}  {'Close':>8}  {'Body':>7}  Dir")
print("  " + "-"*62)
for c in today_candles:
    body = c.close - c.open
    d = "▲" if body > 0 else ("▼" if body < 0 else "─")
    print(f"  {c.timestamp.strftime('%H:%M'):>6}  {c.open:>8.0f}  {c.high:>8.0f}  {c.low:>8.0f}  {c.close:>8.0f}  {body:>+7.1f}  {d}")

# ── Compute EMA on the full series (for accuracy) ─────────────────────────────
ema9_all  = calc_ema(all_candles, 9)
ema21_all = calc_ema(all_candles, 20)

# ── Detailed analysis for the ONE signal candle (11:55) ──────────────────────
signal_candle = next(
    (c for c in today_candles if c.timestamp.hour == 11 and c.timestamp.minute == 55
     and c.close < c.open),  # the bearish 11:55 candle
    None
)
# fallback: last today candle
if signal_candle is None:
    # pick the one that triggered PE signal (close=71941.34 per log)
    signal_candle = next((c for c in today_candles if abs(c.close - 71941.34) < 1), None)

if signal_candle:
    idx = all_candles.index(signal_candle)
    e9  = ema9_all[idx]
    e21 = ema21_all[idx]
    e9p = ema9_all[idx-1]  if idx >= 1 else None
    e21p = ema21_all[idx-1] if idx >= 1 else None
    prev = all_candles[idx-1]
    body = abs(signal_candle.close - signal_candle.open)
    atr_val = atr_at(all_candles[:idx+1], period=14)

    print()
    print("="*65)
    print(f"SIGNAL CANDLE DEEP DIVE: {signal_candle.timestamp.strftime('%H:%M')}")
    print("="*65)
    print(f"  O={signal_candle.open:.2f}  H={signal_candle.high:.2f}  L={signal_candle.low:.2f}  C={signal_candle.close:.2f}")
    print(f"  Body (abs)          : {body:.2f} pts")
    print(f"  ATR(14)             : {atr_val:.2f} pts")
    print(f"  Body/ATR ratio      : {body/atr_val:.4f}x  (need ≥ 0.35x = {atr_val*0.35:.2f} pts)")
    print()
    print("  ── Core PE conditions (raw strategy check) ──")
    r1 = signal_candle.close < e21
    r2 = e9 < e21
    r3 = signal_candle.close < prev.low
    print(f"  1. close({signal_candle.close:.2f}) < EMA21({e21:.2f})      : {'✓ PASS' if r1 else '✗ FAIL'}")
    print(f"  2. EMA9({e9:.2f}) < EMA21({e21:.2f})         : {'✓ PASS' if r2 else '✗ FAIL'}")
    print(f"  3. close({signal_candle.close:.2f}) < prev.low({prev.low:.2f})  : {'✓ PASS' if r3 else '✗ FAIL'}")
    print(f"  Raw PE signal fired : {'YES' if (r1 and r2 and r3) else 'NO'}")
    print()
    print("  ── Smart Entry Filter checks ──")
    print(f"  F1 Body/ATR (0.35)  : body={body:.2f}  need={atr_val*0.35:.2f}  → {'✓ PASS' if body >= atr_val*0.35 else '✗ BLOCK ← STOPS HERE'}")
    if e9p:
        slope_ok = e9 < e9p
        print(f"  F2 EMA9 slope       : {e9:.2f} < {e9p:.2f} → {'✓ falling (PE)' if slope_ok else '✗ NOT falling'}")
    if e9 and e21 and e9p and e21p:
        gap_now  = e21 - e9
        gap_prev = e21p - e9p
        print(f"  F4 EMA gap (PE)     : {gap_now:.2f} pts  (need ≥ 10)  → {'✓ PASS' if gap_now >= 10 else '✗ BLOCK'}")
        print(f"  F5 Gap widening     : gap={gap_now:.2f} vs prev={gap_prev:.2f} → {'✓ widening' if gap_now > gap_prev else '✗ NOT widening'}")

# ── Scan ALL today candles for PE raw signal conditions ──────────────────────
print()
print("="*65)
print("ALL TODAY CANDLES — PE RAW SIGNAL SCAN")
print("="*65)
print(f"  {'Time':>5}  {'Body':>6}  {'ATR':>6}  {'Ratio':>6}  {'C<E21':>6}  {'E9<E21':>7}  {'C<PrLo':>7}  {'Raw':>4}  {'BodyF':>5}  Verdict")
print("  " + "-"*80)

for i, c in enumerate(today_candles):
    idx = all_candles.index(c)
    if idx < 21:
        continue
    e9  = ema9_all[idx]
    e21 = ema21_all[idx]
    if e9 is None or e21 is None:
        continue
    prev = all_candles[idx-1]
    body = abs(c.close - c.open)
    atr_val = atr_at(all_candles[:idx+1], period=14) or 1

    r1 = c.close < e21
    r2 = e9 < e21
    r3 = c.close < prev.low
    raw = r1 and r2 and r3
    body_ok = body >= atr_val * 0.35
    ratio = body / atr_val

    if raw:
        verdict = "→ ENTRY ✓" if body_ok else f"BODY_BLOCK (need {atr_val*0.35:.0f})"
    else:
        verdict = "no signal"

    mark = " ◄◄◄" if raw else ""
    print(f"  {c.timestamp.strftime('%H:%M'):>5}  {body:>6.1f}  {atr_val:>6.1f}  {ratio:>6.3f}  {str(r1):>6}  {str(r2):>7}  {str(r3):>7}  {'Y' if raw else 'N':>4}  {'Y' if body_ok else 'N':>5}  {verdict}{mark}")

print()
print("="*65)
print("ROOT CAUSE SUMMARY")
print("="*65)
print("""
  LAYER 1 — WebSocket dead from bot start (09:13) until restart (11:55)
  ────────────────────────────────────────────────────────────────────────
  • Bot process 1 ran from ~09:13 to 11:57 but never logged a single
    candle completion or signal evaluation for today.
  • Continuous WebSocket error 1006 every ~25 seconds all morning.
  • .bot_state.json showed yesterday's (Oct 7) candles — bot was blind.
  • The entire bearish move from 09:15 (72668) to 11:25 (71880) —
    a ~788-point drop — happened with the bot receiving zero ticks.
  • RESULT: All ORB, EMA, NATR, ATR, OB, VWAP, PDHL, TRB strategies
    had no data to evaluate. Zero signals possible.

  LAYER 2 — The ONE signal that did fire was blocked by Smart Entry
  ────────────────────────────────────────────────────────────────────────
  • After restart at 11:55, the EMA PE strategy evaluated the 11:55 candle.
  • Raw signal passed: close < EMA21, EMA9 < EMA21, close < prev.low
  • BUT: The 11:55 candle body was only 3.19 pts (open≈close, near-doji).
  • ATR(14) at that point = 85.87 pts (market was very volatile all day).
  • SMART_ENTRY_MIN_BODY_ATR_RATIO = 0.35 → requires body ≥ 30.05 pts.
  • 3.19 < 30.05 → SMART_ENTRY_BLOCKED_BODY fired. Correct behaviour.
  • The candle had almost no directional momentum despite EMA alignment —
    it would have been a high-risk, low-quality entry near a bounce zone.
""")
