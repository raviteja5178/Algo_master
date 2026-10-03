"""
Paper trading broker adapter.

Simulates order placement, fill confirmation, stop-loss orders, and exits
using real market data without sending any order to Zerodha.

Interface matches the live OrderManager so the rest of the bot is agnostic
to which adapter is active.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import TypedDict

from utils.logging_config import log_event
from utils.time_utils import IST

logger = logging.getLogger(__name__)


class FillResult(TypedDict):
    order_id: str
    status: str          # COMPLETE | REJECTED | PARTIAL
    filled_qty: int
    average_price: float


class PaperBroker:
    """
    Simulates a broker.  All fills are assumed instant at LTP.

    State:
      - positions: {tradingsymbol: qty}
      - open_orders: {order_id: dict}
    """

    def __init__(self) -> None:
        self._positions: dict[str, int] = {}
        self._open_orders: dict[str, dict] = {}
        self._last_ltp: dict[str, float] = {}

    # ── Price feed ─────────────────────────────────────────────────────────────

    def update_ltp(self, tradingsymbol: str, ltp: float) -> None:
        self._last_ltp[tradingsymbol] = ltp
        self._check_stops(tradingsymbol, ltp)

    # ── Order placement ────────────────────────────────────────────────────────

    def place_buy_order(
        self,
        tradingsymbol: str,
        quantity: int,
        exchange: str = "BFO",
        ltp_hint: float | None = None,
    ) -> FillResult:
        order_id = f"PAPER_{uuid.uuid4().hex[:8].upper()}"
        # Use the explicitly passed ltp_hint (e.g. SENSEX LTP at signal time) if
        # provided; otherwise fall back to the last polled LTP for this symbol.
        ltp = ltp_hint if ltp_hint is not None and ltp_hint > 0 else self._last_ltp.get(tradingsymbol, 0.0)
        self._positions[tradingsymbol] = self._positions.get(tradingsymbol, 0) + quantity
        log_event(
            logger, "ENTRY_FILLED",
            mode="PAPER", symbol=tradingsymbol, qty=quantity, fill=ltp, order_id=order_id,
        )
        return {
            "order_id": order_id,
            "status": "COMPLETE",
            "filled_qty": quantity,
            "average_price": ltp,
        }

    def place_sell_order(
        self,
        tradingsymbol: str,
        quantity: int,
        exchange: str = "BFO",
        tag: str = "",
        ltp_hint: float | None = None,
    ) -> FillResult:
        """
        Simulate a market SELL.

        Pre-sell guard mirrors the live OrderManager:
          - actual qty <= 0 → raise RuntimeError (no position; would create naked short).
          - actual qty < quantity → cap to actual qty and log PRE_SELL_QTY_MISMATCH.
        """
        # ── Pre-sell position guard ────────────────────────────────────────────
        actual_qty = self._positions.get(tradingsymbol, 0)
        if actual_qty <= 0:
            log_event(
                logger, "PRE_SELL_QTY_MISMATCH",
                mode="PAPER", symbol=tradingsymbol, expected=quantity, actual=actual_qty,
                tag=tag, action="HALT — no position to sell",
            )
            raise RuntimeError(
                f"PRE_SELL_QTY_MISMATCH: expected {quantity} but paper broker reports "
                f"{actual_qty} for {tradingsymbol}. SELL aborted to prevent naked short."
            )
        if actual_qty < quantity:
            log_event(
                logger, "PRE_SELL_QTY_MISMATCH",
                mode="PAPER", symbol=tradingsymbol, expected=quantity, actual=actual_qty,
                tag=tag, action=f"CAPPED sell qty to {actual_qty}",
            )
            quantity = actual_qty

        order_id = f"PAPER_{uuid.uuid4().hex[:8].upper()}"
        ltp = ltp_hint if ltp_hint is not None and ltp_hint > 0 else self._last_ltp.get(tradingsymbol, 0.0)
        self._positions[tradingsymbol] = actual_qty - quantity
        log_event(
            logger, "EXIT_FILLED",
            mode="PAPER", symbol=tradingsymbol, qty=quantity, fill=ltp,
            order_id=order_id, tag=tag,
        )
        return {
            "order_id": order_id,
            "status": "COMPLETE",
            "filled_qty": quantity,
            "average_price": ltp,
        }

    def place_stop_order(
        self,
        tradingsymbol: str,
        quantity: int,
        trigger_price: float,
        exchange: str = "BFO",
    ) -> str:
        order_id = f"PAPER_SL_{uuid.uuid4().hex[:8].upper()}"
        self._open_orders[order_id] = {
            "type": "SL",
            "tradingsymbol": tradingsymbol,
            "quantity": quantity,
            "trigger_price": trigger_price,
            "status": "TRIGGER PENDING",
        }
        log_event(
            logger, "INITIAL_SL_PLACED",
            mode="PAPER", symbol=tradingsymbol, sl=trigger_price, order_id=order_id,
        )
        return order_id

    def modify_stop_order(self, order_id: str, new_trigger_price: float) -> bool:
        order = self._open_orders.get(order_id)
        if not order or order["status"] != "TRIGGER PENDING":
            logger.warning("Cannot modify paper SL %s — not found or not pending", order_id)
            return False
        old = order["trigger_price"]
        if new_trigger_price <= old:
            logger.warning("Refusing to lower SL from %.2f to %.2f", old, new_trigger_price)
            return False
        order["trigger_price"] = new_trigger_price
        log_event(
            logger, "TRAILING_SL_UPDATED",
            mode="PAPER", order_id=order_id, old_sl=old, new_sl=new_trigger_price,
        )
        return True

    def cancel_order(self, order_id: str) -> bool:
        order = self._open_orders.get(order_id)
        if order is None:
            return False
        # Only cancel orders that are still pending — do not discard a
        # COMPLETE SL order so get_order_status() can still read its status.
        if order["status"] == "TRIGGER PENDING":
            self._open_orders.pop(order_id)
            logger.info("Paper order %s cancelled.", order_id)
            return True
        logger.warning(
            "Paper cancel_order %s ignored — order is already %s.",
            order_id, order["status"],
        )
        return False

    def get_position_qty(self, tradingsymbol: str) -> int:
        return self._positions.get(tradingsymbol, 0)

    def get_order_status(self, order_id: str) -> str | None:
        order = self._open_orders.get(order_id)
        return order["status"] if order else None

    # ── Internal stop-loss simulation ──────────────────────────────────────────

    def _check_stops(self, tradingsymbol: str, ltp: float) -> None:
        for order_id, order in list(self._open_orders.items()):
            if (
                order["type"] == "SL"
                and order["tradingsymbol"] == tradingsymbol
                and order["status"] == "TRIGGER PENDING"
                and ltp <= order["trigger_price"]
            ):
                order["status"] = "COMPLETE"
                # NOTE: do NOT remove the position here.
                # The bot's exit path calls place_sell_order() after seeing the
                # STOP_HIT, and place_sell_order() does its own pre-sell guard
                # and position decrement.  Removing the position here first would
                # cause PRE_SELL_QTY_MISMATCH (qty=0) and a RuntimeError in
                # place_sell_order, leaving the logical position un-exited.
                log_event(
                    logger, "STOP_HIT",
                    mode="PAPER", symbol=tradingsymbol,
                    sl=order["trigger_price"], ltp=ltp, order_id=order_id,
                )
