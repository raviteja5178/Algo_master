"""
Safety and reconciliation manager.

Compares bot-expected state with actual Zerodha state.
On mismatch: halts new entries, logs, raises alert.
"""

from __future__ import annotations

import logging

from broker.position_repository import get_net_position_qty
from utils.logging_config import log_event

logger = logging.getLogger(__name__)


class SafetyManager:
    def __init__(self, state_machine) -> None:  # type: ignore[type-arg]
        self._sm = state_machine
        self._mismatch_detected = False

    def reconcile_position(
        self,
        tradingsymbol: str,
        expected_qty: int,
    ) -> bool:
        """
        Compare bot-expected quantity with broker-reported quantity.
        Returns True if they match; False (and halts) if they don't.
        """
        if tradingsymbol is None:
            return True  # nothing to reconcile

        actual_qty = get_net_position_qty(tradingsymbol)

        if actual_qty is None:
            # Broker API unavailable — cannot confirm position; treat as mismatch
            # to be safe rather than silently assuming position exists.
            log_event(
                logger, "POSITION_MISMATCH",
                symbol=tradingsymbol, expected=expected_qty, actual="API_ERROR",
            )
            self._mismatch_detected = True
            self._sm.force_halt(
                reason=f"Broker API unavailable during reconciliation for {tradingsymbol}"
            )
            return False

        if actual_qty == expected_qty:
            log_event(
                logger, "POSITION_RECONCILED",
                symbol=tradingsymbol, expected=expected_qty, actual=actual_qty,
            )
            self._mismatch_detected = False
            return True

        log_event(
            logger, "POSITION_MISMATCH",
            symbol=tradingsymbol, expected=expected_qty, actual=actual_qty,
        )
        self._mismatch_detected = True
        self._sm.force_halt(
            reason=f"Position mismatch: expected {expected_qty}, got {actual_qty} for {tradingsymbol}"
        )
        return False

    def is_mismatch(self) -> bool:
        return self._mismatch_detected

    def clear_mismatch(self) -> None:
        self._mismatch_detected = False
