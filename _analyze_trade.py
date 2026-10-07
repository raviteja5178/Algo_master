import sqlite3, json
from datetime import datetime

TARGET_SYMBOL = "SENSEX26O0872900CE"

conn = sqlite3.connect("trades.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT * FROM trades WHERE option_symbol=?", (TARGET_SYMBOL,))
rows = cur.fetchall()
print(f"Trades found for {TARGET_SYMBOL}: {len(rows)}\n")
for r in rows:
    print(json.dumps(dict(r), default=str, indent=2))

# Also pull order_actions for this trade
for r in rows:
    trade_id = dict(r).get("trade_id")
    cur.execute("SELECT * FROM order_actions WHERE trade_id=?", (trade_id,))
    actions = cur.fetchall()
    if actions:
        print(f"\nOrder actions for {trade_id}:")
        for a in actions:
            print(json.dumps(dict(a), default=str, indent=2))

conn.close()
