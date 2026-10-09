"""Deep analysis of VWAP false breakout trades on Oct-08 vs Oct-09."""
import json, sys

with open('_vwap_analysis.json') as f:
    d = json.load(f)

# Real VWAP needs volume. Since index has no volume,
# use typical-price rolling average as proxy (same as bot does intraday)
def rolling_vwap(candles):
    """Simple cumulative typical-price average — matches bot VWAP reset at 09:15."""
    cv = 0.0
    result = []
    for i, c in enumerate(candles, 1):
        tp = (c['h'] + c['l'] + c['c']) / 3.0
        cv += tp
        result.append(round(cv / i, 2))
    return result

# ── Trade signal times ─────────────────────────────────────────────────────────
# Oct-08: PE_VWAP @ 12:20 (candle 12:15 close), PE_VWAP @ 13:20 (candle 13:15 close)
# Oct-09: PE_VWAP @ 12:00 (candle 11:55 close), CE_VWAP @ 13:00 (candle 12:55 close)
# Signal fires AFTER candle close, so candle[-1] is the signal candle

SIGNAL_TIMES = {
    '2026-10-08': [
        ('12:15', 'PE_VWAP', 71850.17),  # sensex_entry from DB
        ('13:15', 'PE_VWAP', 71606.82),
    ],
    '2026-10-09': [
        ('11:55', 'PE_VWAP', 72245.04),  # sensex_entry from DB
        ('12:55', 'CE_VWAP', 72448.90),
    ],
}

DB_SL = {
    '2026-10-08': [72008.92, 71718.94],
    '2026-10-09': [72406.16, 72333.28],
}
DB_T1 = {
    '2026-10-08': [71612.05, 71438.57],
    '2026-10-09': [72003.29, 72622.40],
}
DB_ATR = {
    '2026-10-08': [86.41, 78.05],
    '2026-10-09': [53.69, 44.02],
}
DB_PNL = {
    '2026-10-08': [+554, +503],
    '2026-10-09': [-1296, -973],
}

for day in ['2026-10-08', '2026-10-09']:
    candles = d[day]
    vwaps = rolling_vwap(candles)
    by_time = {c['t']: (c, v) for c, v in zip(candles, vwaps)}
    times = [c['t'] for c in candles]

    print(f'\n{"="*72}')
    print(f'  {day}  VWAP TRADE ANALYSIS')
    print(f'{"="*72}')

    # Full-day VWAP context window (11:30 onwards)
    print(f'\n  {"Time":>6}  {"Open":>7}  {"High":>7}  {"Low":>7}  {"Close":>7}  {"VWAP":>8}  {"C-VWAP":>8}')
    print(f'  {"-"*6}  {"-"*7}  {"-"*7}  {"-"*7}  {"-"*7}  {"-"*8}  {"-"*8}')
    for c, v in zip(candles, vwaps):
        if c['t'] < '11:30':
            continue
        diff = c['c'] - v
        tag = ''
        for (st, sig, _) in SIGNAL_TIMES[day]:
            if c['t'] == st:
                tag = f'  <<< SIGNAL CANDLE ({sig})'
        print(f'  {c["t"]:>6}  {c["o"]:>7.1f}  {c["h"]:>7.1f}  {c["l"]:>7.1f}  {c["c"]:>7.1f}  {v:>8.1f}  {diff:>+8.1f}{tag}')

    # Per-signal deep dive
    for idx, (sig_time, sig_type, sensex_entry) in enumerate(SIGNAL_TIMES[day]):
        sl    = DB_SL[day][idx]
        t1    = DB_T1[day][idx]
        atr   = DB_ATR[day][idx]
        pnl   = DB_PNL[day][idx]

        # Get candle index
        try:
            ci = times.index(sig_time)
        except ValueError:
            print(f'\n  Signal candle {sig_time} not found in data')
            continue

        c0 = candles[ci]     # signal candle
        c1 = candles[ci-1]   # previous candle
        vwap0 = vwaps[ci]
        vwap1 = vwaps[ci-1]
        vwap_slope = vwap0 - vwap1

        # Lookback (3 candles before signal)
        lookback = candles[max(0, ci-3):ci]
        lb_above_vwap = [c['c'] > vwaps[ci-3+i] for i,c in enumerate(lookback)]
        lb_below_vwap = [c['c'] < vwaps[ci-3+i] for i,c in enumerate(lookback)]

        print(f'\n  {"─"*70}')
        print(f'  SIGNAL #{idx+1}: {sig_type}  |  Candle {sig_time}  |  Sensex entry ≈ {sensex_entry:,.1f}')
        print(f'  {"─"*70}')
        print(f'  Signal candle:  O={c0["o"]:.1f}  H={c0["h"]:.1f}  L={c0["l"]:.1f}  C={c0["c"]:.1f}')
        print(f'  Prev candle:    O={c1["o"]:.1f}  H={c1["h"]:.1f}  L={c1["l"]:.1f}  C={c1["c"]:.1f}')
        print(f'  VWAP @ signal:  {vwap0:.1f}  (slope: {vwap_slope:+.1f} pts vs prev candle VWAP)')
        print(f'  C - VWAP:       {c0["c"] - vwap0:+.1f} pts  (VWAP_MIN_BOUNCE_PTS threshold = 30)')

        if sig_type.startswith('PE'):
            print(f'  Momentum test:  C={c0["c"]:.1f} < prevLow={c1["l"]:.1f}? → {"PASS" if c0["c"] < c1["l"] else "FAIL"}')
            print(f'  VWAP cross:     C={c0["c"]:.1f} < VWAP={vwap0:.1f}? → {"PASS" if c0["c"] < vwap0 else "FAIL"}')
            print(f'  Lookback retest (any close > VWAP): {lb_above_vwap} → {"PASS" if any(lb_above_vwap) else "FAIL"}')
        else:
            print(f'  Momentum test:  C={c0["c"]:.1f} > prevHigh={c1["h"]:.1f}? → {"PASS" if c0["c"] > c1["h"] else "FAIL"}')
            print(f'  VWAP cross:     C={c0["c"]:.1f} > VWAP={vwap0:.1f}? → {"PASS" if c0["c"] > vwap0 else "FAIL"}')
            print(f'  Lookback retest (any close < VWAP): {lb_below_vwap} → {"PASS" if any(lb_below_vwap) else "FAIL"}')

        print(f'\n  Risk at entry:')
        print(f'  ATR(5m,5):   {atr:.1f} pts index')
        print(f'  Sensex SL:   {sl:,.1f}  (dist = {abs(sensex_entry-sl):.1f} pts)')
        print(f'  Sensex T1:   {t1:,.1f}  (dist = {abs(t1-sensex_entry):.1f} pts)')
        rr = abs(t1-sensex_entry) / abs(sensex_entry-sl) if abs(sensex_entry-sl) > 0 else 0
        print(f'  R:R ratio:   1:{rr:.2f}')
        print(f'  P&L:         {"+" if pnl>0 else ""}{pnl}  {"✓ WIN" if pnl>0 else "✗ LOSS"}')

        # What happened after signal
        after = candles[ci+1:ci+10]
        print(f'\n  Post-entry candles (next 9 × 5m):')
        for j, ca in enumerate(after, 1):
            vj = vwaps[ci+j]
            dist_from_vwap = ca['c'] - vj
            print(f'    +{j*5:2d}m  {ca["t"]}  C={ca["c"]:.1f}  VWAP={vj:.1f}  C-VWAP={dist_from_vwap:+.1f}')

print('\n')
