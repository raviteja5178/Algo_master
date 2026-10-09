"""Replay today's SENSEX data through the live Pivot Sustain code (find_pivot_setup + PivotTradeManager).
Lists every signal (taken + blocked) and each trade's exit and exit reason. Index-point based; Rs is approx (delta × qty)."""
import logging
from datetime import date, timedelta

from config import settings as S
from market.historical_data import fetch_historical_candles, fetch_pivot_levels, SENSEX_TOKEN
from strategies.pivot_strategy import find_pivot_setup
from execution.pivot_trade_manager import PivotTradeManager

logging.getLogger("execution.pivot_trade_manager").propagate = False
logging.getLogger("market.historical_data").propagate = False

TODAY = date.today()
hm = lambda t: (t.hour, t.minute)
fmt = lambda t: t.strftime("%H:%M")
NO_NEW = tuple(map(int, S.NO_NEW_ENTRY_AFTER.split(":")))
FORCE = tuple(map(int, S.FORCE_EXIT_TIME.split(":")))
DELTA, QTY, COST = S.PIVOT_OPTION_DELTA, S.QUANTITY, 10.0

pl = fetch_pivot_levels(SENSEX_TOKEN)
if pl is None:
    raise SystemExit("No pivot levels.")
print(f"Pivot levels  P={pl.pivot:.2f}  R1={pl.r1:.2f}  R2={pl.r2:.2f}  S1={pl.s1:.2f}  S2={pl.s2:.2f}")

c5 = fetch_historical_candles(SENSEX_TOKEN, "5minute", days_back=6)
c1 = [c for c in fetch_historical_candles(SENSEX_TOKEN, "minute", days_back=1) if c.timestamp.date() == TODAY]
idx = [i for i, c in enumerate(c5) if c.timestamp.date() == TODAY]
if not idx:
    raise SystemExit("No 5m candles for today.")

signals, trades = [], []
mgr = pos = None
trades_today = 0


def close(t, px, reason):
    global mgr, pos
    pts = (px - pos["entry"]) * mgr.sign
    trades.append({**pos, "exit_t": fmt(t), "exit": round(px, 2), "reason": reason,
                   "stage": mgr.stage, "pts": round(pts, 2),
                   "rs": round((pts * DELTA - COST * DELTA) * QTY, 0)})
    mgr = pos = None


def step(start, end):
    """Walk 1m bars in [start, end) through the manager (adverse extreme first, then favourable)."""
    for b in c1:
        if mgr is None:
            return
        if not (start <= b.timestamp < end):
            continue
        if hm(b.timestamp) >= FORCE:
            close(b.timestamp, b.open, "FORCE_EXIT"); return
        adv, fav = (b.low, b.high) if mgr.sign == 1 else (b.high, b.low)
        for px in (adv, fav):
            r = mgr.on_index_price(px)
            if r and r[0] == "EXIT":
                exit_px = mgr.stop_index if "T2" not in r[1] else mgr.t2
                close(b.timestamp + timedelta(minutes=1), exit_px, r[1]); return
        r = mgr.on_index_price(b.close)
        if r and r[0] == "EXIT":
            close(b.timestamp + timedelta(minutes=1), b.close, r[1]); return


for i in idx:
    bar = c5[i]
    signal_t = bar.timestamp + timedelta(minutes=5)          # candle close = decision time
    step(bar.timestamp, signal_t)                            # manage open trade through this candle
    setup = find_pivot_setup(
        c5[: i + 1], pl, sustain_candles=S.PIVOT_SUSTAIN_CANDLES, atr_period=S.PIVOT_ATR_PERIOD,
        sl_mode=S.PIVOT_SL_MODE, sl_atr_mult=S.PIVOT_SL_ATR_MULT,
        sl_buffer_atr=S.PIVOT_SL_BUFFER_ATR, min_room_r=0.0)  # room checked below so we can report it
    if setup is None:
        # Report sustains rejected inside find_pivot_setup (entry already at/through T1 → no room)
        today = [c for c in c5[: i + 1] if c.timestamp.date() == TODAY]
        n = S.PIVOT_SUSTAIN_CANDLES
        if len(today) >= n:
            w, before = today[-n:], (today[-n - 1] if len(today) > n else None)
            for side, ok, fresh, t1 in (
                ("CE", all(c.close > pl.pivot for c in w), before is None or before.close <= pl.pivot, pl.r1),
                ("PE", all(c.close < pl.pivot for c in w), before is None or before.close >= pl.pivot, pl.s1)):
                if ok and fresh:
                    signals.append({"t": fmt(signal_t), "side": f"{side}_PIVOT", "entry": bar.close, "sl": 0.0,
                                    "risk": 0.0, "t1": t1, "t2": pl.r2 if side == "CE" else pl.s2, "atr": 0.0,
                                    "status": "BLOCKED: entry already beyond T1 (no room)"})
        continue
    room = abs(setup.t1 - setup.entry)
    block = None
    if room < S.PIVOT_MIN_ROOM_R * setup.risk:
        block = f"ROOM {room:.0f} < {S.PIVOT_MIN_ROOM_R}R ({setup.risk:.0f})"
    elif hm(signal_t) >= NO_NEW:
        block = "AFTER NO_NEW_ENTRY"
    elif mgr is not None:
        block = "POSITION OPEN"
    elif trades_today >= S.PIVOT_MAX_TRADES_PER_DAY:
        block = "MAX TRADES/DAY"
    signals.append({"t": fmt(signal_t), "side": f"{setup.side}_PIVOT", "entry": setup.entry,
                    "sl": setup.stop, "risk": setup.risk, "t1": setup.t1, "t2": setup.t2,
                    "atr": setup.atr, "status": block or "TAKEN"})
    if block:
        continue
    trades_today += 1
    mgr = PivotTradeManager(setup.side, setup.entry, setup.stop, setup.t1, setup.t2, setup.atr, 100.0,
                            delta=DELTA, be_trigger_r=S.PIVOT_BE_TRIGGER_R, be_buffer_pts=S.PIVOT_BE_BUFFER_PTS,
                            t1_lock_pct=S.PIVOT_T1_LOCK_PCT, trail_atr_mult=S.PIVOT_TRAIL_ATR_MULT,
                            hard_sl_cushion=S.PIVOT_HARD_SL_CUSHION)
    pos = {"entry_t": fmt(signal_t), "side": f"{setup.side}_PIVOT", "entry": setup.entry,
           "sl0": setup.stop, "t1": setup.t1, "t2": setup.t2}

if mgr is not None:
    step(c1[0].timestamp, c1[-1].timestamp + timedelta(minutes=1))
if mgr is not None:
    close(c1[-1].timestamp, c1[-1].close, "OPEN_AT_DATA_END")

print(f"\nSIGNALS ({len(signals)})")
print(f"{'time':5} {'side':9} {'entry':>9} {'SL':>9} {'risk':>5} {'T1':>9} {'T2':>9} {'ATR':>5}  status")
for s in signals:
    print(f"{s['t']:5} {s['side']:9} {s['entry']:9.2f} {s['sl']:9.2f} {s['risk']:5.0f} "
          f"{s['t1']:9.2f} {s['t2']:9.2f} {s['atr']:5.0f}  {s['status']}")
print(f"\nTRADES ({len(trades)})")
print(f"{'in':5} {'side':9} {'entry':>9} {'SL0':>9} {'out':5} {'exit':>9} {'stage':7} {'reason':18} {'pts':>7} {'~Rs':>7}")
for t in trades:
    print(f"{t['entry_t']:5} {t['side']:9} {t['entry']:9.2f} {t['sl0']:9.2f} {t['exit_t']:5} {t['exit']:9.2f} "
          f"{t['stage']:7} {t['reason']:18} {t['pts']:7.1f} {t['rs']:7.0f}")
tot = sum(t["pts"] for t in trades)
print(f"\nNet index pts: {tot:+.1f}   ~Rs (delta {DELTA}, qty {QTY}, {COST:.0f} pts cost/trade): "
      f"{sum(t['rs'] for t in trades):+.0f}")
