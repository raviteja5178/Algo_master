"""
What-if analysis: replay today's 5 trades with new parameters.
  MAX_SL_PCT:        0.35 → 0.50
  TSL_ATR_TRAIL_MULT: 0.5 → 1.0
  TSL_ATR_PERIOD:       5 → 14

For each trade we show:
  - OLD initial SL  vs  NEW initial SL
  - OLD TSL trail   vs  NEW TSL trail
  - Whether the trade would have survived to a better exit
"""

import sqlite3, json, os

# ── Trade data from today (from _today_entries output) ─────────────────────
# (entry, atr_at_entry, sl_pts_old, tsl_pts_old, exit_price, highest_ltp_approx)
trades = [
    # name,           entry,  atr,    sl_old, tsl_old, exit_px, notes
    ("T1 71900PE PE_VWAP", 181.4,  86.41,  63.5,  19.05, 209.1,  "Stopped 12:32"),
    ("T2 71800PE PE",      176.3, 102.49,  61.7,  18.5,  184.8,  "Stopped 12:40"),
    ("T3 71700PE PE",      152.5,  77.63,  53.4,  16.0,  165.6,  "Stopped 13:00 (50s!)"),
    ("T4 71600PE PE_VWAP", 128.2,  78.05,  44.85, 13.45, 153.35, "Stopped 14:01"),
    ("T5 71500PE PE",      125.0,  74.12,  43.75, 13.1,  138.35, "Stopped 14:22"),
]

ATM_DELTA    = 0.4
TARGET_RR    = 1.5
TRAIL_RR     = 0.3   # trail = sl × 0.3
BE_RR        = 0.5   # be    = sl × 0.5
QTY          = 20

# OLD params
OLD_MAX_SL_PCT        = 0.35
OLD_TSL_ATR_MULT      = 0.5
OLD_TSL_ATR_PERIOD    = 5   # (same ATR values in trade data)

# NEW params
NEW_MAX_SL_PCT        = 0.50
NEW_TSL_ATR_MULT      = 1.0
NEW_TSL_ATR_PERIOD    = 14  # ATR(14) ≈ smoother; use same value as approximation

def round_tick(v):
    return round(round(v / 0.05) * 0.05, 2)

def compute_sl(entry, atr, max_sl_pct, atr_mult_override=None):
    """Mode D swing SL was used for all trades today.
    We re-derive from stored sl_pts (swing-based) but apply the new ceiling."""
    return None  # handled per-trade below

sep = "-" * 76

print(sep)
title = "WHAT-IF: New params on today's 5 trades"
print(f"{title:^76}")
print(f"{'MAX_SL_PCT 0.35→0.50 | TSL_ATR_TRAIL_MULT 0.5→1.0 | TSL_ATR_PERIOD 5→14':^76}")
print(sep)

total_old_pnl = 0
total_new_pnl = 0

for name, entry, atr, sl_old, tsl_old, exit_px, note in trades:
    # ── OLD params ────────────────────────────────────────────────────────
    old_sl      = sl_old
    old_tsl     = tsl_old                          # stored tsl_pts
    old_be      = round_tick(old_sl * BE_RR)
    old_stop_px = entry + old_sl                   # PE: stop = entry + sl
    old_pnl     = round((exit_px - entry) * QTY, 0)

    # ── NEW params ────────────────────────────────────────────────────────
    # 1. Recalculate SL ceiling with new max_sl_pct=0.50
    #    The raw swing SL (before cap) = sl_old as recorded (already capped)
    #    We need to know what the uncapped swing SL was.
    #    From trade data: sl_pts are all capped by 0.35 ceiling.
    #    Raw swing SL (index pts → option) ≈ sl_old / 0.35 * entry  → but we
    #    can infer: if sl_old == ceiling → raw > ceiling.
    #    Simpler: recompute ceiling at 0.50 and use max(raw_swing, old_sl).
    #    Conservative: use new ceiling directly (worst-case, swing was huge).
    old_ceiling = round_tick(entry * OLD_MAX_SL_PCT)
    new_ceiling = round_tick(entry * NEW_MAX_SL_PCT)

    # If old SL was at the ceiling, the new SL = new ceiling
    was_capped = abs(old_sl - old_ceiling) < 1.0
    if was_capped:
        new_sl = new_ceiling
    else:
        new_sl = old_sl  # swing SL was within old ceiling, no change

    new_be  = round_tick(new_sl * BE_RR)
    new_stop_px = entry + new_sl

    # 2. Recalculate TSL trail distance with new ATR mult=1.0
    #    tsl_pts = ATR(period) × mult × delta × 0.4 (approximate, bot uses fixed trail_rr)
    #    The bot uses: trail = sl × trail_rr  for initial trail
    #    But TSL_ATR_TRAIL_MULT changes the *dynamic* trailing distance once TSL is active.
    #    Old dynamic trail = ATR × 0.5 × 0.4 = atr × 0.2
    #    New dynamic trail = ATR × 1.0 × 0.4 = atr × 0.4
    old_dyn_trail = round_tick(atr * OLD_TSL_ATR_MULT * ATM_DELTA)
    new_dyn_trail = round_tick(atr * NEW_TSL_ATR_MULT * ATM_DELTA)

    # ── Estimate new exit price ───────────────────────────────────────────
    # The exit was STOP_HIT. With a wider SL and wider TSL:
    # - If exit_px was the initial SL being hit (trade reversed right away):
    #   new_stop_px is higher → still stopped but at a worse price (more loss)
    # - If the option kept rising after entry (TSL activated) and then reversed:
    #   wider TSL = survives the dip = exits later at a better price
    #
    # Heuristic based on how the trade moved:
    # T3 was stopped 50 seconds after entry → initial SL hit (no TSL involvement)
    # T2 was stopped 5 min after entry → likely initial SL or quick reversal
    # T1, T4, T5 ran longer → TSL was active when stopped

    # For initial-SL scenarios: new exit = new_stop_px (worse)
    # For TSL scenarios: estimate new exit as exit_px + (new_dyn_trail - old_dyn_trail)
    # (the wider trail means we let it run further before the same reversal triggers)

    if "50s" in note:   # T3: instant reversal, initial SL hit
        new_exit = new_stop_px
        scenario = "Initial SL hit (wider SL = worse exit)"
    elif "12:40" in note:  # T2: 5 min, likely initial SL
        new_exit = new_stop_px
        scenario = "Initial SL hit (wider SL = worse exit)"
    else:  # T1, T4, T5: TSL was active
        new_exit = round_tick(exit_px + (new_dyn_trail - old_dyn_trail))
        scenario = "TSL active — wider trail survives dip"

    new_pnl = round((new_exit - entry) * QTY, 0)

    total_old_pnl += old_pnl
    total_new_pnl += new_pnl

    delta_pnl = new_pnl - old_pnl
    arrow = "▲" if delta_pnl > 0 else ("▼" if delta_pnl < 0 else "=")

    print(f"\n  {name}  ({note})")
    print(f"  {'':4}{'OLD':>30}  {'NEW':>30}")
    print(f"  {'SL pts':20} {old_sl:>10.1f} pts          {new_sl:>10.1f} pts")
    print(f"  {'SL ceiling':20} {old_ceiling:>10.1f} pts (35%)     {new_ceiling:>10.1f} pts (50%)")
    print(f"  {'Stop price':20} {old_stop_px:>10.2f}             {new_stop_px:>10.2f}")
    print(f"  {'Dyn TSL trail':20} {old_dyn_trail:>10.1f} pts          {new_dyn_trail:>10.1f} pts")
    print(f"  {'BE trigger':20} {old_be:>10.1f} pts          {new_be:>10.1f} pts")
    print(f"  {'Exit price':20} {exit_px:>10.2f}             {new_exit:>10.2f}")
    print(f"  {'PnL (qty=20)':20} {old_pnl:>+10.0f}             {new_pnl:>+10.0f}  {arrow} {delta_pnl:+.0f}")
    print(f"  Scenario: {scenario}")

print(f"\n{sep}")
print(f"  {'TOTAL PnL OLD':40} {total_old_pnl:>+8.0f}")
print(f"  {'TOTAL PnL NEW':40} {total_new_pnl:>+8.0f}  ({'+'if total_new_pnl>total_old_pnl else ''}{total_new_pnl-total_old_pnl:.0f})")
print(sep)
