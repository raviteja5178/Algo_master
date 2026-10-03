"""
Generate Oct 01 2026 Trading Report — Excel audit file
Parses bot.log for all Oct 1 signals, blocks, entries, and exits
"""
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
from openpyxl.utils import get_column_letter
from datetime import datetime

# ─────────────────────────────────────────────────────────
# DATA — extracted from bot.log for 2026-10-01
# ─────────────────────────────────────────────────────────

# Market Context
MARKET_DATE = "2026-10-01"
REGIME = "CHOPPY"
ATR_MULT = 0.8
MIN_PCT = 0.3
PDH = 73062.23
PDL = 72366.44

# ── SECTION 1: ACTUAL TRADES (order fills) ───────────────
# These were pre-market / carry-over orders filled at open
actual_trades = [
    {
        "order_id": "261001150061815",
        "fill_time": "09:15:30",
        "symbol": "SENSEX26O0173000CE",
        "option_type": "CE",
        "strike": 73000,
        "atm_underlying": 73000,
        "ltp_fill": 29.6,
        "qty": 40,
        "strategy": "Prior Session Order",
        "sl": None,
        "tsl": None,
        "target": None,
        "exit_time": "Pre-existing",
        "exit_reason": "Filled from prior session order (carry-over)",
        "status": "FILLED (carry-over)",
    },
    {
        "order_id": "261001150082911",
        "fill_time": "09:16:43",
        "symbol": "SENSEX26O0173600CE",
        "option_type": "CE",
        "strike": 73600,
        "atm_underlying": 73600,
        "ltp_fill": 9.0,
        "qty": 40,
        "strategy": "Prior Session Order",
        "sl": None,
        "tsl": None,
        "target": None,
        "exit_time": "—",
        "exit_reason": "Filled from prior session order (carry-over)",
        "status": "FILLED (carry-over)",
    },
    {
        "order_id": "261001150311809",
        "fill_time": "09:38:55",
        "symbol": "SENSEX26O0173600CE",
        "option_type": "CE",
        "strike": 73600,
        "atm_underlying": 73600,
        "ltp_fill": 6.6,
        "qty": 40,
        "strategy": "Prior Session Order",
        "sl": None,
        "tsl": None,
        "target": None,
        "exit_time": "—",
        "exit_reason": "Filled from prior session order (carry-over)",
        "status": "FILLED (carry-over)",
    },
    {
        "order_id": "261001150739910",
        "fill_time": "11:12:30",
        "symbol": "SENSEX26O0173600CE",
        "option_type": "CE",
        "strike": 73600,
        "atm_underlying": 73600,
        "ltp_fill": 4.6,
        "qty": 20,
        "strategy": "Prior Session Order",
        "sl": None,
        "tsl": None,
        "target": None,
        "exit_time": "—",
        "exit_reason": "Filled from prior session order (carry-over)",
        "status": "FILLED (carry-over)",
    },
    {
        "order_id": "261001150741131",
        "fill_time": "11:12:56",
        "symbol": "SENSEX26O0173600CE",
        "option_type": "CE",
        "strike": 73600,
        "atm_underlying": 73600,
        "ltp_fill": 4.65,
        "qty": 80,
        "strategy": "Prior Session Order",
        "sl": None,
        "tsl": None,
        "target": None,
        "exit_time": "—",
        "exit_reason": "Filled from prior session order (carry-over)",
        "status": "FILLED (carry-over)",
    },
]

# ── SECTION 2: BLOCKED ENTRIES (all signals that did not result in trade) ─────
blocked_entries = [
    # #  time       signal       candle_close  block_type            block_detail                                    ai_score  ai_reason
    ("09:27:18", "EMA_PE",      72393.5,  "AI_BLOCK",       "ema9=—, ema21=—",                                     8,  "Option premium already up 80% from day low"),
    ("10:00:00", "EMA_CE",      72441.63, "SMART_EMA_GAP",  "ema9=72395.85, ema21=72463.6, gap=-67.76, req=10",    None, "EMA9 < EMA21 — not bullish alignment"),
    ("10:05:00", "EMA_CE",      72515.88, "SMART_EMA_GAP",  "ema9=72419.85, ema21=72468.33, gap=-48.47, req=10",   None, "EMA9 < EMA21"),
    ("10:15:00", "EMA_PE_NATR", 72447.55, "SMART_SLOPE",    "ema9_now=72435.5, ema9_prev=72432.49",                None, "EMA9 not falling for PE"),
    ("10:25:00", "EMA_PE_VWAP", 72398.27, "AI_BLOCK",       "Squeeze bypass triggered (3 consec candles)",         8,  "Option premium already up 80% from day low"),
    ("10:35:00", "EMA_CE",      72477.77, "SMART_EMA_GAP",  "ema9=72432.72, ema21=72455.43, gap=-22.71, req=10",   None, "EMA9 < EMA21"),
    ("10:50:00", "EMA_PE_VWAP", 72411.65, "SMART_BODY",     "body=4.78, atr=80.83, required=28.29",                None, "Candle body too small"),
    ("10:55:00", "EMA_CE_VWAP", 72420.09, "SMART_BODY",     "body=6.52, atr=80.63, required=28.22",                None, "Candle body too small"),
    ("11:05:00", "EMA_PE_VWAP", 72375.1,  "AI_BLOCK",       "ema9=—, ema21=—",                                     8,  "Option premium already up 80% from day low"),
    ("11:10:00", "EMA_PE_VWAP", 72333.01, "AI_BLOCK",       "ema9=—, ema21=—",                                     8,  "Option premium already up 80% from day low"),
    ("11:25:00", "EMA_PE_PDHL", 72323.6,  "AI_BLOCK",       "close=72323.6 < pdl=72366.44",                        8,  "Option premium already up 80% from day low"),
    ("11:45:00", "EMA_CE",      72429.56, "SMART_EMA_GAP",  "ema9=72385.64, ema21=72406.08, gap=-20.44, req=10",   None, "EMA9 < EMA21"),
    ("11:50:00", "EMA_PE_VWAP", 72343.61, "AI_BLOCK",       "ema9=—, ema21=—",                                     8,  "Option premium already up 80% from day low"),
    ("12:30:00", "EMA_PE",      72066.57, "SMART_BODY",     "body=18.9, atr=87.85, required=30.75",                None, "Candle body too small"),
    ("12:45:00", "EMA_PE",      71964.42, "AI_BLOCK",       "ema9=—, ema21=—",                                     8,  "Option premium already up 80% from day low"),
    ("13:27:00", "EMA_PE",      71899.94, "AI_BLOCK",       "ema9=—, ema21=—",                                     8,  "Option premium already up 80% from day low"),
    ("13:30:00", "EMA_PE",      71600.0,  "SMART_BODY",     "body=34.73, atr=105.62, required=36.97 (squeeze bypass tried)", None, "Body slightly below threshold"),
    ("13:45:01", "EMA_PE_VWAP", 71535.92, "AI_BLOCK",       "Squeeze bypass (3 consec) + vwap=71596.49",           6,  "Lack of clear momentum and EMA alignment"),
    ("14:00:01", "EMA_PE_VWAP", 71389.62, "AI_BLOCK",       "Squeeze bypass (3 consec) + vwap=71524.61",           6,  "Choppy market, no clear trend direction"),
    ("14:05:00", "EMA_PE_VWAP", 71308.49, "AI_BLOCK",       "Squeeze bypass (3 consec) + vwap=71491.79",           6,  "Choppy market, no clear trend direction"),
    ("14:15:01", "EMA_CE_VWAP", 71552.18, "SMART_EMA_GAP",  "ema9=71512.73, ema21=71663.75, gap=-151.03, req=10",  None, "EMA9 < EMA21 — bearish alignment"),
    ("14:20:01", "EMA_PE_NATR", 71464.63, "SMART_EMA_GAP",  "gap_now=-142.81, gap_prev=-151.32 (shrinking)",       None, "EMA gap not widening for PE"),
    ("15:11:12", "EMA_CE_VWAP", 71564.29, "SMART_EMA_GAP",  "ema9=71511.39, ema21=71624.93, gap=-113.54, req=10",  None, "EMA9 < EMA21"),
    ("15:15:00", "EMA_CE_VWAP", 72010.13, "SMART_BODY",     "body=33.14, atr=130.79, required=45.77 (squeeze bypass tried)", None, "Body below required for ATR regime"),
]

# ─────────────────────────────────────────────────────────
# BUILD EXCEL
# ─────────────────────────────────────────────────────────

wb = openpyxl.Workbook()

# ── COLOURS ──
HDR_FILL   = PatternFill("solid", fgColor="1F3864")   # dark navy
SUB_FILL   = PatternFill("solid", fgColor="2E75B6")   # mid blue
ALT_FILL   = PatternFill("solid", fgColor="DEEAF1")   # light blue alt row
RED_FILL   = PatternFill("solid", fgColor="FFD7D7")
YEL_FILL   = PatternFill("solid", fgColor="FFF2CC")
GRN_FILL   = PatternFill("solid", fgColor="E2EFDA")
WHITE      = PatternFill("solid", fgColor="FFFFFF")
CARRY_FILL = PatternFill("solid", fgColor="F4E6FF")   # purple-ish

HDR_FONT  = Font(bold=True, color="FFFFFF", size=11)
SUB_FONT  = Font(bold=True, color="FFFFFF", size=10)
BOLD      = Font(bold=True, size=10)
NORM      = Font(size=10)
LINK_FONT = Font(bold=True, color="1F3864", size=14)

thin = Side(style="thin", color="AAAAAA")
med  = Side(style="medium", color="4472C4")
THIN_BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
MED_BORDER  = Border(left=med, right=med, top=med, bottom=med)

def set_hdr(ws, row, col, val, fill=None, font=None, align="center"):
    c = ws.cell(row=row, column=col, value=val)
    c.fill  = fill  or HDR_FILL
    c.font  = font  or HDR_FONT
    c.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)
    c.border = THIN_BORDER
    return c

def set_cell(ws, row, col, val, fill=None, font=None, align="center", fmt=None):
    c = ws.cell(row=row, column=col, value=val)
    c.fill  = fill or WHITE
    c.font  = font or NORM
    c.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)
    c.border = THIN_BORDER
    if fmt:
        c.number_format = fmt
    return c

# ═══════════════════════════════════════════════
# SHEET 1: Summary / Cover
# ═══════════════════════════════════════════════
ws1 = wb.active
ws1.title = "Summary"
ws1.column_dimensions["A"].width = 30
ws1.column_dimensions["B"].width = 45

ws1.merge_cells("A1:B1")
c = ws1["A1"]
c.value = "SENSEX Auto-Trader — Audit Report"
c.font  = Font(bold=True, color="1F3864", size=16)
c.alignment = Alignment(horizontal="center", vertical="center")
c.fill = PatternFill("solid", fgColor="DEEAF1")
ws1.row_dimensions[1].height = 36

def kv(ws, r, k, v, vfill=None):
    set_cell(ws, r, 1, k, fill=PatternFill("solid", fgColor="E2EFDA"), font=BOLD, align="left")
    set_cell(ws, r, 2, v, fill=vfill or WHITE, align="left")

kv(ws1, 2, "Date", MARKET_DATE)
kv(ws1, 3, "Market Regime", f"{REGIME}  (ATR mult={ATR_MULT}, min_pct={MIN_PCT})")
kv(ws1, 4, "PDH (Prev Day High)", f"₹{PDH:,.2f}")
kv(ws1, 5, "PDL (Prev Day Low)",  f"₹{PDL:,.2f}")
kv(ws1, 6, "Total Signals Fired", 24)
kv(ws1, 7, "Signals Blocked",     24)
kv(ws1, 8, "New Live Trades",     "0  (all fills were carry-over orders)")
kv(ws1, 9, "Carry-over Fills",    5)
kv(ws1,10, "Net P&L (live)",      "N/A — no strategy-initiated trades on this day")

ws1.merge_cells("A12:B12")
c = ws1["A12"]
c.value = "ℹ️  All 24 signals on Oct 01 were BLOCKED — no new strategy entries were made. "\
           "5 order fills relate to carry-over limit orders placed from a prior session."
c.font = Font(italic=True, size=10, color="595959")
c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
ws1.row_dimensions[12].height = 48

# ═══════════════════════════════════════════════
# SHEET 2: Carry-Over Order Fills
# ═══════════════════════════════════════════════
ws2 = wb.create_sheet("Carry-Over Fills")
headers = ["Order ID","Fill Time","Symbol","Type","Strike","ATM","Entry LTP","Qty",
           "Strategy","SL","TSL","Target","Exit Time","Exit Reason","Status"]
col_w   = [22, 12, 24, 8, 10, 10, 12, 8, 22, 10, 10, 10, 16, 35, 22]

ws2.merge_cells(f"A1:{get_column_letter(len(headers))}1")
c = ws2["A1"]
c.value = "Carry-Over Order Fills — 2026-10-01"
c.font  = Font(bold=True, color="FFFFFF", size=12)
c.fill  = PatternFill("solid", fgColor="7030A0")
c.alignment = Alignment(horizontal="center", vertical="center")
ws2.row_dimensions[1].height = 28

for ci, (h, w) in enumerate(zip(headers, col_w), start=1):
    set_hdr(ws2, 2, ci, h, fill=PatternFill("solid", fgColor="7030A0"))
    ws2.column_dimensions[get_column_letter(ci)].width = w

for ri, t in enumerate(actual_trades, start=3):
    fill = CARRY_FILL if ri % 2 == 0 else WHITE
    row_data = [
        t["order_id"], t["fill_time"], t["symbol"], t["option_type"],
        t["strike"], t["atm_underlying"], t["ltp_fill"], t["qty"],
        t["strategy"],
        t["sl"] or "—", t["tsl"] or "—", t["target"] or "—",
        t["exit_time"], t["exit_reason"], t["status"],
    ]
    for ci, val in enumerate(row_data, start=1):
        set_cell(ws2, ri, ci, val, fill=fill)

# ═══════════════════════════════════════════════
# SHEET 3: Blocked Entries (main audit sheet)
# ═══════════════════════════════════════════════
ws3 = wb.create_sheet("Blocked Entries")

headers3 = ["#","Signal Time","Strategy","Signal Type","Candle Close","Block Layer",
            "Block Detail","AI Score","AI Reason","Action"]
col_w3   = [5, 12, 18, 16, 14, 22, 48, 10, 45, 14]

ws3.merge_cells(f"A1:{get_column_letter(len(headers3))}1")
c = ws3["A1"]
c.value = "All Blocked Entry Signals — 2026-10-01  (24 Signals, 0 Entries)"
c.font  = Font(bold=True, color="FFFFFF", size=12)
c.fill  = PatternFill("solid", fgColor="C00000")
c.alignment = Alignment(horizontal="center", vertical="center")
ws3.row_dimensions[1].height = 28

for ci, (h, w) in enumerate(zip(headers3, col_w3), start=1):
    set_hdr(ws3, 2, ci, h, fill=PatternFill("solid", fgColor="C00000"))
    ws3.column_dimensions[get_column_letter(ci)].width = w

BLOCK_FILLS = {
    "AI_BLOCK":         PatternFill("solid", fgColor="FFD7D7"),   # red tint
    "SMART_EMA_GAP":    PatternFill("solid", fgColor="FFF2CC"),   # yellow tint
    "SMART_BODY":       PatternFill("solid", fgColor="DEEBF7"),   # blue tint
    "SMART_SLOPE":      PatternFill("solid", fgColor="E2EFDA"),   # green tint
    "SMART_EMA_GAP":    PatternFill("solid", fgColor="FFF2CC"),
}

for ri, entry in enumerate(blocked_entries, start=1):
    t, strat, close, blk, detail, score, reason = entry
    fill = BLOCK_FILLS.get(blk, WHITE)
    row_data = [
        ri, t, strat, strat.split("_")[1] if "_" in strat else strat,
        close, blk, detail,
        score if score else "N/A",
        reason, "BLOCKED"
    ]
    actual_row = ri + 2
    for ci, val in enumerate(row_data, start=1):
        c = set_cell(ws3, actual_row, ci, val, fill=fill)
    # colour the Action cell red
    ws3.cell(row=actual_row, column=10).fill = RED_FILL
    ws3.cell(row=actual_row, column=10).font = Font(bold=True, color="C00000", size=10)

# ═══════════════════════════════════════════════
# SHEET 4: Strategy Logic Reference
# ═══════════════════════════════════════════════
ws4 = wb.create_sheet("Strategy Logic")
ws4.column_dimensions["A"].width = 28
ws4.column_dimensions["B"].width = 70

ws4.merge_cells("A1:B1")
c = ws4["A1"]
c.value = "Strategy & Filter Logic Reference"
c.font  = Font(bold=True, color="FFFFFF", size=13)
c.fill  = HDR_FILL
c.alignment = Alignment(horizontal="center", vertical="center")
ws4.row_dimensions[1].height = 30

logic_rows = [
    ("MARKET CONTEXT", ""),
    ("Regime (Oct 01)", "CHOPPY — detected by AI LLM (Ollama local) at bot start"),
    ("ATR Multiplier", "0.8× (reduced SL/target in CHOPPY regime)"),
    ("Min Candle %", "0.3% min move required"),
    ("PDH", f"₹{PDH:,.2f}  (prev day high from 2026-09-30)"),
    ("PDL", f"₹{PDL:,.2f}  (prev day low from 2026-09-30)"),
    ("", ""),
    ("SIGNAL STRATEGIES", ""),
    ("EMA_CE", "CE entry signal: EMA9 crosses above EMA21 on 15m chart — bullish momentum"),
    ("EMA_PE", "PE entry signal: EMA9 crosses below EMA21 on 15m chart — bearish momentum"),
    ("EMA_CE_VWAP / EMA_PE_VWAP", "CE/PE signal confirmed when price closes above/below VWAP"),
    ("EMA_PE_NATR", "PE signal confirmed via NATR (Normalised ATR) — high volatility bearish move"),
    ("EMA_CE_NATR", "CE signal confirmed via NATR — high volatility bullish move"),
    ("EMA_PE_PDHL", "PE entry when price breaks below Previous Day Low (PDL)"),
    ("EMA_CE_ATR / EMA_PE_ATR", "Entry based on ATR breakout candles"),
    ("", ""),
    ("SMART ENTRY FILTERS (pre-AI gate)", ""),
    ("SMART_EMA_GAP", "Requires EMA9 > EMA21 for CE (EMA9 - EMA21 ≥ +10) or EMA9 < EMA21 for PE. "
                      "Blocks entry when EMAs are inverted vs trade direction."),
    ("SMART_SLOPE", "Requires EMA9 to be rising for CE or falling for PE. "
                    "Blocks if EMA9 slope is counter-directional."),
    ("SMART_BODY", "Candle body must be ≥ 35% of ATR. Blocks weak/doji candles."),
    ("SMART_EMA_GAP_SHRINKING", "For continuation trades: EMA gap must be widening. "
                                "Blocks if gap is converging (momentum fading)."),
    ("SQUEEZE_BYPASS", "If 3+ consecutive same-direction 5m candles: bypasses 15m/slope filters "
                       "but still subject to AI gate and body filter."),
    ("", ""),
    ("AI CONFIRMATION GATE (post smart-entry)", ""),
    ("AI Verdict", "Local LLM (Ollama) scores the trade 1–10. Score < threshold → SKIP."),
    ("Score = 8, blocked", "Blocked reason: 'Option premium already up 80% from day low' — "
                            "AI identified inflated option prices as risk"),
    ("Score = 6, blocked", "Blocked reason: 'Choppy market' / 'Lack of clear EMA alignment' — "
                            "AI confirmed regime uncertainty"),
    ("", ""),
    ("SL / TSL / TARGET LOGIC", ""),
    ("Initial SL", "ATR × regime_mult below entry LTP (CHOPPY: 0.8× ATR)"),
    ("TSL (Trailing SL)", "Once trade hits 1× ATR profit, SL trails at breakeven then 50% of move"),
    ("Target", "2× ATR from entry (CHOPPY regime softens this to 1.6× ATR)"),
    ("EOD Exit", "All positions force-closed at 15:15 IST"),
]

for ri, (k, v) in enumerate(logic_rows, start=2):
    if v == "" and k == "":
        ws4.row_dimensions[ri].height = 8
        continue
    if v == "":
        # section header row
        ws4.merge_cells(f"A{ri}:B{ri}")
        c = ws4.cell(row=ri, column=1, value=k)
        c.fill = SUB_FILL
        c.font = SUB_FONT
        c.alignment = Alignment(horizontal="left", vertical="center")
        c.border = THIN_BORDER
        ws4.row_dimensions[ri].height = 22
    else:
        set_cell(ws4, ri, 1, k, fill=PatternFill("solid", fgColor="E2EFDA"), font=BOLD, align="left")
        set_cell(ws4, ri, 2, v, align="left")
        ws4.row_dimensions[ri].height = 30

# ═══════════════════════════════════════════════
# SHEET 5: Block Type Legend
# ═══════════════════════════════════════════════
ws5 = wb.create_sheet("Legend")
ws5.column_dimensions["A"].width = 30
ws5.column_dimensions["B"].width = 60
ws5.column_dimensions["C"].width = 20

set_hdr(ws5, 1, 1, "Block Type")
set_hdr(ws5, 1, 2, "Description")
set_hdr(ws5, 1, 3, "Sheet Colour")

legend = [
    ("AI_BLOCK",              "Signal passed Smart Entry filters but AI LLM rejected it",        RED_FILL,  "🔴 Red tint"),
    ("SMART_EMA_GAP",         "EMA9 vs EMA21 gap is in wrong direction for trade",               YEL_FILL,  "🟡 Yellow tint"),
    ("SMART_BODY",            "Candle body < 35% of ATR (too weak/doji)",                        PatternFill("solid", fgColor="DEEBF7"), "🔵 Blue tint"),
    ("SMART_SLOPE",           "EMA9 slope not aligned with trade direction",                     GRN_FILL,  "🟢 Green tint"),
    ("SMART_EMA_GAP_SHRINKING","EMA gap narrowing — momentum fading",                            YEL_FILL,  "🟡 Yellow tint"),
    ("CARRY-OVER FILL",       "Order placed in prior session, filled on Oct 01 open",            CARRY_FILL,"🟣 Purple tint"),
]

for ri, (bt, desc, f, col_txt) in enumerate(legend, start=2):
    set_cell(ws5, ri, 1, bt, fill=f, font=BOLD, align="left")
    set_cell(ws5, ri, 2, desc, fill=WHITE, align="left")
    set_cell(ws5, ri, 3, col_txt, fill=f, align="center")

# ─── SAVE ────────────────────────────────────────────────
out = "oct01_2026_audit_report.xlsx"
wb.save(out)
print(f"✅  Report saved → {out}")
