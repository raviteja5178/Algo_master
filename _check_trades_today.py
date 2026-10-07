import sqlite3, json
from datetime import date

conn = sqlite3.connect('trades.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print('Tables:', tables)

today = date.today().isoformat()
print(f'Today: {today}\n')

for tbl in tables:
    try:
        cur.execute(f"SELECT * FROM {tbl} ORDER BY rowid DESC")
        rows = cur.fetchall()
    except Exception as e:
        print(f"[{tbl}] error: {e}")
        continue
    if not rows:
        print(f"[{tbl}] empty")
        continue
    today_rows = [dict(r) for r in rows if today in str(list(dict(r).values()))]
    if today_rows:
        print(f"=== {tbl} ({len(today_rows)} entries today) ===")
        for r in today_rows:
            print(json.dumps(r, default=str, indent=2))
        print()
    else:
        sample = dict(rows[0])
        print(f"=== {tbl} (0 today; last row) ===")
        print(json.dumps(sample, default=str))
        print()

conn.close()
