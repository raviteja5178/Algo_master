import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

entry = 128.20
atr   = 78.05
atm_delta = 0.5 * 0.4  # mult=0.5, delta=0.4

# Exact tick-by-tick from log
steps = [
    (151.45, 128.20, "BE activated"),
    (150.95, 137.30, "step 1"),
    (152.15, 138.00, "step 2"),
    (154.90, 140.75, "step 3"),
    (156.50, 142.35, "step 4"),
    (156.70, 142.55, "step 5"),
    (162.15, 148.00, "step 6"),
    (165.75, 151.60, "step 7"),
    (166.40, 152.25, "step 8"),
    (168.80, 154.65, "step 9"),
    (153.35, 154.65, "EXIT (SL hit)"),
]

print("=" * 65)
print("TRADE: SENSEX26O0871600PE  (entry=128.20, be_trigger=150.60)")
print("=" * 65)
print(f"  {'Event':<18}  {'LTP':>7}  {'SL':>7}  {'Locked':>8}  {'Trail gap':>10}")
print(f"  {'-'*18}  {'-'*7}  {'-'*7}  {'-'*8}  {'-'*10}")
for ltp, sl, label in steps:
    locked = sl - entry
    gap = ltp - sl
    print(f"  {label:<18}  {ltp:>7.2f}  {sl:>7.2f}  {locked:>+8.2f}  {gap:>10.2f}")

exit_price = 153.35
peak_ltp   = 168.80
pnl_actual = (exit_price - entry) * 20
pnl_peak   = (peak_ltp   - entry) * 20
pnl_left   = (peak_ltp - exit_price) * 20

print()
print(f"  Actual exit      : {exit_price}  PnL = +{pnl_actual:.0f}")
print(f"  Peak LTP         : {peak_ltp}  PnL at peak = +{pnl_peak:.0f}")
print(f"  Left on table    : +{pnl_left:.0f}  ({(pnl_left/pnl_peak*100):.0f}% of peak)")
print(f"  Trail dist@peak  : {peak_ltp - 154.65:.2f} pts  (very tight vs ATR={atr})")

print()
print("=" * 65)
print("ROOT CAUSE: WHY TSL CLOSED EARLY")
print("=" * 65)
print("""
  The ATR-dynamic trail distance = ATR(5) x 0.5 x 0.4 = ~15.6 pts
  But the bot ran 9 rapid-fire step updates in just 24 SECONDS
  (14:00:34 to 14:00:58) as the PaperFeed ticks spiked.

  At each tick, the stop chased the LTP extremely tightly:
    LTP 168.80  -->  SL 154.65  =  only 14.15 pts trail gap
    14.15 pts on a 78-ATR day = trail is only 18% of ATR

  When Sensex bounced even slightly (LTP fell from 168.80 to 153.35)
  the stop was hit immediately. The trail was too tight to survive
  a normal intraday pause/bounce.
""")

print("=" * 65)
print("WHAT-IF: Effect of widening TSL_ATR_TRAIL_MULT")
print("=" * 65)
print(f"  {'Mult':>5}  {'Trail dist':>11}  {'SL at peak 168.80':>18}  {'Locked PnL':>12}  {'% of peak'}")
print(f"  {'-'*5}  {'-'*11}  {'-'*18}  {'-'*12}  {'-'*10}")
for mult in [0.5, 0.7, 1.0, 1.25, 1.5, 2.0]:
    td  = round(atr * mult * 0.4, 2)
    slp = round(168.80 - td, 2)
    locked = max(0, round((slp - entry) * 20, 0))
    pct = locked / pnl_peak * 100
    current = " <-- CURRENT" if mult == 0.5 else ""
    print(f"  {mult:>5.2f}  {td:>11.2f}  {slp:>18.2f}  {locked:>+12.0f}  {pct:>8.0f}%{current}")

print()
print("=" * 65)
print("OTHER IMPROVEMENTS POSSIBLE")
print("=" * 65)
print("""
  1. INCREASE TSL_ATR_TRAIL_MULT  0.5 → 1.0 or 1.25
     - Trail dist grows from 15.6 to 31.2–39.1 pts
     - Survives normal intraday bounces without closing
     - Still ratchets up following the trend

  2. TSL_ATR_PERIOD 5 → 14
     - Uses longer-period ATR = smoother, less reactive
     - On this day ATR(14)≈86 vs ATR(5)≈78, wider trail

  3. SPOT_ATR_TRAIL_RR 0.3 → 0.5
     - Fixed-step fallback trail grows from 13.45 → 22.4 pts
     - Protects when ATR-dynamic mode is unavailable

  4. max_sl_pct cap is crushing SL width
     - Both trades: swing SL was 105-130 pts but capped to 44-54 pts
     - The CAP is making trail_pts (sl x 0.3) too tight
     - Consider raising max_sl_pct 0.35 → 0.50 for wider initial SL
       which naturally produces wider BE and trail too

  5. SENSEX26O0871600PE specifically:
     - Entry at 13:20 was mid-range (Sensex 71,607)
     - Market continued falling to 71,498 by 14:00 (-109 pts)
     - Then bounced +100pts to 71,660 — this bounce hit the TSL
     - A wider trail would have held through that bounce
""")
