"""
Expiry-day iron butterfly -- pure logic (no I/O).

On a SENSEX weekly expiry day:
    sell ATM CE + ATM PE, buy CE/PE `wing` points further out (the wings cap
    the loss).  Stop when the cost of buying the whole position back reaches
    credit * (1 + stop_pct); otherwise close at the exit time.

Prices come from real quotes: shorts are SOLD at the bid and BOUGHT BACK at the
ask, wings are BOUGHT at the ask and SOLD at the bid, so spread and slippage
are paid in the simulation exactly where they would be paid live.  Stop
monitoring uses mid prices so a wide spread alone cannot trigger it.

Leg order in every tuple/dict: SC (short call), SP (short put),
LC (long call), LP (long put).
"""

from __future__ import annotations

from dataclasses import dataclass

LEGS = ("SC", "SP", "LC", "LP")
STRIKE_STEP = 100
MIN_PX = 0.05


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float
    last: float

    @classmethod
    def from_kite(cls, q: dict) -> "Quote":
        depth = q.get("depth") or {}
        buy, sell = depth.get("buy") or [], depth.get("sell") or []
        bid = float((buy[0] or {}).get("price", 0) or 0) if buy else 0.0
        ask = float((sell[0] or {}).get("price", 0) or 0) if sell else 0.0
        return cls(bid=bid, ask=ask, last=float(q.get("last_price", 0) or 0))

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.last

    def buy_px(self, extra: float = 0.0) -> float:
        """Price paid to buy: the ask (last traded if no ask) plus slippage."""
        return round(max(MIN_PX, (self.ask if self.ask > 0 else self.last) + extra), 2)

    def sell_px(self, extra: float = 0.0) -> float:
        """Price received to sell: the bid (floor price if no bid) minus slippage."""
        base = self.bid if self.bid > 0 else MIN_PX
        return round(max(MIN_PX, base - extra), 2)

    def usable_for_buy(self) -> bool:
        return (self.ask > 0 or self.last > 0)

    def usable_for_sell(self) -> bool:
        return self.bid > 0


def pick_strikes(spot: float, wing: int) -> dict[str, tuple[int, str]]:
    """{'SC': (strike, 'CE'), 'SP': (strike, 'PE'), 'LC': ..., 'LP': ...} for *spot*."""
    atm = int(round(spot / STRIKE_STEP) * STRIKE_STEP)
    return {
        "SC": (atm, "CE"),
        "SP": (atm, "PE"),
        "LC": (atm + wing, "CE"),
        "LP": (atm - wing, "PE"),
    }


def entry_fills(q: dict[str, Quote], extra: float = 0.0) -> dict[str, float]:
    """Simulated entry fill per leg: shorts sold at the bid, wings bought at the ask."""
    return {
        "SC": q["SC"].sell_px(extra), "SP": q["SP"].sell_px(extra),
        "LC": q["LC"].buy_px(extra), "LP": q["LP"].buy_px(extra),
    }


def exit_fills(q: dict[str, Quote], extra: float = 0.0) -> dict[str, float]:
    """Simulated exit fill per leg: shorts bought back at the ask, wings sold at the bid."""
    return {
        "SC": q["SC"].buy_px(extra), "SP": q["SP"].buy_px(extra),
        "LC": q["LC"].sell_px(extra), "LP": q["LP"].sell_px(extra),
    }


def net_credit(fills: dict[str, float]) -> float:
    """Credit received per unit: shorts sold minus wings bought."""
    return fills["SC"] + fills["SP"] - fills["LC"] - fills["LP"]


def buyback_cost(prices: dict[str, float]) -> float:
    """Cost to close the position per unit: shorts bought back minus wings sold."""
    return prices["SC"] + prices["SP"] - prices["LC"] - prices["LP"]


def mid_value(q: dict[str, Quote]) -> float:
    """Mark-to-market buy-back cost at mid prices (used for the stop)."""
    return buyback_cost({k: q[k].mid for k in LEGS})


def stop_level(credit: float, stop_pct: float) -> float:
    return round(credit * (1.0 + stop_pct), 2)


def pnl(credit: float, exit_value: float, qty: int) -> float:
    return round((credit - exit_value) * qty, 2)
