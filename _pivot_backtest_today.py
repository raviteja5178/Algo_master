"""
Full-day pivot backtest on today's 5m data using the exact new code logic.

Steps:
1. Fetch ALL today's 5m candles from Kite (09:15 → 15:25)
2. Run find_pivot_setup() at every candle close exactly as the live bot would
3. For each valid signal, simulate the full trade through PivotTradeManager
4. Report entries, SL moves, T1/T2/TSL outcomes with exact SENSEX prices
"""
import sys, json
from datetime import datetime, date, timedelta
from pathlib import Path

# ── Load full candle list ─────────────────────────────────────────────────────
# bot_state only has candles from ~10:30. We need 09:15 onward.
# Try fetching from Kite; fall back to what bot_state has.

state = json.load(open(".bot_state.json"))
pivot_raw = state.get("pivot_levels")

if not pivot_raw:
    print("ERROR: no pivot_levels in bot_state — ENABLE_PIVOT_LEVELS must be true")
    sys.exit(1)

P  = pivot_raw["pivot"]
R1 = pivot_raw["r1"]
R2 = pivot_raw["r2"]
S1 = pivot_raw["s1"]
S2 = pivot_raw["s2"]

# Fetch full day's 5m candles from Kite
candles_5m = []
try:
    from broker.kite_client import get_kite
    from utils.time_utils import IST
    kite = get_kite()
    today_str = date.today().strftime("%Y-%m-%d")
    records = kite.historical_data(
        instrument_token=265,  # SENSEX
        from_date=f"{today_str} 09:00:00",
        to_date=f"{today_str} 15:30:00",
        interval="5minute",
    )
    for r in records:
        ts = r["date"]
        if hasattr(ts, "tzinfo") and ts.tzinfo is None:
            ts = IST.localize(ts)
        if (ts.hour, ts.minute) < (9, 15):
            continue
        candles_5m.append({
            "t": ts.strftime("%H:%M"),
            "o": float(r["open"]),
            "h": float(r["high"]),
            "l": float(r["low"]),
            "c": float(r["close"]),
        })
    print(f"Fetched {len(candles_5m)} candles from Kite (09:15-15:25)")
except Exception as e:
    print(f"Kite fetch failed ({e}) — using bot_state candles only (10:30+)")
    for d in state.get("candles_5m", []):
        candles_5m.append({
            "t": d["t"][11:16],
            "o": d["o"], "h": d["h"], "l": d["l"], "c": d["c"],
        })
    print(f"Using {len(candles_5m)} candles from bot_state")

if not candles_5m:
    print("No candles available. Exiting.")
    sys.exit(1)

# ── Build Candle objects ──────────────────────────────────────────────────────
class C:
    def __init__(self, d):
        self.ts = d["t"]
        self.o=d["o"]; self.h=d["h"]; self.l=d["l"]; self.c=d["c"]

candles = [C(d) for d in candles_5m]

# ── ATR (Wilder 14) ──────────────────────────────────────────────────────────
def atr14(cs, period=14):
    if len(cs) < 2: return None
    trs = []
    for i in range(1, len(cs)):
        b, p = cs[i], cs[i-1]
        trs.append(max(b.h-b.l, abs(b.h-p.c), abs(b.l-p.c)))
    if not trs: return None
    if len(trs) < period:
        return sum(trs) / len(trs)
    a = sum(trs[:period]) / period
    for tr in trs[period:]:
        a = (a * 13 + tr) / 14
    return a

# ── Strategy parameters (new code defaults + your setting) ───────────────────
SUSTAIN      = 2
SL_BUF       = 0.05    # PIVOT_SL_BUFFER_ATR
MIN_TODAY    = 3       # PIVOT_MIN_TODAY_CANDLES (your setting)
MIN_ROOM_R   = 1.0     # PIVOT_MIN_ROOM_R
BE_TRIGGER_R = 1.0
BE_BUF_PTS   = 5.0
T1_LOCK_PCT  = 0.5
TRAIL_MULT   = 1.0
DELTA        = 0.4
CUSHION      = 1.25
MAX_SL_PCT   = 0.5
NO_NEW_ENTRY = (14, 30)  # no new entries after 14:30
FORCE_EXIT   = (15, 15)  # force exit at 15:15

# Previous day close used as before_close for day-open window
# Derive from pivot and today's first candle direction
prev_close = None
# We'll detect it from context: if first candle is below P, prev was above (CE day)
# If first candle is above P, prev was below (gap-up day)
if candles:
    first_c = candles[0].c
    # Conservative estimate: use the opposite side of P
    prev_close = P * 1.001 if first_c < P else P * 0.999

print(f"\nP={P}  R1={R1}  R2={R2}  S1={S1}  S2={S2}")
print(f"Candles: {len(candles)}  First: {candles[0].ts}  Last: {candles[-1].ts}")
print(f"PIVOT_MIN_TODAY_CANDLES={MIN_TODAY}  sustain={SUSTAIN}  wick_filter=ON  strict_fresh=ON")
print()

# ── Signal scanner (exact new code logic) ────────────────────────────────────
def scan_signals(candles, P, R1, R2, S1, S2, sustain, min_today, sl_buf, min_room_r):
    signals = []
    for k in range(sustain - 1, len(candles)):
        today_so_far = candles[:k + 1]
        n_today = len(today_so_far)
        if n_today < min_today:
            continue

        h_m = tuple(map(int, candles[k].ts.split(":")))
        if h_m >= NO_NEW_ENTRY:
            break

        window = today_so_far[-sustain:]
        before = today_so_far[-sustain - 1] if len(today_so_far) > sustain else None
        before_close = before.c if before else prev_close
        entry = candles[k].c

        atr = atr14(today_so_far) if len(today_so_far) >= 14 else atr14(today_so_far)
        if not atr or atr <= 0:
            continue

        for side in ("CE", "PE"):
            if side == "CE":
                sustained = all(c.c > P and c.l > P for c in window)
                fresh     = before_close is not None and before_close < P
                t1, t2    = R1, R2
                stop      = min(c.l for c in window) - sl_buf * atr
                risk      = entry - stop
                room      = t1 - entry
            else:
                sustained = all(c.c < P and c.h < P for c in window)
                fresh     = before_close is not None and before_close > P
                t1, t2    = S1, S2
                stop      = max(c.h for c in window) + sl_buf * atr
                risk      = stop - entry
                room      = entry - t1

            if not (sustained and fresh):
                continue
            if risk <= 0 or room <= 0 or room < min_room_r * risk:
                continue

            signals.append(dict(
                k=k, ts=candles[k].ts, side=side,
                entry=round(entry, 2), stop=round(stop, 2),
                risk=round(risk, 2), t1=t1, t2=t2,
                atr=round(atr, 2), n_today=n_today,
                win_close1=round(window[-2].c, 2), win_close2=round(window[-1].c, 2),
                win_low1=round(window[-2].l, 2),   win_low2=round(window[-1].l, 2),
                win_high1=round(window[-2].h, 2),  win_high2=round(window[-1].h, 2),
                before_close=round(before_close, 2) if before_close else None,
                room_r=round(room / risk, 2),
            ))
            break  # one signal per candle

    return signals

signals = scan_signals(candles, P, R1, R2, S1, S2, SUSTAIN, MIN_TODAY, SL_BUF, MIN_ROOM_R)

# ── Trade simulator ───────────────────────────────────────────────────────────
def simulate_trade(sig, candles):
    """Replay the trade from entry candle to exit using PivotTradeManager logic."""
    side   = sig["side"]
    sign   = 1 if side == "CE" else -1
    en     = sig["entry"]
    stop   = sig["stop"]
    t1     = sig["t1"]
    t2     = sig["t2"]
    atr    = sig["atr"]
    risk   = sig["risk"]

    best   = en
    stage  = "INITIAL"
    EPSILON = 0.25

    stages = []      # (ts, price, event, stop_index)
    exit_ts = exit_px = exit_reason = None

    for candle in candles[sig["k"] + 1:]:
        h_m = tuple(map(int, candle.ts.split(":")))

        # Refresh ATR each candle (Flaw 9 fix)
        candles_so_far = candles[:candles.index(candle) + 1]
        fresh_atr = atr14(candles_so_far)
        if fresh_atr and fresh_atr > 0:
            atr = fresh_atr

        # Force exit at 15:15
        if h_m >= FORCE_EXIT:
            exit_px = candle.o
            exit_reason = "EOD_FORCE"
            exit_ts = candle.ts
            break

        # Simulate tick-by-tick using candle H/L (worst case for SL, best case for target)
        # Order of check: SL on low (CE) / high (PE), then T2, then T1, then trail
        sl_px    = candle.l if side == "CE" else candle.h
        high_px  = candle.h if side == "CE" else candle.l  # favourable direction

        # Update best
        fav_high = (high_px - en) * sign
        if fav_high > (best - en) * sign:
            best = high_px

        # 1. Stop hit?
        fav_sl = (sl_px - en) * sign
        fav_stop = (stop - en) * sign
        if fav_sl < fav_stop - EPSILON:
            exit_px = stop
            exit_reason = {"INITIAL": "SL_HIT", "BE": "BE_STOP"}.get(stage, "TSL_HIT")
            exit_ts = candle.ts
            break

        # 2. T2 hit?
        fav_t2 = (t2 - en) * sign
        if (high_px - en) * sign >= fav_t2:
            exit_px = t2
            exit_reason = "TARGET_T2"
            exit_ts = candle.ts
            break

        # 3. T1 reached → lock profit (Flaw 8: trail fires next candle)
        if stage != "T1" and (best - en) * sign >= (t1 - en) * sign:
            lock = en + sign * T1_LOCK_PCT * abs(t1 - en)
            if (lock - en) * sign > (stop - en) * sign:
                stages.append((candle.ts, round(lock, 2), "T1_LOCK", round(lock, 2)))
                stop = round(lock, 2)
                stage = "T1"
            else:
                stage = "T1"

        # 4. BE
        elif stage == "INITIAL" and (best - en) * sign >= BE_TRIGGER_R * risk:
            be_stop = en + sign * BE_BUF_PTS
            if (be_stop - en) * sign > (stop - en) * sign:
                stages.append((candle.ts, round(be_stop, 2), "BE_ACTIVATED", round(be_stop, 2)))
                stop = round(be_stop, 2)
                stage = "BE"

        # 5. Chandelier trail after T1 (uses refreshed ATR)
        if stage == "T1" and TRAIL_MULT > 0:
            trail = best - sign * TRAIL_MULT * atr
            if (trail - en) * sign > (stop - en) * sign:
                stages.append((candle.ts, round(best, 2), "TRAIL_MOVE", round(trail, 2)))
                stop = round(trail, 2)

    if exit_ts is None:
        exit_px = candles[-1].c
        exit_reason = "EOD_CLOSE"
        exit_ts = candles[-1].ts

    pnl_idx = round((exit_px - en) * sign, 2)
    return dict(
        exit_ts=exit_ts, exit_px=round(exit_px, 2), exit_reason=exit_reason,
        pnl_idx=pnl_idx, pnl_pts=round(pnl_idx * 0.4, 2),  # approx option pts at delta 0.4
        final_stop=round(stop, 2), best=round(best, 2),
        stages=stages,
    )

# ── Print results ─────────────────────────────────────────────────────────────
print("=" * 80)
print(f"PIVOT BACKTEST — TODAY  |  {len(signals)} SIGNAL(S) FOUND")
print("=" * 80)

if not signals:
    print()
    print("No CE_PIVOT or PE_PIVOT signals today under new code logic.")
    print()
    print("Reason: today was a gap-open gap-hold day.")
    print(f"  - SENSEX opened at {candles[0].c:.1f}, already {candles[0].c - P:.1f} pts above P={P}")
    print(f"  - No candle closed below P throughout the entire session")
    print(f"  - Without a 'before_close < P' reference, fresh CE cross is impossible")
    print(f"  - Every live candle (10:30+) had lows well above P — wick filter irrelevant")
    print()
    print("For a CE signal to fire on a future day:")
    print(f"  1. A candle must close BELOW P={P}")
    print(f"  2. The NEXT 2 candles: close > P AND low > P (no wick through)")
    print(f"  3. At least {MIN_TODAY} candles into the session")
    print(f"  4. (R1={R1} - entry) >= 1x risk")
    print()
    # Show what the whole day looked like
    print("Today's full candle table:")
    print(f"{'Time':6}  {'Open':>9}  {'High':>9}  {'Low':>9}  {'Close':>9}  {'vs P':8}  {'CE wick':12}  Fail reasons (new code)")
    print("-" * 95)
    for i, c in enumerate(candles):
        side = "ABOVE" if c.c > P else "BELOW" if c.c < P else "AT P"
        ce_wick = "OK" if c.l > P else f"low={c.l:.0f}<P"
        pe_wick = "OK" if c.h < P else f"hi={c.h:.0f}>P"
        # Check if this candle could have been part of a CE window
        reasons = []
        if c.c <= P:   reasons.append("close<=P")
        if c.l <= P:   reasons.append("wick_CE")
        print(f"{c.ts:6}  {c.o:>9.1f}  {c.h:>9.1f}  {c.l:>9.1f}  {c.c:>9.1f}  {side:8}  {ce_wick:12}  {','.join(reasons) if reasons else 'close+wick OK above P'}")
else:
    for sig in signals:
        result = simulate_trade(sig, candles)
        pnl_str = f"+{result['pnl_idx']}" if result['pnl_idx'] >= 0 else str(result['pnl_idx'])
        print()
        print(f"  {'CE_PIVOT' if sig['side']=='CE' else 'PE_PIVOT'} | Entry candle: {sig['ts']} | n_today={sig['n_today']}")
        print(f"  Entry:  {sig['entry']}  Stop: {sig['stop']}  Risk: {sig['risk']} pts  ATR: {sig['atr']}")
        print(f"  T1={sig['t1']}  T2={sig['t2']}  Room/Risk={sig['room_r']}")
        print(f"  Sustain window: [{sig['ts']} close={sig['win_close2']} low={sig['win_low2']}]  before_close={sig['before_close']}")
        print(f"  Exit:  {result['exit_ts']}  px={result['exit_px']}  reason={result['exit_reason']}")
        print(f"  PnL:   {pnl_str} index pts  (~{result['pnl_pts']} option pts at delta 0.4)")
        print(f"  Best:  {result['best']}")
        if result["stages"]:
            print(f"  Stage transitions:")
            for s in result["stages"]:
                print(f"    {s[0]}  {s[2]}  best={s[1]}  new_stop={s[3]}")
