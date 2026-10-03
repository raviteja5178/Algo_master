"""
Position repository — reads live Zerodha positions.
"""

from __future__ import annotations

import logging

from broker.kite_client import get_kite

logger = logging.getLogger(__name__)


_UNAVAILABLE = object()  # sentinel: API failed, result unknown


def get_net_position_qty(tradingsymbol: str) -> int | None:
    """
    Return the net intraday quantity for *tradingsymbol*, or None if the
    broker API call failed.  Callers must treat None as "unknown" — never
    as a confirmed flat position.
    """
    try:
        positions = get_kite().positions()
        for p in positions.get("day", []):
            if p["tradingsymbol"] == tradingsymbol:
                return int(p["quantity"])
        return 0  # symbol not in positions → genuinely flat
    except Exception as exc:
        logger.error("get_net_position_qty error: %s", exc)
        return None  # unknown — do not treat as flat
