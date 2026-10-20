"""
Parameter-sensitivity sweep around the LIVE pivot configuration.

Research only.  One parameter is changed at a time (all others stay at the live
.env values) and the full pivot backtest is re-run, so a result that only exists
at one exact setting shows up as a spike rather than a plateau.

Metrics are reported in index POINTS as well as R, because several parameters
(sustain candles, SL buffer, min room) change the stop size and therefore the
meaning of "R".

Columns
    n, win%, avgR, avgPts, totPts     headline results
    exTop5Pts                          avg points per trade without the 5 best trades
    H1Pts / H2Pts                      avg points per trade in each half of the sample
    dTot%                              change in total points vs the live baseline
    flag                               '!' = total points change > 35% or sign flips
                                       '~' = a half-sample is negative

Usage
    python -m research.pivot_sensitivity
    python -m research.pivot_sensitivity --workers 4 --only trail,bounce
"""

from __future__ import annotations

import argparse
import logging
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from config import settings
from research.cpr_study import OUT_DIR, load_data
from research.pivot_backtest import backtest_variant

# (label, group, kind, payload)
#   kind "sig"  -> overrides for find_pivot_setup
#   kind "mgr"  -> overrides for PivotTradeManager
#   kind "top"  -> keyword args of backtest_variant itself
Case = tuple[str, str, str, dict]

_G = {}


def build_cases() -> list[Case]:
    s = settings
    cases: list[Case] = [("LIVE", "base", "sig", {})]

    def add(group, kind, key, values, live):
        for v in values:
            if v != live:
                cases.append((f"{key}={v}", group, kind, {key: v}))

    add("sustain", "sig", "sustain_candles", [1, 2, 3, 4], s.PIVOT_SUSTAIN_CANDLES)
    add("sl", "sig", "sl_buffer_atr", [0.0, 0.05, 0.15, 0.3], s.PIVOT_SL_BUFFER_ATR)
    add("room", "sig", "min_room_r", [0.5, 1.0, 1.5, 2.0], s.PIVOT_MIN_ROOM_R)
    add("entry", "sig", "min_today_candles", [3, 6, 9], s.PIVOT_MIN_TODAY_CANDLES)
    add("bounce", "sig", "bounce_zone_atr", [0.0, 0.1, 0.15, 0.25, 0.4], s.PIVOT_BOUNCE_ZONE_ATR)
    add("bounce", "sig", "bounce_min_range_atr", [0.0, 0.3, 0.6, 0.9], s.PIVOT_BOUNCE_MIN_RANGE_ATR)
    add("bounce", "sig", "bounce_min_wick_pct", [0.0, 0.3, 0.5, 0.7], s.PIVOT_BOUNCE_MIN_WICK_PCT)
    add("bounce", "sig", "bounce_trend_ema", [0, 9, 21, 50], s.PIVOT_BOUNCE_TREND_EMA)
    add("bounce", "sig", "bounce_confirm_next", [False, True], s.PIVOT_BOUNCE_CONFIRM_NEXT)
    add("accept", "sig", "enable_acceptance", [False, True], s.PIVOT_ACCEPTANCE)
    add("trail", "mgr", "trail_atr_mult", [0.5, 0.75, 1.0, 1.5, 2.0], s.PIVOT_TRAIL_ATR_MULT)
    add("trail", "mgr", "t2_trail_atr_mult", [0.5, 0.75, 1.0], s.PIVOT_T2_TRAIL_ATR_MULT)
    add("be", "mgr", "be_trigger_r", [0.5, 0.75, 1.0, 1.5, 2.0], s.PIVOT_BE_TRIGGER_R)
    add("be", "mgr", "be_buffer_pts", [0.0, 5.0, 15.0, 30.0], s.PIVOT_BE_BUFFER_PTS)
    add("lock", "mgr", "t1_lock_pct", [0.25, 0.5, 0.75], s.PIVOT_T1_LOCK_PCT)
    add("lock", "mgr", "t2_lock_pct", [0.25, 0.5, 0.75], s.PIVOT_T2_LOCK_PCT)
    add("limit", "top", "max_trades", [1, 2, 3, 5], s.PIVOT_MAX_TRADES_PER_DAY)
    cases.append(("formula=TRADITIONAL", "formula", "top", {"formula": "TRADITIONAL"}))
    return cases


def _init(daily, m5):
    _G["daily"], _G["m5"] = daily, m5


def _run_case(case: Case) -> tuple[str, pd.DataFrame]:
    label, _group, kind, payload = case
    daily, m5 = _G["daily"], _G["m5"]
    if kind == "sig":
        t = backtest_variant(daily, m5, payload)
    elif kind == "mgr":
        t = backtest_variant(daily, m5, {}, mgr_overrides=payload)
    else:
        t = backtest_variant(daily, m5, {}, **payload)
    return label, t


def summarise(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return dict(n=0, win=np.nan, avgR=np.nan, avgPts=np.nan, totPts=0.0,
                    exTop5Pts=np.nan, H1Pts=np.nan, H2Pts=np.nan)
    d = pd.to_datetime(trades["date"])
    mid = d.sort_values().iloc[len(d) // 2]
    top = trades["pts"].sort_values(ascending=False)
    return dict(
        n=len(trades),
        win=round((trades["r"] > 0).mean() * 100, 1),
        avgR=round(trades["r"].mean(), 3),
        avgPts=round(trades["pts"].mean(), 1),
        totPts=round(trades["pts"].sum()),
        exTop5Pts=round(top.iloc[5:].mean(), 1) if len(top) > 5 else np.nan,
        H1Pts=round(trades.loc[d < mid, "pts"].mean(), 1),
        H2Pts=round(trades.loc[d >= mid, "pts"].mean(), 1),
    )


def flag(row: dict, base_tot: float) -> str:
    out = ""
    if base_tot and row["n"]:
        change = (row["totPts"] - base_tot) / abs(base_tot)
        if abs(change) > 0.35 or (row["totPts"] > 0) != (base_tot > 0):
            out += "!"
    if row["n"] and (row["H1Pts"] < 0 or row["H2Pts"] < 0):
        out += "~"
    return out


def run_sweep(daily, m5, cases: list[Case], workers: int = 4) -> pd.DataFrame:
    results: dict[str, pd.DataFrame] = {}
    if workers <= 1:
        _init(daily, m5)
        for c in cases:
            label, t = _run_case(c)
            results[label] = t
    else:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init,
                                 initargs=(daily, m5)) as ex:
            for label, t in ex.map(_run_case, cases):
                results[label] = t

    base_tot = summarise(results["LIVE"])["totPts"]
    rows = []
    for label, group, _k, _p in cases:
        s = summarise(results[label])
        rows.append({"group": group, "case": label, **s,
                     "dTot%": round((s["totPts"] - base_tot) / abs(base_tot) * 100)
                     if base_tot else np.nan,
                     "flag": flag(s, base_tot)})
    return pd.DataFrame(rows)


def format_report(df: pd.DataFrame) -> str:
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    out = ["\n=== Sensitivity: one parameter at a time around the LIVE config ==="]
    for group, g in df.groupby("group", sort=False):
        out.append(f"\n-- {group} --")
        out.append(g.drop(columns="group").to_string(index=False))
    out.append("\nLegend: '!' total points moved >35% or flipped sign vs LIVE;"
               " '~' one half-sample is negative.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pivot parameter sensitivity")
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", default="", help="comma list of groups to run (plus LIVE)")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    daily, m5 = load_data(args.days, False, None, None)
    cases = build_cases()
    if args.only:
        keep = {g.strip() for g in args.only.split(",")}
        cases = [c for c in cases if c[1] == "base" or c[1] in keep]
    df = run_sweep(daily, m5, cases, workers=args.workers)
    print(format_report(df))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_DIR / "pivot_sensitivity.csv", index=False)
    print(f"\nWritten to {OUT_DIR / 'pivot_sensitivity.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
