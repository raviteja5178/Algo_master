"""
Deep analysis: candle-by-candle trace of EVERY pivot signal check today.
Shows exactly which filter passed/failed on each candle.
"""
import sys, json, os
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from config import settings
from market.historical_data import PivotLevels
from market.candle_builder import Candle
from market.indicators import atr_at
from datetime import date
import pytz

IST = pytz.timezone("Asia/Kolkata")

# Fetch candles
from broker.kite_client import get_kite
kite = get_kite()
today_str = date.today().strftime("%Y-%m-%d")
records = kite.historical_data(
    instrument_token=265,
    from_date=f"{today_str} 09:00:00",
    to_date=f"{today_str} 15:30:00",
    interval="5minute",
)
candles_raw = []
for r in records:
    ts = r["date"]
    if hasattr(ts, "tzinfo") and ts.tzinfo is None:
        ts = IST.localize(ts)
    if (ts.hour, ts.minute) < (9, 15):
        continue
    candles_raw.append(Candle(timestamp=ts, open=float(r["open"]),
        high=float(r["high"]), low=float(r["low"]), close=float(r["close"])))

state   = json.load(open(".bot_state.json"))
pv_raw  = state["pivot_levels"]
pivot_levels = PivotLevels(
    pivot=pv_raw["pivot"], r1=pv_raw["r1"], r2=pv_raw["r2"],
    s1=pv_raw["s1"], s2=pv_raw["s2"],
    prev_high=pv_raw.get("prev_high", 0.0),
    prev_low=pv_raw.get("prev_low", 0.0),
    prev_close=pv_raw.get("prev_close", 0.0),
)

P  = pivot_levels.pivot
R1 = pivot_levels.r1;  R2 = pivot_levels.r2
S1 = pivot_levels.s1;  S2 = pivot_levels.s2
PC = pivot_levels.prev_close

S_CANDLES   = settings.PIVOT_SUSTAIN_CANDLES    # 2
S_ATR_P     = settings.PIVOT_ATR_PERIOD         # 14
S_SL_BUF    = settings.PIVOT_SL_BUFFER_ATR      # 0.05
S_MIN_ROOM  = settings.PIVOT_MIN_ROOM_R         # 1.0
S_MIN_TODAY = settings.PIVOT_MIN_TODAY_CANDLES  # from .env

NO_ENTRY_HM = tuple(int(x) for x in settings.NO_NEW_ENTRY_AFTER.split(":"))

print(f"P={P}  R1={R1}  R2={R2}  S1={S1}  S2={S2}  prev_close={PC}")
print(f"PIVOT_MIN_TODAY_CANDLES={S_MIN_TODAY}  SUSTAIN={S_CANDLES}  SL_BUF={S_SL_BUF}  MIN_ROOM_R={S_MIN_ROOM}")
print(f"NO_NEW_ENTRY_AFTER={settings.NO_NEW_ENTRY_AFTER}")
print()
print(f"{'Time':5}  {'Close':>9}  {'Low':>9}  {'High':>9}  {'vs P':6}  {'n':>3}  {'ATR':>7}  CE_check  PE_check  SIGNAL?  Reason")
print("-" * 130)

NO_ENTRY_AFTER = settings.NO_NEW_ENTRY_AFTER

for i in range(len(candles_raw)):
    c    = candles_raw[i]
    ts   = c.timestamp
    hhmm = ts.strftime("%H:%M")
    hm   = (ts.hour, ts.minute)

    if hm >= NO_ENTRY_HM:
        break

    candles_so_far = candles_raw[:i + 1]
    today_so_far   = [x for x in candles_so_far if x.timestamp.date() == ts.date()]
    n_today        = len(today_so_far)

    pos = "ABOVE" if c.close > P else "BELOW"

    # ATR
    atr = atr_at(candles_so_far, period=S_ATR_P)
    atr_str = f"{atr:.1f}" if atr else "N/A"

    # Min candles guard
    if S_MIN_TODAY > 0 and n_today < S_MIN_TODAY:
        print(f"{hhmm}  {c.close:>9.2f}  {c.low:>9.2f}  {c.high:>9.2f}  {pos:6}  {n_today:>3}  {atr_str:>7}  --        --        SKIP     min_today({n_today}<{S_MIN_TODAY})")
        continue

    if not atr or atr <= 0:
        print(f"{hhmm}  {c.close:>9.2f}  {c.low:>9.2f}  {c.high:>9.2f}  {pos:6}  {n_today:>3}  {atr_str:>7}  --        --        SKIP     ATR_UNAVAILABLE")
        continue

    # Need at least sustain_candles candles
    if n_today < S_CANDLES:
        print(f"{hhmm}  {c.close:>9.2f}  {c.low:>9.2f}  {c.high:>9.2f}  {pos:6}  {n_today:>3}  {atr_str:>7}  --        --        SKIP     n<sustain({n_today}<{S_CANDLES})")
        continue

    window     = today_so_far[-S_CANDLES:]
    before     = today_so_far[-S_CANDLES - 1] if len(today_so_far) > S_CANDLES else None
    before_close = before.close if before else PC

    # --- CE check ---
    ce_sustained = all(x.close > P and x.low > P for x in window)
    ce_fresh     = before_close is not None and before_close < P
    ce_pass_sus  = "Y" if ce_sustained else "N"
    ce_pass_fr   = "Y" if ce_fresh else "N"
    ce_ok        = ce_sustained and ce_fresh
    ce_str       = f"sus={ce_pass_sus} fr={ce_pass_fr}"

    # --- PE check ---
    pe_sustained = all(x.close < P and x.high < P for x in window)
    pe_fresh     = before_close is not None and before_close > P
    pe_pass_sus  = "Y" if pe_sustained else "N"
    pe_pass_fr   = "Y" if pe_fresh else "N"
    pe_ok        = pe_sustained and pe_fresh
    pe_str       = f"sus={pe_pass_sus} fr={pe_pass_fr}"

    signal = None
    reason = ""

    for side, ok, t1, t2 in [("CE", ce_ok, R1, S2), ("PE", pe_ok, S1, S2)]:
        if side == "CE":
            t1, t2 = R1, R2
            stop   = min(x.low for x in window) - S_SL_BUF * atr
            risk   = c.close - stop
            room   = t1 - c.close
        else:
            t1, t2 = S1, S2
            stop   = max(x.high for x in window) + S_SL_BUF * atr
            risk   = stop - c.close
            room   = c.close - t1

        if not ok:
            sus_fail = (ce_sustained if side=="CE" else pe_sustained)
            fr_fail  = (ce_fresh    if side=="CE" else pe_fresh)
            if not (ce_sustained if side=="CE" else pe_sustained):
                # Check which candle in window failed
                fails = []
                for wc in window:
                    if side == "CE" and not (wc.close > P and wc.low > P):
                        fails.append(f"{wc.timestamp.strftime('%H:%M')}:c={wc.close:.0f},l={wc.low:.0f}")
                    if side == "PE" and not (wc.close < P and wc.high < P):
                        fails.append(f"{wc.timestamp.strftime('%H:%M')}:c={wc.close:.0f},h={wc.high:.0f}")
            continue

        if risk <= 0 or room <= 0:
            reason = f"{side}: risk={round(risk,1)} room={round(room,1)} invalid"
            continue
        if room < S_MIN_ROOM * risk:
            reason = f"{side}: room({round(room,1)})<{S_MIN_ROOM}xrisk({round(risk,1)})"
            continue

        signal = f"{side}_PIVOT"
        reason = f"entry={round(c.close,2)} stop={round(stop,2)} risk={round(risk,2)} t1={t1} room/risk={round(room/risk,2)}x"
        break

    if signal:
        print(f"{hhmm}  {c.close:>9.2f}  {c.low:>9.2f}  {c.high:>9.2f}  {pos:6}  {n_today:>3}  {atr_str:>7}  {ce_str:9} {pe_str:9} *** {signal} *** {reason}")
    else:
        if not reason:
            reason = f"CE[sus={ce_pass_sus},fr={ce_pass_fr}] PE[sus={pe_pass_sus},fr={pe_pass_fr}]"
        print(f"{hhmm}  {c.close:>9.2f}  {c.low:>9.2f}  {c.high:>9.2f}  {pos:6}  {n_today:>3}  {atr_str:>7}  {ce_str:9} {pe_str:9} none     {reason}")
