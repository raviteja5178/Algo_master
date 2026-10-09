import json

data = json.load(open("_pivot_research.json"))

# All RUN_LOCK50
rl = [r for r in data if r["mgmt"] == "RUN_LOCK50"]
print("Total RUN_LOCK50 rows:", len(rl))
print()
hdr = "entry SL                     BE   room    n  win%   total    PF  maxDD  avgR"
print(hdr)
print("-" * len(hdr))
for r in sorted(rl, key=lambda x: -x["total"])[:20]:
    line = "  %3s  %-22s %-4s %-4s %4d %5s %7d %5s %5d %5s" % (
        r["entry"], r["sl"], str(r["be"]), str(r["room"]),
        r["n"], str(r["win"]), r["total"], str(r["pf"]), r["maxdd"], str(r["avgR"])
    )
    print(line)

print()
print("=== ALL MGMTS for E2/SIGNAL_CANDLE_LOW/be=1.0/room=1.0 ===")
rows = [r for r in data if r["entry"] == "E2" and r["sl"] == "SIGNAL_CANDLE_LOW"
        and str(r["be"]) == "1.0" and r["room"] == 1.0]
for r in sorted(rows, key=lambda x: -x["total"]):
    line = "  mgmt=%-15s n=%3d win=%5s%% total=%6d PF=%5s maxDD=%5d avgR=%5s" % (
        r["mgmt"], r["n"], str(r["win"]), r["total"], str(r["pf"]), r["maxdd"], str(r["avgR"])
    )
    print(line)

print()
print("=== E2 / be=1.0 / room=1.0 — best mgmt per SL ===")
for sl in sorted(set(r["sl"] for r in data)):
    rows = [r for r in data if r["entry"] == "E2" and str(r["be"]) == "1.0"
            and r["room"] == 1.0 and r["sl"] == sl]
    if not rows:
        continue
    best = max(rows, key=lambda x: x["total"])
    line = "  %-22s  best=%-15s  n=%3d  win=%5s%%  total=%6d  PF=%5s  maxDD=%5d" % (
        sl, best["mgmt"], best["n"], str(best["win"]), best["total"], str(best["pf"]), best["maxdd"]
    )
    print(line)
