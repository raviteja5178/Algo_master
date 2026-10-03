"""
ATR Copilot – Sep 1 2026  –  Option LTP Report
================================================
Shows ALL 7 signal candidates (FRESH + CONTINUATION).
For each:
  • Whether it fires under current rules or is blocked (and why)
  • What WOULD happen if the CONTINUATION block was lifted
  • All values in OPTION PREMIUM POINTS only (ATM LTP)
  • Full trade lifecycle: Entry LTP → SL → BE → TSL → Target → Exit
"""
import sys, os, math, warnings
sys.path.insert(0, os.path.dirname(__file__))
warnings.filterwarnings("ignore")

from datetime import timedelta, date as dt_date, datetime
from collections import deque

import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from broker.kite_client import get_kite
from market.candle_builder import Candle
from market.indicators import atr as calc_atr, ema as calc_ema
from strategies.atr_copilot_strategy import _compute_bands
from config import settings
from utils.time_utils import IST

# ── Config ─────────────────────────────────────────────────────────────────
ATR_P     = settings.ATR_COPILOT_PERIOD       # 5
EMA_P     = settings.ATR_COPILOT_EMA_PERIOD   # 21
MULT      = settings.ATR_COPILOT_BAND_MULT    # 3.0
BUFFER    = settings.ATR_COPILOT_BREAKOUT_BUFFER  # 0.0
SL_MULT   = settings.SPOT_ATR_SL_MULT        # 3.0
RR        = settings.SPOT_ATR_TARGET_RR      # 1.2
TRAIL_RR  = settings.SPOT_ATR_TRAIL_RR       # 0.5

TARGET_DATE    = dt_date(2026, 9, 1)
FORCE_EXIT     = (15, 15)
NO_ENTRY_AFTER = (15,  0)
SENSEX_TOKEN   = 265
EXPIRY_DATE    = dt_date(2026, 9, 5)
IV_ANNUAL      = 0.135
RISK_FREE      = 0.065
ATM_DELTA      = 0.4   # ATM option delta ≈ 0.4
ATM_STEP       = 100   # SENSEX strike step

# ── Black-Scholes ATM option price ─────────────────────────────────────────
def _bs_atm(spot: float, ts_ist: datetime) -> float:
    days_left = max((EXPIRY_DATE - ts_ist.date()).days, 0) or 0.5
    T = days_left / 365.0
    d1 = (IV_ANNUAL * math.sqrt(T)) / 2.0
    def N(x): return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))
    return round(spot * math.exp(-RISK_FREE * T) * N(d1) - spot * N(-d1), 2)

def _atm_strike(spot: float) -> int:
    return round(spot / ATM_STEP) * ATM_STEP

# ── Fetch live data ─────────────────────────────────────────────────────────
print("Connecting to Zerodha...", end=" ", flush=True)
kite = get_kite()
print("OK")
warm = TARGET_DATE - timedelta(days=14)
print(f"Fetching 5m SENSEX: {warm} → {TARGET_DATE}...", end=" ", flush=True)
raw = kite.historical_data(instrument_token=SENSEX_TOKEN,
    from_date=f"{warm} 09:15:00",
    to_date=f"{TARGET_DATE} 15:30:00",
    interval="5minute")

def mc(r):
    ts = IST.localize(r["date"]) if r["date"].tzinfo is None else r["date"].astimezone(IST)
    return Candle(timestamp=ts, open=float(r["open"]), high=float(r["high"]),
                  low=float(r["low"]), close=float(r["close"]), volume=0)

all_c = [mc(r) for r in raw if (r["date"].hour, r["date"].minute) >= (9, 15)]
print(f"{len(raw)} raw → {len(all_c)} usable")

# ── Collect ALL band-touch candidates on Sep 1 ─────────────────────────────
buf  = deque(maxlen=300)
min_c = EMA_P + ATR_P + 2
candidates = []

for candle in all_c:
    buf.append(candle); c5 = list(buf)
    ts_ist  = candle.timestamp.astimezone(IST)
    hhmm    = (ts_ist.hour, ts_ist.minute)
    if ts_ist.date() != TARGET_DATE: continue
    if len(c5) < min_c: continue

    atr_v = calc_atr(c5, ATR_P)[-1]
    if not atr_v: continue

    upper, lower = _compute_bands(c5, ATR_P, EMA_P, MULT)
    ub, ub_p = upper[-1], upper[-2]
    lb, lb_p = lower[-1], lower[-2]
    if None in (ub, ub_p, lb, lb_p): continue

    cl, prev_cl = candle.close, c5[-2].close
    buf_pts = round(BUFFER * atr_v, 2)
    sl_pts  = round(SL_MULT * atr_v, 2)
    be_pts  = round(sl_pts * 0.5, 2)
    tr_pts  = round(sl_pts * TRAIL_RR, 2)
    tgt_pts = round(sl_pts * RR, 2)

    for direction, band, band_p, sg in [("CE", ub, ub_p, 1), ("PE", lb, lb_p, -1)]:
        outside = (cl > band) if direction == "CE" else (cl < band)
        if not outside: continue

        is_pe      = direction == "PE"
        clearance  = round((cl - band) * sg, 2)
        is_cont    = (prev_cl > band_p) if direction == "CE" else (prev_cl < band_p)
        passes_buf = clearance >= buf_pts or BUFFER == 0

        # Current blocking rules
        block_cur = []
        if is_cont:       block_cur.append("CONTINUATION")
        if not passes_buf and BUFFER > 0: block_cur.append(f"BUFFER<{buf_pts:.1f}pts")
        if hhmm >= NO_ENTRY_AFTER: block_cur.append("AFTER 15:00")

        fires_current = not block_cur

        # Hypothetical: what if CONTINUATION block is lifted?
        block_no_cont = [b for b in block_cur if b != "CONTINUATION"]
        fires_no_cont = not block_no_cont

        # Option ATM pricing at entry
        atm_strike   = _atm_strike(cl)
        entry_ltp    = _bs_atm(cl, ts_ist)
        # Translate index SL/target/trail → option premium via delta
        opt_sl_pts   = round(sl_pts  * ATM_DELTA, 2)
        opt_tgt_pts  = round(tgt_pts * ATM_DELTA, 2)
        opt_be_pts   = round(be_pts  * ATM_DELTA, 2)
        opt_tr_pts   = round(tr_pts  * ATM_DELTA, 2)

        opt_sl_ltp   = round(entry_ltp - opt_sl_pts, 2)
        opt_tgt_ltp  = round(entry_ltp + opt_tgt_pts, 2)
        opt_be_ltp   = round(entry_ltp + opt_be_pts,  2)  # LTP when BE triggered

        symbol = f"SENSEX{ts_ist.strftime('%y%b').upper()}{atm_strike}{'PE' if is_pe else 'CE'}"

        candidates.append({
            "time":           ts_ist.strftime("%H:%M"),
            "ts_ist":         ts_ist,
            "direction":      direction,
            "touch_type":     "CONTINUATION" if is_cont else "FRESH",
            "fires_current":  fires_current,
            "fires_no_cont":  fires_no_cont,
            "block_current":  ", ".join(block_cur) if block_cur else "—  (fires)",
            "block_no_cont":  ", ".join(block_no_cont) if block_no_cont else "—  (fires)",
            "strategy":       f"ATR_COPILOT {'CE' if not is_pe else 'PE'}",
            # option levels
            "symbol":         symbol,
            "entry_ltp":      entry_ltp,
            "sl_ltp":         opt_sl_ltp,
            "be_ltp":         opt_be_ltp,
            "tgt_ltp":        opt_tgt_ltp,
            "tsl_step":       opt_tr_pts,
            # raw pts for simulation
            "sl_pts":         sl_pts,
            "be_pts":         be_pts,
            "tr_pts":         tr_pts,
            "tgt_pts":        tgt_pts,
            "is_pe":          is_pe,
            "sensex_cl":      cl,
            "atr5":           round(atr_v, 2),
            "clearance":      clearance,
        })

print(f"Candidates collected: {len(candidates)}")

# ── Simulate trade lifecycle for each candidate ─────────────────────────────
# We simulate each candidate INDEPENDENTLY (ignoring one-at-a-time rule)
# so the user can see what WOULD happen for every touch.

def simulate_trade(entry_ts_ist, is_pe, entry_ltp,
                   sl_pts, be_pts, tr_pts, tgt_pts):
    """
    Walk forward from entry_ts_ist through Sep 1 candles.
    Returns (exit_ltp, exit_reason, be_hit, tsl_steps, final_stop_ltp)
    Uses SENSEX candle OHLC converted to option premium via delta.
    """
    entry_cl = None
    for c in all_c:
        if c.timestamp.astimezone(IST) == entry_ts_ist:
            entry_cl = c.close
            break
    if entry_cl is None:
        return None, "NO_CANDLE", False, [], entry_ltp - sl_pts * ATM_DELTA

    # option target / sl in SENSEX pts
    tgt_idx   = round(entry_cl - tgt_pts, 2) if is_pe else round(entry_cl + tgt_pts, 2)
    sl_idx    = round(entry_cl + sl_pts,  2) if is_pe else round(entry_cl - sl_pts,  2)
    be_idx    = round(entry_cl - be_pts,  2) if is_pe else round(entry_cl + be_pts,  2)

    current_sl_idx = sl_idx
    be_hit         = False
    extreme        = entry_cl
    tsl_log        = []
    started        = False

    for c in all_c:
        ts = c.timestamp.astimezone(IST)
        hhmm = (ts.hour, ts.minute)
        if ts < entry_ts_ist: continue
        if ts == entry_ts_ist: started = True; continue
        if not started: continue

        # update extreme
        extreme = min(extreme, c.low) if is_pe else max(extreme, c.high)

        # check BE
        if not be_hit:
            if is_pe and c.low <= be_idx:
                be_hit = True
                current_sl_idx = entry_cl
                tsl_log.append(f"{ts.strftime('%H:%M')} BE → stop={entry_cl:.0f}")
            elif not is_pe and c.high >= be_idx:
                be_hit = True
                current_sl_idx = entry_cl
                tsl_log.append(f"{ts.strftime('%H:%M')} BE → stop={entry_cl:.0f}")

        # update TSL
        if be_hit:
            if is_pe:
                steps = int(((entry_cl - be_pts) - extreme) // tr_pts) if extreme < entry_cl - be_pts else 0
                nsl = entry_cl - steps * tr_pts
                if nsl < current_sl_idx:
                    current_sl_idx = round(nsl, 2)
                    tsl_log.append(f"{ts.strftime('%H:%M')} TSL→{current_sl_idx:.0f}")
            else:
                steps = int((extreme - (entry_cl + be_pts)) // tr_pts) if extreme > entry_cl + be_pts else 0
                nsl = entry_cl + steps * tr_pts
                if nsl > current_sl_idx:
                    current_sl_idx = round(nsl, 2)
                    tsl_log.append(f"{ts.strftime('%H:%M')} TSL→{current_sl_idx:.0f}")

        # check target
        if (not is_pe and c.high >= tgt_idx) or (is_pe and c.low <= tgt_idx):
            exit_idx = tgt_idx
            exit_ltp = round(entry_ltp + tgt_pts * ATM_DELTA, 2)
            return exit_ltp, "TARGET_HIT", be_hit, tsl_log, round(entry_ltp - (entry_cl - current_sl_idx) * ATM_DELTA if is_pe else entry_ltp - (current_sl_idx - entry_cl) * ATM_DELTA, 2)

        # check SL
        if (not is_pe and c.low <= current_sl_idx) or (is_pe and c.high >= current_sl_idx):
            sl_diff = abs(entry_cl - current_sl_idx)
            exit_ltp = round(entry_ltp - sl_diff * ATM_DELTA, 2)
            reason = "TRAILING_SL" if be_hit else "INITIAL_SL"
            return exit_ltp, reason, be_hit, tsl_log, round(entry_ltp - sl_diff * ATM_DELTA, 2)

        # EOD
        if hhmm >= FORCE_EXIT:
            eod_cl    = c.close
            idx_pnl   = (entry_cl - eod_cl) if is_pe else (eod_cl - entry_cl)
            exit_ltp  = round(entry_ltp + idx_pnl * ATM_DELTA, 2)
            cur_stop_ltp = round(entry_ltp - abs(entry_cl - current_sl_idx) * ATM_DELTA, 2)
            return exit_ltp, "EOD_EXIT", be_hit, tsl_log, cur_stop_ltp

    return None, "NO_EXIT", be_hit, tsl_log, round(entry_ltp - sl_pts * ATM_DELTA, 2)

# Run simulation for every candidate
for cand in candidates:
    exit_ltp, exit_reason, be_hit, tsl_log, final_stop = simulate_trade(
        cand["ts_ist"], cand["is_pe"],
        cand["entry_ltp"],
        cand["sl_pts"], cand["be_pts"], cand["tr_pts"], cand["tgt_pts"]
    )
    pnl = round(exit_ltp - cand["entry_ltp"], 2) if exit_ltp else None
    cand.update({
        "exit_ltp":    exit_ltp,
        "exit_reason": exit_reason,
        "be_hit":      be_hit,
        "tsl_log":     " → ".join(tsl_log) if tsl_log else "No TSL adjustments",
        "final_stop":  final_stop,
        "pnl_opt":     pnl,
    })

# ── Build Excel ────────────────────────────────────────────────────────────
wb = openpyxl.Workbook()

# Styles
C_BG      = "0D1117"
C_HDR     = "1F2937"
C_GREEN   = "14532D"
C_RED     = "7F1D1D"
C_AMBER   = "3B2A00"
C_CONT    = "2A1F00"
C_BLUE    = "1E3A5F"
C_FIRED   = "0F2E1A"
T_WHITE   = "E2E8F0"
T_GREEN   = "4ADE80"
T_RED     = "F87171"
T_AMBER   = "FCD34D"
T_CYAN    = "22D3EE"
T_BLUE    = "60A5FA"
T_MUTED   = "6B7A99"

def fill(hex_c): return PatternFill("solid", fgColor=hex_c)
def font(hex_c, bold=False, sz=9): return Font(color=hex_c, bold=bold, size=sz)
thin = Side(style="thin", color="374151")
bdr  = Border(left=thin, right=thin, top=thin, bottom=thin)
ctr  = Alignment(horizontal="center", vertical="center", wrap_text=False)
lft  = Alignment(horizontal="left",   vertical="center", wrap_text=False)
wlft = Alignment(horizontal="left",   vertical="center", wrap_text=True)

def cell(ws, r, c, v, bg=C_BG, fg=T_WHITE, bold=False, sz=9, align=None, bdr_on=True):
    cel = ws.cell(row=r, column=c, value=v)
    cel.fill = fill(bg)
    cel.font = font(fg, bold, sz)
    cel.alignment = align or ctr
    if bdr_on: cel.border = bdr
    return cel

# ════════════════════════════════════════════════════════════════════════════
# SHEET 1:  CURRENT RULES  (with CONTINUATION block active)
# ════════════════════════════════════════════════════════════════════════════
ws1 = wb.active
ws1.title = "Current Rules"
ws1.sheet_view.showGridLines = False
ws1.freeze_panes = "A3"

HDR = [
    ("A",  "Time",           8),
    ("B",  "Dir",            5),
    ("C",  "Strategy",      18),
    ("D",  "Touch Type",    14),
    ("E",  "Status",        12),
    ("F",  "Block Reason",  32),
    ("G",  "Symbol",        26),
    ("H",  "Entry LTP (₹)", 13),
    ("I",  "SL LTP (₹)",    12),
    ("J",  "BE LTP (₹)",    12),
    ("K",  "Target LTP (₹)",13),
    ("L",  "TSL Step (₹)",  12),
    ("M",  "Exit LTP (₹)",  12),
    ("N",  "Exit Reason",   16),
    ("O",  "BE Hit?",        9),
    ("P",  "TSL History",   40),
    ("Q",  "P&L (₹ opt)",   12),
]

ws1.row_dimensions[1].height = 24
title = (f"ATR Copilot  |  Sep 1 2026  |  CURRENT RULES  (CONTINUATION blocked)  |  "
         f"EMA{EMA_P} ± ATR{ATR_P}×{MULT}  |  Buffer={BUFFER}  |  "
         f"SL=ATR×{SL_MULT}  RR={RR}  Trail={TRAIL_RR}×SL  |  "
         f"Expiry {EXPIRY_DATE}  IV {IV_ANNUAL*100:.0f}%  Δ={ATM_DELTA}")
cell(ws1, 1, 1, title, bg=C_HDR, fg=T_BLUE, bold=True, sz=11, align=lft, bdr_on=False)
ws1.merge_cells(f"A1:{get_column_letter(len(HDR))}1")

ws1.row_dimensions[2].height = 18
for i, (col, label, width) in enumerate(HDR, 1):
    cell(ws1, 2, i, label, bg=C_HDR, fg=T_WHITE, bold=True, sz=10)
    ws1.column_dimensions[col].width = width

for ri, cand in enumerate(candidates, 3):
    fires  = cand["fires_current"]
    is_pe  = cand["is_pe"]
    is_cont = cand["touch_type"] == "CONTINUATION"
    bg = C_FIRED if fires else (C_CONT if is_cont else C_AMBER)
    pnl = cand.get("pnl_opt")
    pnl_str = (f"+{pnl:.2f}" if pnl and pnl >= 0 else f"{pnl:.2f}") if pnl is not None else "—"
    pnl_fg  = T_GREEN if pnl and pnl > 0 else (T_RED if pnl and pnl < 0 else T_MUTED)

    row_vals = [
        (cand["time"],        T_CYAN,  False),
        (cand["direction"],   T_GREEN if not is_pe else T_RED, True),
        (cand["strategy"],    T_WHITE, False),
        (cand["touch_type"],  T_AMBER if is_cont else T_GREEN, False),
        ("✅ FIRES" if fires else "❌ BLOCKED", T_GREEN if fires else T_RED, True),
        (cand["block_current"], T_AMBER if not fires else T_MUTED, False),
        (cand["symbol"],       T_CYAN,  False),
        (cand["entry_ltp"],    T_WHITE, True),
        (cand["sl_ltp"],       T_RED,   False),
        (cand["be_ltp"],       T_AMBER, False),
        (cand["tgt_ltp"],      T_GREEN, False),
        (cand["tsl_step"],     T_CYAN,  False),
        (cand["exit_ltp"] if fires else "—",   pnl_fg if fires else T_MUTED, fires),
        (cand["exit_reason"] if fires else "—", T_MUTED, False),
        ("✅" if cand.get("be_hit") else "❌",   T_GREEN if cand.get("be_hit") else T_RED, False),
        (cand["tsl_log"] if fires else "—",     T_MUTED, False),
        (pnl_str if fires else "—",             pnl_fg,  True),
    ]
    for ci, (val, fg, bold) in enumerate(row_vals, 1):
        aln = wlft if ci == 16 else ctr
        cell(ws1, ri, ci, val, bg=bg, fg=fg, bold=bold, align=aln)

# ════════════════════════════════════════════════════════════════════════════
# SHEET 2:  NO CONTINUATION BLOCK  (what if all FRESH+CONT are allowed?)
# ════════════════════════════════════════════════════════════════════════════
ws2 = wb.create_sheet("No Continuation Block")
ws2.sheet_view.showGridLines = False
ws2.freeze_panes = "A3"

ws2.row_dimensions[1].height = 24
title2 = (f"ATR Copilot  |  Sep 1 2026  |  CONTINUATION BLOCK REMOVED  (all FRESH + CONT allowed)  |  "
          f"EMA{EMA_P} ± ATR{ATR_P}×{MULT}  |  Buffer={BUFFER}  |  "
          f"SL=ATR×{SL_MULT}  RR={RR}  Trail={TRAIL_RR}×SL  |  "
          f"Expiry {EXPIRY_DATE}  IV {IV_ANNUAL*100:.0f}%  Δ={ATM_DELTA}")
cell(ws2, 1, 1, title2, bg=C_HDR, fg=T_BLUE, bold=True, sz=11, align=lft, bdr_on=False)
ws2.merge_cells(f"A1:{get_column_letter(len(HDR))}1")

ws2.row_dimensions[2].height = 18
for i, (col, label, width) in enumerate(HDR, 1):
    cell(ws2, 2, i, label, bg=C_HDR, fg=T_WHITE, bold=True, sz=10)
    ws2.column_dimensions[col].width = width

# For sheet 2 we simulate one-at-a-time WITH continuation allowed
# Track which trades are blocked only by TRADE_OPEN
open_until = None
for ri, cand in enumerate(candidates, 3):
    fires  = cand["fires_no_cont"]
    is_pe  = cand["is_pe"]
    is_cont = cand["touch_type"] == "CONTINUATION"
    bg = C_FIRED if fires else (C_CONT if is_cont else C_AMBER)
    pnl = cand.get("pnl_opt")
    pnl_str = (f"+{pnl:.2f}" if pnl and pnl >= 0 else f"{pnl:.2f}") if pnl is not None else "—"
    pnl_fg  = T_GREEN if pnl and pnl > 0 else (T_RED if pnl and pnl < 0 else T_MUTED)
    block_lbl = cand["block_no_cont"]

    row_vals = [
        (cand["time"],         T_CYAN,  False),
        (cand["direction"],    T_GREEN if not is_pe else T_RED, True),
        (cand["strategy"],     T_WHITE, False),
        (cand["touch_type"],   T_AMBER if is_cont else T_GREEN, False),
        ("✅ FIRES" if fires else "❌ BLOCKED", T_GREEN if fires else T_RED, True),
        (block_lbl,            T_AMBER if not fires else T_MUTED, False),
        (cand["symbol"],       T_CYAN,  False),
        (cand["entry_ltp"],    T_WHITE, True),
        (cand["sl_ltp"],       T_RED,   False),
        (cand["be_ltp"],       T_AMBER, False),
        (cand["tgt_ltp"],      T_GREEN, False),
        (cand["tsl_step"],     T_CYAN,  False),
        (cand["exit_ltp"] if fires else "—",    pnl_fg if fires else T_MUTED, fires),
        (cand["exit_reason"] if fires else "—", T_MUTED, False),
        ("✅" if cand.get("be_hit") else "❌",   T_GREEN if cand.get("be_hit") else T_RED, False),
        (cand["tsl_log"] if fires else "—",     T_MUTED, False),
        (pnl_str if fires else "—",             pnl_fg,  True),
    ]
    for ci, (val, fg, bold) in enumerate(row_vals, 1):
        aln = wlft if ci == 16 else ctr
        cell(ws2, ri, ci, val, bg=bg, fg=fg, bold=bold, align=aln)

# ════════════════════════════════════════════════════════════════════════════
# SHEET 3: LEGEND
# ════════════════════════════════════════════════════════════════════════════
ws3 = wb.create_sheet("Legend")
ws3.sheet_view.showGridLines = False
ws3.column_dimensions["A"].width = 22
ws3.column_dimensions["B"].width = 60

legend_rows = [
    ("FIELD", "EXPLANATION", True),
    ("", "", False),
    ("Entry LTP (₹)",     f"Estimated ATM option premium at entry time — Black-Scholes ATM approx (IV={IV_ANNUAL*100:.0f}%, Expiry {EXPIRY_DATE})", False),
    ("SL LTP (₹)",        f"Entry LTP − (index SL pts × Δ{ATM_DELTA}) — stop loss level in option premium", False),
    ("BE LTP (₹)",        f"Entry LTP + (index BE pts × Δ{ATM_DELTA}) — break-even trigger in option premium. When hit, SL moves to entry LTP", False),
    ("Target LTP (₹)",    f"Entry LTP + (index target pts × Δ{ATM_DELTA}) — take profit level in option premium", False),
    ("TSL Step (₹)",      f"Trail step in option premium pts = index trail pts × Δ{ATM_DELTA}. After BE: SL trails up in these steps as premium rises", False),
    ("Exit LTP (₹)",      "Estimated option premium at exit. Computed from SENSEX OHLC × Δ for TARGET/SL exits; EOD uses closing index", False),
    ("P&L (₹ opt)",       "Exit LTP − Entry LTP. Positive = profit, Negative = loss. Per lot = this × lot size (20 qty × 1 = 20 units)", False),
    ("", "", False),
    ("TOUCH TYPE", "", True),
    ("FRESH",             "Previous 5m candle was INSIDE the band. This is a new breakout — the current signal rule allows entry", False),
    ("CONTINUATION",      "Previous 5m candle was ALREADY outside the band. Current rule blocks this to avoid chasing. Sheet 2 removes this block", False),
    ("", "", False),
    ("BLOCK REASON", "", True),
    ("CONTINUATION",      "Previous candle was already outside the band — the 'no chasing' rule blocks re-entry", False),
    ("TRADE_OPEN",        "A trade is already open from an earlier signal — one-at-a-time rule applies", False),
    ("AFTER 15:00",       "No new entries allowed after 15:00 IST", False),
    ("", "", False),
    ("SIMULATION NOTES", "", True),
    ("Independent sim",   "Each candidate is simulated independently to show what would happen if that specific trade was taken", False),
    ("Delta approx",      f"Δ={ATM_DELTA} (ATM delta). Index move of 100 pts → option moves ~₹{100*ATM_DELTA:.0f}. Actual delta varies with time/IV", False),
    ("BS ATM approx",     f"Price = S × e^(-rT) × N(d1) − S × N(−d1); d1 = σ√T/2 at ATM. IV={IV_ANNUAL*100:.1f}%, r={RISK_FREE*100:.1f}%", False),
    ("SL=ATR×3.0",        f"Index SL = Wilder ATR(5) × {SL_MULT}. Option SL = index SL × Δ{ATM_DELTA}", False),
    ("Trail=50% of SL",   f"Trail step = SL × {TRAIL_RR} — aggressive TSL locks profit fast after break-even", False),
]

cell(ws3, 1, 1, "ATR Copilot Signal Report — Legend & Methodology", bg=C_HDR, fg=T_BLUE, bold=True, sz=12, align=lft, bdr_on=False)
ws3.merge_cells("A1:B1")
for ri, (field, expl, bold) in enumerate(legend_rows, 2):
    bg = C_HDR if bold and field else C_BG
    cell(ws3, ri, 1, field, bg=bg, fg=T_CYAN if bold else T_WHITE,   bold=bold, align=lft)
    cell(ws3, ri, 2, expl,  bg=bg, fg=T_AMBER if bold else T_MUTED,  bold=False, align=wlft)
    ws3.row_dimensions[ri].height = 20

# ── Save ──────────────────────────────────────────────────────────────────
out = "_sep01_option_ltp_report.xlsx"
wb.save(out)
print(f"\n✅  Saved → {out}")
print(f"   Sheet 1 — Current Rules:       {len(candidates)} signals ({sum(1 for c in candidates if c['fires_current'])} fire, {sum(1 for c in candidates if not c['fires_current'])} blocked)")
print(f"   Sheet 2 — No Cont Block:       {len(candidates)} signals ({sum(1 for c in candidates if c['fires_no_cont'])} fire, {sum(1 for c in candidates if not c['fires_no_cont'])} blocked)")
print(f"   Sheet 3 — Legend")

# Console preview
print()
print("="*110)
print(f"  {'#':2}  {'Time':5}  {'Dir':3}  {'Type':13}  {'Status':8}  {'Entry':>7}  {'SL':>7}  {'Target':>7}  {'Exit':>7}  {'Reason':15}  {'P&L':>8}  Block")
print("-"*110)
for i, c in enumerate(candidates, 1):
    fires = c['fires_current']
    pnl = c.get('pnl_opt') if fires else None
    pnl_s = f"{pnl:+.0f}" if pnl is not None else "—"
    el   = f"{c['entry_ltp']:.0f}"
    sl   = f"{c['sl_ltp']:.0f}"
    tg   = f"{c['tgt_ltp']:.0f}"
    ex   = f"{c['exit_ltp']:.0f}" if fires and c.get('exit_ltp') else "—"
    er   = c['exit_reason'] if fires else "—"
    st   = "FIRES" if fires else "BLOCKED"
    blk  = c['block_current']
    print(f"  {i:2}  {c['time']:5}  {c['direction']:3}  {c['touch_type']:13}  {st:8}  {el:>7}  {sl:>7}  {tg:>7}  {ex:>7}  {er:15}  {pnl_s:>8}  {blk}")
print("="*110)
