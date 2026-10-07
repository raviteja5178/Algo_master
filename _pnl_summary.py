import sqlite3
from datetime import date

conn = sqlite3.connect("trades.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("""
    SELECT trade_id, option_symbol, strategy_type, entry_price, exit_price,
           realized_pnl, exit_reason, sl_points, target_points, atr_value,
           entry_time, exit_time, trade_mode
    FROM trades ORDER BY created_at DESC LIMIT 20
""")
rows = [dict(r) for r in cur.fetchall()]
conn.close()

total_pnl = 0
wins = losses = bes = 0

header = f"{'Date':<12} {'Symbol':<24} {'Strat':<10} {'Entry':>7} {'Exit':>7} {'PnL':>8}  {'Reason':<14} {'RR':>4}  Mode"
print(header)
print("-" * len(header))

for d in rows:
    pnl = d["realized_pnl"] or 0
    total_pnl += pnl
    if pnl > 0:   wins += 1
    elif pnl < 0: losses += 1
    else:         bes += 1
    sl  = d["sl_points"] or 0
    tgt = d["target_points"] or 0
    rr  = f"{tgt/sl:.1f}" if sl else "—"
    dt  = str(d["entry_time"])[:10]
    sym = d["option_symbol"]
    reason = (d["exit_reason"] or "")[:14]
    mode = d["trade_mode"]
    print(f"{dt:<12} {sym:<24} {d['strategy_type']:<10} {d['entry_price']:>7.2f} {(d['exit_price'] or 0):>7.2f} {pnl:>+8.0f}  {reason:<14} {rr:>4}  {mode}")

print("-" * len(header))
total = wins + losses + bes
wr = f"{wins/total*100:.0f}%" if total else "—"
print(f"Trades: {total}   W={wins}  L={losses}  BE={bes}   Winrate={wr}   Net PnL (₹)={total_pnl:+,.0f}")
