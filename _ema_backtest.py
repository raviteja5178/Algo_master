"""
EMA Strategy Full Backtest — 2026-10-08
Uses Zerodha historical API for complete 09:15-15:30 candles.
Applies EVERY filter currently in the live code:
  - 4-condition EMA (5m + 15m)
  - SmartEntry: body ratio, EMA gap, slope, cooldown
  - Pivot zone filter (PIVOT_ZONE_BUFFER=25)
  - No-new-entry cutoff (NO_NEW_ENTRY_AFTER)
  - One-trade-at-a-time (dedup)
Then simulates each trade tick-by-tick using 1m candles for TSL/SL/target tracking.
"""
import json, sys
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# ── Load settings from env ────────────────────────────────────────────────────
import os
from dotenv import load_dotenv
load_dotenv()

PIVOT_ZONE_BUF    = float(os.getenv("PIVOT_ZONE_BUFFER", 25))
NO_NEW_AFTER      = os.getenv("NO_NEW_ENTRY_AFTER", "14:30")
ATM_DELTA         = 0.4
SL_MULT           = float(os.getenv("SPOT_ATR_SL_MULT", 3.0))
TARGET_RR         = float(os.getenv("SPOT_ATR_TARGET_RR", 1.5))
TRAIL_RR          = float(os.getenv("SPOT_ATR_TRAIL_RR", 0.3))
BE_PCT            = 0.5
MAX_SL_PCT        = float(os.getenv("MAX_SL_PCT", 0.50))
TSL_ATR_MULT      = float(os.getenv("TSL_ATR_TRAIL_MULT", 1.0))
TSL_ATR_PERIOD    = int(os.getenv("TSL_ATR_PERIOD", 14))
SMART_BODY_RATIO  = float(os.getenv("SMART_ENTRY_MIN_BODY_ATR_RATIO", 0.25))
SMART_EMA_GAP     = float(os.getenv("SMART_ENTRY_MIN_EMA_GAP_PTS", 10.0))
SMART_COOLDOWN    = int(os.getenv("SMART_ENTRY_COOLDOWN_CANDLES", 3))
SMART_SLOPE       = os.getenv("SMART_ENTRY_REQUIRE_EMA_SLOPE", "true").lower() == "true"
QTY               = int(os.getenv("QUANTITY", 20))

no_new_h, no_new_m = map(int, NO_NEW_AFTER.split(":"))

def round_tick(v):
    return round(round(v / 0.05) * 0.05, 2)

# ── Fetch candles from Zerodha ─────────────────────────────────────────────────
from broker.kite_client import get_kite
kite = get_kite()

today_str = "2026-10-08"
print(f"Fetching 5m candles for {today_str}...")
raw5 = kite.historical_data(265, f"{today_str} 09:00:00", f"{today_str} 15:35:00", "5minute")
print(f"Fetching 15m candles for {today_str}...")
raw15 = kite.historical_data(265, f"{today_str} 09:00:00", f"{today_str} 15:35:00", "15minute")
print(f"Fetching 1m candles for trade simulation...")
raw1 = kite.historical_data(265, f"{today_str} 09:00:00", f"{today_str} 15:35:00", "minute")

def to_candles(raw):
    out = []
    for r in raw:
        dt = r["date"]
        if hasattr(dt, "astimezone"):
            dt = dt.astimezone(IST)
        h, m = dt.hour, dt.minute
        if (h, m) < (9, 15) or (h, m) > (15, 30):
            continue
        out.append({"t": dt, "o": float(r["open"]), "h": float(r["high"]),
                    "l": float(r["low"]), "c": float(r["close"]),
                    "v": int(r.get("volume") or 0)})
    return out

c5  = to_candles(raw5)
c15 = to_candles(raw15)
c1  = to_candles(raw1)
print(f"5m candles: {len(c5)}  15m candles: {len(c15)}  1m candles: {len(c1)}")

# ── EMA helpers ──────────────────────────────────────────────────────────────
def ema_series(candles, period):
    closes = [c["c"] for c in candles]
    k = 2 / (period + 1)
    vals = []
    for i, c in enumerate(closes):
        if i == 0:
            vals.append(c)
        else:
            vals.append(c * k + vals[-1] * (1 - k))
    return vals

def atr_series(candles, period=14):
    trs = [None]
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["h"], candles[i]["l"], candles[i-1]["c"]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    vals = [None] * len(candles)
    if len(candles) <= period:
        return vals
    vals[period] = sum(trs[1:period+1]) / period
    for i in range(period+1, len(candles)):
        vals[i] = (vals[i-1] * (period-1) + trs[i]) / period
    return vals

ema9_5  = ema_series(c5, 9)
ema21_5 = ema_series(c5, 21)
atr14_5 = atr_series(c5, 14)
ema21_15= ema_series(c15, 21)

# ── Pivot levels ──────────────────────────────────────────────────────────────
# Oct 7 H/L/C needed. Fetch from state.
s = json.load(open(".bot_state.json"))
pl = s.get("pivot_levels")
if not pl:
    # compute from prev day
    raw_prev = kite.historical_data(265, "2026-10-04", "2026-10-08", "day")
    prev = [r for r in raw_prev if r["date"].date() < date(2026,10,8)][-1]
    H,L,C = float(prev["high"]),float(prev["low"]),float(prev["close"])
    P=(H+L+C)/3
    pl={"pivot":round(P,2),"r1":round(2*P-L,2),"r2":round(P+(H-L),2),
        "s1":round(2*P-H,2),"s2":round(P-(H-L),2)}
print(f"Pivot: P={pl['pivot']}  R1={pl['r1']}  R2={pl['r2']}  S1={pl['s1']}  S2={pl['s2']}")

ALL_PIVOT_LEVELS = [pl["pivot"], pl["r1"], pl["r2"], pl["s1"], pl["s2"]]

def near_pivot(close):
    for name, val in zip(["Pivot","R1","R2","S1","S2"], ALL_PIVOT_LEVELS):
        if abs(close - val) <= PIVOT_ZONE_BUF:
            return name
    return None

# ── Smart Entry helpers ───────────────────────────────────────────────────────
def ema_slope_ok(ema_arr, i, direction):
    if not SMART_SLOPE or i < 1:
        return True
    if direction == "PE":
        return ema_arr[i] < ema_arr[i-1]   # EMA9 falling
    return ema_arr[i] > ema_arr[i-1]       # EMA9 rising

def body_ok(candle, atr_val):
    if atr_val is None or SMART_BODY_RATIO <= 0:
        return True
    body = abs(candle["c"] - candle["o"])
    return body >= atr_val * SMART_BODY_RATIO

def ema_gap_ok(e9, e21):
    if SMART_EMA_GAP <= 0:
        return True
    return abs(e9 - e21) >= SMART_EMA_GAP

# ── 15m EMA21 lookup at a 5m candle timestamp ─────────────────────────────────
def get_e21_15_at(i5):
    """Return the last completed 15m EMA21 before candle i5."""
    t5 = c5[i5]["t"]
    completed = [j for j, c in enumerate(c15) if c["t"] < t5]
    if not completed:
        return None
    return ema21_15[completed[-1]]

def get_close15_at(i5):
    t5 = c5[i5]["t"]
    completed = [c for c in c15 if c["t"] < t5]
    return completed[-1]["c"] if completed else None

# ── Risk param computation ────────────────────────────────────────────────────
def compute_risk(entry_px, atr_val):
    if atr_val is None:
        sl = 30.0
    else:
        sl = round_tick(atr_val * SL_MULT * ATM_DELTA)
    sl = max(sl, 20.0)
    sl = min(sl, round_tick(entry_px * MAX_SL_PCT))
    tgt   = round_tick(sl * TARGET_RR)
    trail = round_tick(sl * TRAIL_RR)
    be    = round_tick(sl * BE_PCT)
    # Dynamic TSL trail using ATR * mult * delta
    dyn_trail = round_tick(atr_val * TSL_ATR_MULT * ATM_DELTA) if atr_val else trail
    return sl, tgt, trail, be, dyn_trail

# ── 1m candle range for a trade window ───────────────────────────────────────
def get_1m_range(entry_time, exit_by=None):
    return [c for c in c1 if c["t"] >= entry_time and (exit_by is None or c["t"] <= exit_by)]

# ── Simulate trade on 1m candles ──────────────────────────────────────────────
def simulate_trade(direction, entry_px, entry_time, sl, tgt, dyn_trail, be):
    """
    Walk 1m candles from entry_time.
    Returns: (exit_px, exit_time, exit_reason, highest_favourable, peak_pnl_pts)
    """
    stop    = entry_px + sl if direction == "PE" else entry_px - sl
    target  = entry_px - tgt if direction == "PE" else entry_px + tgt
    highest = entry_px   # highest favourable (option proxy = entry sensex)
    be_triggered = False
    tsl_active   = False
    tsl_stop     = stop

    eod = entry_time.replace(hour=15, minute=30, second=0, microsecond=0)
    candles_1m = get_1m_range(entry_time, eod)

    for c in candles_1m:
        lo, hi = c["l"], c["h"]

        if direction == "PE":
            # favourable direction = price falling = option value rising
            fav = entry_px - lo      # how far sensex fell = proxy option gain
            adv_px = lo              # most adverse = highest sensex tick
            fav_px = lo              # most favourable = lowest sensex tick

            # BE check: option gained be pts
            if not be_triggered and (entry_px - lo) >= be:
                be_triggered = True
                tsl_active   = True
                highest = lo   # track lowest sensex from here
            if be_triggered and lo < highest:
                highest = lo
            if tsl_active:
                # TSL stop = highest sensex + dyn_trail (PE: stop is ABOVE current low)
                tsl_stop = round_tick(highest + dyn_trail)
                stop = min(stop, tsl_stop)  # TSL only tightens

            # Check SL hit (sensex rallied above stop)
            if hi >= stop:
                exit_px = stop
                exit_reason = "TSL_HIT" if tsl_active else "SL_HIT"
                peak = entry_px - highest
                return exit_px, c["t"], exit_reason, round(peak, 2)

            # Check target hit
            if lo <= target:
                exit_px = target
                exit_reason = "TARGET_HIT"
                peak = entry_px - lo
                return exit_px, c["t"], exit_reason, round(peak, 2)

        else:  # CE
            if not be_triggered and (hi - entry_px) >= be:
                be_triggered = True
                tsl_active   = True
                highest = hi
            if be_triggered and hi > highest:
                highest = hi
            if tsl_active:
                tsl_stop = round_tick(highest - dyn_trail)
                stop = max(stop, tsl_stop)

            if lo <= stop:
                exit_px = stop
                exit_reason = "TSL_HIT" if tsl_active else "SL_HIT"
                peak = highest - entry_px
                return exit_px, c["t"], exit_reason, round(peak, 2)

            if hi >= target:
                exit_px = target
                exit_reason = "TARGET_HIT"
                peak = hi - entry_px
                return exit_px, c["t"], exit_reason, round(peak, 2)

    # EOD exit
    eod_c = [c for c in c1 if c["t"].hour == 15 and c["t"].minute == 30]
    exit_px = eod_c[-1]["c"] if eod_c else entry_px
    peak = (entry_px - min(c["l"] for c in candles_1m)) if direction == "PE" else (max(c["h"] for c in candles_1m) - entry_px)
    return exit_px, eod, "EOD_EXIT", round(peak, 2)

# ── MAIN BACKTEST LOOP ────────────────────────────────────────────────────────
SEP = "=" * 100
print()
print(SEP)
print(f"  EMA BACKTEST  2026-10-08  |  Full day 09:15-15:30  |  All filters active")
print(f"  SL_MULT={SL_MULT}x  TARGET_RR={TARGET_RR}x  MAX_SL_PCT={MAX_SL_PCT*100:.0f}%  TSL_ATR_MULT={TSL_ATR_MULT}x  PIVOT_BUF={PIVOT_ZONE_BUF:.0f}pts")
print(SEP)

print(f"\n{'#':>3}  {'Time':6}  {'Close':>8}  {'EMA9':>8}  {'EMA21':>8}  "
      f"{'C<E21':5}  {'E9<E21':6}  {'C<PL':5}  {'15m':5}  "
      f"{'Body':5}  {'Gap':5}  {'Slope':6}  {'PivotZ':8}  {'Result'}")
print("-" * 115)

trades     = []
cooldown   = 0
in_trade   = False
sig_count  = 0
MIN_I      = 21  # need 21 candles for EMA21 to be meaningful

for i in range(MIN_I, len(c5)):
    c0 = c5[i]
    c1_ = c5[i-1]
    ts   = c0["t"]
    hm   = ts.hour * 60 + ts.minute
    time_str = f"{ts.hour:02d}:{ts.minute:02d}"

    close = c0["c"]
    e9    = ema9_5[i]
    e21   = ema21_5[i]
    atr_v = atr14_5[i]

    # No new entry after cutoff
    if ts.hour > no_new_h or (ts.hour == no_new_h and ts.minute >= no_new_m):
        if in_trade:
            continue
        print(f"{'':>3}  {time_str}  {'—':>8}  {'':>8}  {'':>8}  "
              f"{'':5}  {'':6}  {'':5}  {'':5}  "
              f"{'':5}  {'':5}  {'':6}  {'':8}  [NO_NEW_ENTRY after {NO_NEW_AFTER}]")
        break

    # Cooldown
    if cooldown > 0:
        cooldown -= 1

    # 15m values
    e21_15  = get_e21_15_at(i)
    cl15    = get_close15_at(i)

    # 4 EMA conditions — PE
    pe1 = close < e21
    pe2 = e9    < e21
    pe3 = close < c1_["l"]
    pe4 = (cl15 < e21_15) if (cl15 is not None and e21_15 is not None) else None

    # 4 EMA conditions — CE
    ce1 = close > e21
    ce2 = e9    > e21
    ce3 = close > c1_["h"]
    ce4 = (cl15 > e21_15) if (cl15 is not None and e21_15 is not None) else None

    raw_pe = pe1 and pe2 and pe3 and (pe4 is True)
    raw_ce = ce1 and ce2 and ce3 and (ce4 is True)

    def yn(v):
        if v is None: return "?"
        return "Y" if v else "n"

    direction = None
    if raw_pe:
        direction = "PE"
    elif raw_ce:
        direction = "CE"

    # Smart Entry filters
    se_body   = body_ok(c0, atr_v) if direction else True
    se_gap    = ema_gap_ok(e9, e21) if direction else True
    se_slope  = ema_slope_ok(ema9_5, i, direction) if direction else True

    # Pivot zone
    pz = near_pivot(close)

    # Block reasons
    block_reason = None
    if direction and not se_body:
        block_reason = "SmartEntry:Body"
    elif direction and not se_gap:
        block_reason = "SmartEntry:EMAGap"
    elif direction and not se_slope:
        block_reason = "SmartEntry:Slope"
    elif direction and pz:
        block_reason = f"PivotZone:{pz}"
    elif direction and cooldown > 0:
        block_reason = f"Cooldown:{cooldown}"
    elif direction and in_trade:
        block_reason = "InTrade"

    signal_fires = direction is not None and block_reason is None

    result_str = ""
    if direction:
        if block_reason:
            result_str = f"[{direction} BLOCKED: {block_reason}]"
        else:
            result_str = f">>> {direction} SIGNAL FIRES"
            sig_count += 1

    # Only print candles with a signal or near-signal
    if direction or (i % 6 == 0):  # print every 6th candle as context
        pe_str = f"{yn(pe1)}{yn(pe2)}{yn(pe3)}{yn(pe4)}" if direction=="PE" or raw_pe or (pe1 and pe2) else "    "
        ce_str = f"{yn(ce1)}{yn(ce2)}{yn(ce3)}{yn(ce4)}" if direction=="CE" or raw_ce or (ce1 and ce2) else "    "
        cond_str = pe_str if raw_pe else ce_str

        print(f"{sig_count if signal_fires else '':>3}  {time_str}  {close:>8.2f}  {e9:>8.2f}  {e21:>8.2f}  "
              f"{yn(pe1 if raw_pe or direction=='PE' else ce1):5}  "
              f"{yn(pe2 if raw_pe or direction=='PE' else ce2):6}  "
              f"{yn(pe3 if raw_pe or direction=='PE' else ce3):5}  "
              f"{yn(pe4 if raw_pe else ce4):5}  "
              f"{'Y' if se_body else 'n':5}  {'Y' if se_gap else 'n':5}  "
              f"{'Y' if se_slope else 'n':6}  {pz or '':8}  {result_str}")

    if signal_fires:
        sl, tgt, trail, be, dyn_trail = compute_risk(close, atr_v)
        in_trade = True
        cooldown = SMART_COOLDOWN

        # Simulate on 1m candles
        exit_px, exit_time, exit_reason, peak_pts = simulate_trade(
            direction, close, ts, sl, tgt, dyn_trail, be
        )

        if direction == "PE":
            pnl_pts = close - exit_px
            stop_px = round_tick(close + sl)
            tgt_px  = round_tick(close - tgt)
        else:
            pnl_pts = exit_px - close
            stop_px = round_tick(close - sl)
            tgt_px  = round_tick(close + tgt)

        pnl_rs  = round(pnl_pts * ATM_DELTA * QTY, 0)
        et_str  = f"{exit_time.hour:02d}:{exit_time.minute:02d}" if hasattr(exit_time,"hour") else str(exit_time)

        trades.append({
            "n": sig_count, "time": time_str, "dir": direction,
            "entry": close, "sl_pts": sl, "tgt_pts": tgt,
            "be_pts": be, "dyn_trail": dyn_trail,
            "stop_px": stop_px, "tgt_px": tgt_px,
            "exit_px": exit_px, "exit_time": et_str,
            "exit_reason": exit_reason, "peak_pts": peak_pts,
            "pnl_pts": round(pnl_pts, 2), "pnl_rs": pnl_rs,
            "atr": round(atr_v, 1) if atr_v else None,
        })

        print(f"     {'':6}  {'ENTRY':>8}  stop={stop_px:.2f}  target={tgt_px:.2f}  "
              f"SL={sl:.1f}  TGT={tgt:.1f}  BE={be:.1f}  TSL={dyn_trail:.1f}  ATR={atr_v:.1f}")
        print(f"     {'':6}  {'EXIT':>8}  @ {exit_px:.2f}  ({et_str})  reason={exit_reason}  "
              f"peak={peak_pts:.1f}pts  PnL={pnl_pts:+.1f}pts = Rs{pnl_rs:+.0f}")
        in_trade = False

# ── SUMMARY ───────────────────────────────────────────────────────────────────
print()
print(SEP)
print(f"  BACKTEST SUMMARY  |  {sig_count} signal(s) fired  |  {len(trades)} trade(s)")
print(SEP)
total_pnl = 0
for t in trades:
    flag = "TARGET" if t["exit_reason"]=="TARGET_HIT" else ("TSL" if "TSL" in t["exit_reason"] else "SL")
    print(f"\n  #{t['n']}  {t['time']}  {t['dir']} @ {t['entry']:.2f}")
    print(f"     SL={t['sl_pts']:.1f}pts  TGT={t['tgt_pts']:.1f}pts  BE={t['be_pts']:.1f}pts  TSL-trail={t['dyn_trail']:.1f}pts  ATR={t['atr']}")
    print(f"     Stop px={t['stop_px']:.2f}  Target px={t['tgt_px']:.2f}")
    print(f"     Exit: {t['exit_px']:.2f} @ {t['exit_time']}  [{t['exit_reason']}]  peak={t['peak_pts']:.1f}pts")
    print(f"     PnL: {t['pnl_pts']:+.2f} SENSEX pts  = Rs {t['pnl_rs']:+.0f}  (qty {QTY})")
    total_pnl += t["pnl_rs"]
print(f"\n  {'─'*50}")
print(f"  TOTAL P&L : Rs {total_pnl:+.0f}")
winners = [t for t in trades if t["pnl_rs"] > 0]
losers  = [t for t in trades if t["pnl_rs"] < 0]
print(f"  Win/Loss  : {len(winners)}W / {len(losers)}L")
if trades:
    print(f"  Best      : Rs {max(t['pnl_rs'] for t in trades):+.0f}")
    print(f"  Worst     : Rs {min(t['pnl_rs'] for t in trades):+.0f}")
print(SEP)
