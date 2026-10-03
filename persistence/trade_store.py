"""
High-level trade store facade — single import point for persistence ops.
"""

from persistence.models import (
    fetch_active_trade,
    fetch_shadow_trade_dates,
    fetch_shadow_trades,
    fetch_today_realised_pnl,
    fetch_trade,
    has_action,
    has_processed_signal,
    init_db,
    mark_trade_closed,
    mark_trade_closed_with_reason,
    record_action,
    record_processed_signal,
    update_action_status,
    upsert_trade,
)

__all__ = [
    "init_db",
    "upsert_trade",
    "fetch_active_trade",
    "fetch_today_realised_pnl",
    "fetch_trade",
    "mark_trade_closed",
    "mark_trade_closed_with_reason",
    "fetch_shadow_trades",
    "fetch_shadow_trade_dates",
    "has_processed_signal",
    "record_processed_signal",
    "has_action",
    "record_action",
    "update_action_status",
]
