"""
Full pivot trade review for today with before/after analysis of all fixes.
"""
import json, math

state = json.load(open(".bot_state.json"))
candles_raw = state.get("candles_5m", [])
pivot_raw   = state.get("pivot_levels")
ltp         = state.get("ltp", 0)

P  = pivot_raw["pivot"]   # 71871.65
R1 = pivot_raw["r1"]      # 72415.56
R2 = pivot_raw["r2"]      # 73237.87
S1 = pivot_raw["s1"]      # 71049.34
S2 = pivot_raw["s2"]      # 70505.43

class C:
    def __init__(self, d):
        self.ts = d["t"][11:16]
        self.o=d["o"]; self.h=d["h"]; self.l=d["l"]; self.c=d["c"]

candles = [C(d) for d in candles_raw]

def atr14(cs):
    if len(cs) < 2: return None
    trs = []
    for i in range(1, len(cs)):
        b, p = cs[i], cs[i-1]
        trs.append(max(b.h-b.l, abs(b.h-p.c), abs(b.l-p.c)))
    if not trs: return None
    if len(trs) < 14: return sum(trs)/len(trs)
    a = sum(trs[:14])/14
    for tr in trs[14:]: a = (a*13+tr)/14
    return a

# ── Scan all candles for OLD logic (no wick filter, <= boundary) ───────────
def scan_OLD(candles, P, R1, R2, S1, S2, sustain=2, buf=0.05):
    hits = []
    for k in range(sustain-1, len(candles)):
        window = candles[k-sustain+1:k+1]
        before = candles[k-sustain] if k >= sustain else None
        before_close = before.c if before else None
        entry = candles[k].c
        a = atr14(candles[:k+1]) or 1

        for side in ("CE","PE"):
            if side == "CE":
                sustained = all(c.c > P for c in window)   # OLD: close only
                fresh     = before_close is not None and before_close <= P  # OLD: <=
                t1,t2 = R1,R2
                stop  = min(c.l for c in window) - buf*a
                risk  = entry - stop
                room  = t1 - entry
            else:
                sustained = all(c.c < P for c in window)
                fresh     = before_close is not None and before_close >= P  # OLD: >=
                t1,t2 = S1,S2
                stop  = max(c.h for c in window) + buf*a
                risk  = stop - entry
                room  = entry - t1
            if not (sustained and fresh): continue
            if risk<=0 or room<=0: continue
            room_r = round(room/risk,2)
            hits.append(dict(ts=candles[k].ts, side=side, entry=round(entry,1),
                             stop=round(stop,1), risk=round(risk,1), t1=t1, t2=t2,
                             room_r=room_r, blocked_old=(room_r<1.0), candle=candles[k]))
    return hits

# ── Scan all candles for NEW logic (wick filter, strict <, today-ATR) ──────
def scan_NEW(candles, P, R1, R2, S1, S2, sustain=2, buf=0.05):
    hits = []
    for k in range(sustain-1, len(candles)):
        window = candles[k-sustain+1:k+1]
        before = candles[k-sustain] if k >= sustain else None
        before_close = before.c if before else None
        entry = candles[k].c
        a = atr14(candles[:k+1]) or 1

        for side in ("CE","PE"):
            if side == "CE":
                sustained = all(c.c > P and c.l > P for c in window)  # NEW: wick filter
                fresh     = before_close is not None and before_close < P  # NEW: strict <
                t1,t2 = R1,R2
                stop  = min(c.l for c in window) - buf*a
                risk  = entry - stop
                room  = t1 - entry
            else:
                sustained = all(c.c < P and c.h < P for c in window)
                fresh     = before_close is not None and before_close > P  # NEW: strict >
                t1,t2 = S1,S2
                stop  = max(c.h for c in window) + buf*a
                risk  = stop - entry
                room  = entry - t1
            if not (sustained and fresh): continue
            if risk<=0 or room<=0: continue
            room_r = round(room/risk,2)
            hits.append(dict(ts=candles[k].ts, side=side, entry=round(entry,1),
                             stop=round(stop,1), risk=round(risk,1), t1=t1, t2=t2,
                             room_r=room_r, blocked_new=(room_r<1.0), candle=candles[k]))
    return hits

old_hits = scan_OLD(candles, P, R1, R2, S1, S2)
new_hits = scan_NEW(candles, P, R1, R2, S1, S2)

print(f"P={P}  R1={R1}  R2={R2}  S1={S1}  S2={S2}")
print(f"LTP={ltp}  ATR(14)={round(atr14(candles) or 0,1)} pts")
print(f"Candles today: {len(candles)}")
print()
print(f"OLD logic hits: {len(old_hits)}   NEW logic hits: {len(new_hits)}")
print()

# print each candle's open/high/low/close vs Pivot for reference
print("=== TODAY'S CANDLES vs PIVOT ===")
print(f"{'Time':6}  {'Open':>9}  {'High':>9}  {'Low':>9}  {'Close':>9}  {'vs P':>8}  Notes")
print("-"*75)
for c in candles:
    side = "ABOVE" if c.c > P else "BELOW" if c.c < P else "AT"
    wick = ""
    if c.c > P and c.l < P: wick = " ⚠ LOW WICK BELOW P"
    if c.c < P and c.h > P: wick = " ⚠ HIGH WICK ABOVE P"
    print(f"{c.ts:6}  {c.o:>9.1f}  {c.h:>9.1f}  {c.l:>9.1f}  {c.c:>9.1f}  {side:>8}{wick}")

print()
print("=== OLD LOGIC SIGNALS (pre-fix) ===")
if old_hits:
    for h in old_hits:
        status = "BLOCKED(room)" if h["blocked_old"] else "VALID"
        print(f"  {h['ts']} {h['side']:2} entry={h['entry']} stop={h['stop']} risk={h['risk']} T1={h['t1']} room_r={h['room_r']} [{status}]")
else:
    print("  None")

print()
print("=== NEW LOGIC SIGNALS (post-fix) ===")
if new_hits:
    for h in new_hits:
        status = "BLOCKED(room)" if h["blocked_new"] else "VALID"
        print(f"  {h['ts']} {h['side']:2} entry={h['entry']} stop={h['stop']} risk={h['risk']} T1={h['t1']} room_r={h['room_r']} [{status}]")
else:
    print("  None")

print()
print("=== DIFFERENCE (signals removed by fixes) ===")
old_keys = set((h["ts"], h["side"]) for h in old_hits)
new_keys = set((h["ts"], h["side"]) for h in new_hits)
removed  = old_keys - new_keys
added    = new_keys - old_keys
if removed:
    for k in sorted(removed):
        h = next(x for x in old_hits if x["ts"]==k[0] and x["side"]==k[1])
        c = h["candle"]
        reason = []
        if h["side"]=="CE" and c.l < P: reason.append("wick below P")
        elif h["side"]=="PE" and c.h > P: reason.append("wick above P")
        if h["side"]=="CE":
            bc = candles[candles.index(c)-2].c if candles.index(c)>=2 else None
            if bc is not None and bc == P: reason.append("prev_close exactly at P (boundary removed)")
        print(f"  REMOVED: {k[0]} {k[1]} — {', '.join(reason) or 'strict boundary'}")
else:
    print("  No signals removed")
if added:
    for k in sorted(added):
        print(f"  ADDED (PE rescued from CE room-fail): {k[0]} {k[1]}")
else:
    print("  No new signals added (Flaw 1 rescue)")
