"""
Download SENSEX index history from Kite for the full-system backtest.

Writes (cached; re-run only to extend the range):
    research/data/sensex_1m_full.csv     1-minute OHLC
    research/data/sensex_daily_full.csv  daily OHLC (starts 90 days earlier, for warm-up)
    research/data/india_vix_1m_full.csv  India VIX 1-minute (implied vol for option pricing)

Kite serves at most 60 days of minute data per request, so the range is
fetched in 55-day chunks.

Usage
    python -m research.fetch_history --start 2024-01-01 --end 2026-10-16
    python -m research.fetch_history --start 2024-01-01 --end 2026-10-16 --vix-only
"""

from __future__ import annotations

import argparse
import time
from datetime import date, datetime, timedelta

import pandas as pd
from pathlib import Path

from broker.kite_client import get_kite
from market.historical_data import SENSEX_TOKEN

DATA_DIR = Path(__file__).resolve().parent / "data"
MINUTE_CSV = DATA_DIR / "sensex_1m_full.csv"
DAILY_CSV = DATA_DIR / "sensex_daily_full.csv"
VIX_CSV = DATA_DIR / "india_vix_1m_full.csv"

INDIA_VIX_TOKEN = 264969

_CHUNK_DAYS = 55


def _to_frame(records: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    return df[["timestamp", "open", "high", "low", "close"]]


def fetch_minutes(token: int, start: date, end: date, label: str) -> pd.DataFrame:
    kite = get_kite()
    frames = []
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=_CHUNK_DAYS - 1), end)
        recs = kite.historical_data(token, f"{cur} 09:15:00", f"{stop} 15:30:00", "minute")
        frames.append(_to_frame(recs))
        print(f"  {label} {cur} -> {stop}: {len(recs)} bars", flush=True)
        cur = stop + timedelta(days=1)
        time.sleep(0.4)   # Kite historical rate limit: 3 req/s
    return pd.concat(frames).drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


def fetch(start: date, end: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    kite = get_kite()
    frames = []
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=_CHUNK_DAYS - 1), end)
        recs = kite.historical_data(
            SENSEX_TOKEN, f"{cur} 09:15:00", f"{stop} 15:30:00", "minute",
        )
        frames.append(_to_frame(recs))
        print(f"  minute {cur} -> {stop}: {len(recs)} bars", flush=True)
        cur = stop + timedelta(days=1)
        time.sleep(0.4)   # Kite historical rate limit: 3 req/s
    minute = pd.concat(frames).drop_duplicates("timestamp").sort_values("timestamp")

    daily = _to_frame(kite.historical_data(
        SENSEX_TOKEN, f"{start - timedelta(days=90)} 00:00:00", f"{end} 23:59:59", "day",
    ))
    daily["date"] = daily["timestamp"].dt.date
    daily = daily[["date", "open", "high", "low", "close"]]
    return minute.reset_index(drop=True), daily.reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default=str(date.today()))
    ap.add_argument("--vix-only", action="store_true", help="only (re)fetch India VIX minutes")
    a = ap.parse_args()
    start = datetime.strptime(a.start, "%Y-%m-%d").date()
    end = datetime.strptime(a.end, "%Y-%m-%d").date()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    vix = fetch_minutes(INDIA_VIX_TOKEN, start, end, "vix")
    vix.to_csv(VIX_CSV, index=False)
    print(f"Wrote {len(vix)} India VIX minute bars -> {VIX_CSV}")
    if a.vix_only:
        return
    minute, daily = fetch(start, end)
    minute.to_csv(MINUTE_CSV, index=False)
    daily.to_csv(DAILY_CSV, index=False)
    print(f"Wrote {len(minute)} minute bars ({minute.timestamp.dt.date.nunique()} sessions) "
          f"→ {MINUTE_CSV}")
    print(f"Wrote {len(daily)} daily bars -> {DAILY_CSV}")


if __name__ == "__main__":
    main()
