import sqlite3, json

conn = sqlite3.connect("trades.db")
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT * FROM trades WHERE entry_time LIKE '2026-10-09%' OR signal_timestamp LIKE '2026-10-09%' ORDER BY created_at"
).fetchall()

print(f"Trades found today: {len(rows)}")
for r in rows:
    d = dict(r)
    print(json.dumps(d, indent=2, default=str))

conn.close()
