import sqlite3, json
from datetime import date

conn = sqlite3.connect('trades.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

today = date.today().isoformat()
print(f"=== BLOCKED / SKIPPED / REJECTED ENTRIES TODAY: {today} ===\n")

# 1. Trades with non-normal statuses today
print("── TRADES (any status) today ──")
cur.execute("""
    SELECT trade_id, option_symbol, strategy_type, status, entry_time,
           entry_price, realized_pnl, exit_reason, smart_entry_flags
    FROM trades
    WHERE date(entry_time) = ? OR date(created_at) = ?
    ORDER BY created_at
""", (today, today))
rows = cur.fetchall()
if rows:
    for r in rows:
        print(f"  [{r['status']}] {r['option_symbol']} | {r['strategy_type']} | entry={r['entry_time']} price={r['entry_price']} | exit_reason={r['exit_reason']} | flags={r['smart_entry_flags']}")
else:
    print("  (none)")

print()

# 2. Processed signals today (signals that were seen but may not have traded)
print("── PROCESSED SIGNALS today ──")
cur.execute("""
    SELECT signal_id, strategy_type, candle_timestamp, processed_at
    FROM processed_signals
    WHERE date(candle_timestamp) = ? OR date(processed_at) = ?
    ORDER BY processed_at
""", (today, today))
sigs = cur.fetchall()
if sigs:
    for r in sigs:
        print(f"  [{r['signal_id']}] {r['strategy_type']} | candle={r['candle_timestamp']} | processed={r['processed_at']}")
else:
    print("  (none)")

print()

# 3. Order actions today
print("── ORDER ACTIONS today ──")
cur.execute("""
    SELECT a.action_id, a.trade_id, a.action_type, a.broker_order_id, a.status, a.created_at
    FROM order_actions a
    WHERE date(a.created_at) = ?
    ORDER BY a.created_at
""", (today,))
actions = cur.fetchall()
if actions:
    for r in actions:
        print(f"  [{r['status']}] trade={r['trade_id']} | {r['action_type']} | broker_order={r['broker_order_id']} | {r['created_at']}")
else:
    print("  (none)")

print()

# 4. Summary
print("── SUMMARY ──")
print(f"  Trades today        : {len(rows)}")
print(f"  Signals processed   : {len(sigs)}")
print(f"  Order actions today : {len(actions)}")

conn.close()
