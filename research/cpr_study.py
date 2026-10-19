"""
Offline CPR (Central Pivot Range) day-type study for SENSEX.

Question answered
-----------------
Does the CPR (known BEFORE the open) and the open/first-15-minutes position
relative to it predict whether the day will be a TRENDING day or a
RANGE-bound day, and a HIGH- or LOW-volatility day?

This script is read-only research: it imports nothing from the live trading
path except the Kite client (for data) and changes no bot behaviour.

CPR definition (from the PREVIOUS day's H / L / C)
    P  = (H + L + C) / 3
    BC = (H + L) / 2
    TC = 2P - BC          (BC / TC are re-ordered so BC <= TC)
    width = TC - BC = |2C - H - L| / 3

Note: width depends on WHERE the close sat in the range, not on how big the
range was.  That is why the study also looks at previous-day range vs daily
ATR and the gap, to separate "narrow CPR after a quiet day" from "narrow CPR
after a big day".

Pre-open features (no look-ahead)
    width_pct        CPR width as % of P
    width_rank       percentile of width_pct vs the previous N days (0-100)
    cpr_rel          HIGHER / LOWER / OVERLAP_UP / OVERLAP_DOWN vs yesterday's CPR
    prev_range_atr   yesterday's range / daily ATR(14)
    open_pos         ABOVE_TC / INSIDE / BELOW_BC
    gap_atr          |open - prev close| / daily ATR(14)

Early (09:30) feature
    early_state      first three 5m closes all above TC / below BC / MIXED

Outcomes (measured over the full session)
    range_atr        (day high - day low) / daily ATR       -> volatility
    efficiency       |close - open| / (high - low)          -> trendiness
    day_type         TREND (eff >= 0.5) / RANGE (eff < 0.25) / MIXED
    vol_class        HIGH (range_atr >= 1.2) / LOW (< 0.8) / NORMAL
    outside_share    share of 5m closes outside [BC, TC]
    side_flips       times price closed on the opposite side of the band
    post_edge_atr    after 09:30: (max up-move - max down-move) / ATR

Usage
    python -m research.cpr_study --days 400
    python -m research.cpr_study --days 400 --refresh        # re-download
    python -m research.cpr_study --daily d.csv --intraday m5.csv   # offline

CSV formats (columns): daily  -> date,open,high,low,close
                       5m     -> timestamp,open,high,low,close
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SENSEX_TOKEN = 265
DATA_DIR = Path(__file__).resolve().parent / "data"
OUT_DIR = Path(__file__).resolve().parent / "output"

ATR_PERIOD = 14
RANK_LOOKBACK = 60          # trading days used for the width percentile
MIN_RANK_HISTORY = 20       # days of history required before ranking
TREND_EFF = 0.5
RANGE_EFF = 0.25
HIGH_VOL_ATR = 1.2
LOW_VOL_ATR = 0.8
KITE_5M_CHUNK_DAYS = 90     # Kite caps 5minute history at 100 days per call


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_daily(days: int) -> pd.DataFrame:
    from datetime import datetime, timedelta

    from broker.kite_client import get_kite

    kite = get_kite()
    to_dt = datetime.now()
    recs = kite.historical_data(
        SENSEX_TOKEN,
        (to_dt - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S"),
        to_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "day",
    )
    df = pd.DataFrame(recs)
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    return df[["date", "open", "high", "low", "close"]]


def _fetch_5m(days: int) -> pd.DataFrame:
    from datetime import datetime, timedelta

    from broker.kite_client import get_kite

    kite = get_kite()
    end = datetime.now()
    start = end - timedelta(days=days)
    frames = []
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=KITE_5M_CHUNK_DAYS), end)
        recs = kite.historical_data(
            SENSEX_TOKEN,
            cur.strftime("%Y-%m-%d %H:%M:%S"),
            nxt.strftime("%Y-%m-%d %H:%M:%S"),
            "5minute",
        )
        if recs:
            frames.append(pd.DataFrame(recs))
        cur = nxt
    if not frames:
        raise RuntimeError("Kite returned no 5-minute data")
    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df.drop_duplicates("timestamp").sort_values("timestamp")
    return df[["timestamp", "open", "high", "low", "close"]]


def load_data(
    days: int,
    refresh: bool,
    daily_csv: str | None,
    intraday_csv: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (daily, intraday_5m).  Explicit CSVs win; else cache; else Kite."""
    if daily_csv and intraday_csv:
        daily = pd.read_csv(daily_csv, parse_dates=["date"])
        m5 = pd.read_csv(intraday_csv, parse_dates=["timestamp"])
        return daily, m5

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    d_path, m_path = DATA_DIR / "sensex_daily.csv", DATA_DIR / "sensex_5m.csv"
    if not refresh and d_path.exists() and m_path.exists():
        logger.info("Using cached data in %s", DATA_DIR)
        return (pd.read_csv(d_path, parse_dates=["date"]),
                pd.read_csv(m_path, parse_dates=["timestamp"]))

    logger.info("Downloading %d days of SENSEX data from Kite...", days)
    daily, m5 = _fetch_daily(days), _fetch_5m(days)
    daily.to_csv(d_path, index=False)
    m5.to_csv(m_path, index=False)
    return daily, m5


# ─────────────────────────────────────────────────────────────────────────────
# Pure feature functions
# ─────────────────────────────────────────────────────────────────────────────

def cpr_levels(high: float, low: float, close: float) -> tuple[float, float, float]:
    """Return (BC, P, TC) with BC <= TC."""
    p = (high + low + close) / 3.0
    mid = (high + low) / 2.0
    other = 2.0 * p - mid
    return min(mid, other), p, max(mid, other)


def cpr_relation(bc: float, tc: float, prev_bc: float, prev_tc: float) -> str:
    """Relation of today's CPR to the previous day's CPR."""
    if bc > prev_tc:
        return "HIGHER"
    if tc < prev_bc:
        return "LOWER"
    return "OVERLAP_UP" if (bc + tc) >= (prev_bc + prev_tc) else "OVERLAP_DOWN"


def open_position(open_: float, bc: float, tc: float) -> str:
    if open_ > tc:
        return "ABOVE_TC"
    if open_ < bc:
        return "BELOW_BC"
    return "INSIDE"


def early_state(closes: list[float], bc: float, tc: float) -> str:
    """State of the first three 5m closes relative to the CPR band."""
    if len(closes) < 3:
        return "NA"
    first3 = closes[:3]
    if all(c > tc for c in first3):
        return "ABOVE"
    if all(c < bc for c in first3):
        return "BELOW"
    return "MIXED"


def band_sides(closes: list[float], bc: float, tc: float) -> list[int]:
    """+1 above TC, -1 below BC, 0 inside the band."""
    return [1 if c > tc else -1 if c < bc else 0 for c in closes]


def count_side_flips(sides: list[int]) -> int:
    """Times price went from one side of the band to the other (inside ignored)."""
    nz = [s for s in sides if s != 0]
    return sum(1 for a, b in zip(nz, nz[1:]) if a != b)


def classify_day(efficiency: float, range_atr: float) -> tuple[str, str]:
    if efficiency >= TREND_EFF:
        day_type = "TREND"
    elif efficiency < RANGE_EFF:
        day_type = "RANGE"
    else:
        day_type = "MIXED"
    if range_atr >= HIGH_VOL_ATR:
        vol = "HIGH"
    elif range_atr < LOW_VOL_ATR:
        vol = "LOW"
    else:
        vol = "NORMAL"
    return day_type, vol


def _daily_atr(daily: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    prev_close = daily["close"].shift(1)
    tr = pd.concat(
        [daily["high"] - daily["low"],
         (daily["high"] - prev_close).abs(),
         (daily["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


# ─────────────────────────────────────────────────────────────────────────────
# Feature table
# ─────────────────────────────────────────────────────────────────────────────

def build_features(
    daily: pd.DataFrame,
    m5: pd.DataFrame,
    rank_lookback: int = RANK_LOOKBACK,
) -> pd.DataFrame:
    """One row per trading day that has both a prior-2-day history and 5m data."""
    daily = daily.sort_values("date").reset_index(drop=True).copy()
    daily["date"] = pd.to_datetime(daily["date"]).dt.normalize()
    daily["atr"] = _daily_atr(daily)

    # CPR for every day, built from the day BEFORE it.
    bcs, ps, tcs = [], [], []
    for i in range(len(daily)):
        if i == 0:
            bcs.append(np.nan); ps.append(np.nan); tcs.append(np.nan)
            continue
        r = daily.iloc[i - 1]
        bc, p, tc = cpr_levels(r["high"], r["low"], r["close"])
        bcs.append(bc); ps.append(p); tcs.append(tc)
    daily["bc"], daily["p"], daily["tc"] = bcs, ps, tcs
    daily["width_pct"] = (daily["tc"] - daily["bc"]) / daily["p"] * 100.0

    m5 = m5.copy()
    m5["timestamp"] = pd.to_datetime(m5["timestamp"])
    m5["date"] = m5["timestamp"].dt.normalize()
    m5 = m5[(m5["timestamp"].dt.time >= pd.Timestamp("09:15").time())
            & (m5["timestamp"].dt.time <= pd.Timestamp("15:25").time())]
    by_day = {d: g.sort_values("timestamp") for d, g in m5.groupby("date")}

    rows = []
    for i in range(2, len(daily)):
        row, prev = daily.iloc[i], daily.iloc[i - 1]
        day = row["date"]
        g = by_day.get(day)
        if g is None or len(g) < 20 or np.isnan(prev["atr"]):
            continue
        atr = float(prev["atr"])          # ATR through the prior day: no look-ahead
        bc, p, tc = float(row["bc"]), float(row["p"]), float(row["tc"])
        prev_bc, prev_tc = float(prev["bc"]), float(prev["tc"])

        hist = daily["width_pct"].iloc[max(0, i - rank_lookback):i].dropna()
        width_rank = (float((hist <= row["width_pct"]).mean() * 100.0)
                      if len(hist) >= MIN_RANK_HISTORY else np.nan)

        o = float(g["open"].iloc[0])
        h, l, c = float(g["high"].max()), float(g["low"].min()), float(g["close"].iloc[-1])
        rng = h - l
        if rng <= 0:
            continue
        closes = g["close"].tolist()
        sides = band_sides(closes, bc, tc)
        eff = abs(c - o) / rng
        range_atr = rng / atr
        day_type, vol_class = classify_day(eff, range_atr)

        c3 = closes[2]
        after = g.iloc[3:]
        post_up = float(after["high"].max() - c3) if len(after) else 0.0
        post_dn = float(c3 - after["low"].min()) if len(after) else 0.0

        rows.append({
            "date": day.date(),
            "bc": round(bc, 2), "p": round(p, 2), "tc": round(tc, 2),
            "width_pct": float(row["width_pct"]),
            "width_rank": width_rank,
            "cpr_rel": cpr_relation(bc, tc, prev_bc, prev_tc),
            "prev_range_atr": float((prev["high"] - prev["low"]) / atr),
            "open": o,
            "open_pos": open_position(o, bc, tc),
            "gap_atr": abs(o - float(prev["close"])) / atr,
            "early_state": early_state(closes, bc, tc),
            "range_pct": rng / o * 100.0,
            "range_atr": range_atr,
            "efficiency": eff,
            "day_type": day_type,
            "vol_class": vol_class,
            "outside_share": float(np.mean([s != 0 for s in sides])),
            "side_flips": count_side_flips(sides),
            "post_edge_atr": (post_up - post_dn) / atr,
            "day_dir": 1 if c > o else -1,
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Analysis / reporting
# ─────────────────────────────────────────────────────────────────────────────

def add_buckets(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["width_bucket"] = pd.cut(
        df["width_rank"], [-0.1, 33.3, 66.7, 100.1],
        labels=["NARROW", "NORMAL", "WIDE"],
    )
    return df


def summarise(df: pd.DataFrame, by: str | list[str]) -> pd.DataFrame:
    g = df.groupby(by, observed=True)
    out = pd.DataFrame({
        "n": g.size(),
        "range_atr": g["range_atr"].mean(),
        "range_pct": g["range_pct"].mean(),
        "efficiency": g["efficiency"].mean(),
        "%TREND": g["day_type"].apply(lambda s: (s == "TREND").mean() * 100),
        "%RANGE": g["day_type"].apply(lambda s: (s == "RANGE").mean() * 100),
        "%HIGHVOL": g["vol_class"].apply(lambda s: (s == "HIGH").mean() * 100),
        "outside%": g["outside_share"].mean() * 100,
        "flips": g["side_flips"].mean(),
    })
    return out.round(2)


def rank_correlations(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["width_rank", "prev_range_atr", "gap_atr",
            "range_atr", "efficiency", "outside_share", "side_flips"]
    ranked = df[cols].dropna().rank()
    return ranked.corr().loc[
        ["width_rank", "prev_range_atr", "gap_atr"],
        ["range_atr", "efficiency", "outside_share", "side_flips"],
    ].round(3)


def early_direction_edge(df: pd.DataFrame) -> pd.DataFrame:
    """After 09:30: does the early ABOVE/BELOW state keep paying in its direction?"""
    sub = df[df["early_state"].isin(["ABOVE", "BELOW"])].copy()
    sign = np.where(sub["early_state"] == "ABOVE", 1, -1)
    sub["directional_edge_atr"] = sub["post_edge_atr"] * sign
    sub["continued"] = sub["directional_edge_atr"] > 0
    g = sub.groupby(["early_state", "width_bucket"], observed=True)
    return pd.DataFrame({
        "n": g.size(),
        "%continued": g["continued"].mean() * 100,
        "edge_atr": g["directional_edge_atr"].mean(),
    }).round(2)


def stability(df: pd.DataFrame) -> pd.DataFrame:
    """%TREND per width bucket in the first and second half of the sample."""
    df = df.sort_values("date").reset_index(drop=True)
    mid = len(df) // 2
    parts = {"H1": df.iloc[:mid], "H2": df.iloc[mid:]}
    out = {}
    for name, part in parts.items():
        out[name] = part.groupby("width_bucket", observed=True)["day_type"].apply(
            lambda s: (s == "TREND").mean() * 100
        )
    return pd.DataFrame(out).round(1)


def report(df: pd.DataFrame) -> str:
    df = add_buckets(df).dropna(subset=["width_rank"])
    lines: list[str] = []
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)

    def sec(title: str, body) -> None:
        lines.append(f"\n=== {title} ===")
        lines.append(body.to_string() if hasattr(body, "to_string") else str(body))

    base = {
        "days": len(df),
        "from": str(df["date"].min()), "to": str(df["date"].max()),
        "%TREND": round((df["day_type"] == "TREND").mean() * 100, 1),
        "%RANGE": round((df["day_type"] == "RANGE").mean() * 100, 1),
        "%HIGHVOL": round((df["vol_class"] == "HIGH").mean() * 100, 1),
        "avg range_atr": round(df["range_atr"].mean(), 2),
    }
    sec("Baseline (all days)", pd.Series(base))
    sec("By CPR width bucket (percentile vs previous "
        f"{RANK_LOOKBACK} days)", summarise(df, "width_bucket"))
    sec("By open position vs CPR", summarise(df, "open_pos"))
    sec("By CPR relation to previous day", summarise(df, "cpr_rel"))
    sec("By early state (first 3 closes vs CPR)", summarise(df, "early_state"))
    sec("Width bucket x open position", summarise(df, ["width_bucket", "open_pos"]))
    sec("Width bucket x early state", summarise(df, ["width_bucket", "early_state"]))
    sec("By gap size (ATR) tercile",
        summarise(df.assign(gap_bucket=pd.qcut(df["gap_atr"].rank(method="first"), 3,
                                               labels=["SMALL", "MED", "LARGE"])), "gap_bucket"))
    sec("Spearman rank correlation (pre-open feature vs outcome)", rank_correlations(df))
    sec("Direction edge after 09:30 (ATR units)", early_direction_edge(df))
    sec("Stability: %TREND per width bucket by half-sample", stability(df))
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=400, help="calendar days of history")
    ap.add_argument("--refresh", action="store_true", help="ignore cache and re-download")
    ap.add_argument("--daily", help="daily OHLC csv (date,open,high,low,close)")
    ap.add_argument("--intraday", help="5m OHLC csv (timestamp,open,high,low,close)")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    daily, m5 = load_data(args.days, args.refresh, args.daily, args.intraday)
    feats = build_features(daily, m5)
    if feats.empty:
        print("No usable days — check the input data.")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUT_DIR / "cpr_features.csv"
    feats.to_csv(out_csv, index=False)
    print(report(feats))
    print(f"\nPer-day feature table written to {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
