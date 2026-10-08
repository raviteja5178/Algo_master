import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

entry       = 128.20
sl_pts      = 44.85
be_pts      = 22.40
trail_pts   = 13.45
target_pts  = 67.30
atr         = 78.05
tsl_atr_mult = 0.5
ATM_DELTA    = 0.4
highest_ltp  = 147.95

print("=== TRADE: SENSEX26O0871600PE ===")
print(f"  Entry price    : {entry}")
print(f"  Initial SL     : {entry - sl_pts:.2f}  (sl_pts={sl_pts})")
print(f"  BE trigger     : LTP >= {entry + be_pts:.2f}  (entry + {be_pts} pts)")
print(f"  Trail step     : {trail_pts} pts  (fixed-step fallback)")
print(f"  Target         : {entry + target_pts:.2f}  (entry + {target_pts} pts)")
print(f"  ATR(14) at entry: {atr}")
print()

trail_dist_atr = round(atr * tsl_atr_mult * ATM_DELTA, 2)
print("=== ATR-DYNAMIC TSL (TSL_ATR_TRAIL_MULT=0.5, active after BE) ===")
print(f"  Trail dist = ATR({atr}) x {tsl_atr_mult} x delta({ATM_DELTA}) = {trail_dist_atr:.2f} pts")
print()

print("=== WHAT UI SHOWS ===")
print("  TSL STEPS: 1 dot filled  (1 x 13 pts = +13 pts SL raise)")
print("  This label uses trail_pts=13.45, implying fixed-step mode display")
print()

print("=== BREAK-EVEN CHECK ===")
be_threshold = entry + be_pts
gap = be_threshold - highest_ltp
if highest_ltp >= be_threshold:
    print(f"  BE threshold {be_threshold:.2f}: REACHED (highest={highest_ltp})")
else:
    print(f"  BE threshold {be_threshold:.2f}: NOT REACHED")
    print(f"  Highest LTP reached: {highest_ltp}  (fell short by {gap:.2f} pts)")
    print(f"  SL correctly stays at: {entry - sl_pts:.2f} (original)")
print()

print("=== IS '1 dot filled' CORRECT? ===")
print(f"  BE not activated -> 0 trail steps completed")
print(f"  UI shows 1 dot filled -> this is the BE dot (step 0), not a trail step")
print(f"  The label '1 x 13 pts' is misleading — it means '1 unit of trail_pts'")
print(f"  which would only apply IF BE was activated, which it was not.")
print()

print("=== TSL STEP PROGRESSION (what would happen if price moves up) ===")
print(f"  {'Condition':<35}  {'SL moves to':>12}  {'Locked profit':>14}")
print(f"  {'-'*35}  {'-'*12}  {'-'*14}")
print(f"  LTP >= {be_threshold:.2f} (Break-even)          ->  {entry:>10.2f}  {'(BE, 0 pts)':>14}")
for step in range(1, 9):
    ltp_needed = be_threshold + step * trail_pts
    new_sl = entry + step * trail_pts
    profit_locked = step * trail_pts
    print(f"  LTP >= {ltp_needed:.2f} (Step {step})              ->  {new_sl:>10.2f}  {'+' + str(round(profit_locked,2)) + ' pts':>14}")
print()

print("=== VERDICT ===")
print("  Q: Is the TSL step display correct?")
print(f"  A: The dot count and label are displayed by the UI, but conceptually")
print(f"     0 trail steps have actually been EXECUTED because:")
print(f"     1. Highest LTP = {highest_ltp} < BE threshold {be_threshold:.2f}")
print(f"        -> Break-even was never activated")
print(f"        -> SL correctly remains at {entry - sl_pts:.2f}")
print(f"     2. The '1 dot' in UI likely represents the BE step slot (pre-activation)")
print(f"        not a completed trail step")
print(f"     3. trail_pts = {trail_pts} and the UI label says 13 pts — this is CORRECT")
print(f"        (13.45 rounded to 13 for display)")
print(f"     4. ATR-dynamic mode (mult=0.5) only activates AFTER BE fires,")
print(f"        so fixed-step trail_pts is shown in the label — also CORRECT")
