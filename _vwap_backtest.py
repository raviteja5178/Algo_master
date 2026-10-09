"""
VWAP Retest backtest for TODAY. It uses the live bot's own modules:
  - strategies.vwap_strategy  (raw CE/PE signal)
  - SmartEntryFilter          (same settings as main.py; records the block reason)
  - compute_risk_params       (Mode D swing SL, falling back to Mode C ATR)
  - TrailingStopManager / DynamicTargetManager (BE + ATR-dynamic TSL)
Exits are simulated on the REAL option 1-minute candles (ATM strike at signal time).
Lists every raw signal, including blocked ones, and every trade with its exit reason.
"""
import csv
import logging
from datetime import date, timedelta

from config import settings as S
from broker.kite_client import get_kite
from market.historical_data import fetch_historical_candles, SENSEX_TOKEN
from market.candle_builder import Candle
from market.indicators import swing_levels
from strategies.vwap_strategy import is_vwap_ce_signal, is_vwap_pe_signal
from strategies.smart_entry import SmartEntryFilter
from execution.atr_risk import compute_risk_params
from execution.trailing_stop import TrailingStopManager
from execution.target_manager import DynamicTargetManager
from execution.option_selector import select_atm_candidates

# ── Capture SmartEntry block reasons from its log events ─────────────────────
_msgs: list[str] = []
class _Cap(logging.Handler):
    def emit(self, r): _msgs.append(r.getMessage())
_se_log = logging.getLogger("strategies.smart_entry")
_se_log.setLevel(logging.INFO); _se_log.addHandler(_Cap()); _se_log.propagate = False
for n in ("execution.atr_risk", "execution.trailing_stop", "execution.target_manager",
          "market.historical_data", "broker.instrument_repository", "execution.option_selector"):
    logging.getLogger(n).propagate = False

import sys
TODAY = date.today()
# Optional: VWAP anchor HH:MM (e.g. 11:55) to mimic a bot restart mid-day. Default = 09:15 (true VWAP).
ANCHOR = tuple(map(int, (sys.argv[1] if len(sys.argv) > 1 else "09:15").split(":")))
M1, M5, M15 = timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15)
kite = get_kite()

c5_all  = fetch_historical_candles(SENSEX_TOKEN, "5minute", days_back=6)
c15_all = fetch_historical_candles(SENSEX_TOKEN, "15minute", days_back=6)
today_idx = [i for i, c in enumerate(c5_all) if c.timestamp.date() == TODAY]
if not today_idx:
    raise SystemExit("No 5m candles for today.")

smart = SmartEntryFilter(
    min_body_atr_ratio=S.SMART_ENTRY_MIN_BODY_ATR_RATIO, require_ema_slope=S.SMART_ENTRY_REQUIRE_EMA_SLOPE,
    cooldown_candles=S.SMART_ENTRY_COOLDOWN_CANDLES, min_ema_gap_pts=S.SMART_ENTRY_MIN_EMA_GAP_PTS,
    gap_close_rate=S.SMART_ENTRY_GAP_CLOSE_RATE, require_ema_gap_widening=S.SMART_ENTRY_REQUIRE_EMA_GAP_WIDENING,
    require_15m_trend=S.SMART_ENTRY_REQUIRE_15M_TREND, max_15m_gap_pts=S.SMART_ENTRY_15M_MAX_GAP_PTS,
    squeeze_bypass=S.SMART_ENTRY_SQUEEZE_BYPASS, squeeze_candles=S.SMART_ENTRY_SQUEEZE_CANDLES,
    max_premium_extension_pct=S.SMART_ENTRY_MAX_PREMIUM_EXTENSION_PCT,
    squeeze_body_atr_ratio=S.SMART_ENTRY_SQUEEZE_BODY_ATR_RATIO,
    structure_bypass_candles=S.SMART_ENTRY_STRUCTURE_BYPASS_CANDLES,
    structure_bypass_ema_confirm=S.SMART_ENTRY_STRUCTURE_BYPASS_EMA_CONFIRM,
    bounce_exempt_strategies=S.SMART_ENTRY_BOUNCE_EXEMPT_STRATEGIES,
    slope_exempt_strategies=S.SMART_ENTRY_SLOPE_EXEMPT_STRATEGIES,
)

h, m = map(int, S.NO_NEW_ENTRY_AFTER.split(":")); NO_NEW = (h, m)
h, m = map(int, S.FORCE_EXIT_TIME.split(":"));   FORCE = (h, m)
h, m = map(int, S.TIME_DECAY_EXIT_AFTER.split(":")); TDECAY = (h, m)
hm = lambda t: (t.hour, t.minute)
fmt = lambda t: t.strftime("%H:%M")

_opt_cache: dict[int, list[Candle]] = {}
def option_bars(token: int) -> list[Candle]:
    if token not in _opt_cache:
        raw = kite.historical_data(token, f"{TODAY} 09:15:00", f"{TODAY} 15:30:00", "minute")
        _opt_cache[token] = [Candle(r["date"], float(r["open"]), float(r["high"]),
                                    float(r["low"]), float(r["close"])) for r in raw]
    return _opt_cache[token]

def completed_5m(at):   # 5m candles fully closed at time `at`
    return [c for c in c5_all if c.timestamp + M5 <= at]

signals, trades = [], []
pos = None   # open trade dict

def close_pos(t, px, reason):
    global pos
    pnl_pts = round(px - pos["entry"], 2)
    pos.update(exit_time=fmt(t), exit_px=round(px, 2), exit_reason=reason, pnl_pts=pnl_pts,
               pnl_rs=round(pnl_pts * pos["qty"], 2), final_stop=pos["tsl"].current_stop,
               be_hit="Y" if pos["tsl"].break_even_activated else "N",
               trail_steps=pos["tsl"].trail_steps_completed, peak=round(pos["peak"], 2),
               mfe_pts=round(pos["peak"] - pos["entry"], 2))
    smart.on_trade_closed(pnl_pts)
    trades.append(pos); pos = None

def step_position(until):
    """Walk option 1m bars from pos['next'] up to (not incl.) `until`."""
    for b in pos["bars"]:
        if b.timestamp < pos["next"] or b.timestamp >= until:
            continue
        pos["next"] = b.timestamp + M1
        tsl, tgt = pos["tsl"], pos["tgt"]
        if hm(b.timestamp) >= FORCE:
            return close_pos(b.timestamp, b.open, "FORCE_EXIT_EOD")
        # 1) stop check first (conservative: adverse move assumed before favourable)
        if b.low <= tsl.current_stop:
            px = min(tsl.current_stop, b.open)
            if tsl.current_stop > pos["entry"]:   reason = "TSL_HIT (profit locked)"
            elif tsl.break_even_activated:        reason = "TSL_HIT (break-even)"
            else:                                 reason = "SL_HIT"
            return close_pos(b.timestamp, px, reason)
        # 2) target check
        if b.high >= tgt.target_reference:
            return close_pos(b.timestamp, max(tgt.target_reference, b.open), "TARGET_HIT")
        # 3) trail with the bar high
        pos["peak"] = max(pos["peak"], b.high)
        if tsl.update(b.high, completed_5m(b.timestamp + M1)) is not None:
            tgt.sync_trail_steps(tsl.trail_steps_completed)
        # 4) time-decay smart exit
        if S.ENABLE_SMART_EXIT and S.ENABLE_TIME_DECAY_EXIT and hm(b.timestamp) >= TDECAY \
                and (b.close - pos["entry"]) < S.TIME_DECAY_MIN_PNL_PTS:
            return close_pos(b.timestamp + M1, b.close, "TIME_DECAY")

for i in today_idx:
    c = c5_all[i]
    T = c.timestamp + M5                      # candle close / evaluation time
    if pos: step_position(T)
    smart.on_candle()

    w5 = c5_all[:i + 1]
    w15 = [x for x in c15_all if x.timestamp + M15 <= T]
    today_c = [x for x in w5 if x.timestamp.date() == TODAY and hm(x.timestamp) >= ANCHOR]
    if not today_c:
        continue
    vol = lambda x: x.volume if x.volume > 0 else 1
    vwap = sum((x.high + x.low + x.close) / 3 * vol(x) for x in today_c) / sum(vol(x) for x in today_c)
    kw = dict(retest_lookback=S.VWAP_RETEST_LOOKBACK, min_bounce_pts=S.VWAP_MIN_BOUNCE_PTS)

    sig = "CE_VWAP" if is_vwap_ce_signal(w5, vwap, **kw) else \
          "PE_VWAP" if is_vwap_pe_signal(w5, vwap, **kw) else None
    if not sig:
        continue

    _msgs.clear()
    ok = smart.allow(sig, w5, candles_15m=w15)
    blk = next((mm for mm in _msgs if "BLOCKED" in mm), "")
    bypass = "SQUEEZE_BYPASS" if any("SQUEEZE_BYPASS" in mm for mm in _msgs) else ""
    row = dict(time=fmt(c.timestamp), signal=sig, close=round(c.close, 2), vwap=round(vwap, 2),
               dist=round(c.close - vwap, 2), status="", reason="")
    side = sig[:2]
    if not ok:
        row.update(status="BLOCKED", reason=blk.split("]")[0].strip("[") + " |" + blk.split("]", 1)[-1])
    elif pos and pos["side"] != side:
        row.update(status="REVERSAL_EXIT", reason=f"closes open {pos['side']} trade")
        bar = next((b for b in pos["bars"] if b.timestamp >= T), pos["bars"][-1])
        close_pos(T, bar.open, "REVERSAL_SIGNAL")
    elif pos:
        row.update(status="BLOCKED", reason="position already open (same side)")
    elif hm(T) >= NO_NEW:
        row.update(status="BLOCKED", reason=f"NO_NEW_ENTRY_AFTER {S.NO_NEW_ENTRY_AFTER}")
    else:
        inst = select_atm_candidates(c.close, side)[0]
        bars = option_bars(inst["instrument_token"])
        eb = next((b for b in bars if b.timestamp >= T), None)
        if eb is None:
            row.update(status="BLOCKED", reason="no option data")
        else:
            entry = eb.open
            sh, sl_ = swing_levels(w5, length=S.SWING_SL_LENGTH, reference_price=c.close) \
                if S.USE_SWING_SL else (None, None)
            r = compute_risk_params(
                w5, fixed_sl=S.INITIAL_SL_POINTS, fixed_target=S.INITIAL_TARGET_OFFSET_POINTS,
                fixed_trail=S.TRAIL_STEP_POINTS, min_sl_pts=S.MIN_SL_POINTS,
                min_target_pts=S.MIN_TARGET_POINTS, min_trail_pts=S.MIN_TRAIL_POINTS,
                entry_price=entry, use_spot_atr=S.USE_SPOT_ATR_RISK, spot_atr_period=S.SPOT_ATR_PERIOD,
                spot_sl_mult=S.SPOT_ATR_SL_MULT, target_rr=S.SPOT_ATR_TARGET_RR, trail_rr=S.SPOT_ATR_TRAIL_RR,
                use_swing_sl=S.USE_SWING_SL, option_type=side, sensex_ltp=c.close,
                swing_high=sh, swing_low=sl_, swing_sl_min_atr_mult=S.SWING_SL_MIN_ATR_MULT,
                max_sl_pct=S.MAX_SL_PCT)
            tsl = TrailingStopManager(entry, r.initial_sl_points, r.break_even_trigger_points,
                                      r.trail_step_points, tsl_atr_trail_mult=S.TSL_ATR_TRAIL_MULT,
                                      tsl_atr_period=S.TSL_ATR_PERIOD)
            tgt = DynamicTargetManager(entry, r.initial_target_points, r.trail_step_points)
            row.update(status="TRADED" + (f" ({bypass})" if bypass else ""))
            pos = dict(n=len(trades) + 1, signal=sig, side=side, symbol=inst["tradingsymbol"],
                       entry_time=fmt(T), sensex=round(c.close, 2), entry=entry, qty=S.QUANTITY,
                       sl_mode=r.sl_mode, sl_pts=r.initial_sl_points, be_pts=r.break_even_trigger_points,
                       trail_pts=r.trail_step_points, tgt_pts=r.initial_target_points,
                       init_stop=tsl.current_stop, init_target=round(tgt.target_reference, 2),
                       tsl=tsl, tgt=tgt, bars=bars, next=T, peak=entry)
    signals.append(row)

if pos:
    step_position(T + timedelta(hours=2))
    if pos:
        lb = pos["bars"][-1]; close_pos(lb.timestamp, lb.close, "EOD_DATA_END")

# ── Output ────────────────────────────────────────────────────────────────────
L = "=" * 118
print(L); print(f"  VWAP RETEST BACKTEST  {TODAY}  | lookback={S.VWAP_RETEST_LOOKBACK} min_bounce={S.VWAP_MIN_BOUNCE_PTS} "
               f"| SL mode={'SWING->ATR' if S.USE_SWING_SL else 'ATR'} RR={S.SPOT_ATR_TARGET_RR} "
               f"TSL ATR x{S.TSL_ATR_TRAIL_MULT} | qty={S.QUANTITY}"); print(L)
print(f"\nALL RAW VWAP SIGNALS ({len(signals)})")
print(f"{'Time':5}  {'Signal':7}  {'Close':>9}  {'VWAP':>9}  {'Dist':>7}  {'Status':24}  Reason")
print("-" * 118)
for s in signals:
    print(f"{s['time']:5}  {s['signal']:7}  {s['close']:>9.2f}  {s['vwap']:>9.2f}  {s['dist']:>+7.1f}  "
          f"{s['status']:24}  {s['reason'][:60]}")

print(f"\nTRADES ({len(trades)})")
tot = 0
for t in trades:
    tot += t["pnl_rs"]
    print("-" * 118)
    print(f" #{t['n']} {t['signal']}  {t['symbol']}  entry {t['entry_time']} @ {t['entry']:.2f}  (SENSEX {t['sensex']:.2f})")
    print(f"    Risk [{t['sl_mode']}]: SL {t['sl_pts']} pts -> stop {t['init_stop']:.2f} | Target {t['tgt_pts']} pts -> "
          f"{t['init_target']:.2f} | BE trigger +{t['be_pts']} | Trail step {t['trail_pts']}")
    print(f"    Peak {t['peak']:.2f} (MFE +{t['mfe_pts']:.2f}) | BE hit {t['be_hit']} | trail steps {t['trail_steps']} | "
          f"final stop {t['final_stop']:.2f}")
    print(f"    EXIT {t['exit_time']} @ {t['exit_px']:.2f}  reason={t['exit_reason']}  "
          f"P&L {t['pnl_pts']:+.2f} pts = Rs {t['pnl_rs']:+.2f}")
print(L)
w = sum(1 for t in trades if t["pnl_rs"] > 0)
print(f"  TOTAL P&L: Rs {tot:+.2f}   |  {w}W / {len(trades) - w}L   |  "
      f"signals {len(signals)}, blocked {sum(1 for s in signals if s['status'] == 'BLOCKED')}")
print(L)

with open("_vwap_signals_today.csv", "w", newline="") as f:
    wr = csv.DictWriter(f, fieldnames=list(signals[0].keys()) if signals else ["time"]); wr.writeheader(); wr.writerows(signals)
cols = ["n", "signal", "symbol", "entry_time", "sensex", "entry", "qty", "sl_mode", "sl_pts", "be_pts", "trail_pts",
        "tgt_pts", "init_stop", "init_target", "peak", "mfe_pts", "be_hit", "trail_steps", "final_stop",
        "exit_time", "exit_px", "exit_reason", "pnl_pts", "pnl_rs"]
with open("_vwap_trades_today.csv", "w", newline="") as f:
    wr = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); wr.writeheader(); wr.writerows(trades)
print("Saved: _vwap_signals_today.csv, _vwap_trades_today.csv")
