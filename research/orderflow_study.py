"""
Order-flow confirmation study for the pivot strategy (research only, no live changes).

Question: does volume / open-interest on the SENSEX future at the signal candle separate
winning pivot trades from losing ones?

The SENSEX index has no volume, so the near-month future is the proxy.  Kite only lists
live contracts, so history starts when the earliest listed contract began trading
(~mid-2026) -- a small sample.  Read results as a screening test, not proof.

Features (all from CLOSED candles up to and including the signal candle; no look-ahead):
    rel_vol     signal-candle volume / median volume of the previous ``VOL_LOOKBACK`` candles
    oi_chg      OI now - OI ``OI_LOOKBACK`` candles ago   (> 0 = new positions being opened)
    flow_align  candle-direction-signed volume over the last ``OI_LOOKBACK`` candles, signed
                to the trade side (> 0 = volume on the trade's side).  A crude delta proxy,
                NOT true bid/ask delta (that needs tick data).

Usage:
    python -m research.orderflow_study            # uses cached futures data if present
    python -m research.orderflow_study --refresh  # re-download futures 5m (needs Kite login)
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from research.blueprint_sim import _stats
from research.cpr_study import DATA_DIR, OUT_DIR, load_data
from research.pivot_backtest import VARIANT_OVERRIDES, backtest_variant

logger = logging.getLogger(__name__)

VOL_LOOKBACK = 20
OI_LOOKBACK = 3
FUT_CSV = DATA_DIR / "sensex_fut_5m.csv"
FETCH_CHUNK_DAYS = 60
FETCH_MAX_CHUNKS = 8
_NO_ACCEPT_GUARDS = dict(acceptance_min_dist_atr=0.0, acceptance_min_room_r=0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

def fetch_futures_5m(end: datetime | None = None) -> pd.DataFrame:
    """Download 5m candles with volume and OI for the earliest-listed SENSEX future."""
    from broker.instrument_repository import load_instruments
    from broker.kite_client import get_kite

    kite = get_kite()
    futs = sorted(
        (i for i in load_instruments()
         if i.get("name") == "SENSEX" and i.get("instrument_type") == "FUT"),
        key=lambda x: x["expiry"],
    )
    if not futs:
        raise RuntimeError("No SENSEX futures in the instrument master")
    tok = futs[0]["instrument_token"]
    cur = end or datetime.now()
    frames = []
    for _ in range(FETCH_MAX_CHUNKS):
        start = cur - timedelta(days=FETCH_CHUNK_DAYS)
        recs = kite.historical_data(
            tok, start.strftime("%Y-%m-%d %H:%M:%S"), cur.strftime("%Y-%m-%d %H:%M:%S"),
            "5minute", oi=True,
        )
        if not recs:
            break
        frames.append(pd.DataFrame(recs))
        cur = start
    if not frames:
        raise RuntimeError("Kite returned no futures data")
    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df.drop_duplicates("timestamp").sort_values("timestamp")
    return df[["timestamp", "open", "high", "low", "close", "volume", "oi"]]


def load_futures(refresh: bool = False) -> pd.DataFrame:
    if not refresh and FUT_CSV.exists():
        return pd.read_csv(FUT_CSV, parse_dates=["timestamp"])
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = fetch_futures_5m()
    df.to_csv(FUT_CSV, index=False)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Features (pure)
# ─────────────────────────────────────────────────────────────────────────────

def orderflow_features(
    fut: pd.DataFrame,
    vol_lookback: int = VOL_LOOKBACK,
    oi_lookback: int = OI_LOOKBACK,
) -> pd.DataFrame:
    """One row per candle: rel_vol, oi_chg, signed_vol_sum.  Uses only data up to that candle."""
    f = fut.sort_values("timestamp").reset_index(drop=True).copy()
    # median of the PREVIOUS candles only (shift) so the candle is not compared to itself
    base = f["volume"].shift(1).rolling(vol_lookback, min_periods=max(5, vol_lookback // 2)).median()
    f["rel_vol"] = np.where(base > 0, f["volume"] / base, np.nan)
    f["oi_chg"] = f["oi"] - f["oi"].shift(oi_lookback)
    direction = np.sign(f["close"] - f["open"])
    f["signed_vol_sum"] = (direction * f["volume"]).rolling(oi_lookback, min_periods=oi_lookback).sum()
    return f[["timestamp", "rel_vol", "oi_chg", "signed_vol_sum"]]


def attach_features(trades: pd.DataFrame, feats: pd.DataFrame) -> pd.DataFrame:
    """Join each trade to the features of its SIGNAL candle (the candle before entry_time)."""
    if trades.empty:
        return trades.assign(rel_vol=np.nan, oi_chg=np.nan, flow_align=np.nan)
    t = trades.copy()
    entry_ts = pd.to_datetime(t["date"].astype(str) + " " + t["entry_time"])
    t["signal_ts"] = entry_ts - pd.Timedelta(minutes=5)
    t = t.merge(feats, left_on="signal_ts", right_on="timestamp", how="left")
    sign = np.where(t["side"] == "CE", 1.0, -1.0)
    t["flow_align"] = t["signed_vol_sum"] * sign
    return t.drop(columns=["timestamp"])


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

def _bucket_table(t: pd.DataFrame) -> pd.DataFrame:
    """Overall stats, then each rule's KEPT and REJECTED trades."""
    rules = {
        "rel_vol >= 1.0": t["rel_vol"] >= 1.0,
        "rel_vol >= 1.5": t["rel_vol"] >= 1.5,
        "oi_chg > 0": t["oi_chg"] > 0,
        "flow_align > 0": t["flow_align"] > 0,
        "rel_vol>=1.0 & oi_chg>0": (t["rel_vol"] >= 1.0) & (t["oi_chg"] > 0),
        "rel_vol>=1.0 & flow_align>0": (t["rel_vol"] >= 1.0) & (t["flow_align"] > 0),
    }
    known = t[["rel_vol", "oi_chg", "flow_align"]].notna().all(axis=1)
    rows = {"ALL trades": _stats(t["r"])}
    for name, mask in rules.items():
        rows[f"KEEP   {name}"] = _stats(t.loc[known & mask, "r"])
        rows[f"REJECT {name}"] = _stats(t.loc[known & ~mask, "r"])
    return pd.DataFrame(rows).T


def run(refresh: bool = False, days: int = 400) -> str:
    fut = load_futures(refresh)
    feats = orderflow_features(fut)
    first = fut["timestamp"].min().normalize()

    daily, m5 = load_data(days, False, None, None)
    m5_last = pd.to_datetime(m5["timestamp"]).max().date()
    out = [f"Futures data: {len(fut)} candles, {first.date()} -> {fut['timestamp'].max().date()}, "
           f"{fut['timestamp'].dt.date.nunique()} sessions",
           f"Index 5m cache ends {m5_last} -> overlap with futures is "
           f"{first.date()} -> {m5_last}"]
    pd.set_option("display.width", 200)

    variants = {
        "LIVE (current guards)": VARIANT_OVERRIDES["LIVE"],
        "LIVE, acceptance guards off": {**VARIANT_OVERRIDES["LIVE"], **_NO_ACCEPT_GUARDS},
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for label, ov in variants.items():
        trades = backtest_variant(daily, m5, ov)
        if trades.empty:
            out.append(f"\n=== {label}: no trades ===")
            continue
        trades["date"] = pd.to_datetime(trades["date"])
        t = attach_features(trades[trades["date"] >= first].reset_index(drop=True), feats)
        out.append(f"\n=== {label}: {len(trades)} trades over the full cache, "
                   f"{len(t)} inside the futures window ===")
        out.append(f"full-cache baseline: {_stats(trades['r'])}")
        if len(t) < 5:
            out.append("too few trades in the futures window to bucket")
            continue
        out.append(_bucket_table(t).to_string())
        t.to_csv(OUT_DIR / f"orderflow_trades_{'live' if 'current' in label else 'noguard'}.csv", index=False)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Volume/OI confirmation study for pivot trades")
    ap.add_argument("--refresh", action="store_true", help="re-download futures 5m data")
    ap.add_argument("--days", type=int, default=400)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    print(run(args.refresh, args.days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
