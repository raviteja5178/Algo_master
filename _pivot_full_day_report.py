"""
Full reconstruction of today's two pivot trades from the DB records.
Also reconstructs what candles triggered them and why the _vwap_analysis.json
showed different (later) data from the live bot.
"""
import json, sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

state = json.load(open('.bot_state.json'))
pv = state['pivot_levels']
P, R1, R2, S1, S2 = pv['pivot'], pv['r1'], pv['r2'], pv['s1'], pv['s2']

conn = sqlite3.connect('trades.db')

# Pull the two pivot trades
pivot_trades = conn.execute(
    "SELECT * FROM trades WHERE strategy_type IN ('CE_PIVOT','PE_PIVOT') "
    "AND date(entry_time) = '2026-10-09' ORDER BY entry_time"
).fetchall()
cols = [d[0] for d in conn.execute('SELECT * FROM trades LIMIT 0').description]

print("=" * 80)
print("TODAY'S PIVOT TRADES — FULL DETAIL  (2026-10-09)")
print("=" * 80)
print(f"\nPivot Levels:  P={P}  R1={R1}  R2={R2}  S1={S1}  S2={S2}\n")

for row in pivot_trades:
    t = dict(zip(cols, row))
    side = t['strategy_type']
    sign = 1 if side == 'CE_PIVOT' else -1
    entry = t['entry_price']
    entry_idx = t['sensex_entry']
    sl_idx = t['sensex_sl']
    t1_idx = t['sensex_t1']
    t2_idx = t['sensex_t2']
    risk_idx = abs(entry_idx - sl_idx)
    room_idx = abs(t1_idx - entry_idx)

    print("-" * 70)
    print(f"  Trade ID : {t['trade_id']}")
    print(f"  Strategy : {side}")
    print(f"  Mode     : {t['trade_mode']}")
    print(f"  Symbol   : {t['option_symbol']}")
    print()
    print(f"  SIGNAL   : candle {t['signal_timestamp'][:19].replace('T',' ')}")
    print(f"  ENTRY    : {t['entry_time'][:19].replace('T',' ')}  @  ₹{entry}  (SENSEX {entry_idx})")
    print(f"  Qty      : {t['quantity']} lots")
    print()
    print(f"  SENSEX setup:")
    print(f"    Stop (SL)    = {sl_idx}   ({'below' if side=='CE_PIVOT' else 'above'} entry)")
    print(f"    Risk         = {round(risk_idx,2)} idx pts  (~{round(risk_idx*0.4,1)} option pts at delta 0.4)")
    print(f"    T1           = {t1_idx}  ({'R1' if side=='CE_PIVOT' else 'S1'})")
    print(f"    T2           = {t2_idx}  ({'R2' if side=='CE_PIVOT' else 'S2'})")
    print(f"    Room to T1   = {round(room_idx,2)} idx pts")
    print(f"    Room/Risk    = {round(room_idx/risk_idx,2)}x  (min required: 1.0x)")
    print(f"    ATR at entry = {t['atr_value']}")
    print()
    print(f"  OPTION setup:")
    print(f"    Entry price  = ₹{entry}")
    print(f"    Init SL pts  = {t['sl_points']}  (option)")
    print(f"    TSL step pts = {t['tsl_points']}  (option trail step)")
    print(f"    Target pts   = {t['target_points']}  (option)")
    print(f"    Target ref   = ₹{t['target_reference']}")
    print()
    print(f"  DURING TRADE:")
    print(f"    Highest LTP  = ₹{t['highest_ltp']}")
    print(f"    Final stop   = ₹{t['current_stop']}")
    
    mfe = round(t['highest_ltp'] - entry, 2)
    print(f"    Max fav move = +{mfe} pts  (from entry to peak)")
    be_threshold = entry + sign * t['sl_points']  # approx
    print(f"    BE threshold ≈ ₹{round(entry + t['tsl_points']*2, 2)}  (moved to BE when +1x risk reached)")
    print()
    print(f"  EXIT:")
    print(f"    Exit time    = {t['exit_time'][:19].replace('T',' ')}")
    print(f"    Exit price   = ₹{t['exit_price']}")
    print(f"    Exit reason  = {t['exit_reason']}")
    pnl_pts = round(t['exit_price'] - entry, 2) * sign
    print(f"    PnL (option) = {'+' if t['realized_pnl']>0 else ''}{round(t['realized_pnl'],2)} rupees")
    print(f"    PnL pts      = {'+' if pnl_pts>0 else ''}{pnl_pts} pts x {t['quantity']} qty")
    print()

conn.close()
print("=" * 80)
print("SUMMARY")
print("=" * 80)

total = sum(dict(zip(cols, r))['realized_pnl'] for r in pivot_trades)
print(f"\n  Total pivot P&L today: {'+'if total>0 else ''}{round(total,2)} rupees")
print(f"  Trades: {len(pivot_trades)}")
print()
