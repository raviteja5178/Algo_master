import sqlite3, json
conn = sqlite3.connect("trades.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT * FROM trades WHERE option_symbol=?", ("SENSEX26O0872700PE",))
rows = cur.fetchall()
print(f"Trades: {len(rows)}")
for r in rows:
    print(json.dumps(dict(r), default=str, indent=2))
conn.close()
