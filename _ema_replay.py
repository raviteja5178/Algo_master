"""
Replay EMA CE/PE strategy on today's 5m candles.
Shows every candle, EMA values, which conditions pass/fail,
and for signals: entry price, SL, target, TSL.
"""
import json, math

# ── Load state ────────────────────────────────────────────────────────────────
s      = json.load(open(".bot_state.json"))
raw    = s.get("candles_today") or s.get("candles_5m") or []
pl     = s.get("pivot_levels")
pdh    = s.get("prev_day_high")
pdl    = s.get("prev_day_low")

print(f"Candles loaded : {len(raw)}")
print(f"Range          : {raw[0]['t']} → {raw[-1]['t']}")
print(f"Pivot levels   : {pl}")
print()

# ── EMA helper ────────────────────────────────────────────────────────────────
def ema_series(closes, period):
    k = 2 / (period + 1)
    vals = [None] * len(closes)
    for i, c in enumerate(closes):
        if i == 0:
            vals[i] = c
        else:
            prev = vals[i-1]
            vals[i] = c * k + prev * (1 - k) if prev is not None else c
    return vals

# ── ATR helper ────────────────────────────────────────────────────────────────
def atr(candles, period=14):
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]['h'], candles[i]['l'], candles[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return None
    val = sum(trs[:period]) / period
    for tr in trs[period:]:
        val = (val * (period - 1) + tr) / period
    return val

def round_tick(v):
    return round(round(v / 0.05) * 0.05, 2)

# ── Compute EMA series for 5m ─────────────────────────────────────────────────
closes5 = [c['c'] for c in raw]
ema9_5  = ema_series(closes5, 9)
ema21_5 = ema_series(closes5, 21)

# ── Simulate 15m candles by grouping 5m (every 3 candles) ────────────────────
# Use actual ema21_15m from state if available
ema21_15_series = s.get("ema21_15m") or []

# Build 15m candle list from raw 5m (group by 15m window)
def build_15m(candles5):
    buckets = {}
    for c in candles5:
        from datetime import datetime
        dt = datetime.fromisoformat(c['t'])
        # floor to 15m boundary
        m15 = (dt.minute // 15) * 15
        key = dt.replace(minute=m15, second=0, microsecond=0).isoformat()
        if key not in buckets:
            buckets[key] = {'t': key, 'o': c['o'], 'h': c['h'], 'l': c['l'], 'c': c['c']}
        else:
            buckets[key]['h'] = max(buckets[key]['h'], c['h'])
            buckets[key]['l'] = min(buckets[key]['l'], c['l'])
            buckets[key]['c'] = c['c']
    return sorted(buckets.values(), key=lambda x: x['t'])

candles15 = build_15m(raw)
closes15  = [c['c'] for c in candles15]
ema21_15  = ema_series(closes15, 21)

def get_ema21_15m_at(ts5):
    """Get the most recent completed 15m EMA21 value at the time of ts5."""
    from datetime import datetime
    dt = datetime.fromisoformat(ts5)
    m15 = (dt.minute // 15) * 15
    # The completed 15m candle is the one BEFORE the current 15m block
    boundary = dt.replace(minute=m15, second=0, microsecond=0).isoformat()
    completed = [i for i, c in enumerate(candles15) if c['t'] < boundary]
    if not completed:
        return None
    idx = completed[-1]
    return ema21_15[idx]

# ── Pivot zone check ──────────────────────────────────────────────────────────
PIVOT_ZONE_BUF = 25.0
def near_pivot(close):
    if not pl:
        return None
    for name, val in [('R2', pl['r2']), ('R1', pl['r1']), ('P', pl['pivot']),
                      ('S1', pl['s1']), ('S2', pl['s2'])]:
        if abs(close - val) <= PIVOT_ZONE_BUF:
            return name
    return None

# ── Risk params (today's ATR) ──────────────────────────────────────────────────
today_atr = atr(raw, 14)
ATM_DELTA = 0.4
SL_MULT   = 3.0
TARGET_RR = 1.5
TRAIL_RR  = 0.3
BE_RR     = 0.5
MAX_SL_PCT = 0.50

def compute_risk(entry_px, direction):
    """Compute SL/target/trail from ATR. Returns (sl_pts, tsl_pts, be_pts, tgt_pts)."""
    if today_atr:
        sl_pts = round_tick(today_atr * SL_MULT * ATM_DELTA)
        ceil   = round_tick(entry_px * MAX_SL_PCT)
        sl_pts = min(sl_pts, ceil)
        sl_pts = max(sl_pts, 20.0)
    else:
        sl_pts = 30.0
    tgt_pts  = round_tick(sl_pts * TARGET_RR)
    trail_pts= round_tick(sl_pts * TRAIL_RR)
    be_pts   = round_tick(sl_pts * BE_RR)
    return sl_pts, trail_pts, be_pts, tgt_pts

# ── Replay ────────────────────────────────────────────────────────────────────
print(f"{'Time':8}  {'Close':>10}  {'EMA9':>10}  {'EMA21':>10}  {'C>E21':5}  {'E9>E21':6}  {'C>PHi':6}  {'15m':5}  {'PivotZ':7}  {'Signal'}")
print("-" * 110)

signals_found = []
MIN_CANDLES = 21

for i in range(MIN_CANDLES, len(raw)):
    c0 = raw[i]
    c1 = raw[i-1]
    ts = c0['t'][11:16]  # HH:MM

    close  = c0['c']
    e9     = ema9_5[i]
    e21    = ema21_5[i]
    if e9 is None or e21 is None:
        continue

    # 15m EMA21
    e21_15 = get_ema21_15m_at(c0['t'])
    close15_val = None
    # get last completed 15m close before current candle
    from datetime import datetime
    dt = datetime.fromisoformat(c0['t'])
    m15 = (dt.minute // 15) * 15
    boundary = dt.replace(minute=m15, second=0, microsecond=0).isoformat()
    completed15 = [c for c in candles15 if c['t'] < boundary]
    if completed15:
        close15_val = completed15[-1]['c']

    # 4 CE conditions
    ce1 = close > e21
    ce2 = e9    > e21
    ce3 = close > c1['h']
    ce4 = (close15_val > e21_15) if (close15_val is not None and e21_15 is not None) else None

    # 4 PE conditions
    pe1 = close < e21
    pe2 = e9    < e21
    pe3 = close < c1['l']
    pe4 = (close15_val < e21_15) if (close15_val is not None and e21_15 is not None) else None

    ce_ok = ce1 and ce2 and ce3 and (ce4 is True)
    pe_ok = pe1 and pe2 and pe3 and (pe4 is True)

    pz = near_pivot(close)

    def cond(v):
        if v is None: return '?'
        return 'Y' if v else 'n'

    sig_str = ''
    if ce_ok:
        sig_str = 'CE'
        if pz:
            sig_str = f'CE(BLOCKED-{pz})'
    elif pe_ok:
        sig_str = 'PE'
        if pz:
            sig_str = f'PE(BLOCKED-{pz})'

    print(f"{ts:8}  {close:10.2f}  {e9:10.2f}  {e21:10.2f}  {cond(ce1):5}  {cond(ce2):6}  {cond(ce3):6}  {cond(ce4):5}  {pz or '':7}  {sig_str}")

    if sig_str and 'BLOCKED' not in sig_str:
        sl_pts, trail_pts, be_pts, tgt_pts = compute_risk(close, sig_str)
        signals_found.append({
            'time': ts, 'dir': sig_str, 'entry': close,
            'sl_pts': sl_pts, 'trail_pts': trail_pts,
            'be_pts': be_pts, 'tgt_pts': tgt_pts,
            'atr': today_atr,
        })

# ── Signal summary ─────────────────────────────────────────────────────────────
print()
print("=" * 90)
print(f"  TODAY's EMA Signals  |  ATR(14) = {today_atr:.1f} pts  |  Pivot: {pl}")
print("=" * 90)
if not signals_found:
    print("  No valid EMA CE/PE signals today.")
else:
    for sig in signals_found:
        d   = sig['dir']
        e   = sig['entry']
        sl  = sig['sl_pts']
        tgt = sig['tgt_pts']
        tsl = sig['trail_pts']
        be  = sig['be_pts']
        if d == 'CE':
            stop_px   = round_tick(e - sl)
            target_px = round_tick(e + tgt)
        else:
            stop_px   = round_tick(e + sl)
            target_px = round_tick(e - tgt)
        print(f"\n  {sig['time']}  {d} @ {e:.2f}")
        print(f"    SL      : {sl:.1f} pts  → Stop @ {stop_px:.2f}")
        print(f"    Target  : {tgt:.1f} pts  → Target @ {target_px:.2f}  (RR {TARGET_RR}x)")
        print(f"    BE      : {be:.1f} pts  → trail activates after +{be:.1f} pts")
        print(f"    TSL     : {tsl:.1f} pts  → trailing distance once active")
print()
