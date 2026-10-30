"""
Replay the bot's REAL pivot strategy on cached SENSEX 5m data.

Research only — no live state is touched.  The backtest calls the production
``find_pivot_setup`` candle-by-candle and manages every trade with the
production ``PivotTradeManager`` (BE / T1 lock / T2 lock / chandelier / T3), so
the numbers are directly comparable with research.blueprint_sim.

Model
    Signal   : find_pivot_setup(history up to the just-completed candle), the
               same call the signal engine makes.  Config = live settings
               (.env) unless a named variant overrides it.
    Entry    : setup.entry (the signal candle's close, as the bot sizes it).
    Ticks    : each later 5m candle is fed to the manager as four ticks,
               ADVERSE extreme first (CE: O,L,H,C  PE: O,H,L,C) — conservative.
    Stops    : filled at the stop level; if the candle OPENS through the stop
               the fill is the open (gap).
    ATR      : refreshed on every completed candle, as main.py does.
    Limits   : one position at a time, PIVOT_MAX_TRADES_PER_DAY per day, no
               new entries at/after NO_NEW_ENTRY_AFTER, forced exit at the
               close of the last candle before FORCE_EXIT_TIME.
    Result   : R = pnl_points / setup.risk (index points, before costs).

Usage
    python -m research.pivot_backtest
    python -m research.pivot_backtest --variants LIVE,LEGACY_AB
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import time as dtime

import numpy as np
import pandas as pd

from config import settings
from execution.pivot_trade_manager import PivotTradeManager
from market.candle_builder import Candle
from market.historical_data import compute_pivot_levels
from market.indicators import atr_at
from research.blueprint_sim import _stats
from research.cpr_study import OUT_DIR, build_features, load_data
from strategies.pivot_strategy import find_pivot_setup

logger = logging.getLogger(__name__)

HISTORY_CANDLES = 400            # ≈ 5 sessions of 5m bars, like the bot's bootstrap
FORCE_EXIT = dtime(15, 15)
NO_NEW_ENTRY = dtime(15, 0)


def _t(hhmm: str) -> dtime:
    h, m = hhmm.split(":")
    return dtime(int(h), int(m))


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

def live_signal_kwargs() -> dict:
    """find_pivot_setup kwargs exactly as strategies/signal_engine.py builds them."""
    return dict(
        sustain_candles=settings.PIVOT_SUSTAIN_CANDLES,
        atr_period=settings.PIVOT_ATR_PERIOD,
        sl_mode=settings.PIVOT_SL_MODE,
        sl_atr_mult=settings.PIVOT_SL_ATR_MULT,
        sl_buffer_atr=settings.PIVOT_SL_BUFFER_ATR,
        min_room_r=settings.PIVOT_MIN_ROOM_R,
        min_today_candles=settings.PIVOT_MIN_TODAY_CANDLES,
        pivot_mode=settings.PIVOT_MODE,
        od_window_start=_t(settings.PIVOT_OD_WINDOW_START),
        od_window_end=_t(settings.PIVOT_OD_WINDOW_END),
        rejection_zone_atr=settings.PIVOT_REJECTION_ZONE_ATR,
        min_od_gap_atr=settings.PIVOT_OD_MIN_GAP_ATR,
        first_candle_confirm=settings.PIVOT_OD_FIRST_CANDLE_CONFIRM,
        max_first_wick_atr=settings.PIVOT_OD_MAX_FIRST_WICK_ATR,
        enable_acceptance=settings.PIVOT_ACCEPTANCE,
        acceptance_min_dist_atr=settings.PIVOT_ACCEPT_MIN_DIST_ATR,
        acceptance_min_room_r=settings.PIVOT_ACCEPT_MIN_ROOM_R,
        bounce_zone_atr=settings.PIVOT_BOUNCE_ZONE_ATR,
        bounce_min_range_atr=settings.PIVOT_BOUNCE_MIN_RANGE_ATR,
        bounce_min_wick_pct=settings.PIVOT_BOUNCE_MIN_WICK_PCT,
        bounce_trend_ema=settings.PIVOT_BOUNCE_TREND_EMA,
        bounce_confirm_next=settings.PIVOT_BOUNCE_CONFIRM_NEXT,
        enable_swing_pivot=settings.PIVOT_ENABLE_SWING,
        swing_pivot_left=settings.PIVOT_SWING_LEFT,
        swing_pivot_right=settings.PIVOT_SWING_RIGHT,
        swing_pivot_trend_ema=settings.PIVOT_SWING_TREND_EMA,
        swing_pivot_rr_t1=settings.PIVOT_SWING_RR_T1,
        swing_pivot_rr_t2=settings.PIVOT_SWING_RR_T2,
        swing_pivot_rr_t3=settings.PIVOT_SWING_RR_T3,
        swing_pivot_use_atr_sl=settings.PIVOT_SWING_USE_ATR_SL,
        swing_pivot_atr_mult=settings.PIVOT_SWING_ATR_MULT,
    )


_NO_FILTERS = dict(min_od_gap_atr=0.0, first_candle_confirm=False, max_first_wick_atr=0.0)
_NO_EXTRAS = dict(enable_acceptance=False, bounce_zone_atr=0.0, enable_swing_pivot=False)

# name -> overrides applied on top of the live config
VARIANT_OVERRIDES: dict[str, dict] = {
    "ACCEPTANCE_PLUS_BOUNCE": dict(pivot_mode="NONE", enable_acceptance=True, bounce_zone_atr=0.15, enable_swing_pivot=False),
    "ACCEPTANCE_BOUNCE_MODE_A": dict(pivot_mode="OPEN_DIRECTION", enable_acceptance=True, bounce_zone_atr=0.15, enable_swing_pivot=False),
    "ACCEPTANCE_ONLY": dict(pivot_mode="NONE", enable_acceptance=True, bounce_zone_atr=0.0, enable_swing_pivot=False),
    "BOUNCE_ONLY": dict(pivot_mode="NONE", enable_acceptance=False, bounce_zone_atr=0.15, enable_swing_pivot=False),
    "FULL_PIVOT_SUITE": dict(pivot_mode="BOTH", enable_acceptance=True, bounce_zone_atr=0.15, enable_swing_pivot=False),
    "FULL_WITH_SWING_5_2": dict(pivot_mode="BOTH", enable_acceptance=True, bounce_zone_atr=0.15, enable_swing_pivot=True, swing_pivot_left=5, swing_pivot_right=2, swing_pivot_trend_ema=50),
}


def manager_kwargs() -> dict:
    return dict(
        delta=1.0,
        be_trigger_r=settings.PIVOT_BE_TRIGGER_R,
        be_buffer_pts=settings.PIVOT_BE_BUFFER_PTS,
        t1_lock_pct=settings.PIVOT_T1_LOCK_PCT,
        t2_lock_pct=settings.PIVOT_T2_LOCK_PCT,
        trail_atr_mult=settings.PIVOT_TRAIL_ATR_MULT,
        t2_trail_atr_mult=settings.PIVOT_T2_TRAIL_ATR_MULT,
        hard_sl_cushion=settings.PIVOT_HARD_SL_CUSHION,
        max_sl_pct=0.0,          # index-level study: no premium clamp
    )


# ─────────────────────────────────────────────────────────────────────────────
# Trade simulation
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PivotTrade:
    date: object
    mode: str
    side: str
    entry: float
    stop: float
    risk: float
    t1: float
    exit: float
    reason: str
    r: float
    pts: float
    bars: int
    stage: str
    entry_time: str = ""      # open time of the first candle AFTER the signal candle


def _ticks(c: Candle, side: str) -> list[float]:
    return [c.open, c.low, c.high, c.close] if side == "CE" else [c.open, c.high, c.low, c.close]


def simulate_trade(
    setup,
    later: list[Candle],
    atr_after,
    mgr_kwargs: dict,
    day,
) -> tuple[PivotTrade, int]:
    """Run one setup through PivotTradeManager.  Returns (trade, index in ``later`` of exit candle).

    ``later`` = completed candles after the signal candle, same session, already
    truncated at the forced-exit candle.  ``atr_after(j)`` = ATR after candle j.
    """
    mgr = PivotTradeManager(
        setup.side, setup.entry, setup.stop, setup.t1, setup.t2, setup.t3,
        setup.atr, setup.entry, signal_risk=setup.risk, **mgr_kwargs,
    )
    sign = 1 if setup.side == "CE" else -1
    reason, exit_px, exit_j = "EOD", None, len(later) - 1

    for j, c in enumerate(later):
        for k, px in enumerate(_ticks(c, setup.side)):
            stop_before = mgr.stop_index
            res = mgr.on_index_price(px)
            if res and res[0] == "EXIT":
                reason = str(res[1])
                if reason == "PIVOT_TARGET_T3":
                    exit_px = px if k == 0 else setup.t3
                else:
                    exit_px = px if k == 0 else stop_before
                exit_j = j
                break
        if exit_px is not None:
            break
        if (a := atr_after(j)):
            mgr.update_atr(a)

    if exit_px is None:
        exit_px = later[-1].close if later else setup.entry
    pts = (exit_px - setup.entry) * sign
    return PivotTrade(
        date=later[0].timestamp.date() if later else day,
        mode=setup.mode, side=setup.side, entry=setup.entry, stop=setup.stop,
        risk=setup.risk, t1=setup.t1, exit=round(exit_px, 2), reason=reason,
        r=round(pts / setup.risk, 3), pts=round(pts, 2), bars=exit_j + 1, stage=mgr.stage,
        entry_time=later[0].timestamp.strftime("%H:%M") if later else "",
    ), exit_j


def backtest_variant(
    daily: pd.DataFrame,
    m5: pd.DataFrame,
    overrides: dict,
    *,
    max_trades: int | None = None,
    mgr_overrides: dict | None = None,
    formula: str | None = None,
) -> pd.DataFrame:
    max_trades = settings.PIVOT_MAX_TRADES_PER_DAY if max_trades is None else max_trades
    kw = {**live_signal_kwargs(), **overrides}
    mkw = {**manager_kwargs(), **(mgr_overrides or {})}

    daily = daily.sort_values("date").reset_index(drop=True)
    daily["date"] = pd.to_datetime(daily["date"]).dt.normalize()
    prev_of = {daily["date"].iloc[i]: daily.iloc[i - 1] for i in range(1, len(daily))}

    m5 = m5.copy()
    m5["timestamp"] = pd.to_datetime(m5["timestamp"])
    m5 = m5[(m5["timestamp"].dt.time >= dtime(9, 15))
            & (m5["timestamp"].dt.time <= dtime(15, 25))].sort_values("timestamp")
    candles = [Candle(timestamp=r.timestamp.to_pydatetime(), open=float(r.open),
                      high=float(r.high), low=float(r.low), close=float(r.close))
               for r in m5.itertuples(index=False)]
    day_of = [c.timestamp.date() for c in candles]

    out: list[PivotTrade] = []
    gi = 0
    n = len(candles)
    while gi < n:
        day = day_of[gi]
        gj = gi
        while gj < n and day_of[gj] == day:
            gj += 1
        idxs = list(range(gi, gj))                 # global indices of this session
        gi = gj
        prev = prev_of.get(pd.Timestamp(day))
        if prev is None or len(idxs) < 20 or idxs[0] < HISTORY_CANDLES // 4:
            continue
        levels = compute_pivot_levels(prev["high"], prev["low"], prev["close"],
                                      formula=formula or settings.PIVOT_FORMULA)
        # session candles that may still be traded (before the forced exit)
        live_idxs = [g for g in idxs if candles[g].timestamp.time() < FORCE_EXIT]

        trades_today, pos = 0, 0
        while pos < len(live_idxs) and trades_today < max_trades:
            g = live_idxs[pos]
            c = candles[g]
            if c.timestamp.time() >= NO_NEW_ENTRY:
                break
            hist = candles[max(0, g + 1 - HISTORY_CANDLES): g + 1]
            setup = find_pivot_setup(hist, levels, **kw)
            if setup is None:
                pos += 1
                continue
            later = [candles[x] for x in live_idxs[pos + 1:]]
            if not later:
                break
            base = live_idxs[pos + 1]

            def atr_after(j, _base=base):
                return atr_at(candles[max(0, _base + j + 1 - HISTORY_CANDLES): _base + j + 1],
                              period=settings.PIVOT_ATR_PERIOD)

            trade, exit_j = simulate_trade(setup, later, atr_after, mkw, day)
            out.append(trade)
            trades_today += 1
            pos = pos + 1 + exit_j + 1
    return pd.DataFrame([t.__dict__ for t in out])


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

def _ci(r: pd.Series, reps: int = 3000, seed: int = 1) -> tuple[float, float]:
    if len(r) < 5:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    v = r.to_numpy()
    b = [rng.choice(v, len(v)).mean() for _ in range(reps)]
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def report(results: dict[str, pd.DataFrame], feats: pd.DataFrame) -> str:
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 40)
    lines: list[str] = []

    def sec(title: str, df: pd.DataFrame) -> None:
        lines.append(f"\n=== {title} ===")
        lines.append(df.to_string())

    rows = {}
    for name, t in results.items():
        s = _stats(t["r"]) if len(t) else _stats(pd.Series(dtype=float))
        lo, hi = _ci(t["r"]) if len(t) else (np.nan, np.nan)
        s.update({"ci_lo": round(lo, 3), "ci_hi": round(hi, 3),
                  "pts/trade": round(t["pts"].mean(), 1) if len(t) else np.nan,
                  "days": t["date"].nunique() if len(t) else 0})
        rows[name] = s
    sec("Overall by variant (R = pts / signal risk, before costs)", pd.DataFrame(rows).T)

    live = results.get("LIVE")
    if live is not None and len(live):
        t = live.copy()
        t["date"] = pd.to_datetime(t["date"]).dt.date
        sec("LIVE config — by entry mode", pd.DataFrame(
            {m: _stats(g["r"]) for m, g in t.groupby("mode")}).T)
        sec("LIVE config — by side", pd.DataFrame(
            {s: _stats(g["r"]) for s, g in t.groupby("side")}).T)
        sec("LIVE config — exit reason (count / avgR)", t.groupby("reason")["r"]
            .agg(["count", "mean"]).round(3))
        sec("LIVE config — final stage reached (count / avgR)", t.groupby("stage")["r"]
            .agg(["count", "mean"]).round(3))
        m = t.merge(feats[["date", "day_type", "vol_class", "open_pos", "width_pct",
                           "width_rank"]], on="date", how="left")
        m["width_bucket"] = pd.cut(m["width_rank"], [-0.1, 33.3, 66.7, 100.1],
                                   labels=["NARROW", "NORMAL", "WIDE"])
        for col, title in (("day_type", "day type"), ("open_pos", "open vs CPR"),
                           ("width_bucket", "CPR width bucket"), ("vol_class", "volatility class")):
            sec(f"LIVE config — by {title}", pd.DataFrame(
                {str(k): _stats(g["r"]) for k, g in m.groupby(col, observed=True)}).T)
        dates = sorted(t["date"].unique())
        if dates:
            mid = dates[len(dates) // 2]
            t["half"] = np.where(t["date"] < mid, "H1", "H2")
            sec("LIVE config — stability by half-sample", pd.DataFrame(
                {h: _stats(g["r"]) for h, g in t.groupby("half")}).T)

    stab = {}
    for name, t in results.items():
        if len(t):
            d = pd.to_datetime(t["date"])
            mid = d.sort_values().iloc[len(d) // 2]
            stab[name] = {"avgR_H1": round(t.loc[d < mid, "r"].mean(), 3),
                          "avgR_H2": round(t.loc[d >= mid, "r"].mean(), 3)}
    sec("Stability — avgR by half-sample, all variants", pd.DataFrame(stab).T)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Backtest the live pivot strategy")
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--daily")
    ap.add_argument("--intraday")
    ap.add_argument("--variants", default=",".join(VARIANT_OVERRIDES))
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    daily, m5 = load_data(args.days, args.refresh, args.daily, args.intraday)
    feats = build_features(daily, m5)

    results: dict[str, pd.DataFrame] = {}
    for name in [v.strip() for v in args.variants.split(",") if v.strip()]:
        if name not in VARIANT_OVERRIDES:
            raise SystemExit(f"unknown variant {name!r}; choose from {list(VARIANT_OVERRIDES)}")
        results[name] = backtest_variant(daily, m5, VARIANT_OVERRIDES[name])
        print(f"  {name}: {len(results[name])} trades", flush=True)

    print(report(results, feats))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, t in results.items():
        t.to_csv(OUT_DIR / f"pivot_backtest_{name}.csv", index=False)
    print(f"\nTrade logs written to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
