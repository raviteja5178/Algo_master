"""
Run pivot signal simulation on today's candles from .bot_state.json
using the fixed strategy logic (strict fresh-cross, wick filter, today-ATR).
"""
import json, math
from datetime import datetime, date

state = json.load(open(".bot_state.json"))
candles_raw = state.get("candles_5m", [])
pivot_raw   = state.get("pivot_levels")
ltp         = state.get("ltp", 0)

if not pivot_raw:
    print("No pivot_levels in .bot_state.json — bot may have ENABLE_PIVOT_LEVELS=false")
    exit(0)

P  = pivot_raw["pivot"]
R1 = pivot_raw["r1"]
R2 = pivot_raw["r2"]
S1 = pivot_raw["s1"]
S2 = pivot_raw["s2"]
print(f"TODAY PIVOT LEVELS — P={P}  R1={R1}  R2={R2}  S1={S1}  S2={S2}")
print(f"Current LTP: {ltp}")
print(f"Total 5m candles today: {len(candles_raw)}")
print()

# Build candle structs
class C:
    def __init__(self, d):
        self.ts  = d["t"]
        self.o   = d["o"]; self.h = d["h"]
        self.l   = d["l"]; self.c = d["c"]

candles = [C(d) for d in candles_raw]

# ── ATR (Wilder 14) on today's candles ──────────────────────────────────────
def atr14(candles):
    if len(candles) < 2: return None
    trs = []
    for i in range(1, len(candles)):
        b, p = candles[i], candles[i-1]
        trs.append(max(b.h-b.l, abs(b.h-p.c), abs(b.l-p.c)))
    if len(trs) < 14: return sum(trs)/len(trs)  # simple avg if too few
    a = sum(trs[:14])/14
    for tr in trs[14:]:
        a = (a*13 + tr)/14
    return a

atr = atr14(candles)
print(f"ATR(14) today: {round(atr,1) if atr else 'N/A'} pts")

# ── Simulate sustain=2 with all fixes ───────────────────────────────────────
SUSTAIN = 2
SL_BUFFER = 0.05

print()
print(f"{'Candle':20}  {'Side':4}  {'Entry':>8}  {'Stop':>8}  {'Risk':>6}  {'T1':>8}  {'T2':>8}  {'Room':>6}  {'RoomR':>6}  Status")
print("-"*120)

signals_found = []
for k in range(SUSTAIN, len(candles)):
    window = candles[k-SUSTAIN+1 : k+1]   # last 2 completed candles
    before = candles[k-SUSTAIN] if k >= SUSTAIN else None
    before_close = before.c if before else None
    entry_c = candles[k]
    entry = entry_c.c

    # ATR at this point
    a = atr14(candles[:k+1]) or atr or 1

    ts_label = entry_c.ts[11:16]

    for side in ("CE", "PE"):
        if side == "CE":
            sustained = all(c.c > P and c.l > P for c in window)
            fresh     = before_close is not None and before_close < P
            t1, t2    = R1, R2
            stop      = min(c.l for c in window) - SL_BUFFER * a
            risk      = entry - stop
            room      = t1 - entry
        else:
            sustained = all(c.c < P and c.h < P for c in window)
            fresh     = before_close is not None and before_close > P
            t1, t2    = S1, S2
            stop      = max(c.h for c in window) + SL_BUFFER * a
            risk      = stop - entry
            room      = entry - t1

        if not (sustained and fresh): continue
        if risk <= 0 or room <= 0: continue
        room_r = round(room / risk, 2)
        status = "✓ VALID (room>=1R)" if room_r >= 1.0 else "✗ BLOCKED (room<1R)"
        print(f"{ts_label:20}  {side:4}  {entry:>8.1f}  {round(stop,1):>8.1f}  {round(risk,1):>6.1f}  {t1:>8.1f}  {t2:>8.1f}  {round(room,1):>6.1f}  {room_r:>6.2f}  {status}")
        if room_r >= 1.0:
            signals_found.append(dict(ts=ts_label, side=side, entry=entry,
                                      stop=round(stop,1), risk=round(risk,1),
                                      t1=t1, t2=t2, room_r=room_r, atr=round(a,1)))

print()
print(f"Valid signals found today: {len(signals_found)}")

# ── For each valid signal, simulate trade management (mark-to-current) ───────
if signals_found and ltp:
    print()
    print("=== TRADE SIMULATION (entry → current LTP) ===")
    for sig in signals_found:
        side  = sig["side"]
        en    = sig["entry"]
        stop  = sig["stop"]
        t1    = sig["t1"]
        t2    = sig["t2"]
        risk  = sig["risk"]
        a     = sig["atr"]
        sign  = 1 if side=="CE" else -1
        fav   = (ltp - en) * sign

        be_trigger = 1.0 * risk
        be_stop    = en + sign * 5.0  # be_buffer_pts=5

        print(f"  [{sig['ts']}] {side} entry={en:.1f}  stop={stop:.1f}  T1={t1:.1f}  T2={t2:.1f}  risk={risk:.1f}")
        print(f"    Current LTP={ltp:.1f}  fav={fav:+.1f} pts  ({round(fav/risk*100,1)}% of risk)")

        if fav < -0.25:  # epsilon guard
            print(f"    Stage: STOPPED OUT  (below stop {stop})")
        elif (ltp * sign) >= (t2 * sign):
            print(f"    Stage: T2 HIT — full exit")
        elif (ltp * sign) >= (t1 * sign):
            lock = en + sign * 0.5 * abs(t1 - en)
            trail = ltp - sign * 1.0 * a
            current_stop = max(lock, trail) if side == "CE" else min(lock, trail)
            locked = (current_stop - en) * sign
            print(f"    Stage: T1 HIT — locked {locked:+.1f} pts  chandelier_stop={current_stop:.1f}")
        elif fav >= be_trigger:
            print(f"    Stage: BE — stop moved to {be_stop:.1f}  (break-even + 5 pts)")
        else:
            print(f"    Stage: INITIAL — holding, stop={stop:.1f}")
        print()
