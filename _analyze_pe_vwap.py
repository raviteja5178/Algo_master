from market.historical_data import fetch_historical_candles, SENSEX_TOKEN
from market.candle_builder import Candle
from market.indicators import ema, atr as atr_ind

candles_all = fetch_historical_candles(SENSEX_TOKEN, interval="5minute", days_back=2)
oct07 = [c for c in candles_all if c.timestamp.date().isoformat() == "2026-10-07"]
oct06 = [c for c in candles_all if c.timestamp.date().isoformat() == "2026-10-06"]

# ── Context window ────────────────────────────────────────────────────────────
print("=== SENSEX 5m candles 12:30 – 13:30 (2026-10-07) ===")
window = [c for c in oct07 if "12:30" <= c.timestamp.strftime("%H:%M") <= "13:30"]
print(f"  {'Time':<6}  {'Open':>8}  {'High':>8}  {'Low':>8}  {'Close':>8}  {'Body':>6}  Note")
for c in window:
    t = c.timestamp.strftime("%H:%M")
    body = abs(c.close - c.open)
    d = "UP" if c.close > c.open else "DN"
    note = ""
    if t == "12:55": note = " <── signal candle (close=72720, vwap=72857)"
    if t == "13:00": note = " <── entry candle"
    if t == "13:10": note = " <── highest_ltp=435 window"
    if t == "13:15": note = " <── exit window (stop ratcheted, then hit)"
    print(f"  {t:<6}  {c.open:>8.2f}  {c.high:>8.2f}  {c.low:>8.2f}  {c.close:>8.2f}  {body:>6.1f}  [{d}]{note}")

# ── EMA context at signal (candle 12:55) ─────────────────────────────────────
combo = oct06 + oct07
idx_signal = next((i for i, c in enumerate(combo) if c.timestamp.date().isoformat() == "2026-10-07" and c.timestamp.strftime("%H:%M") == "12:55"), None)

if idx_signal:
    closes = [c.close for c in combo[:idx_signal+1]]
    e9  = ema(closes, 9)
    e21 = ema(closes, 21)
    gap_now  = e9[-1]  - e21[-1]
    gap_prev = e9[-2]  - e21[-2]
    gap_vel  = gap_now - gap_prev
    print(f"\n=== EMA context at signal candle (12:55) ===")
    print(f"  EMA9={e9[-1]:.2f}  EMA21={e21[-1]:.2f}  gap={gap_now:+.2f}  velocity={gap_vel:+.2f}")
    print(f"  Gap direction: {'PE territory (EMA9<EMA21)' if gap_now < 0 else 'CE territory — WRONG for PE'}")
    print(f"  EMA9 slope: {'FALLING ✓ (consistent with PE)' if e9[-1] < e9[-2] else 'RISING ✗ (conflicts with PE)'}")

    # ATR
    a = atr_ind(combo[:idx_signal+1], 14)
    atr14 = next((v for v in reversed(a) if v is not None), None)
    sig_candle = combo[idx_signal]
    body = abs(sig_candle.close - sig_candle.open)
    print(f"\n=== Body / ATR check (signal candle 12:55) ===")
    print(f"  O={sig_candle.open:.2f}  H={sig_candle.high:.2f}  L={sig_candle.low:.2f}  C={sig_candle.close:.2f}")
    print(f"  body={body:.2f}  ATR(14)={atr14:.2f}  ratio={body/atr14:.3f}")
    print(f"  Would body filter (ratio>=0.35) have blocked? {'YES — body too small' if body < atr14*0.35 else 'NO — body passes'}")

    # EMA gap widening check
    print(f"\n=== EMA gap widening check ===")
    print(f"  gap_prev={gap_prev:+.2f}  gap_now={gap_now:+.2f}  velocity={gap_vel:+.2f}")
    # For PE, gap should be growing more negative (gap_now < gap_prev)
    widening_for_pe = gap_now < gap_prev
    print(f"  PE needs gap growing more negative (gap_now < gap_prev)")
    print(f"  Widening? {'YES ✓' if widening_for_pe else 'NO ✗ — gap shrinking, would have blocked'}")

# ── VWAP context ──────────────────────────────────────────────────────────────
print(f"\n=== VWAP context ===")
print(f"  signal close=72720.0  VWAP=72857.53  → close is {72857.53-72720.0:.2f} pts BELOW vwap ✓ (bearish)")
print(f"  VWAP bounce: price closed below VWAP = confirms PE_VWAP signal direction")

# ── Trade timeline reconstruction ────────────────────────────────────────────
print(f"\n=== Trade Timeline ===")
events = [
    ("13:00:01", "ENTRY",    296.85, "SL=205.20 (91.65 pts below)"),
    ("13:05:59", "BE",       342.75, "Stop 205.20 → 296.85 (entry). +45.9 pts gain triggered BE"),
    ("13:08:20", "TRAIL #1", 363.95, "Stop 296.85 → 315.20  (+18.35 pts)"),
    ("13:08:34", "TRAIL #2", 379.45, "Stop 315.20 → 333.55  (+18.35 pts)"),
    ("13:09:09", "TRAIL #3", 404.60, "Stop 333.55 → 351.90  (+18.35 pts)"),
    ("13:10:02", "TRAIL #4", 417.95, "Stop 351.90 → 370.25  (+18.35 pts)"),
    ("13:10:34", "TRAIL #5", 435.00, "Stop 370.25 → 388.60  (+18.35 pts) ← HIGHEST LTP"),
    ("13:12:39", "SL HIT",   387.05, "Exit @ 387.05  PnL = +₹1,804"),
]
for ts, ev, ltp, note in events:
    pnl = (ltp - 296.85) * 20
    print(f"  {ts}  {ev:<12}  LTP={ltp:>6.2f}  option_gain={ltp-296.85:>+7.2f}  {note}")

print(f"\n=== Summary ===")
print(f"  Highest LTP reached : 435.00  (+138.15 pts from entry)")
print(f"  Exit price          : 387.05  (+90.20 pts from entry)")
print(f"  PnL                 : +₹1,804  (20 qty × 90.20 pts)")
print(f"  SL hit at           : 388.60 (TSL stop after 5 trail steps)")
print(f"  Exit reason         : STOP_HIT — but this is a PROFITABLE trail exit, not a loss SL")

# ── Post-exit SENSEX ──────────────────────────────────────────────────────────
exit_c = next((c for c in oct07 if c.timestamp.strftime("%H:%M") == "13:15"), None)
if exit_c:
    print(f"\n=== SENSEX after exit (13:15 candle) ===")
    print(f"  O={exit_c.open:.2f}  H={exit_c.high:.2f}  L={exit_c.low:.2f}  C={exit_c.close:.2f}")
    after = [c for c in oct07 if c.timestamp.strftime("%H:%M") > "13:12"]
    if after:
        low_after  = min(c.low  for c in after[:6])
        high_after = max(c.high for c in after[:6])
        print(f"  Next 6 candles: low={low_after:.2f}  high={high_after:.2f}")
        print(f"  Sensex continued falling? {'YES' if low_after < exit_c.open - 50 else 'NO — reversed'}")
