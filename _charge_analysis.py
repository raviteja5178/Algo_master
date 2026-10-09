print('=== REAL PROBLEM ANALYSIS ===')
print()

gross   = 922
charges = 514.49
net     = gross - charges
trades  = 10
total_loss = 814 + 908
total_win  = gross + total_loss

print(f'Today backtest: 8W / 2L')
print(f'  Total wins   : Rs +{total_win:.0f}')
print(f'  Total losses : Rs -{total_loss:.0f}')
print(f'  Gross P&L    : Rs +{gross:.0f}')
print(f'  Charges      : Rs -{charges:.2f}  ({charges/gross*100:.0f}% of gross!)')
print(f'  NET          : Rs +{net:.2f}')
print()

print('=== THE REAL PROBLEM ===')
print()
print('  10 trades x Rs51 charges each = charges eating 56% of gross P&L')
print('  The 2 early losses (11:20, 11:25) lost Rs 1,722 combined')
print('  The 8 wins only recovered Rs 2,644 -- net gross just Rs 922')
print()

print('=== SCENARIOS ===')
print()
header = f"  {'Scenario':<42}  {'Trades':>6}  {'Gross':>8}  {'Charges':>8}  {'NET':>8}"
print(header)
print('  ' + '-' * 78)

scenarios = [
    ('All 10 trades (today backtest)',         10, 922,              514),
    ('Remove 2 early losses (wait 12:00+)',     8, 922+814+908,      int(8/10*514)),
    ('Max 3 trades/day cap',                    3, 437+195+339,      int(3/10*514)),
    ('Max 5 trades/day cap',                    5, 437+195+339+544+166, int(5/10*514)),
]

for name, t, gross_s, chg_s in scenarios:
    net_s = gross_s - chg_s
    print(f"  {name:<42}  {t:>6}  Rs{gross_s:>6.0f}  Rs{chg_s:>6.0f}  Rs{net_s:>+7.0f}")

print()
print('=== BREAK-EVEN PER TRADE ===')
print()
charge_pt = 514/10
min_pts   = charge_pt / (0.4 * 20)
print(f'  Charges per trade            : Rs {charge_pt:.1f}')
print(f'  Min SENSEX pts to break even : {min_pts:.1f} pts  (qty=20, delta=0.4)')
print()

print('=== WHAT NEEDS TO CHANGE ===')
print()
print('  1. REDUCE TRADE COUNT  -->  max 3-4 good trades/day not 10')
print('     Set NO_NEW_ENTRY_AFTER=12:30  OR  SMART_COOLDOWN_CANDLES=8')
print()
print('  2. WIDER TARGETS  -->  let winners run beyond TSL at 50-80 pts')
print('     Set SPOT_ATR_TARGET_RR=2.5  (was 1.5)  = 250 pts target')
print()
print('  3. INCREASE QUANTITY  -->  more profit per trade, same charges')
print('     Set QUANTITY=50  (was 20)  -> P&L scales 2.5x, charges stay flat')
print()
print('  4. AVOID FIRST 45 MIN  -->  block signals before 10:00')
print('     Most SL hits are in high-volatility open')
print()

avg_w_pts = (54.6+24.4+42.4+68.1+20.8+52.2+20.0+48.1) / 8
print('=== PROJECTION WITH FIXES ===')
print()
print(f'  Avg win today (8 wins)       : {avg_w_pts:.1f} SENSEX pts')
print(f'  At qty=50  : Rs {avg_w_pts*0.4*50:.0f} per win')
print()
print('  Qty=50, max 3 trades, wider target (2.5x RR):')
tgt_pts_wide = 90 * 2.5  # avg SL ~90 * 2.5
win_rs = tgt_pts_wide * 0.4 * 50
chg3   = 3 * 51.45
print(f'    Target pts   : {tgt_pts_wide:.0f} pts (ATR90 x3 x0.4 x2.5RR)')
print(f'    Win value    : Rs {win_rs:.0f}  per trade')
print(f'    3 trades     : Rs {3*win_rs:.0f} gross  -  Rs {chg3:.0f} charges')
print(f'    NET (2W 1L)  : Rs {2*win_rs - 90*0.4*50 - chg3:.0f}')
print()
print('  CONCLUSION: With qty=50 + max 4 trades/day, charges become <10% of P&L')
charge_pct_qty50 = (4*51.45) / (4 * avg_w_pts * 0.4 * 50) * 100
print(f'  Charge % at qty=50, 4 trades : {charge_pct_qty50:.1f}%  (vs 56% today)')
