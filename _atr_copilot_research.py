"""ATR Copilot band research — 1 year SENSEX 5m, index-point simulation.

Signal (same as strategies/atr_copilot_strategy.py):
  Upper = EMA(ema_p) + mult × ATR(atr_p);  Lower = EMA - mult × ATR
  CE: prev close <= Upper[-2] and close > Upper[-1] + buffer × ATR[-1]   (PE mirror)
Entry at signal-candle close. One position at a time, no entries after 14:30, force exit 15:15.
Cost 10 idx pts / trade. Bars walked adverse-extreme first (conservative).

Exit models (risk unit R = 1.0 × ATR14 at entry):
  BOT_LIKE  : SL 1R, target 1.5R, BE at +0.5R, then trail best - 0.3R   (mirrors live generic TSL)
  CHANDELIER: SL 1R, BE at +1R, then trail best - 1.5 × ATR14, no target
  EMA_EXIT  : SL 1R, exit on a 5m close back through EMA(ema_p)
"""
import itertools, json, sys
from datetime import date, timedelta
from collections import defaultdict
from broker.kite_client import get_kite

kite = get_kite()
END = date.today(); START = END - timedelta(days=365)
COST = 10.0
NO_NEW = (14, 30); FORCE = (15, 15)
EMA_P = 21

bars = []
d = START - timedelta(days=7)
while d <= END:
    e = min(d + timedelta(days=90), END)
    for r in kite.historical_data(265, f"{d} 09:15:00", f"{e} 15:30:00", "5minute"):
        t = r["date"]
        if (9, 15) <= (t.hour, t.minute) <= (15, 25):
            bars.append(dict(t=t, o=r["open"], h=r["high"], l=r["low"], c=r["close"]))
    d = e + timedelta(days=1)
bars.sort(key=lambda b: b["t"])
N = len(bars)
hm = lambda t: (t.hour, t.minute)


def ema(p):
    out = [None] * N; k = 2 / (p + 1)
    out[p - 1] = sum(b["c"] for b in bars[:p]) / p
    for i in range(p, N): out[i] = bars[i]["c"] * k + out[i - 1] * (1 - k)
    return out


def atr(p):
    out = [None] * N; tr = [None]
    for i in range(1, N):
        b, q = bars[i], bars[i - 1]
        tr.append(max(b["h"] - b["l"], abs(b["h"] - q["c"]), abs(b["l"] - q["c"])))
    out[p] = sum(tr[1:p + 1]) / p
    for i in range(p + 1, N): out[i] = (out[i - 1] * (p - 1) + tr[i]) / p
    return out


E = ema(EMA_P); A14 = atr(14); ATRS = {p: atr(p) for p in (3, 5, 7, 10, 14)}
first_i = next(i for i, b in enumerate(bars) if b["t"].date() >= START)


def run(atr_p, mult, buf, exit_mode):
    A = ATRS[atr_p]; trades = []; i = max(first_i, EMA_P + atr_p + 2)
    while i < N:
        b = bars[i]
        if hm(b["t"]) >= NO_NEW or A[i] is None or A[i - 1] is None or A14[i] is None:
            i += 1; continue
        up, lo = E[i] + mult * A[i], E[i] - mult * A[i]
        up_p, lo_p = E[i - 1] + mult * A[i - 1], E[i - 1] - mult * A[i - 1]
        side = None
        if bars[i - 1]["c"] <= up_p and b["c"] > up + buf * A[i]: side = 1
        elif bars[i - 1]["c"] >= lo_p and b["c"] < lo - buf * A[i]: side = -1
        if side is None:
            i += 1; continue
        entry, R = b["c"], A14[i]; stop = entry - side * R; best = entry; be = False
        exit_px = reason = None; j = i + 1
        while j < N and bars[j]["t"].date() == b["t"].date():
            x = bars[j]
            if hm(x["t"]) >= FORCE: exit_px, reason = x["o"], "FORCE"; break
            adv = x["l"] if side == 1 else x["h"]; fav = x["h"] if side == 1 else x["l"]
            if (adv - stop) * side <= 0:
                exit_px, reason = stop, ("TSL" if be else "SL"); break
            if exit_mode == "BOT_LIKE" and (fav - entry) * side >= 1.5 * R:
                exit_px, reason = entry + side * 1.5 * R, "TP"; break
            if (fav - best) * side > 0: best = fav
            gain = (best - entry) * side
            if exit_mode == "BOT_LIKE" and gain >= 0.5 * R:
                be = True; ns = best - side * 0.3 * R
                ns = ns if (ns - entry) * side > 0 else entry
                if (ns - stop) * side > 0: stop = ns
            elif exit_mode == "CHANDELIER" and gain >= 1.0 * R:
                be = True; ns = max((best - side * 1.5 * A14[j] - entry) * side, 0) * side + entry
                if (ns - stop) * side > 0: stop = ns
            elif exit_mode == "EMA_EXIT" and (x["c"] - E[j]) * side < 0:
                exit_px, reason = x["c"], "EMA"; break
            j += 1
        if exit_px is None: exit_px, reason, j = bars[j - 1]["c"], "EOD", j - 1
        pnl = (exit_px - entry) * side - COST
        trades.append(dict(d=str(b["t"].date()), t=b["t"].strftime("%H:%M"), side="CE" if side == 1 else "PE",
                           pnl=round(pnl, 1), R=round(pnl / R, 2), reason=reason))
        i = j + 1
    return trades


def stats(tr):
    if not tr: return dict(n=0, net=0, wr=0, pf=0, avg=0, dd=0, ce=0, pe=0)
    w = [t["pnl"] for t in tr if t["pnl"] > 0]; l = [t["pnl"] for t in tr if t["pnl"] <= 0]
    eq = pk = dd = 0
    for t in tr: eq += t["pnl"]; pk = max(pk, eq); dd = max(dd, pk - eq)
    return dict(n=len(tr), net=round(sum(t["pnl"] for t in tr)), wr=round(100 * len(w) / len(tr)),
                pf=round(sum(w) / -sum(l), 2) if l and sum(l) else 99, avg=round(sum(t["pnl"] for t in tr) / len(tr), 1),
                dd=round(dd), ce=round(sum(t["pnl"] for t in tr if t["side"] == "CE")),
                pe=round(sum(t["pnl"] for t in tr if t["side"] == "PE")))


rows = []
for ap, m, bf, ex in itertools.product((3, 5, 7, 10, 14), (1.5, 2.0, 2.5, 3.0), (0.0, 0.25), ("BOT_LIKE", "CHANDELIER", "EMA_EXIT")):
    tr = run(ap, m, bf, ex); s = stats(tr); rows.append(dict(atr=ap, mult=m, buf=bf, exit=ex, **s))

days = len({b["t"].date() for b in bars[first_i:]})
print(f"Data {bars[first_i]['t'].date()} -> {bars[-1]['t'].date()} | {days} days | EMA{EMA_P} | cost {COST} pts/trade\n")
hdr = f"{'ATR':>3} {'mult':>4} {'buf':>4} {'exit':10} {'n':>4} {'net':>7} {'WR%':>4} {'PF':>5} {'avg':>6} {'maxDD':>6} {'CE':>6} {'PE':>6}"
fmt = lambda r: (f"{r['atr']:>3} {r['mult']:>4} {r['buf']:>4} {r['exit']:10} {r['n']:>4} {r['net']:>7} {r['wr']:>4} "
                 f"{r['pf']:>5} {r['avg']:>6} {r['dd']:>6} {r['ce']:>6} {r['pe']:>6}")
cur = [r for r in rows if r["atr"] == 3 and r["mult"] == 3.0 and r["buf"] == 0.0]
print("CURRENT LIVE CONFIG (ATR 3, mult 3.0, buffer 0):"); print(hdr); [print(fmt(r)) for r in cur]
ok = [r for r in rows if r["n"] >= 30]
print("\nTOP 15 by net pts (n >= 30):"); print(hdr)
[print(fmt(r)) for r in sorted(ok, key=lambda r: -r["net"])[:15]]
print("\nTOP 10 by profit factor (n >= 30):"); print(hdr)
[print(fmt(r)) for r in sorted(ok, key=lambda r: (-r["pf"], -r["net"]))[:10]]
print("\nBEST per ATR period (by net):"); print(hdr)
for ap in (3, 5, 7, 10, 14):
    print(fmt(max((r for r in ok if r["atr"] == ap), key=lambda r: r["net"])))
json.dump(rows, open("_atr_copilot_research.json", "w"), indent=1)
print("\nSaved _atr_copilot_research.json")
