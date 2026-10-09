import sqlite3, json
from pathlib import Path

db = Path('trades.db')
if not db.exists():
    print('No trades.db found')
    exit()

conn = sqlite3.connect('trades.db')

tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print('Tables:', [t[0] for t in tables])
print()

# All trades
try:
    cols_q = conn.execute('SELECT * FROM trades LIMIT 0')
    cols = [d[0] for d in cols_q.description]
    print('trades columns:', cols)
    rows = conn.execute('SELECT * FROM trades ORDER BY rowid DESC LIMIT 20').fetchall()
    print('Last 20 trades in DB:')
    for r in rows:
        print(dict(zip(cols, r)))
except Exception as e:
    print('trades error:', e)

print()

# Processed signals - pivot only
try:
    sig_cols_q = conn.execute('SELECT * FROM processed_signals LIMIT 0')
    sig_cols = [d[0] for d in sig_cols_q.description]
    print('processed_signals columns:', sig_cols)
    sigs = conn.execute("SELECT * FROM processed_signals WHERE signal_id LIKE '%PIVOT%' ORDER BY rowid DESC LIMIT 30").fetchall()
    print('PIVOT processed_signals (%d):' % len(sigs))
    for s in sigs:
        print(dict(zip(sig_cols, s)))
    
    print()
    all_recent = conn.execute("SELECT * FROM processed_signals ORDER BY rowid DESC LIMIT 30").fetchall()
    print('All recent processed_signals (last 30):')
    for s in all_recent:
        print(dict(zip(sig_cols, s)))
except Exception as e:
    print('processed_signals error:', e)

conn.close()
