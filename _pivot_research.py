"""
Pivot-sustain strategy research — 1 year SENSEX 5m.
CE: 5m candle closes above Pivot (fresh cross)  -> T1=R1, T2=R2
PE: 5m candle closes below Pivot (fresh cross)  -> T1=S1, T2=S2
Tests SL methods x trade management x entry confirmation x room filter.
Simulated on SENSEX index points (expired weekly option history is not available from Kite).
Option P&L approx = index pts x 0.4 delta. Costs: 10 index pts per trade (charges+slippage).
"""
import itertools, statistics, json
from datetime import date, timedelta, datetime
from collections import defaultdict
from broker.kite_client import get_kite

kite = get_kite()
END = date.today(); START = END - timedelta(days=365)
COST = 10.0          # index pts per round-trip
MAX_TRADES_DAY = 3
NO_NEW = (14, 30); FORCE = (15, 15)

# ── Data ─────────────────────────────────────────────────────────────────────
bars = []
d = START
while d <= END:
    e = min(d + timedelta(days=90), END)
    for r in kite.historical_data(265, f"{d} 09:15:00", f"{e} 15:30:00", "5minute"):
        t = r["date"]
        if (t.hour, t.minute) < (9, 15) or (t.hour, t.minute) > (15, 25): continue
        bars.append(dict(t=t, o=r["open"], h=r["high"], l=r["low"], c=r["close"]))
    d = e + timedelta(days=1)
bars.sort(key=lambda b: b["t"])
daily = kite.historical_data(265, f"{START - timedelta(days=10)}", f"{END}", "day")
dclose = {r["date"].date(): r for r in daily}
ddays = sorted(dclose)

# ATR(14) Wilder on continuous 5m series
atr = [None] * len(bars); trs = []
for i in range(1, len(bars)):
    b, p = bars[i], bars[i - 1]
    trs.append(max(b["h"] - b["l"], abs(b["h"] - p["c"]), abs(b["l"] - p["c"])))
    if len(trs) == 14: atr[i] = sum(trs) / 14
    elif len(trs) > 14: atr[i] = (atr[i - 1] * 13 + trs[-1]) / 14

by_day = defaultdict(list)
for i, b in enumerate(bars): by_day[b["t"].date()].append(i)

def pivots(day):
    prev = [x for x in ddays if x < day]
    if not prev: return None
    r = dclose[prev[-1]]; H, L, C = r["high"], r["low"], r["close"]
    P = (H + L + C) / 3
    return dict(P=P, R1=2 * P - L, R2=P + (H - L), S1=2 * P - H, S2=P - (H - L))

# ── Simulation (CE logic; PE handled by price negation) ──────────────────────
def flip(b): return dict(t=b["t"], o=-b["o"], h=-b["l"], l=-b["h"], c=-b["c"])

def run(entry_mode, sl_mode, mgmt, be_r, room):
    trades = []
    for day, idx in by_day.items():
        pv = pivots(day)
        if not pv or len(idx) < 10: continue

        # FIX (Flaw 12): use the previous trading day's close (from dclose) as the
        # gap-open reference — matching the live code which uses PivotLevels.prev_close.
        # The old code used cur["o"] (today's open) which is a different price.
        prev_days = [x for x in ddays if x < day]
        prev_day_close_raw = dclose[prev_days[-1]]["close"] if prev_days else None

        n_today = 0
        # iterate bars chronologically, both sides, one position at a time
        k = 0
        # FIX (Flaw 13): in live code, ENABLE_PIVOT_STRATEGY evaluation now runs
        # independently of the candle-attempted guard (Flaw 6 fix), so every
        # candle is evaluated for a pivot setup regardless of whether EMA/VWAP
        # fired first.  The backtest already evaluates pivot on every bar, so
        # this is now consistent.  No backtest code change required here; the
        # NOTE is preserved so future research readers understand the behaviour.
        # FIX (Flaw 14): track the bar index just before the current signal search
        # window started (not the bar after a trade exit) so the prev_ref for the
        # next entry attempt always reflects the candle immediately before the
        # potential cross, not an arbitrary mid-trade candle.
        while k < len(idx):
            i = idx[k]; t = bars[i]["t"]
            if (t.hour, t.minute) >= NO_NEW or n_today >= MAX_TRADES_DAY: break
            fired = None
            for side in ("CE", "PE"):
                f = (lambda b: b) if side == "CE" else flip
                P = pv["P"] if side == "CE" else -pv["P"]
                T1 = pv["R1"] if side == "CE" else -pv["S1"]
                T2 = pv["R2"] if side == "CE" else -pv["S2"]
                OPP = pv["S1"] if side == "CE" else -pv["R1"]
                cur = f(bars[i])
                # FIX (Flaw 12): when k==0 (first bar of the day) use the previous
                # day's close (same as PivotLevels.prev_close in live code).
                # For intraday bars use the immediately preceding bar's close.
                if k == 0:
                    prev_close_raw = prev_day_close_raw
                    prev_ref = (f({"o": prev_close_raw, "h": prev_close_raw,
                                   "l": prev_close_raw, "c": prev_close_raw})["c"]
                                if prev_close_raw is not None else None)
                else:
                    prev_ref = f(bars[idx[k - 1]])["c"]
                # Fresh cross: prev_ref must be STRICTLY on the other side of P
                # (strict inequality — matches the updated live code).
                if prev_ref is None:
                    continue  # no reference available → block signal (gap-open conservative)
                cross = cur["c"] > P and prev_ref < P
                if not cross: continue
                ent_k = k
                if entry_mode == "E2":          # 2nd candle must also close above P
                    if k + 1 >= len(idx): continue
                    nxt = f(bars[idx[k + 1]])
                    if nxt["c"] <= P: continue
                    ent_k = k + 1
                ei = idx[ent_k]; eb = f(bars[ei]); entry = eb["c"]
                a = atr[ei] or 0
                if not a: continue
                lows = [f(bars[idx[j]])["l"] for j in range(max(0, ent_k - 5), ent_k + 1)]
                sig_low = min(f(bars[idx[j]])["l"] for j in range(k, ent_k + 1))
                stop = {"PIVOT-0.25ATR": P - 0.25 * a,
                        "SIGNAL_CANDLE_LOW": sig_low - 0.05 * a,
                        "ATR_1.0": entry - 1.0 * a,
                        "ATR_1.5": entry - 1.5 * a,
                        "MID_P_S1": (P + OPP) / 2,
                        "SWING_6": min(lows) - 0.05 * a}[sl_mode]
                risk = entry - stop
                if risk <= 0 or entry >= T1: continue
                # FIX (Flaw 1): use `continue` not `break` so that when CE fails
                # the room filter, PE is still evaluated on the same bar.
                if (T1 - entry) < room * risk: continue
                fired = (side, f, ent_k, entry, stop, risk, T1, T2, a)
                break
            if not fired:
                k += 1; continue

            side, f, ent_k, entry, stop, risk, T1, T2, a = fired
            n_today += 1
            rem = 1.0; pnl = 0.0; t1 = False; hi = entry; reason = "EOD"
            j = ent_k + 1
            while j < len(idx):
                b = f(bars[idx[j]]); tt = bars[idx[j]]["t"]
                if (tt.hour, tt.minute) >= FORCE:
                    pnl += rem * (b["o"] - entry); reason = "EOD" if not t1 else "T1+EOD"; break
                if b["l"] <= stop:
                    px = min(stop, b["o"]); pnl += rem * (px - entry)
                    reason = ("SL" if px < entry - 0.01 else "BE/TSL") if not t1 else "T1+TSL"
                    if not t1 and px > entry + 0.01: reason = "TSL_PROFIT"
                    break
                if not t1 and b["h"] >= T1:
                    if mgmt == "FULL_T1":
                        pnl += rem * (max(T1, b["o"]) - entry); reason = "T1"; rem = 0; break
                    if mgmt == "RUN_LOCK50":   # 1 lot: no partial, lock 50% of T1 gain, trail to T2
                        t1 = True; stop = max(stop, entry + 0.5 * (T1 - entry))
                        j += 1; hi = max(hi, b["h"]); continue
                    pnl += 0.5 * (T1 - entry); rem = 0.5; t1 = True
                    if mgmt == "HALF_LOCK50": stop = max(stop, entry + 0.5 * (T1 - entry))
                    else: stop = max(stop, entry)
                if t1 and b["h"] >= T2:
                    pnl += rem * (T2 - entry); reason = "T1+T2"; rem = 0; break
                hi = max(hi, b["h"])
                if be_r and hi - entry >= be_r * risk: stop = max(stop, entry + COST / 2)
                if t1 and mgmt in ("HALF_ATR_TRAIL", "HALF_LOCK50", "RUN_LOCK50"):
                    stop = max(stop, hi - 1.0 * a)
                j += 1
            else:
                lb = f(bars[idx[-1]]); pnl += rem * (lb["c"] - entry)
            trades.append(dict(day=str(day), side=side, entry=round(entry * (1 if side == "CE" else -1), 2),
                               risk=round(risk, 1), pnl=round(pnl - COST, 1), reason=reason, R=round((pnl - COST) / risk, 2)))
            k = j + 1
    return trades

def stats(tr):
    if not tr: return None
    p = [t["pnl"] for t in tr]; w = [x for x in p if x > 0]; l = [x for x in p if x <= 0]
    eq = 0; pk = 0; dd = 0
    for x in p: eq += x; pk = max(pk, eq); dd = max(dd, pk - eq)
    return dict(n=len(p), win=round(100 * len(w) / len(p), 1), total=round(sum(p)), avg=round(sum(p) / len(p), 1),
                pf=round(sum(w) / abs(sum(l)), 2) if l and sum(l) else 99, maxdd=round(dd),
                avg_risk=round(statistics.median(t["risk"] for t in tr), 1),
                avgR=round(sum(t["R"] for t in tr) / len(tr), 2))

SLS = ["PIVOT-0.25ATR", "SIGNAL_CANDLE_LOW", "ATR_1.0", "ATR_1.5", "MID_P_S1", "SWING_6"]
MG = ["FULL_T1", "HALF_BE", "HALF_ATR_TRAIL", "HALF_LOCK50", "RUN_LOCK50"]
import sys
if len(sys.argv) > 1 and sys.argv[1] == "single-lot":
    for s in ("ATR_1.0", "SIGNAL_CANDLE_LOW"):
        for m in ("FULL_T1", "RUN_LOCK50", "HALF_BE"):
            st = stats(run("E2", s, m, 1.0, 1.0))
            print(f"{s:18} {m:12} n={st['n']} win={st['win']}% total={st['total']} PF={st['pf']} maxDD={st['maxdd']}")
    sys.exit()
res = []
for e, s, m, be, rm in itertools.product(["E1", "E2"], SLS, MG, [None, 1.0], [0.0, 1.0]):
    st = stats(run(e, s, m, be, rm))
    if st: res.append(dict(entry=e, sl=s, mgmt=m, be=be or "-", room=rm, **st))

print(f"Data: {bars[0]['t'].date()} -> {bars[-1]['t'].date()}  | {len(by_day)} days | {len(bars)} bars | cost {COST} idx pts/trade")
hdr = f"{'entry':5} {'SL':18} {'mgmt':15} {'BE@R':4} {'room':4} {'n':>4} {'win%':>5} {'total':>7} {'avg':>6} {'PF':>5} {'maxDD':>6} {'medRisk':>7} {'avgR':>5}"
def show(rows, title):
    print("\n" + title); print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{r['entry']:5} {r['sl']:18} {r['mgmt']:15} {str(r['be']):4} {r['room']:<4} {r['n']:>4} {r['win']:>5} "
              f"{r['total']:>7} {r['avg']:>6} {r['pf']:>5} {r['maxdd']:>6} {r['avg_risk']:>7} {r['avgR']:>5}")
show(sorted(res, key=lambda r: -r["total"])[:15], "TOP 15 BY TOTAL INDEX PTS")
show(sorted([r for r in res if r["n"] >= 60], key=lambda r: -(r["total"] / max(r["maxdd"], 1)))[:10], "TOP 10 BY RETURN / MAX-DRAWDOWN (n>=60)")
best_per_sl = [max([r for r in res if r["sl"] == s], key=lambda r: r["total"]) for s in SLS]
show(best_per_sl, "BEST CONFIG PER SL METHOD")

b = sorted([r for r in res if r["n"] >= 60], key=lambda r: -(r["total"] / max(r["maxdd"], 1)))[0]
tr = run(b["entry"], b["sl"], b["mgmt"], None if b["be"] == "-" else b["be"], b["room"])
print(f"\nDEEP DIVE: {b['entry']} / {b['sl']} / {b['mgmt']} / BE@{b['be']} / room {b['room']}")
for key in ("side", "reason"):
    g = defaultdict(list)
    for t in tr: g[t[key]].append(t)
    for kk, v in sorted(g.items()):
        s_ = stats(v); print(f"  {key}={kk:12} n={s_['n']:>3} win={s_['win']:>5}% total={s_['total']:>6} avg={s_['avg']:>6}")
g = defaultdict(list)
for t in tr: g[t["day"][:7]].append(t["pnl"])
print("  monthly: " + "  ".join(f"{m}:{round(sum(v))}" for m, v in sorted(g.items())))
json.dump(res, open("_pivot_research.json", "w"), indent=1, default=str)
