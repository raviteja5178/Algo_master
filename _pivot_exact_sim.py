"""
Exact simulation of find_pivot_setup() on today's candles
with PIVOT_MIN_TODAY_CANDLES=3 and the new wick filter (Flaw 3) active.

For each completed candle from the 3rd onwards, we check:
  - sustain: all(c.close > P AND c.low > P) for CE window [last 2 candles]
  - fresh:   before_close < P (strict)
  - room:    (T1 - entry) >= 1.0 * risk

We also check what OLD code would have done (no wick filter, <= boundary).
"""
import json

state = json.load(open(".bot_state.json"))
raw = state.get("candles_5m", [])
ltp = state.get("ltp", 0)
pivot_raw = state.get("pivot_levels")

if not pivot_raw:
    print("No pivot_levels in bot_state — ENABLE_PIVOT_LEVELS must be true")
    exit(1)

P  = pivot_raw["pivot"]
R1 = pivot_raw["r1"]
R2 = pivot_raw["r2"]
S1 = pivot_raw["s1"]
S2 = pivot_raw["s2"]

# The bot_state only has candles from 10:30 onward (warm-up window retained).
# We also need the early candles (09:15-10:25) from today which are NOT in bot_state.
# We know from DB: PE_PIVOT entry sensex=71824 at 09:25, CE_PIVOT entry sensex=72080 at 09:35.
# These give us the approximate early candle structure.
# Reconstruct first 5 candles from DB trade data.

# From DB: PE_PIVOT at 09:25 had sensex_entry=71824.92, sensex_sl=72039.48
# inferred: sustain window [09:20, 09:25] had max_high = 72039.48 - 0.05*150.85 = 72031.94
# and those candles closed below P=71871.65

# From DB: CE_PIVOT at 09:35 had sensex_entry=72080.28, sensex_sl=71800.95
# inferred: sustain window [09:30, 09:35] had min_low = 71800.95 + 0.05*152 = 71808.55
# Note: 71808.55 < P=71871.65 → wick below Pivot on CE sustain window

# So early candles:
# 09:15: around 71800 (just below P) — the PE setup candle 1
# 09:20: close~71824 (below P), high~72031 (ABOVE P!) → wick above P
# 09:25: close~71824 (below P), this is the PE entry candle
# 09:30: close~72080 (above P), low~71808 (below P!) → wick below P
# 09:35: close~72080 (above P), this is the CE entry candle

class Candle:
    def __init__(self, ts, o, h, l, c):
        self.ts = ts; self.o=o; self.h=h; self.l=l; self.c=c

# Reconstruct approximate early candles from trade evidence
# (prev_close from PivotLevels = yesterday's close, used as before_close when k=0)
# PE fresh cross: before_close > P → yesterday closed above P
prev_close = 72100.0  # reasonable estimate: yesterday closed above P (CE day)

early = [
    Candle("09:15", 71900, 71920, 71750, 71820),  # 1st: below P, after gap down open
    Candle("09:20", 71820, 72032, 71760, 71825),  # 2nd: close below P, high ABOVE P (wick)
    Candle("09:25", 71825, 71900, 71760, 71825),  # 3rd: PE entry — close below P
    Candle("09:30", 71825, 72120, 71808, 72080),  # 4th: cross above P, low BELOW P (wick)
    Candle("09:35", 72080, 72150, 71808, 72080),  # 5th: CE entry — close above P, low BELOW P
]

# Today's candles from bot_state (10:30 onward)
live = []
for d in raw:
    ts = d["t"][11:16]
    live.append(Candle(ts, d["o"], d["h"], d["l"], d["c"]))

all_today = early + live
print(f"P={P}  R1={R1}  R2={R2}  S1={S1}  S2={S2}")
print(f"Total today candles: {len(all_today)} ({len(early)} reconstructed early + {len(live)} from bot_state)")
print(f"Current LTP: {ltp}")
print()

# ATR helper (simple — multi-day fallback; today has <14 for early candles)
def atr_simple(candles, period=14):
    if len(candles) < 2: return None
    trs = []
    for i in range(1, len(candles)):
        b, p = candles[i], candles[i-1]
        trs.append(max(b.h-b.l, abs(b.h-p.c), abs(b.l-p.c)))
    if not trs: return None
    if len(trs) < period: return sum(trs)/len(trs)
    a = sum(trs[:period])/period
    for tr in trs[period:]: a = (a*13+tr)/14
    return a

SUSTAIN = 2
SL_BUF  = 0.05
MIN_TODAY_NEW = 3   # NEW setting you specified
MIN_TODAY_OLD = 0   # what was effectively running before (or whatever fired the trades)

print("=" * 90)
print(f"SIMULATION: PIVOT_MIN_TODAY_CANDLES=3, sustain=2, wick filter ON (new code)")
print("=" * 90)
print()
print(f"{'Time':6}  {'Open':>9}  {'High':>9}  {'Low':>9}  {'Close':>9}  {'vs P':7}  {'WickOK_CE':10}  {'WickOK_PE':10}")
print("-" * 85)

for c in all_today:
    side_str = "ABOVE" if c.c > P else "BELOW" if c.c < P else "AT P "
    wick_ce = "low>P" if c.l > P else f"low={c.l:.0f}(<P!)"
    wick_pe = "high<P" if c.h < P else f"high={c.h:.0f}(>P!)"
    print(f"{c.ts:6}  {c.o:>9.1f}  {c.h:>9.1f}  {c.l:>9.1f}  {c.c:>9.1f}  {side_str:7}  {wick_ce:15}  {wick_pe}")

print()
print("=" * 90)
print("SIGNAL SCAN — NEW CODE (min_today=3, strict fresh-cross, wick filter ON)")
print("=" * 90)
print()

signals_new = []
signals_old = []

for k in range(SUSTAIN-1, len(all_today)):
    today_so_far = all_today[:k+1]
    n_today = len(today_so_far)
    window = today_so_far[-SUSTAIN:]
    before = today_so_far[-SUSTAIN-1] if len(today_so_far) > SUSTAIN else None
    entry_c = today_so_far[-1]
    entry = entry_c.c
    ts = entry_c.ts

    # before_close: if no before candle (first N of day), use prev_close
    if before is None:
        before_close = prev_close
    else:
        before_close = before.c

    # ATR at this point (today only if >=14, else all today)
    a = atr_simple(today_so_far) or 50.0  # fallback

    for side in ("CE", "PE"):
        if side == "CE":
            # NEW: wick filter
            sustained_new = all(c.c > P and c.l > P for c in window)
            # OLD: close only
            sustained_old = all(c.c > P for c in window)
            # NEW: strict <
            fresh_new = before_close is not None and before_close < P
            # OLD: <=
            fresh_old = before_close is not None and before_close <= P
            t1, t2 = R1, R2
            stop = min(c.l for c in window) - SL_BUF * a
            risk = entry - stop
            room = t1 - entry
        else:
            # NEW: wick filter
            sustained_new = all(c.c < P and c.h < P for c in window)
            # OLD: close only
            sustained_old = all(c.c < P for c in window)
            # NEW: strict >
            fresh_new = before_close is not None and before_close > P
            # OLD: >=
            fresh_old = before_close is not None and before_close >= P
            t1, t2 = S1, S2
            stop = max(c.h for c in window) + SL_BUF * a
            risk = stop - entry
            room = entry - t1

        if risk <= 0 or room <= 0:
            continue
        room_r = round(room / risk, 2)

        # NEW code evaluation
        if (sustained_new and fresh_new and n_today >= MIN_TODAY_NEW and room_r >= 1.0):
            signals_new.append(dict(ts=ts, side=side, entry=round(entry,1),
                                    stop=round(stop,1), risk=round(risk,1),
                                    t1=t1, t2=t2, room_r=room_r, atr=round(a,1),
                                    n_today=n_today, window=[(c.ts,round(c.c,1),round(c.l,1),round(c.h,1)) for c in window]))

        # OLD code evaluation (no wick, <=/>= boundary, min_today=0)
        if (sustained_old and fresh_old and room_r >= 1.0):
            signals_old.append(dict(ts=ts, side=side, entry=round(entry,1),
                                    stop=round(stop,1), risk=round(risk,1),
                                    t1=t1, t2=t2, room_r=room_r, atr=round(a,1),
                                    n_today=n_today))

# ─── Print NEW results ────────────────────────────────────────────────────────
if signals_new:
    print(f"{'Time':6}  {'Side':4}  {'Entry':>9}  {'Stop':>9}  {'Risk':>6}  {'T1':>9}  {'T2':>9}  {'RoomR':>6}  {'ATR':>6}  nToday  Window")
    print("-" * 110)
    for s in signals_new:
        w = "  ".join(f"{t[0]}(c={t[1]},l={t[2]},h={t[3]})" for t in s["window"])
        print(f"{s['ts']:6}  {s['side']:4}  {s['entry']:>9.1f}  {s['stop']:>9.1f}  {s['risk']:>6.1f}  {s['t1']:>9.1f}  {s['t2']:>9.1f}  {s['room_r']:>6.2f}  {s['atr']:>6.1f}  {s['n_today']:>3}     {w}")
else:
    print("  No valid signals found today under new code (min_today=3, wick filter ON)")

print()
print("=" * 90)
print("SIGNAL SCAN — OLD CODE (min_today=0, no wick filter, <= boundary)")
print("=" * 90)
print()
if signals_old:
    print(f"{'Time':6}  {'Side':4}  {'Entry':>9}  {'Stop':>9}  {'Risk':>6}  {'RoomR':>6}  nToday")
    print("-" * 60)
    for s in signals_old:
        print(f"{s['ts']:6}  {s['side']:4}  {s['entry']:>9.1f}  {s['stop']:>9.1f}  {s['risk']:>6.1f}  {s['room_r']:>6.2f}  {s['n_today']:>3}")
else:
    print("  No valid signals found today under old code either")

print()
print("=" * 90)
print("WHAT NEEDS TO HAPPEN FOR NEW CODE TO FIRE A CE SIGNAL TODAY")
print("=" * 90)
print()
print(f"  CE requirements (all must hold simultaneously):")
print(f"  1. At least 3 today-candles completed (min_today=3)")
print(f"  2. Last 2 candles: close > {P} AND low > {P}  [wick filter]")
print(f"  3. The candle before the window: close < {P}  [strict fresh cross from below]")
print(f"  4. room = (R1 - entry) >= 1.0 * risk  [R1={R1}]")
print()
print(f"  Today's candle lows vs P={P}:")
for c in all_today:
    ok = "OK (low>P)" if c.l > P else f"FAIL (low={c.l:.1f} < P)"
    print(f"    {c.ts}  low={c.l:.1f}  {ok}")
print()
print(f"  ALL live candles (10:30+) have lows > {P}? Let's check:")
all_ok = all(c.l > P for c in live)
print(f"    {all_ok} — " + ("YES, all live candles (10:30+) pass wick filter" if all_ok else "NO, some live candles wick below P"))
print()
print(f"  Can CE fire now? SENSEX is {ltp} which is {round(ltp - P, 1)} pts above P.")
print(f"  Every candle today (10:30+) has closed well above P. No cross of P has occurred.")
print(f"  For a CE_PIVOT: need a candle that closes below P first (to set fresh_cross for the next window).")
print(f"  Current distance to P: {round(ltp - P, 1)} pts down needed to touch P.")
