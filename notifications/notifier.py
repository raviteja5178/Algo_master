"""
Notification dispatcher.

Writes structured events to the log (mandatory).
Optional adapters (Telegram, email) can be enabled via config without
touching the critical execution path — notifications are best-effort.
"""

from __future__ import annotations

import logging
from typing import Any

from utils.logging_config import log_event

logger = logging.getLogger(__name__)

# Valid event names (from Section 25 of PROJECT.md)
EVENTS = {
    "CE_SIGNAL", "PE_SIGNAL", "ENTRY_SENT", "ENTRY_FILLED", "ENTRY_REJECTED",
    "INITIAL_SL_PLACED", "BREAK_EVEN_ACTIVATED", "TRAILING_SL_UPDATED",
    "STOP_HIT", "FORCED_EOD_EXIT", "EXIT_FILLED", "POSITION_RECONCILED",
    "POSITION_MISMATCH", "API_ERROR", "BOT_HALTED",
    "REGIME_HEURISTIC", "ITM_FALLBACK_SELECTED",
}


class Notifier:
    """
    Emit trade events to all registered adapters.
    Failures in adapters are caught and logged — never propagated.
    """

    def __init__(self) -> None:
        self._adapters: list[Any] = []

    def register(self, adapter: Any) -> None:
        self._adapters.append(adapter)

    def notify(self, event: str, **fields: Any) -> None:
        log_event(logger, event, **fields)
        for adapter in self._adapters:
            try:
                adapter.send(event, **fields)
            except Exception as exc:
                logger.warning("Notification adapter error (%s): %s", type(adapter).__name__, exc)


# Module-level singleton
_notifier = Notifier()


def notify(event: str, **fields: Any) -> None:
    _notifier.notify(event, **fields)


def register_adapter(adapter: Any) -> None:
    _notifier.register(adapter)
