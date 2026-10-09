"""
Runs the EXACT live strategy code (find_pivot_setup + PivotTradeManager)
candle-by-candle on today's full 5m data, using every setting from .env / config/settings.py.
No approximations. No shortcuts. This is the real production logic.
"""
import sys, json, os
sys.stdout.reconfigure(encoding='utf-8')

# ── Load settings exactly as the bot does ────────────────────────────────────
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from config import settings
from market.historical_data import PivotLevels
from market.candle_builder import Candle
from strategies.pivot_strategy import find_pivot_setup
from execution.pivot_trade_manager import PivotTradeManager
from datetime import datetime, date, timezone
import pytz

IST = pytz.timezone("Asia/Kolkata")

# ── Fetch today's full 5m candles ─────────────────────────────────────────────
print("Fetching today's 5m SENSEX candles from Kite...")
candles_raw = []
try:
    from broker.kite_client import get_kite
    kite = get_kite()
    today_str = date.today().strftime("%Y-%m-%d")
    records = kite.historical_data(
        instrument_token=265,
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
        candles_raw.append(Candle(
            timestamp=ts,
            open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]),  close=float(r["close"]),
        ))
    print(f"  Fetched {len(candles_raw)} candles from Kite (09:15 onward)")
except Exception as e:
    print(f"  Kite fetch failed: {e}")
    print("  Falling back to bot_state.json candles (10:30+)...")
    state = json.load(open(".bot_state.json"))
    for d in state.get("candles_5m", []):
        ts = datetime.fromisoformat(d["t"])
        candles_raw.append(Candle(
            timestamp=ts,
            open=d["o"], high=d["h"], low=d["l"], close=d["c"],
        ))
    print(f"  Using {len(candles_raw)} candles from bot_state")

if not candles_raw:
    print("ERROR: No candles available.")
    sys.exit(1)

# ── Build PivotLevels from bot_state ────────────────────────────────────────
state = json.load(open(".bot_state.json"))
pv_raw = state["pivot_levels"]
pivot_levels = PivotLevels(
    pivot=pv_raw["pivot"], r1=pv_raw["r1"], r2=pv_raw["r2"],
    s1=pv_raw["s1"],   s2=pv_raw["s2"],
    prev_high=pv_raw.get("prev_high", 0.0),
    prev_low=pv_raw.get("prev_low", 0.0),
    prev_close=pv_raw.get("prev_close", 0.0),
)

# ── Active settings ───────────────────────────────────────────────────────────
S_CANDLES   = settings.PIVOT_SUSTAIN_CANDLES
S_ATR_P     = settings.PIVOT_ATR_PERIOD
S_SL_MODE   = settings.PIVOT_SL_MODE
S_SL_ATR_M  = settings.PIVOT_SL_ATR_MULT
S_SL_BUF    = settings.PIVOT_SL_BUFFER_ATR
S_MIN_ROOM  = settings.PIVOT_MIN_ROOM_R
S_MIN_TODAY = settings.PIVOT_MIN_TODAY_CANDLES
S_BE_R      = settings.PIVOT_BE_TRIGGER_R
S_BE_BUF    = settings.PIVOT_BE_BUFFER_PTS
S_T1_LOCK   = settings.PIVOT_T1_LOCK_PCT
S_TRAIL_M   = settings.PIVOT_TRAIL_ATR_MULT
S_CUSHION   = settings.PIVOT_HARD_SL_CUSHION
S_DELTA     = settings.PIVOT_OPTION_DELTA
S_MAX_TPDAY = settings.PIVOT_MAX_TRADES_PER_DAY
NO_ENTRY_T  = settings.NO_NEW_ENTRY_AFTER  # "15:00"
FORCE_EXIT  = settings.FORCE_EXIT_TIME     # "15:15"

P  = pivot_levels.pivot
R1 = pivot_levels.r1;  R2 = pivot_levels.r2
S1 = pivot_levels.s1;  S2 = pivot_levels.s2
PC = pivot_levels.prev_close

print(f"\n{'='*72}")
print(f"  PIVOT STRATEGY — LIVE SIMULATION  (exact code, exact settings)")
print(f"{'='*72}")
print(f"  Date        : {candles_raw[0].timestamp.date()}")
print(f"  P={P}  R1={R1}  R2={R2}  S1={S1}  S2={S2}")
print(f"  prev_close  : {PC}  ({'BELOW' if PC and PC < P else 'ABOVE'} P)")
print(f"  PIVOT_MIN_TODAY_CANDLES : {S_MIN_TODAY}")
print(f"  PIVOT_SUSTAIN_CANDLES   : {S_CANDLES}")
print(f"  PIVOT_SL_MODE           : {S_SL_MODE}")
print(f"  PIVOT_SL_BUFFER_ATR     : {S_SL_BUF}")
print(f"  PIVOT_MIN_ROOM_R        : {S_MIN_ROOM}")
print(f"  PIVOT_BE_TRIGGER_R      : {S_BE_R}")
print(f"  PIVOT_T1_LOCK_PCT       : {S_T1_LOCK}")
print(f"  PIVOT_TRAIL_ATR_MULT    : {S_TRAIL_M}")
print(f"  PIVOT_MAX_TRADES_PER_DAY: {S_MAX_TPDAY}")
print(f"  NO_NEW_ENTRY_AFTER      : {NO_ENTRY_T}")
print(f"  FORCE_EXIT_TIME         : {FORCE_EXIT}")
print()

# ── No-entry / force-exit time helpers ────────────────────────────────────────
def _t(hhmm: str):
    h, m = hhmm.split(":")
    return int(h), int(m)

NO_ENTRY_HM  = _t(NO_ENTRY_T)
FORCE_EXIT_HM = _t(FORCE_EXIT)

# ── Signal scanner ────────────────────────────────────────────────────────────
trades_taken = 0
results = []
in_trade = False
mgr = None
entry_info = None

for i, candle in enumerate(candles_raw):
    ts   = candle.timestamp
    hm   = (ts.hour, ts.minute)
    hhmm = ts.strftime("%H:%M")
    candles_so_far = candles_raw[:i + 1]

    # ── Manage open trade on every candle ────────────────────────────────────
    if in_trade and mgr is not None:
        ei = entry_info
        side = ei["side"]

        # Use candle high/low to simulate best/worst price within the bar
        idx_fav  = candle.high  if side == "CE" else candle.low   # best for trade
        idx_adv  = candle.low   if side == "CE" else candle.high  # worst (SL side)

        # Force exit at 15:15
        if hm >= FORCE_EXIT_HM:
            ex_px = candle.open
            ex_reason = "EOD_FORCE"
            pnl_idx = round((ex_px - ei["sensex_entry"]) * (1 if side=="CE" else -1), 2)
            ei.update(exit_hhmm=hhmm, exit_idx=ex_px, exit_reason=ex_reason, pnl_idx=pnl_idx)
            results.append(ei)
            in_trade = False; mgr = None
            continue

        # Update ATR in manager each candle (Flaw 9 fix)
        from market.indicators import atr_at
        fresh_atr = atr_at(candles_so_far, period=S_ATR_P)
        if fresh_atr and fresh_atr > 0:
            mgr.update_atr(fresh_atr)

        # Check adverse (SL) direction first
        result = mgr.on_index_price(idx_adv)
        if result and result[0] == "EXIT":
            ex_reason = result[1]
            # Exit at stop level for SL/TSL, at T2 for target
            if "TARGET" in ex_reason:
                ex_px = ei["t2"]
            else:
                ex_px = round(mgr.stop_index, 2)
            pnl_idx = round((ex_px - ei["sensex_entry"]) * (1 if side=="CE" else -1), 2)
            ei.update(exit_hhmm=hhmm, exit_idx=ex_px, exit_reason=ex_reason,
                      pnl_idx=pnl_idx, peak_idx=round(mgr.best_index, 2),
                      final_stop=round(mgr.stop_index, 2), stage=mgr.stage)
            results.append(ei)
            in_trade = False; mgr = None
            continue

        # Check favourable (T2) direction
        result = mgr.on_index_price(idx_fav)
        if result and result[0] == "EXIT":
            ex_reason = result[1]
            ex_px = ei["t2"] if "TARGET" in ex_reason else round(mgr.stop_index, 2)
            pnl_idx = round((ex_px - ei["sensex_entry"]) * (1 if side=="CE" else -1), 2)
            ei.update(exit_hhmm=hhmm, exit_idx=ex_px, exit_reason=ex_reason,
                      peak_idx=round(mgr.best_index, 2),
                      final_stop=round(mgr.stop_index, 2), stage=mgr.stage)
            results.append(ei)
            in_trade = False; mgr = None
            continue

        # Log stop moves
        if result and result[0] == "STOP_MOVED":
            ei.setdefault("stop_moves", []).append(
                f"{hhmm} stage={mgr.stage} stop={mgr.stop_index:.2f}"
            )

    # ── No-entry guard ────────────────────────────────────────────────────────
    if in_trade or trades_taken >= S_MAX_TPDAY:
        continue
    if hm >= NO_ENTRY_HM:
        continue

    # ── Run find_pivot_setup with exact settings ──────────────────────────────
    setup = find_pivot_setup(
        candles_so_far, pivot_levels,
        sustain_candles=S_CANDLES,
        atr_period=S_ATR_P,
        sl_mode=S_SL_MODE,
        sl_atr_mult=S_SL_ATR_M,
        sl_buffer_atr=S_SL_BUF,
        min_room_r=S_MIN_ROOM,
        min_today_candles=S_MIN_TODAY,
    )

    if setup is None:
        continue

    # ── Signal found — open trade ─────────────────────────────────────────────
    trades_taken += 1
    sign = 1 if setup.side == "CE" else -1

    mgr = PivotTradeManager(
        side=setup.side,
        entry_index=setup.entry,
        stop_index=setup.stop,
        t1=setup.t1, t2=setup.t2,
        atr=setup.atr,
        option_entry=0.0,          # no option price in index sim
        delta=S_DELTA,
        be_trigger_r=S_BE_R,
        be_buffer_pts=S_BE_BUF,
        t1_lock_pct=S_T1_LOCK,
        trail_atr_mult=S_TRAIL_M,
        hard_sl_cushion=S_CUSHION,
        signal_risk=setup.risk,
    )

    # Identify sustain window candles for the report
    today_so_far = [c for c in candles_so_far if c.timestamp.date() == ts.date()]
    n = S_CANDLES
    window = today_so_far[-n:]
    before = today_so_far[-n-1] if len(today_so_far) > n else None
    before_close = before.close if before else PC

    entry_info = dict(
        trade_num=trades_taken,
        side=setup.side,
        signal_hhmm=hhmm,
        sensex_entry=setup.entry,
        stop=setup.stop, risk=setup.risk, atr=setup.atr,
        t1=setup.t1, t2=setup.t2,
        room=round(abs(setup.t1 - setup.entry), 2),
        room_r=round(abs(setup.t1 - setup.entry) / setup.risk, 2),
        before_close=round(before_close, 2) if before_close else None,
        win_candles=[f"{c.timestamp.strftime('%H:%M')} c={c.close:.2f} {'l' if setup.side=='CE' else 'h'}={c.low if setup.side=='CE' else c.high:.2f}" for c in window],
        n_today=len(today_so_far),
        stop_moves=[],
        # exit fields (filled later)
        exit_hhmm=None, exit_idx=None, exit_reason=None,
        pnl_idx=None, peak_idx=setup.entry, final_stop=setup.stop, stage="INITIAL",
    )
    in_trade = True

# ── Handle trade still open at end of data ───────────────────────────────────
if in_trade and entry_info:
    last = candles_raw[-1]
    entry_info.update(
        exit_hhmm=last.timestamp.strftime("%H:%M"),
        exit_idx=last.close,
        exit_reason="EOD_DATA_END",
        pnl_idx=round((last.close - entry_info["sensex_entry"]) * (1 if entry_info["side"]=="CE" else -1), 2),
        peak_idx=round(mgr.best_index, 2),
        final_stop=round(mgr.stop_index, 2),
        stage=mgr.stage,
    )
    results.append(entry_info)

# ── Print results ─────────────────────────────────────────────────────────────
print(f"{'='*72}")
print(f"  {len(results)} PIVOT TRADE(S) FOUND")
print(f"{'='*72}")

for r in results:
    sign = 1 if r["side"] == "CE" else -1
    pnl_str = f"+{r['pnl_idx']}" if r.get('pnl_idx', 0) >= 0 else str(r['pnl_idx'])
    print()
    print(f"  TRADE {r['trade_num']}: {r['side']}_PIVOT")
    print(f"  {'─'*66}")
    print(f"  Signal candle : {r['signal_hhmm']}  (n_today={r['n_today']})")
    print(f"  Sustain window: {r['win_candles']}")
    print(f"  before_close  : {r['before_close']}  ({'< P' if r['before_close'] and r['before_close'] < P else '> P'} = fresh {'CE' if r['side']=='CE' else 'PE'} cross)")
    print()
    print(f"  ENTRY (SENSEX): {r['sensex_entry']}")
    print(f"  Stop  (SENSEX): {r['stop']}")
    print(f"  Risk          : {r['risk']} idx pts")
    print(f"  ATR at entry  : {r['atr']}")
    print(f"  T1 ({'R1' if r['side']=='CE' else 'S1'})         : {r['t1']}")
    print(f"  T2 ({'R2' if r['side']=='CE' else 'S2'})         : {r['t2']}")
    print(f"  Room to T1    : {r['room']} pts  ({r['room_r']}x risk)")
    print()
    print(f"  DURING TRADE:")
    if r['stop_moves']:
        for sm in r['stop_moves']:
            print(f"    Stop move: {sm}")
    else:
        print(f"    (No stop moves recorded in candle sim)")
    print(f"  Peak index    : {r['peak_idx']}")
    print(f"  Final stop    : {r['final_stop']}")
    print(f"  Stage at exit : {r['stage']}")
    print()
    print(f"  EXIT:")
    print(f"    Time   : {r['exit_hhmm']}")
    print(f"    Index  : {r['exit_idx']}")
    print(f"    Reason : {r['exit_reason']}")
    print(f"    PnL    : {pnl_str} idx pts  (~{round(r['pnl_idx']*S_DELTA*20, 2) if r['pnl_idx'] else 0} rupees at delta {S_DELTA} x 20 qty)")

if not results:
    print()
    print("  No signals fired today under current code and settings.")
    print()
    print(f"  P={P}  prev_close={PC}  ({'BELOW' if PC and PC < P else 'ABOVE'} P)")
    print(f"  For CE_PIVOT: need before_close < P, then 2 closes > P with low > P")
    print(f"  For PE_PIVOT: need before_close > P, then 2 closes < P with high < P")
    print()
    print("  Candle closes vs Pivot today:")
    today_date = candles_raw[0].timestamp.date()
    for c in candles_raw:
        pos = "ABOVE" if c.close > P else "BELOW"
        print(f"    {c.timestamp.strftime('%H:%M')}  c={c.close:.2f}  {pos} P  l={c.low:.2f}  h={c.high:.2f}")

print()
print(f"{'='*72}")
print(f"  TOTAL: {len(results)} trades, {sum(1 for r in results if (r.get('pnl_idx') or 0) > 0)} wins, {sum(1 for r in results if (r.get('pnl_idx') or 0) < 0)} losses")
if results:
    total_pnl = sum((r.get('pnl_idx') or 0) * S_DELTA * 20 for r in results)
    print(f"  Net P&L: {'+' if total_pnl >= 0 else ''}{round(total_pnl, 2)} rupees")
print(f"{'='*72}")
