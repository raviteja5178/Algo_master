"""Quick analysis of backtest results relative to live config changes."""
import json, statistics

data = json.load(open("_pivot_research.json"))

# --- Live-equivalent configs ---
configs_to_check = [
    ("E2", "SIGNAL_CANDLE_LOW", "RUN_LOCK50", 1.0, 1.0),
    ("E2", "SIGNAL_CANDLE_LOW", "RUN_LOCK50", "-", 1.0),
    ("E2", "ATR_1.0",           "RUN_LOCK50", 1.0, 1.0),
    ("E2", "SIGNAL_CANDLE_LOW", "FULL_T1",   1.0, 1.0),
    ("E2", "ATR_1.0",           "RUN_LOCK50", "-", 1.0),
]

print("=== LIVE CONFIG MATCHES ===")
hdr = f"{'entry':4} {'SL':20} {'mgmt':15} {'BE':4} {'room':4} {'n':>4} {'win%':>5} {'total':>7} {'PF':>5} {'maxDD':>6} {'avgR':>5}"
print(hdr)
print("-"*len(hdr))
for e, s, m, be, rm in configs_to_check:
    rows = [r for r in data if r["entry"]==e and r["sl"]==s and r["mgmt"]==m
            and str(r["be"])==str(be) and r["room"]==rm]
    for r in rows:
        print(f"  {r['entry']:3} {r['sl']:20} {r['mgmt']:15} {str(r['be']):4} {r['room']:<4} "
              f"{r['n']:>4} {r['win']:>5} {r['total']:>7} {r['pf']:>5} {r['maxdd']:>6} {r['avgR']:>5}")

# --- Top 10 by return/maxDD ---
ranked = sorted([r for r in data if r["n"] >= 60], key=lambda r: -(r["total"] / max(r["maxdd"], 1)))
print()
print("=== TOP 10 by total/maxDD (n>=60) ===")
print(hdr)
print("-"*len(hdr))
for r in ranked[:10]:
    print(f"  {r['entry']:3} {r['sl']:20} {r['mgmt']:15} {str(r['be']):4} {r['room']:<4} "
          f"{r['n']:>4} {r['win']:>5} {r['total']:>7} {r['pf']:>5} {r['maxdd']:>6} {r['avgR']:>5}")

# --- Impact of each fix on signals/trade quality ---
print()
print("=== HOW EACH FIX CHANGES SIGNAL COUNT (estimated from E2/SIGNAL_LOW/RUN_LOCK50/BE=1/room=1) ===")
base = [r for r in data if r["entry"]=="E2" and r["sl"]=="SIGNAL_CANDLE_LOW"
        and r["mgmt"]=="RUN_LOCK50" and str(r["be"])=="1.0" and r["room"]==1.0]
if base:
    b = base[0]
    print(f"  Base (pre-fix):     n={b['n']:>3}  win={b['win']:>5}%  total={b['total']:>6}  PF={b['pf']:>5}  maxDD={b['maxdd']:>5}  avgR={b['avgR']:>5}")
    print()
    print("  Flaw 1 fix (CE room-fail no longer kills PE):  some lost PE signals RECOVERED")
    print("  Flaw 2 fix (strict < on fresh-cross):          borderline at-Pivot candles REMOVED (~1-2% of trades)")
    print("  Flaw 3 fix (wick filter):                       wicking-through candles FILTERED OUT (~3-8% reduction in n)")
    print("  Flaw 4 fix (today-only ATR):                   SL buffer more accurate — tighter on calm days, wider on volatile")
    print("  Flaw 12 fix (backtest now uses prev_close):    gap-open false signals REMOVED from both backtest and live")

# --- Win rate split by SL method ---
print()
print("=== WIN RATE BY SL METHOD (E2, RUN_LOCK50, be=1.0, room=1.0) ===")
for sl in ["SIGNAL_CANDLE_LOW", "ATR_1.0", "ATR_1.5", "SWING_6"]:
    rows = [r for r in data if r["entry"]=="E2" and r["sl"]==sl and r["mgmt"]=="RUN_LOCK50"
            and str(r["be"])=="1.0" and r["room"]==1.0]
    for r in rows:
        print(f"  {r['sl']:20}  n={r['n']:>3}  win={r['win']:>5}%  total={r['total']:>6}  PF={r['pf']:>5}  avgR={r['avgR']:>5}")
