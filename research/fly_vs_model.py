"""
Compare the expiry-day iron butterfly's REAL entry quotes (stored by the SHADOW
runner in the fly_trades table) with the backtest's modelled prices.

For every day the runner entered, the same four contracts are re-priced with the
backtest's option model (Black-Scholes, India VIX, trading-time decay) at the
same spot, time and VIX, and the real credit is divided by the model credit.

    ratio >= 0.90   the model is close enough: the backtest edge is credible
    ratio <  0.90   real premiums are cheaper than modelled: the backtest
                    overstates the edge (it turns negative near 0.80)

Usage
    python -m research.fly_vs_model
"""

from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd

from config import settings
from persistence.trade_store import fly_all
from research.system_backtest import Contracts, MarketData, bs_price, tick_round

THRESHOLD = 0.90
MIN_DAYS = 8


def model_credit(ch: Contracts, row: dict) -> float | None:
    """Model credit per unit for the legs/spot/time/VIX stored on a fly row."""
    if not row.get("legs") or not row.get("vix_entry"):
        return None
    at = datetime.fromisoformat(row["entry_time"]).replace(tzinfo=None)
    expiry = date.fromisoformat(row["expiry"])
    years = ch.trading_years(at, expiry)
    vol = float(row["vix_entry"]) / 100.0
    total = 0.0
    for leg in json.loads(row["legs"]):
        px = tick_round(bs_price(float(row["spot_entry"]), float(leg["strike"]), years, vol, leg["type"]))
        total += px if leg["side"] == "SELL" else -px
    return round(total, 2)


def build_table() -> pd.DataFrame:
    ch = Contracts(MarketData())
    rows = []
    for r in fly_all():
        if r["status"] == "SKIPPED" or not r.get("legs"):
            continue
        m = model_credit(ch, r)
        rows.append({
            "day": r["day"], "status": r["status"], "spot": r["spot_entry"], "vix": r["vix_entry"],
            "real_credit_fill": r["credit"], "real_credit_mid": r["credit_mid"],
            "model_credit": m,
            "ratio_mid": round(r["credit_mid"] / m, 3) if m else None,
            "ratio_fill": round(r["credit"] / m, 3) if m else None,
            "exit": r.get("exit_reason"), "net_pnl": r.get("net_pnl"),
        })
    return pd.DataFrame(rows)


def main() -> None:
    print(f"Database: {settings.DB_PATH}")
    t = build_table()
    if t.empty:
        print("No fly entries recorded yet. Enable ENABLE_EXPIRY_FLY in SHADOW and wait for an expiry day.")
        return
    pd.set_option("display.width", 200)
    print(t.to_string(index=False))
    r = t.dropna(subset=["ratio_fill"])
    n = len(r)
    print(f"\nDays with a recorded entry: {n}")
    print(f"Average real/model credit ratio  (at bid/ask fills): {r.ratio_fill.mean():.3f}")
    print(f"Average real/model credit ratio  (at mid prices)   : {r.ratio_mid.mean():.3f}")
    closed = t[t.status == "CLOSED"]
    if len(closed):
        print(f"Closed trades: {len(closed)}, simulated net P&L: Rs {closed.net_pnl.sum():,.0f}")
    if n < MIN_DAYS:
        print(f"Verdict: too early - need at least {MIN_DAYS} expiry days (have {n}).")
    elif r.ratio_fill.mean() >= THRESHOLD:
        print(f"Verdict: real credit is {r.ratio_fill.mean():.0%} of the model's - the backtest assumption holds.")
    else:
        print(f"Verdict: real credit is only {r.ratio_fill.mean():.0%} of the model's - "
              "the backtest overstates the edge; do not trade it.")


if __name__ == "__main__":
    main()
