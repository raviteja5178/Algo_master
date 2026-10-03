"""
Protective stop order placement and management.

Placed immediately after entry confirmation.
Tracks the live broker stop order ID and handles modification + failure.
"""

from __future__ import annotations

import logging

from utils.logging_config import log_event
from utils.price_utils import round_to_tick

logger = logging.getLogger(__name__)


class ProtectiveStop:
    """
    Manages the protective stop for a single open trade.

    Works with any broker adapter that implements:
        place_stop_order(symbol, qty, trigger_price) -> order_id
        modify_stop_order(order_id, new_trigger_price) -> bool
        cancel_order(order_id) -> bool
        get_order_status(order_id) -> str | None
    """

    def __init__(
        self,
        broker,
        tradingsymbol: str,
        quantity: int,
        entry_price: float,
        initial_sl_points: float = 30.0,
    ) -> None:
        self.broker = broker
        self.tradingsymbol = tradingsymbol
        self.quantity = quantity
        self.entry_price = entry_price
        self.initial_sl_price = round_to_tick(entry_price - initial_sl_points)
        self.order_id: str | None = None
        self.current_stop: float = self.initial_sl_price

    def place(self) -> str:
        """Place the initial protective stop order. Returns the broker order_id."""
        self.order_id = self.broker.place_stop_order(
            self.tradingsymbol,
            self.quantity,
            self.initial_sl_price,
        )
        log_event(
            logger, "INITIAL_SL_PLACED",
            symbol=self.tradingsymbol, sl=self.initial_sl_price, order_id=self.order_id,
        )
        return self.order_id

    def modify(self, new_stop: float, max_retries: int = 3) -> bool:
        """
        Modify the broker stop order to new_stop.
        Returns True on success.
        """
        if not self.order_id:
            logger.error("No stop order ID to modify.")
            return False

        if new_stop <= self.current_stop:
            logger.debug("Skipping SL modify — new stop %.2f not above current %.2f",
                         new_stop, self.current_stop)
            return False

        new_stop = round_to_tick(new_stop)

        for attempt in range(1, max_retries + 1):
            status = self.broker.get_order_status(self.order_id)
            if status not in ("TRIGGER PENDING", "OPEN", None):
                logger.warning("Stop order %s has unexpected status %s; cannot modify.",
                               self.order_id, status)
                return False

            ok = self.broker.modify_stop_order(self.order_id, new_stop)
            if ok:
                self.current_stop = new_stop
                return True

            logger.warning("SL modify attempt %d/%d failed.", attempt, max_retries)

        logger.error(
            "Failed to modify stop order %s after %d attempts.", self.order_id, max_retries
        )
        return False

    def cancel(self) -> bool:
        if not self.order_id:
            return False
        return self.broker.cancel_order(self.order_id)
