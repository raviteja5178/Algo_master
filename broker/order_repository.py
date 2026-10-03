"""
Order and position repository — thin wrappers over the KiteConnect REST API
for reading open orders and current positions.
"""

from __future__ import annotations

import logging

from broker.kite_client import get_kite

logger = logging.getLogger(__name__)


def get_open_orders() -> list[dict]:
    try:
        return [o for o in get_kite().orders() if o["status"] not in ("COMPLETE", "REJECTED", "CANCELLED")]
    except Exception as exc:
        logger.error("get_open_orders error: %s", exc)
        return []


def get_day_positions() -> list[dict]:
    try:
        return get_kite().positions().get("day", [])
    except Exception as exc:
        logger.error("get_day_positions error: %s", exc)
        return []
