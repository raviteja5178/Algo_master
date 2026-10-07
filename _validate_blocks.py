"""
Validate today's 7 blocked signals against real candle data.
For each signal, reconstruct the exact indicator values at the time of the block.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone, timedelta

from market.historical_data import fetch_historical_candles, SENSEX_TOKEN
from market.candle_builder import Candle

IST = timezone(timedelta(hours=5, minutes=30))

# ── Fetch today's 5m candles ──────────────────────────────────────────────────
candles: list[Candle] = fetch_historical_candles(SENSEX_TOKEN, interval="5minute", days_back=2)

# Keep only today (2026-10-07) candles
today_candles = [c for c in candles if c.timestamp.date().isoformat() == "2026-10-07"]
print(f"Today 5m candles loaded: {len(today_candles)}")
for c in today_candles:
    print(f"  {c.timestamp.strftime('%H:%M')}  O={c.open:.2f}  H={c.high:.2f}  L={c.low:.2f}  C={c.close:.2f}  body={abs(c.close-c.open):.2f}")

# ── EMA helper ────────────────────────────────────────────────────────────────
def ema_series(closes: list[float], period: int) -> list[float]:
    k = 2 / (period + 1)
    result = []
    for i, c in enumerate(closes):
        if i == 0:
            result.append(c)
        else:
            result.append(c * k + result[-1] * (1 - k))
    return result

# ── VWAP helper ───────────────────────────────────────────────────────────────
def vwap_at(candles_today: list[Candle], idx: int) -> float:
    cum_tp_v = 0.0
    cum_v = 0.0
    for c in candles_today[:idx+1]:
        tp = (c.high + c.low + c.close) / 3
        vol = max(c.volume, 1)
        cum_tp_v += tp * vol
        cum_v += vol
    return cum_tp_v / cum_v if cum_v else 0

# ── ATR helper ────────────────────────────────────────────────────────────────
def atr_at(candles_slice: list[Candle], period: int = 14) -> float:
    if len(candles_slice) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles_slice)):
        c = candles_slice[i]
        prev_c = candles_slice[i-1].close
        tr = max(c.high - c.low, abs(c.high - prev_c), abs(c.low - prev_c))
        trs.append(tr)
    if not trs:
        return 0.0
    # Wilder smoothing
    atr = sum(trs[:period]) / min(period, len(trs))
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr

# ── Blocked signals from log ──────────────────────────────────────────────────
# Signal fires after candle closes, so signal AT 09:20 uses candle 09:15
BLOCKS = [
    {"time": "09:20", "candle": "09:15", "signal": "PE_VWAP",  "reason": "BLOCKED_EMA_GAP",
     "log_ema9": 72893.03, "log_ema21": 72900.26, "log_gap": -7.22, "req": 10.0,
     "log_close": 72665.53, "log_vwap": 72698.58},
    {"time": "09:50", "candle": "09:45", "signal": "PE",       "reason": "BLOCKED_BODY",
     "log_body": 18.16, "log_atr": 70.36, "log_min_ratio": 0.35, "log_req": 24.62,
     "log_close": 72631.93},
    {"time": "10:00", "candle": "09:55", "signal": "PE",       "reason": "BLOCKED_BODY",
     "log_body": 13.63, "log_atr": 67.41, "log_min_ratio": 0.35, "log_req": 23.59,
     "log_close": 72629.34},
    {"time": "10:10", "candle": "10:05", "signal": "CE_VWAP",  "reason": "BLOCKED_SLOPE",
     "log_ema9_now": 72689.07, "log_ema9_prev": 72690.91,
     "log_close": 72681.72, "log_vwap": 72643.48},
    {"time": "10:20", "candle": "10:15", "signal": "CE_VWAP",  "reason": "BLOCKED_EMA_GAP",
     "log_ema9": 72701.67, "log_ema21": 72756.83, "log_gap": -55.16, "req": 10.0,
     "log_close": 72792.39, "log_vwap": 72656.64},
    {"time": "10:25", "candle": "10:20", "signal": "CE_NATR",  "reason": "BLOCKED_EMA_GAP",
     "log_ema9": 72730.69, "log_ema21": 72765.02, "log_gap": -34.33, "req": 10.0,
     "log_close": 72846.78},
    {"time": "10:30", "candle": "10:25", "signal": "PE_OB",    "reason": "BLOCKED_SLOPE",
     "log_ema9_now": 72775.68, "log_ema9_prev": 72730.69,
     "log_close": 72955.61},
]

# ── Build EMA series using ALL candles up to each signal ──────────────────────
# Use full history (yesterday + today) for warm EMA
all_recent = [c for c in candles if c.timestamp >= candles[-len(today_candles)-100].timestamp]
all_closes = [c.close for c in all_recent]
ema9_all  = ema_series(all_closes, 9)
ema21_all = ema_series(all_closes, 21)

# Map timestamp -> index in all_recent
ts_to_idx = {c.timestamp.strftime("%H:%M"): i for i, c in enumerate(all_recent)}

print("\n" + "="*80)
print("  BLOCK VALIDATION  —  2026-10-07")
print("="*80)

for b in BLOCKS:
    ctime = b["candle"]
    # find candle index
    cidx_all = None
    for i, c in enumerate(all_recent):
        if c.timestamp.date().isoformat() == "2026-10-07" and c.timestamp.strftime("%H:%M") == ctime:
            cidx_all = i
            break

    candle = all_recent[cidx_all] if cidx_all is not None else None
    cidx_today = next((i for i, c in enumerate(today_candles) if c.timestamp.strftime("%H:%M") == ctime), None)

    print(f"\n{'─'*78}")
    print(f"  Signal : {b['signal']}  @ {b['time']}  (candle {ctime})   Reason: {b['reason']}")
    if candle:
        body = abs(candle.close - candle.open)
        direction = "BEARISH" if candle.close < candle.open else "BULLISH"
        print(f"  Candle : O={candle.open:.2f}  H={candle.high:.2f}  L={candle.low:.2f}  C={candle.close:.2f}  "
              f"body={body:.2f}  [{direction}]")

    if b["reason"] == "BLOCKED_EMA_GAP":
        if cidx_all is not None:
            e9  = ema9_all[cidx_all]
            e21 = ema21_all[cidx_all]
            gap = e9 - e21
            log_gap = b["log_gap"]
            match = abs(gap - log_gap) < 5  # 5-pt tolerance due to EMA warmup diff
            print(f"  Log    : EMA9={b['log_ema9']:.2f}  EMA21={b['log_ema21']:.2f}  gap={log_gap:.2f}")
            print(f"  Calc   : EMA9={e9:.2f}  EMA21={e21:.2f}  gap={gap:.2f}")
            print(f"  Gap direction correct? {'YES ✓' if (gap < 0) == (log_gap < 0) else 'NO ✗'}")
            print(f"  Required gap: ≥{b['req']:.1f} pts  →  Block VALID? {'YES ✓' if abs(log_gap) < b['req'] else 'NO ✗'}")
        if "log_vwap" in b:
            print(f"  VWAP context: close={b['log_close']:.2f}  vwap={b['log_vwap']:.2f}  "
                  f"close {'< VWAP (bearish ✓)' if b['log_close'] < b['log_vwap'] else '> VWAP (bullish)'}")

    elif b["reason"] == "BLOCKED_BODY":
        if candle:
            body = abs(candle.close - candle.open)
            slc = all_recent[max(0, cidx_all-14):cidx_all+1] if cidx_all else []
            atr = atr_at(slc, 14) if slc else 0
            req = atr * b["log_min_ratio"]
            print(f"  Log    : body={b['log_body']:.2f}  atr={b['log_atr']:.2f}  required={b['log_req']:.2f}")
            print(f"  Calc   : body={body:.2f}  atr={atr:.2f}  required={atr*0.35:.2f}")
            print(f"  Block VALID? body < required? {'YES ✓' if body < req else 'NO ✗'}  "
                  f"(body={body:.2f} vs req={req:.2f})")
            direction = "BEARISH" if candle.close < candle.open else "BULLISH"
            print(f"  Signal wants PE (bearish), candle is {direction} → "
                  f"{'consistent' if direction == 'BEARISH' else 'candle itself contradicts PE signal!'}")

    elif b["reason"] == "BLOCKED_SLOPE":
        if cidx_all is not None and cidx_all > 0:
            e9_now  = ema9_all[cidx_all]
            e9_prev = ema9_all[cidx_all - 1]
            log_now  = b["log_ema9_now"]
            log_prev = b["log_ema9_prev"]
            rising = e9_now > e9_prev
            log_rising = log_now > log_prev
            print(f"  Log    : EMA9_prev={log_prev:.2f}  EMA9_now={log_now:.2f}  "
                  f"{'rising' if log_rising else 'falling'}")
            print(f"  Calc   : EMA9_prev={e9_prev:.2f}  EMA9_now={e9_now:.2f}  "
                  f"{'rising' if rising else 'falling'}")
            sig = b["signal"]
            if "CE" in sig:
                want = "rising"
                blocked_correctly = not rising
                log_blocked_correctly = not log_rising
            else:  # PE
                want = "falling"
                blocked_correctly = rising
                log_blocked_correctly = log_rising
            print(f"  {sig} needs EMA9 {want}  →  Log block VALID? {'YES ✓' if log_blocked_correctly else 'NO ✗'}  "
                  f"Calc confirms? {'YES ✓' if blocked_correctly else 'NO ✗'}")

print(f"\n{'='*78}")

# ── What happened AFTER each block? (outcome) ─────────────────────────────────
print("\n  POST-SIGNAL PRICE ACTION (next 3 candles after signal):")
for b in BLOCKS:
    ctime = b["candle"]
    cidx_today = next((i for i, c in enumerate(today_candles) if c.timestamp.strftime("%H:%M") == ctime), None)
    if cidx_today is None:
        print(f"  {b['signal']} @ {ctime}: candle not yet in history")
        continue
    sig_close = today_candles[cidx_today].close
    nxt = today_candles[cidx_today+1:cidx_today+4]
    if not nxt:
        print(f"  {b['signal']} @ {ctime}: no subsequent candles yet")
        continue
    max_move = max(c.high for c in nxt) - sig_close
    min_move = min(c.low  for c in nxt) - sig_close
    print(f"  {b['signal']} @ {ctime} close={sig_close:.2f} → "
          f"next {len(nxt)} candles: max_up={max_move:+.2f}  max_dn={min_move:+.2f}  "
          f"→ {'Would have been PROFITABLE' if ('PE' in b['signal'] and min_move < -30) or ('CE' in b['signal'] and max_move > 30) else 'Block SAVED loss' if ('PE' in b['signal'] and max_move > 20) or ('CE' in b['signal'] and min_move < -20) else 'Inconclusive'}")
