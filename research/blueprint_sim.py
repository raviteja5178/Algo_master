"""
Blueprint simulator — EMA(21) + Pivot-Point rule set vs. line / CPR-band filters.

Research only: imports nothing from the live trading path.

Blueprint rules (5m SENSEX)
    Long  : price above the pivot filter AND a GREEN candle closes cleanly
            above EMA(21).
    Short : price below the pivot filter AND a RED candle closes cleanly
            below EMA(21).
    Stop  : signal-candle low/high  (CANDLE)  or beyond the pivot level (LEVEL)
    Target: next overhead / downside Fibonacci level (R1..R3 / S1..S3)

Interpretations made explicit (the blueprint leaves them open)
    "closes cleanly" = a fresh cross: the previous close was on the other side
                       of EMA(21) and this candle closes through it.  A state
                       test ("close > EMA") would re-fire on every candle.
    Target           = nearest level in the trade direction that gives at least
                       --min-rr x risk of reward; trade skipped if none.
    Fills            = entry at the signal candle's close; if stop and target
                       are both touched inside one candle the STOP is assumed
                       first (conservative); open positions close at the last
                       5m close of the day.

Pivot filter variants compared
    NONE : EMA cross only (control)
    LINE : long needs close > P, short needs close < P        (the blueprint)
    BAND : long needs close > TC, short needs close < BC      (CPR zone)

Stop variants
    CANDLE : low (long) / high (short) of the signal candle
    LEVEL  : the filter level itself — P for LINE, TC (long) / BC (short) for BAND

Every variant is also split by the day type from research.cpr_study and by
first / second half of the sample, so an edge that only exists in one half
or one day type is visible.

Usage
    python -m research.blueprint_sim --days 400
    python -m research.blueprint_sim --ema 21 --min-rr 1.0 --stop-mult 1
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import time as dtime
from pathlib import Path

import numpy as np
import pandas as pd

from research.cpr_study import (
    OUT_DIR,
    build_features,
    cpr_levels,
    load_data,
)

logger = logging.getLogger(__name__)

DEFAULT_EMA = 21
SCAN_START = dtime(9, 20)
SCAN_END = dtime(14, 45)
MAX_TRADES_PER_DAY = 3

VARIANTS: list[tuple[str, str]] = [
    ("NONE", "CANDLE"),
    ("LINE", "CANDLE"),
    ("LINE", "LEVEL"),
    ("BAND", "CANDLE"),
    ("BAND", "LEVEL"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Pure helpers
# ─────────────────────────────────────────────────────────────────────────────

def fib_levels(high: float, low: float, close: float) -> dict[str, float]:
    """Fibonacci pivot levels + CPR band (mirrors market.historical_data)."""
    p = (high + low + close) / 3.0
    rng = high - low
    bc, _, tc = cpr_levels(high, low, close)
    return {
        "P": p, "BC": bc, "TC": tc,
        "R1": p + 0.382 * rng, "R2": p + 0.618 * rng, "R3": p + 1.0 * rng,
        "S1": p - 0.382 * rng, "S2": p - 0.618 * rng, "S3": p - 1.0 * rng,
    }


def filter_levels(name: str, lv: dict[str, float]) -> tuple[float | None, float | None]:
    """(level price must be ABOVE for longs, level price must be BELOW for shorts)."""
    if name == "LINE":
        return lv["P"], lv["P"]
    if name == "BAND":
        return lv["TC"], lv["BC"]
    return None, None


def blueprint_signal(
    prev_close: float, prev_ema: float,
    o: float, c: float, ema_now: float,
    long_above: float | None, short_below: float | None,
) -> str | None:
    """Return 'CE' / 'PE' / None for one completed candle."""
    if (c > o and prev_close <= prev_ema and c > ema_now
            and (long_above is None or c > long_above)):
        return "CE"
    if (c < o and prev_close >= prev_ema and c < ema_now
            and (short_below is None or c < short_below)):
        return "PE"
    return None


def pick_target(side: str, entry: float, risk: float, lv: dict[str, float],
                min_rr: float) -> float | None:
    """Nearest R/S level giving at least min_rr x risk of reward."""
    if side == "CE":
        cands = sorted(v for k, v in lv.items() if k in ("R1", "R2", "R3") and v > entry)
        return next((v for v in cands if v - entry >= min_rr * risk), None)
    cands = sorted((v for k, v in lv.items() if k in ("S1", "S2", "S3") and v < entry),
                   reverse=True)
    return next((v for v in cands if entry - v >= min_rr * risk), None)


@dataclass(frozen=True)
class Trade:
    date: object
    side: str
    entry: float
    stop: float
    target: float
    exit: float
    reason: str          # TARGET | STOP | EOD
    r: float


def simulate_day(
    rows: list[dict],
    lv: dict[str, float],
    pivot_filter: str,
    stop_mode: str,
    *,
    min_rr: float = 1.0,
    stop_mult: float = 1.0,
    scan_start: dtime = SCAN_START,
    scan_end: dtime = SCAN_END,
    max_trades: int = MAX_TRADES_PER_DAY,
) -> list[Trade]:
    """rows: one day's 5m candles in order, each with timestamp/open/high/low/close/ema.

    The first row's EMA reference (prev candle) is taken from the row itself, so
    callers pass the previous session's last candle as ``rows[0]`` context only
    through the global ema column — signals start at index 1.
    """
    long_above, short_below = filter_levels(pivot_filter, lv)
    trades: list[Trade] = []
    i = 1
    n = len(rows)
    while i < n - 1 and len(trades) < max_trades:
        c, p = rows[i], rows[i - 1]
        t = c["timestamp"].time()
        if t < scan_start or t > scan_end:
            i += 1
            continue
        side = blueprint_signal(p["close"], p["ema"], c["open"], c["close"], c["ema"],
                                long_above, short_below)
        if side is None:
            i += 1
            continue

        entry = c["close"]
        if stop_mode == "LEVEL" and pivot_filter != "NONE":
            level = long_above if side == "CE" else short_below
            stop = level
        else:
            stop = c["low"] if side == "CE" else c["high"]
        risk = (entry - stop) if side == "CE" else (stop - entry)
        if risk <= 0:
            i += 1
            continue
        if stop_mult != 1.0:
            risk *= stop_mult
            stop = entry - risk if side == "CE" else entry + risk
        target = pick_target(side, entry, risk, lv, min_rr)
        if target is None:
            i += 1
            continue

        exit_px, reason, j_exit = rows[-1]["close"], "EOD", n - 1
        for j in range(i + 1, n):
            d = rows[j]
            hit_stop = d["low"] <= stop if side == "CE" else d["high"] >= stop
            hit_tgt = d["high"] >= target if side == "CE" else d["low"] <= target
            if hit_stop:
                exit_px, reason, j_exit = stop, "STOP", j
                break
            if hit_tgt:
                exit_px, reason, j_exit = target, "TARGET", j
                break
        pnl = (exit_px - entry) if side == "CE" else (entry - exit_px)
        trades.append(Trade(
            date=c["timestamp"].date(), side=side,
            entry=round(entry, 2), stop=round(stop, 2), target=round(target, 2),
            exit=round(exit_px, 2), reason=reason, r=round(pnl / risk, 3),
        ))
        i = j_exit + 1
    return trades


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────

def run_simulation(
    daily: pd.DataFrame,
    m5: pd.DataFrame,
    *,
    ema_period: int = DEFAULT_EMA,
    min_rr: float = 1.0,
    stop_mult: float = 1.0,
) -> pd.DataFrame:
    """Return one row per trade with a ``variant`` column."""
    daily = daily.sort_values("date").reset_index(drop=True).copy()
    daily["date"] = pd.to_datetime(daily["date"]).dt.normalize()

    m5 = m5.copy()
    m5["timestamp"] = pd.to_datetime(m5["timestamp"])
    m5 = m5[(m5["timestamp"].dt.time >= dtime(9, 15))
            & (m5["timestamp"].dt.time <= dtime(15, 25))]
    m5 = m5.sort_values("timestamp").reset_index(drop=True)
    # EMA runs continuously across sessions, as the live bot's does.
    m5["ema"] = m5["close"].ewm(span=ema_period, adjust=False).mean()
    m5["date"] = m5["timestamp"].dt.normalize()
    warm_until = m5["timestamp"].iloc[min(len(m5) - 1, ema_period * 2)]

    prev_row = {d: daily.iloc[i - 1] for i, d in enumerate(daily["date"]) if i > 0}

    out: list[dict] = []
    for day, g in m5.groupby("date"):
        if day not in prev_row or g["timestamp"].iloc[0] < warm_until or len(g) < 20:
            continue
        pr = prev_row[day]
        lv = fib_levels(pr["high"], pr["low"], pr["close"])
        rows = g.to_dict("records")
        for pf, sm in VARIANTS:
            for tr in simulate_day(rows, lv, pf, sm, min_rr=min_rr, stop_mult=stop_mult):
                out.append({**tr.__dict__, "variant": f"{pf}/{sm}"})
    return pd.DataFrame(out)


def _stats(r: pd.Series) -> dict:
    if r.empty:
        return {"n": 0, "win%": np.nan, "avgR": np.nan, "totR": 0.0, "PF": np.nan}
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    return {
        "n": int(len(r)),
        "win%": round((r > 0).mean() * 100, 1),
        "avgR": round(r.mean(), 3),
        "totR": round(r.sum(), 1),
        "PF": round(wins / losses, 2) if losses > 0 else np.inf,
    }


def report(trades: pd.DataFrame, feats: pd.DataFrame) -> str:
    if trades.empty:
        return "No trades generated."
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    t = trades.copy()
    t["date"] = pd.to_datetime(t["date"]).dt.date
    t = t.merge(feats[["date", "day_type", "vol_class"]], on="date", how="left")
    order = [f"{a}/{b}" for a, b in VARIANTS]
    lines: list[str] = []

    def sec(title: str, df: pd.DataFrame) -> None:
        lines.append(f"\n=== {title} ===")
        lines.append(df.to_string())

    sec("Overall by variant", pd.DataFrame(
        {v: _stats(t.loc[t["variant"] == v, "r"]) for v in order}).T)
    sec("By side", pd.DataFrame(
        {f"{v} {s}": _stats(t.loc[(t["variant"] == v) & (t["side"] == s), "r"])
         for v in order for s in ("CE", "PE")}).T)
    sec("By exit reason (count)", pd.crosstab(t["variant"], t["reason"]).reindex(order))
    sec("avgR by day type", t.pivot_table(index="variant", columns="day_type",
                                          values="r", aggfunc="mean").round(3).reindex(order))
    sec("n by day type", t.pivot_table(index="variant", columns="day_type",
                                       values="r", aggfunc="count").reindex(order))
    dates = sorted(t["date"].unique())
    mid = dates[len(dates) // 2]
    t["half"] = np.where(t["date"] < mid, "H1", "H2")
    sec("Stability: avgR by half-sample", t.pivot_table(
        index="variant", columns="half", values="r", aggfunc="mean").round(3).reindex(order))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="EMA + pivot blueprint simulator")
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--daily")
    ap.add_argument("--intraday")
    ap.add_argument("--ema", type=int, default=DEFAULT_EMA, help="EMA period (default 21)")
    ap.add_argument("--min-rr", type=float, default=1.0, help="min reward/risk for target pick")
    ap.add_argument("--stop-mult", type=float, default=1.0, help="scale the stop distance")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    daily, m5 = load_data(args.days, args.refresh, args.daily, args.intraday)
    trades = run_simulation(daily, m5, ema_period=args.ema,
                            min_rr=args.min_rr, stop_mult=args.stop_mult)
    feats = build_features(daily, m5)
    print(f"EMA({args.ema})  min_rr={args.min_rr}  stop_mult={args.stop_mult}")
    print(report(trades, feats))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = Path(OUT_DIR) / "blueprint_trades.csv"
    trades.to_csv(path, index=False)
    print(f"\nTrade log written to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
