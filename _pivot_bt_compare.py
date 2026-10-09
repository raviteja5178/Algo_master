"""
Old code signal scan + full trade simulation on real Kite data.
Shows exactly where CE/PE would have fired with old logic vs new logic.
"""
import json, sys
from datetime import date
from pathlib import Path

state = json.load(open(".bot_state.json"))
pivot_raw = state.get("pivot_levels")
P=pivot_raw["pivot"]; R1=pivot_raw["r1"]; R2=pivot_raw["r2"]
S1=pivot_raw["s1"]; S2=pivot_raw["s2"]

# Fetch real candles
try:
    from broker.kite_client import get_kite
    from utils.time_utils import IST
    kite = get_kite()
    today_str = date.today().strftime("%Y-%m-%d")
    records = kite.historical_data(265, f"{today_str} 09:00:00", f"{today_str} 15:30:00", "5minute")
    raw = []
    for r in records:
        ts = r["date"]
        if hasattr(ts, "tzinfo") and ts.tzinfo is None: ts = IST.localize(ts)
        if (ts.hour, ts.minute) < (9,15): continue
        raw.append({"t": ts.strftime("%H:%M"), "o":float(r["open"]),"h":float(r["high"]),"l":float(r["low"]),"c":float(r["close"])})
except Exception as e:
    print(f"Kite error: {e}"); sys.exit(1)

class C:
    def __init__(self, d): self.ts=d["t"]; self.o=d["o"]; self.h=d["h"]; self.l=d["l"]; self.c=d["c"]
candles=[C(d) for d in raw]

def atr14(cs,p=14):
    if len(cs)<2: return None
    trs=[]
    for i in range(1,len(cs)):
        b,pv=cs[i],cs[i-1]; trs.append(max(b.h-b.l,abs(b.h-pv.c),abs(b.l-pv.c)))
    if not trs: return None
    if len(trs)<p: return sum(trs)/len(trs)
    a=sum(trs[:p])/p
    for tr in trs[p:]: a=(a*13+tr)/14
    return a

NO_NEW=(14,30); FORCE=(15,15); SUSTAIN=2; SL_BUF=0.05; MIN_ROOM=1.0
BE_R=1.0; BE_BUF=5.0; T1_LOCK=0.5; TRAIL=1.0; EPS=0.25

# Use first candle to derive prev_close direction
prev_close = P*0.999 if candles[0].c > P else P*1.001

results = {"old": [], "new_3": []}

for label, min_today, use_wick, strict in [
    ("old",   0, False, False),
    ("new_3", 3, True,  True),
]:
    for k in range(SUSTAIN-1, len(candles)):
        today_so_far = candles[:k+1]
        n = len(today_so_far)
        if n < min_today: continue
        hm = tuple(map(int, candles[k].ts.split(":")))
        if hm >= NO_NEW: break
        window = today_so_far[-SUSTAIN:]
        before = today_so_far[-SUSTAIN-1] if n > SUSTAIN else None
        bc = before.c if before else prev_close
        entry = candles[k].c
        atr = atr14(today_so_far) or 0
        if not atr: continue

        for side in ("CE","PE"):
            if side == "CE":
                sus_new = all(c.c>P and c.l>P for c in window)
                sus_old = all(c.c>P for c in window)
                fresh_n = bc is not None and bc < P
                fresh_o = bc is not None and bc <= P
                t1,t2 = R1,R2
                stop = min(c.l for c in window) - SL_BUF*atr
                risk = entry - stop; room = t1 - entry
            else:
                sus_new = all(c.c<P and c.h<P for c in window)
                sus_old = all(c.c<P for c in window)
                fresh_n = bc is not None and bc > P
                fresh_o = bc is not None and bc >= P
                t1,t2 = S1,S2
                stop = max(c.h for c in window) + SL_BUF*atr
                risk = stop - entry; room = entry - t1

            if risk<=0 or room<=0 or room < MIN_ROOM*risk: continue
            sus = sus_new if use_wick else sus_old
            fresh = fresh_n if strict else fresh_o
            if not (sus and fresh): continue

            results[label].append(dict(k=k,ts=candles[k].ts,side=side,
                entry=round(entry,2),stop=round(stop,2),risk=round(risk,2),
                t1=t1,t2=t2,atr=round(atr,2),n=n,room_r=round(room/risk,2),
                bc=round(bc,2) if bc else None,
                w1=(round(window[-2].c,2),round(window[-2].l,2),round(window[-2].h,2)),
                w2=(round(window[-1].c,2),round(window[-1].l,2),round(window[-1].h,2)),
            ))
            break

def sim(sig, candles):
    side=sig["side"]; sign=1 if side=="CE" else -1
    en=sig["entry"]; stop=sig["stop"]; t1=sig["t1"]; t2=sig["t2"]; atr=sig["atr"]; risk=sig["risk"]
    best=en; stage="INITIAL"; events=[]
    for candle in candles[sig["k"]+1:]:
        hm=tuple(map(int,candle.ts.split(":")))
        fa=atr14(candles[:candles.index(candle)+1])
        if fa and fa>0: atr=fa
        if hm>=FORCE:
            return dict(exit_ts=candle.ts,exit_px=round(candle.o,2),reason="EOD",
                        pnl=round((candle.o-en)*sign,2),events=events,final_stop=round(stop,2))
        sl_px=candle.l if side=="CE" else candle.h
        hi_px=candle.h if side=="CE" else candle.l
        if (hi_px-en)*sign>(best-en)*sign: best=hi_px
        if (sl_px-en)*sign < (stop-en)*sign - EPS:
            r={"INITIAL":"SL_HIT","BE":"BE_STOP"}.get(stage,"TSL_HIT")
            return dict(exit_ts=candle.ts,exit_px=round(stop,2),reason=r,
                        pnl=round((stop-en)*sign,2),events=events,final_stop=round(stop,2))
        if (hi_px-en)*sign >= (t2-en)*sign:
            return dict(exit_ts=candle.ts,exit_px=round(t2,2),reason="T2_HIT",
                        pnl=round((t2-en)*sign,2),events=events,final_stop=round(stop,2))
        if stage!="T1" and (best-en)*sign>=(t1-en)*sign:
            lock=en+sign*T1_LOCK*abs(t1-en)
            if (lock-en)*sign>(stop-en)*sign:
                stop=round(lock,2); events.append((candle.ts,"T1_LOCK",round(stop,2)))
            stage="T1"
        elif stage=="INITIAL" and (best-en)*sign>=BE_R*risk:
            be=en+sign*BE_BUF
            if (be-en)*sign>(stop-en)*sign:
                stop=round(be,2); events.append((candle.ts,"BE",round(stop,2)))
            stage="BE"
        if stage=="T1" and TRAIL>0:
            trail=best-sign*TRAIL*atr
            if (trail-en)*sign>(stop-en)*sign:
                stop=round(trail,2); events.append((candle.ts,"TRAIL",round(stop,2)))
    c=candles[-1]
    return dict(exit_ts=c.ts,exit_px=round(c.c,2),reason="EOD_CLOSE",
                pnl=round((c.c-en)*sign,2),events=events,final_stop=round(stop,2))

print(f"P={P}  R1={R1}  R2={R2}  S1={S1}  S2={S2}")
print(f"Candles: {len(candles)}  {candles[0].ts} -> {candles[-1].ts}")
print()

for label, min_today in [("new_3",3),("old",0)]:
    sigs=results[label]
    tag="NEW CODE (min_today=3, wick_filter=ON)" if label=="new_3" else "OLD CODE (min_today=0, no wick filter)"
    print(f"{'='*78}")
    print(f"{tag}  |  {len(sigs)} signal(s)")
    print(f"{'='*78}")
    if not sigs:
        print("  No signals found.")
        print()
        continue
    for sig in sigs:
        r = sim(sig, candles)
        pnl_sign="+" if r["pnl"]>=0 else ""
        opt_pts=round(r["pnl"]*0.4,1)
        money=round(opt_pts*20,0)
        print()
        print(f"  [{sig['ts']}] {sig['side']}_PIVOT  n_today={sig['n']}")
        print(f"  Entry:    SENSEX {sig['entry']}  (candle close)")
        print(f"  SL:       SENSEX {sig['stop']}  (risk={sig['risk']} pts, ATR={sig['atr']})")
        print(f"  T1:       {sig['t1']}  T2: {sig['t2']}  Room/Risk={sig['room_r']}")
        print(f"  Window:   [{sig['w1'][0]} lo={sig['w1'][1]}]  [{sig['w2'][0]} lo={sig['w2'][2] if sig['side']=='PE' else sig['w2'][1]}]")
        print(f"  before_close={sig['bc']} ({'< P' if sig['bc']<P else '> P'} {'STRICT OK' if (sig['side']=='CE' and sig['bc']<P) or (sig['side']=='PE' and sig['bc']>P) else 'OLD ONLY'})")
        print(f"  Exit:     {r['exit_ts']}  SENSEX {r['exit_px']}  [{r['reason']}]")
        print(f"  PnL:      {pnl_sign}{r['pnl']} index pts  ~{'+' if opt_pts>=0 else ''}{opt_pts} option pts  ~Rs.{'+' if money>=0 else ''}{money:.0f}")
        if r["events"]:
            print(f"  Stages:   " + "  ->  ".join(f"{e[0]} {e[1]} stop={e[2]}" for e in r["events"]))
    print()
