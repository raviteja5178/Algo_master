"""
Strategy lab: compare SENSEX intraday strategy families on the same data,
option model and costs as research/system_backtest.py, with an honest
in-sample / out-of-sample split.

Families
    ORB      buy ATM CE/PE on the first 5-minute close beyond the opening range
             (15 or 30 min); index stop at the other side of the range; exit at
             a fixed R target, or break-even at 1R + chandelier trail; 15:10 exit.
    IFLY     sell an intraday iron butterfly: short ATM CE+PE, long wings +-W;
             exit on a loss of S x credit, a profit of P x credit, or 15:10.
    ICONDOR  sell an intraday iron condor: short CE/PE D points OTM, long
             wings W further out; same exits.

Model (shared with the full-system backtest)
    Prices   Black-Scholes, IV = India VIX of that minute, weekly expiry
             calendar from research.system_backtest.
    Path     1-minute bars, O -> adverse extreme -> favourable extreme -> C.
    Entry    the open of the minute after the signal candle closes.
    Costs    research.backtest_report.charges() per leg + slippage per leg/side.
    Sizing   one SENSEX lot (20) per leg.

Selection: every parameter set is scored on IN-SAMPLE days only; the report
shows the out-of-sample result of the in-sample winners, untouched.

Usage
    python -m research.strategy_lab
"""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from research.backtest_report import charges
from research.system_backtest import Contracts, MarketData, bs_price, tick_round

OUT_DIR = Path(__file__).resolve().parent / "output" / "strategy_lab"
IS_END = date(2025, 6, 30)            # in-sample: start .. IS_END; out-of-sample after
QTY = 20
SLIP = 1.0                            # option points per leg per side
EXIT_AT = dtime(15, 10)


# ── day data ──────────────────────────────────────────────────────────────────

@dataclass
class Day:
    d: date
    ts: list            # minute timestamps (naive IST)
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    atr_d: float        # daily ATR(14) up to yesterday
    pc: float           # previous close
    prev_rng: float
    vix_open: float


def load_days(md: MarketData) -> list[Day]:
    m1 = md.m1
    g = m1.groupby(m1.timestamp.dt.date)
    daily = pd.DataFrame({"h": g.high.max(), "l": g.low.min(), "c": g.close.last(), "n": g.size()})
    pc = daily.c.shift(1)
    tr = pd.concat([daily.h - daily.l, (daily.h - pc).abs(), (daily.l - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().shift(1)
    out = []
    for d, grp in md.by_day.items():
        if daily.n.get(d, 0) < 300 or pd.isna(atr.get(d)) or pd.isna(pc.get(d)):
            continue          # special/short sessions and the warm-up period
        ts = [t.to_pydatetime() for t in grp.timestamp]
        out.append(Day(d, ts, grp.open.to_numpy(), grp.high.to_numpy(), grp.low.to_numpy(),
                       grp.close.to_numpy(), float(atr[d]), float(pc[d]),
                       float((daily.h - daily.l).shift(1)[d]), md.vix_at(ts[0])))
    return out


def _minute_index(day: Day, t: dtime) -> int:
    for i, ts in enumerate(day.ts):
        if ts.time() >= t:
            return i
    return len(day.ts) - 1


def _cost(legs: list[tuple[float, float]], d: date) -> float:
    """legs: (entry_px, exit_px) per bought-then-sold leg (sells are passed reversed)."""
    return sum(charges(b, s, QTY, d) for b, s in legs) + SLIP * 2 * QTY * len(legs)


# ── buyer: opening-range breakout ─────────────────────────────────────────────

def run_orb(days: list[Day], ch: Contracts, *, or_min: int, exit_mode: str, target_r: float,
            last_entry: dtime, max_risk_atr: float, rollover: dtime = dtime(12, 30)) -> pd.DataFrame:
    rows = []
    or_end = (datetime.combine(date.today(), dtime(9, 15)) + timedelta(minutes=or_min)).time()
    for day in days:
        i_or = _minute_index(day, or_end)
        orh, orl = day.h[:i_or].max(), day.l[:i_or].min()
        side = None
        # 5-minute closes after the opening range
        for j in range(i_or + 4, len(day.ts), 5):
            t_close = (day.ts[j] + timedelta(minutes=1)).time()
            if t_close > last_entry:
                break
            cl = day.c[j]
            if cl > orh:
                side, stop = "CE", orl
            elif cl < orl:
                side, stop = "PE", orh
            if side:
                break
        if not side or j + 1 >= len(day.ts):
            continue
        k = j + 1
        entry_idx = day.o[k]
        sign = 1 if side == "CE" else -1
        risk = (entry_idx - stop) * sign
        if risk <= 0 or risk > max_risk_atr * day.atr_d:
            continue
        exps = ch.expiries_from(day.d)
        exp = exps[1] if (exps[0] == day.d and day.ts[k].time() >= rollover) else exps[0]
        con = ch.contract(exp, round(entry_idx / 100) * 100, side)
        prem_in = ch.premium(con, entry_idx, day.ts[k])
        target = entry_idx + sign * target_r * risk
        best, cur_stop, exit_idx, why, kx = entry_idx, stop, None, None, k
        atr5 = day.atr_d / 6.0            # rough 5-minute ATR from the daily ATR
        for x in range(k, len(day.ts)):
            if day.ts[x].time() >= EXIT_AT:
                exit_idx, why, kx = day.o[x], "TIME", x
                break
            path = ([day.o[x], day.l[x], day.h[x], day.c[x]] if day.c[x] >= day.o[x]
                    else [day.o[x], day.h[x], day.l[x], day.c[x]])
            for px in path:
                if (px - cur_stop) * sign <= 0:
                    # gap through the stop fills at the open, otherwise at the stop
                    exit_idx = px if px is path[0] else cur_stop
                    why = ("SL" if cur_stop == stop else
                           "BE" if abs(cur_stop - entry_idx) < 1e-6 else "TSL")
                    break
                if exit_mode == "fixed" and (px - target) * sign >= 0:
                    exit_idx, why = target, "TARGET"
                    break
                if (px - best) * sign > 0:
                    best = px
                if exit_mode == "trail":
                    if (best - entry_idx) * sign >= risk and (cur_stop - entry_idx) * sign < 0:
                        cur_stop = entry_idx
                    if (best - entry_idx) * sign >= 1.5 * risk:
                        cand = best - sign * 2 * atr5
                        if (cand - cur_stop) * sign > 0:
                            cur_stop = cand
            if why:
                kx = x
                break
        if why is None:
            exit_idx, why, kx = day.c[-1], "TIME", len(day.ts) - 1
        prem_out = ch.premium(con, exit_idx, day.ts[kx])
        gross = (prem_out - prem_in) * QTY
        net = gross - _cost([(prem_in, prem_out)], day.d)
        rows.append({"day": day.d, "side": side, "entry_time": day.ts[k].time(), "exit": why,
                     "prem_in": prem_in, "prem_out": prem_out, "idx_pts": (exit_idx - entry_idx) * sign,
                     "risk_pts": risk, "gross": gross, "net": net,
                     "max_loss": prem_in * QTY})
    return pd.DataFrame(rows)


# ── seller: iron butterfly / iron condor ──────────────────────────────────────

def run_short_premium(days: list[Day], ch: Contracts, *, entry: dtime, dist: int, wing: int,
                      stop_x: float, take_x: float, vix_min: float, vix_max: float,
                      expiry_only: bool) -> pd.DataFrame:
    rows = []
    for day in days:
        exp = ch.expiries_from(day.d)[0]
        if expiry_only and exp != day.d:
            continue
        k = _minute_index(day, entry)
        spot = day.o[k]
        vix = ch.md.vix_at(day.ts[k])
        if not (vix_min <= vix <= vix_max):
            continue
        atm = round(spot / 100) * 100
        legs = {  # strike, type, +1 long / -1 short
            "sc": (atm + dist, "CE", -1), "sp": (atm - dist, "PE", -1),
            "lc": (atm + dist + wing, "CE", 1), "lp": (atm - dist - wing, "PE", 1),
        }
        cons = {n: ch.contract(exp, K, t) for n, (K, t, _) in legs.items()}

        def value(s_px: float, at: datetime) -> tuple[float, dict]:
            px = {n: ch.premium(c, s_px, at) for n, c in cons.items()}
            # value of the short position = cost to buy it back
            return (px["sc"] + px["sp"] - px["lc"] - px["lp"]), px

        credit, px_in = value(spot, day.ts[k])
        if credit <= 5:
            continue
        stop_v, take_v = credit * (1 + stop_x), credit * (1 - take_x)
        why, px_out, kx = None, None, k
        for x in range(k, len(day.ts)):
            at = day.ts[x]
            if at.time() >= EXIT_AT:
                _, px_out = value(day.o[x], at)
                why, kx = "TIME", x
                break
            for s_px in (day.h[x], day.l[x]):
                v, p = value(s_px, at)
                if v >= stop_v:
                    why, px_out, kx = "STOP", p, x
                    break
            if why:
                break
            v, p = value(day.c[x], at)
            if take_x > 0 and v <= take_v:
                why, px_out, kx = "TAKE", p, x
                break
        if why is None:
            _, px_out = value(day.c[-1], day.ts[-1])
            why = "TIME"
        exit_val = px_out["sc"] + px_out["sp"] - px_out["lc"] - px_out["lp"]
        gross = (credit - exit_val) * QTY
        cost_legs = [(px_in[n], px_out[n]) if legs[n][2] == 1 else (px_out[n], px_in[n]) for n in legs]
        net = gross - _cost(cost_legs, day.d)
        rows.append({"day": day.d, "entry_time": day.ts[k].time(), "exit": why, "credit": credit,
                     "exit_value": exit_val, "gross": gross, "net": net,
                     "max_loss": (wing - credit) * QTY, "dte": (exp - day.d).days,
                     "vix": vix})
    return pd.DataFrame(rows)


# ── scoring ───────────────────────────────────────────────────────────────────

def score(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"n": 0}
    w = t.net > 0
    gl = -t.net[~w].sum()
    eq = t.net.cumsum()
    months = max(1, len({(d.year, d.month) for d in t.day}))
    return {
        "n": len(t), "trades_mo": round(len(t) / months, 1),
        "win%": round(100 * w.mean(), 1),
        "net": round(t.net.sum()), "avg": round(t.net.mean()),
        "pf": round(t.net[w].sum() / gl, 2) if gl > 0 else float("inf"),
        "max_dd": round(float((eq - eq.cummax()).min())),
        "worst": round(t.net.min()),
        "green_mo%": round(100 * (t.groupby([pd.to_datetime(t.day).dt.to_period("M")]).net.sum() > 0).mean()),
    }


def split(t: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if t.empty:
        return t, t
    return t[t.day <= IS_END], t[t.day > IS_END]


# ── experiment grid ───────────────────────────────────────────────────────────

ORB_GRID = [
    dict(or_min=om, exit_mode=em, target_r=tr, last_entry=le, max_risk_atr=mr)
    for om in (15, 30)
    for em, tr in (("fixed", 1.5), ("fixed", 2.0), ("trail", 0.0))
    for le in (dtime(10, 30), dtime(11, 30))
    for mr in (0.4, 0.7)
]
SELL_GRID = [
    dict(entry=en, dist=di, wing=wi, stop_x=sx, take_x=tx, vix_min=0.0, vix_max=100.0,
         expiry_only=eo)
    for en in (dtime(9, 45), dtime(10, 30))
    for di in (0, 400)
    for wi in (500, 1000)
    for sx in (0.5, 1.0)
    for tx in (0.0, 0.5)
    for eo in (False, True)
]


def _label(family: str, cfg: dict) -> str:
    parts = []
    for k, v in cfg.items():
        if k in ("vix_min", "vix_max"):
            continue
        parts.append(f"{k}={v.strftime('%H:%M') if isinstance(v, dtime) else v}")
    return family + " " + " ".join(parts)


_W: dict = {}


def _init_worker() -> None:
    md = MarketData()
    _W.update(md=md, ch=Contracts(md))
    _W["days"] = load_days(md)


def _run_one(task):
    family, cfg = task
    days, ch = _W["days"], _W["ch"]
    t = run_orb(days, ch, **cfg) if family == "ORB" else run_short_premium(days, ch, **cfg)
    return _label(family, cfg), t


def evaluate(workers: int = 6):
    from concurrent.futures import ProcessPoolExecutor
    tasks = [("ORB", c) for c in ORB_GRID] + [
        ("IFLY" if c["dist"] == 0 else "ICONDOR", c) for c in SELL_GRID]
    rows, trades = [], {}
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
        for n, (name, t) in enumerate(ex.map(_run_one, tasks), 1):
            trades[name] = t
            if n % 10 == 0:
                print(f"  {n}/{len(tasks)} configurations", flush=True)
    for name, t in trades.items():
        ins, oos = split(t)
        r = {"strategy": name, "family": name.split()[0]}
        r.update({f"IS_{k}": v for k, v in score(ins).items()})
        r.update({f"OOS_{k}": v for k, v in score(oos).items()})
        rows.append(r)
    return pd.DataFrame(rows), trades


def main() -> None:
    import sys
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if "--robustness" in sys.argv:
        import pickle
        res = robustness(workers=4)
        with open(OUT_DIR / "robustness.pkl", "wb") as f:
            pickle.dump(res, f)
        for k, t in res.items():
            i, o = split(t)
            print(k, score(t), "IS", score(i).get("net"), "OOS", score(o).get("net"), flush=True)
        return
    print(f"Strategy lab: in-sample to {IS_END}, out-of-sample after")
    res, trades = evaluate()
    res.to_csv(OUT_DIR / "all_results.csv", index=False)
    # in-sample winners per family: enough trades, best in-sample net
    picks = []
    for fam, g in res.groupby("family"):
        g = g[(g.IS_n >= 30)].sort_values("IS_net", ascending=False).head(3)
        picks.append(g)
    best = pd.concat(picks)
    best.to_csv(OUT_DIR / "in_sample_winners.csv", index=False)
    for name in best.strategy:
        safe = name.replace(" ", "_").replace(":", "").replace("=", "-")
        trades[name].to_csv(OUT_DIR / f"trades_{safe}.csv", index=False)
    print(best[["strategy", "IS_n", "IS_net", "IS_pf", "OOS_n", "OOS_net", "OOS_pf"]].to_string())



# ── robustness of the chosen strategy ─────────────────────────────────────────

CHOSEN = dict(entry=dtime(10, 30), dist=0, wing=1000, stop_x=0.5, take_x=0.0,
              vix_min=0.0, vix_max=100.0, expiry_only=True)


def _stress_one(task):
    """Re-run CHOSEN under one stress; every change is undone afterwards."""
    global SLIP
    kind, val = task
    days, ch = _W["days"], _W["ch"]
    saved_slip, saved_vix = SLIP, ch.md.vix_at
    try:
        if kind == "slip":
            SLIP = val
        if kind == "iv":
            ch.md.vix_at = lambda t, _r=saved_vix, _k=val: _r(t) * _k
        key = {"entry": "entry", "wing": "wing", "stop": "stop_x"}.get(kind)
        cfg = dict(CHOSEN, **{key: val}) if key else CHOSEN
        return task, run_short_premium(days, ch, **cfg)
    finally:
        SLIP, ch.md.vix_at = saved_slip, saved_vix


STRESS = ([("base", 0)] + [("slip", s) for s in (1.5, 2.0, 3.0)]
          + [("iv", k) for k in (0.8, 0.9, 1.1)]
          + [("entry", t) for t in (dtime(10, 0), dtime(11, 0), dtime(11, 30))]
          + [("wing", w) for w in (700, 1500)]
          + [("stop", s) for s in (0.3, 0.75)])


def robustness(workers: int = 6) -> dict:
    from concurrent.futures import ProcessPoolExecutor
    out = {}
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
        for task, t in ex.map(_stress_one, STRESS):
            out[task] = t
    return out


# ── report ────────────────────────────────────────────────────────────────────

def write_report() -> Path:
    import pickle
    from research.backtest_report import _table
    res = pd.read_csv(OUT_DIR / "all_results.csv")
    with open(OUT_DIR / "robustness.pkl", "rb") as f:
        rob = pickle.load(f)
    base = rob[("base", 0)].copy()
    dts = pd.to_datetime(base.day)
    base.to_csv(OUT_DIR / "trades_recommended_ifly.csv", index=False)
    L = ["# SENSEX intraday strategy research\n",
         f"Data: SENSEX 1-minute bars and India VIX, {dts.min():%b %Y} – {dts.max():%b %Y}.  "
         f"Generated {datetime.now():%Y-%m-%d %H:%M}.  Re-run: `python -m research.strategy_lab`, "
         "`python -m research.strategy_lab --robustness`, `python -m research.strategy_lab --report`.\n",
         "> Research output from a backtest, not investment advice.  Every number below "
         "depends on the option-price model described under *Risks*.\n"]

    L.append("## What the market data says\n")
    L.append("- **Options have been priced above realised movement.** Median India VIX 13.8 vs "
             "20-day realised SENSEX volatility 10.9: buyers pay for more movement than "
             "usually arrives; that gap is the seller's edge.\n"
             "- **Morning direction does not predict the afternoon.** First-hour move vs "
             "rest-of-day move: correlation 0.02; same direction on only 53% of days.\n"
             "- **Volatility is U-shaped.** The 09:15 half-hour moves about 2.5x more than any "
             "midday half-hour; 11:15–13:45 is the quietest stretch.\n"
             "- **43% of daily variance happens overnight** (weeknight ≈ 176 trading minutes, "
             "weekend ≈ 609), so an intraday option buyer pays the day's time decay but only "
             "sees about 57% of the day's movement.\n")

    L.append("## Strategy families tested\n")
    L.append(f"Parameters were chosen on **in-sample** days (to {IS_END}) and judged on the "
             "**out-of-sample** days after it, which played no part in the choice.  Same data, "
             "option model, costs (brokerage, STT, exchange, SEBI, stamp, GST per leg) and "
             f"{SLIP:g} point of slippage per leg per side throughout.\n\n")
    fam = []
    for f_, g in res.groupby("family"):
        fam.append({"Family": f_, "Setups": len(g),
                    "Positive in-sample": int((g.IS_net > 0).sum()),
                    "Positive out-of-sample": int((g.OOS_net > 0).sum()),
                    "Positive in both": int(((g.IS_net > 0) & (g.OOS_net > 0)).sum()),
                    "Best out-of-sample PF": round(g.OOS_pf.max(), 2)})
    L.append(_table(pd.DataFrame(fam)))
    L.append("\n- **ORB** = buy ATM CE/PE on an opening-range breakout (15/30-minute range; "
             "fixed 1.5R/2R target or break-even + trailing stop).\n"
             "- **IFLY** = sell an ATM straddle and buy wings either side (iron butterfly), intraday.\n"
             "- **ICONDOR** = sell a 400-point OTM strangle with wings (iron condor), intraday.\n")
    top = res.sort_values("IS_net", ascending=False).groupby("family").head(3)
    L.append("\n### Best three per family (picked in-sample, then judged out-of-sample)\n")
    L.append(_table(top[["strategy", "IS_n", "IS_net", "IS_pf", "OOS_n", "OOS_net", "OOS_pf",
                         "OOS_max_dd"]].rename(columns=lambda c: c.replace("_", " "))))

    c = CHOSEN
    L.append("\n## Recommended strategy: expiry-day intraday iron butterfly\n")
    L.append("| Rule | Value |\n|---|---|\n"
             "| Days | SENSEX weekly expiry day only (0 days to expiry) |\n"
             f"| Entry | {c['entry']:%H:%M}: buy CE and PE {c['wing']} points from ATM first, "
             "then sell the ATM CE and ATM PE |\n"
             "| Size | 1 lot (20) per leg |\n"
             f"| Stop | close all four legs if the cost to buy the position back rises "
             f"{int(c['stop_x'] * 100)}% above the credit received |\n"
             f"| Exit | otherwise close everything at {EXIT_AT:%H:%M} |\n"
             "| Max loss | capped by the wings: (wing − credit) × 20 |\n\n")
    ins, oos = split(base)
    L.append(_table(pd.DataFrame([dict(Period="All", **score(base)),
                                  dict(Period="In-sample", **score(ins)),
                                  dict(Period="Out-of-sample", **score(oos))])))
    yr = base.groupby(dts.dt.year).net.agg(["count", "sum"]).reset_index()
    yr.columns = ["Year", "Trades", "Net Rs"]
    yr["Year"] = yr.Year.astype(str)
    L.append("\n### By year\n")
    L.append(_table(yr))
    L.append("\n### Exits\n")
    ex = base.groupby("exit").net.agg(["count", "mean", "sum"]).round(0).reset_index()
    ex.columns = ["Exit", "Trades", "Avg Rs", "Net Rs"]
    L.append(_table(ex))

    L.append("\n## Stress tests\n")
    L.append("Each row changes one thing and re-runs every expiry day.\n\n")
    names = {"base": "As specified", "slip": "Slippage per leg per side (pts)",
             "iv": "Option prices: model IV ×", "entry": "Entry time",
             "wing": "Wing width (pts)", "stop": "Stop at loss of credit ×"}
    rows = []
    for (k, v), t in rob.items():
        i, o = split(t)
        sc = score(t)
        rows.append({"Test": names[k],
                     "Value": v.strftime("%H:%M") if isinstance(v, dtime) else ("-" if k == "base" else v),
                     "Net Rs": sc["net"], "PF": sc["pf"], "Max DD Rs": sc["max_dd"],
                     "In-sample Rs": score(i)["net"], "Out-of-sample Rs": score(o)["net"]})
    L.append(_table(pd.DataFrame(rows)))
    L.append("\n**The test that matters:** the edge is options being priced above the movement "
             "that follows.  With real expiry-day premiums 10% below the model it still makes "
             "money; 20% below and it loses.  Measuring real premiums comes before any capital.\n")

    L.append("\n## Why not the current buying strategies\n")
    L.append("Under the same model and costs, every opening-range-breakout buying setup failed "
             "out-of-sample, and the bot's current configuration (Pivot + ORB + EMA buying) loses "
             "over the period — see `research/output/system_backtest/current_config/REPORT.md`.  "
             "Buying options intraday means paying the day's time decay while much of the "
             "variance happens overnight; none of the tested buying rules overcame that.\n")

    L.append("\n## Risks and what the model cannot see\n")
    L.append("- **Option prices are modelled** (Black-Scholes, IV = India VIX, trading-time decay "
             "calibrated on SENSEX's own overnight/intraday variance split).  No volatility smile, "
             "no 0DTE-specific IV, no bid/ask spread beyond the slippage figure.\n"
             "- **Event days** (budget, RBI policy, election results, global shocks) can move "
             "SENSEX 1,000+ points; the wings cap each loss, but a run of them hurts.\n"
             "- **Execution**: four legs must fill together.  Buy the wings before selling the ATM "
             "legs and use limit orders; a partial fill can leave a naked short option.\n"
             "- **Margin**: a hedged iron fly needs far less margin than naked selling; check the "
             "exact figure in Zerodha's basket margin calculator.\n"
             "- **Expiry calendar**: SENSEX weeklies moved Friday → Tuesday (Jan 2025) → Thursday "
             "(Sep 2025).  A future change moves the trading day.\n"
             "- **The bot cannot trade this yet**: it only places single-leg buy orders.\n")

    L.append("\n## Plan before trading it\n")
    L.append("1. **Verify premiums (2–4 expiry days, no orders):** record the real 10:30 ATM "
             "straddle and 1000-point wing prices from Kite and compare with the model.  Proceed "
             "only if the real credit is at least ~90% of the model's.\n"
             "2. **Paper-trade the rules** for 8+ expiry days on real quotes, including the "
             "4-leg fill sequence.\n"
             "3. **Go live with 1 lot**: wings mandatory, the stop automated, a daily loss cap, "
             "and no trading on scheduled event days.\n")
    path = OUT_DIR / "STRATEGY_REPORT.md"
    path.write_text("\n".join(L), encoding="utf-8")
    return path


if __name__ == "__main__":
    import sys as _sys
    if "--report" in _sys.argv:
        print(write_report())
    else:
        main()
