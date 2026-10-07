import sqlite3
from datetime import date

conn = sqlite3.connect('trades.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

today = date.today().isoformat()
print(f"=== TODAY: {today} ===\n")

# ── EXECUTED TRADES ──────────────────────────────────────────────
print("─" * 70)
print("EXECUTED TRADES")
print("─" * 70)
cur.execute("""
    SELECT trade_id, option_symbol, strategy_type, entry_price, exit_price,
           realized_pnl, quantity, entry_time, exit_time, exit_reason,
           current_stop, target_reference, sl_points, tsl_points, target_points,
           atr_value, status, smart_entry_flags, sensex_entry, sensex_sl, sensex_t1
    FROM trades
    WHERE date(entry_time) = ?
    ORDER BY entry_time
""", (today,))
trades = cur.fetchall()
if trades:
    for i, r in enumerate(trades, 1):
        pnl = r["realized_pnl"]
        if pnl is None:
            pnl_str = "OPEN"
        elif pnl > 0:
            pnl_str = f"+{pnl:.0f}"
        else:
            pnl_str = f"{pnl:.0f}"
        flags = r["smart_entry_flags"] or "—"
        print(f"\n  T{i}  {r['option_symbol']}")
        print(f"       Strategy : {r['strategy_type']}")
        print(f"       Status   : {r['status']}")
        print(f"       Entry    : {r['entry_time']}  price={r['entry_price']}")
        print(f"       SL/Tgt   : stop={r['current_stop']}  tgt_ref={r['target_reference']}")
        print(f"       Points   : sl={r['sl_points']}  tsl={r['tsl_points']}  tgt={r['target_points']}  atr={r['atr_value']}")
        print(f"       Sensex   : entry={r['sensex_entry']}  sl={r['sensex_sl']}  t1={r['sensex_t1']}")
        print(f"       Exit     : {r['exit_time']}  price={r['exit_price']}  reason={r['exit_reason']}")
        print(f"       PnL      : {pnl_str}  qty={r['quantity']}")
        print(f"       SE Flags : {flags}")
else:
    print("  (none today)")

print()

# ── ALL PROCESSED SIGNALS ────────────────────────────────────────
print("─" * 70)
print("ALL PROCESSED SIGNALS")
print("─" * 70)
cur.execute("""
    SELECT signal_id, strategy_type, candle_timestamp, processed_at
    FROM processed_signals
    WHERE date(candle_timestamp) = ?
    ORDER BY candle_timestamp
""", (today,))
sigs = cur.fetchall()
if sigs:
    print(f"  {'#':<4} {'Time':<22} {'Strategy':<30} {'Processed At'}")
    print(f"  {'-'*4} {'-'*22} {'-'*30} {'-'*22}")
    for i, r in enumerate(sigs, 1):
        print(f"  {i:<4} {r['candle_timestamp']:<22} {r['strategy_type']:<30} {r['processed_at']}")
else:
    print("  (none today)")

print(f"\n  Total signals processed today: {len(sigs)}")
print(f"  Total trades executed  today: {len(trades)}")

conn.close()
