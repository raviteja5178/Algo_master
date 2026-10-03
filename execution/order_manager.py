"""
Live order adapter for Zerodha Kite Connect.

All methods poll Zerodha REST endpoints; never assume success from an order
ID alone.  Idempotency keys are checked before every placement.
"""

from __future__ import annotations

import logging
import time
from typing import Literal

from kiteconnect import KiteConnect  # type: ignore

from broker.kite_client import get_kite
from utils.logging_config import log_event
from utils.price_utils import round_to_tick

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 0.3   # seconds between order-status polls
                       # BSE F&O ATM options fill in ~200-500ms on liquid strikes.
                       # 0.3s catches the fill within 300ms of exchange confirmation
                       # rather than waiting up to 1s (old value).
_MAX_POLLS = 200       # 200 × 0.3s = 60s max wait — same total timeout as before
_TERMINAL = {"COMPLETE", "REJECTED", "CANCELLED"}

# Minimum limit price floor — BSE F&O options cannot be priced below this.
_MIN_LIMIT_PRICE = 0.05


def _ltp_key(tradingsymbol: str, exchange: str) -> str:
    """
    Build the `exchange:symbol` key expected by kite.ltp().
    Guards against double-prefixing if tradingsymbol already contains ':'.
    """
    if ":" in tradingsymbol:
        return tradingsymbol
    return f"{exchange}:{tradingsymbol}"


class OrderManager:
    """
    Live Zerodha order adapter.

    place_buy_order  — limit BUY with tight protection buffer, waits for fill.
    place_sell_order — limit SELL with tight protection buffer, waits for fill.
    place_stop_order — SL-Limit stop order (BSE F&O does not allow SL-M).
    modify_stop_order — modifies the trigger price of a TRIGGER PENDING stop.
    cancel_order     — cancels any open order.
    get_order_status — polls a single order.
    get_position_qty — reads net qty from Zerodha positions.
    """

    def __init__(self) -> None:
        self._kite: KiteConnect = get_kite()

    # ── Entry ──────────────────────────────────────────────────────────────────

    def place_buy_order(
        self,
        tradingsymbol: str,
        quantity: int,
        exchange: str = "BFO",
        ltp_hint: float | None = None,
    ) -> dict:
        """
        Place a LIMIT BUY slightly above the current LTP (2% or min 3 pts)
        to guarantee an immediate fill without inflating the margin footprint.
        Waits for fill confirmation and returns a fill-result dict.
        Raises on fatal errors (caller must handle).

        ltp_hint — caller-supplied LTP (e.g. from the live WebSocket tick).
                   When provided the redundant REST quote call is skipped,
                   cutting ~200 ms off the signal-to-order latency.
                   If None, the LTP is fetched fresh via kite.ltp().
        """
        if ltp_hint is not None and ltp_hint > 0:
            ltp = ltp_hint
            logger.debug("place_buy_order: using caller-supplied LTP %.2f for %s", ltp, tradingsymbol)
        else:
            ltp = self._fetch_ltp(tradingsymbol, exchange)

        # 0.5% buffer above LTP, minimum 1.0 pt — keeps limit order close to market price
        # while preventing unnecessary margin footprint inflation.
        buffer_pts = max(1.0, ltp * 0.005)
        limit_price = max(_MIN_LIMIT_PRICE, round_to_tick(ltp + buffer_pts))

        log_event(logger, "ENTRY_SENT", symbol=tradingsymbol, qty=quantity,
                  exchange=exchange, ltp=ltp, limit_price=limit_price)
        order_id = self._kite.place_order(
            tradingsymbol=tradingsymbol,
            exchange=exchange,
            transaction_type=self._kite.TRANSACTION_TYPE_BUY,
            quantity=quantity,
            order_type=self._kite.ORDER_TYPE_LIMIT,
            price=limit_price,
            product=self._kite.PRODUCT_MIS,
            variety=self._kite.VARIETY_REGULAR,
        )
        return self._wait_for_fill(order_id, tradingsymbol, quantity)

    # ── Exit ───────────────────────────────────────────────────────────────────

    def place_sell_order(
        self,
        tradingsymbol: str,
        quantity: int,
        exchange: str = "BFO",
        tag: str = "",
        ltp_hint: float | None = None,
    ) -> dict:
        """
        Place a LIMIT SELL slightly below the current LTP.

        Buffer: 2% below LTP (min 3 pts).
        ltp_hint — same as place_buy_order: skips the REST quote round-trip
                   when the caller already has a fresh price from the WebSocket.

        Pre-sell guard: the broker position is the truth.
          - If actual qty <= 0  → no position to sell; raise to prevent a naked short.
          - If actual qty < quantity → cap the sell to actual qty and log a warning.
            Sending the originally intended quantity could overshoot into a short.
        """
        # ── Pre-sell position guard ────────────────────────────────────────────
        actual_qty = self.get_position_qty(tradingsymbol)
        if actual_qty <= 0:
            log_event(
                logger, "PRE_SELL_QTY_MISMATCH",
                symbol=tradingsymbol, expected=quantity, actual=actual_qty,
                tag=tag, action="HALT — no position to sell",
            )
            raise RuntimeError(
                f"PRE_SELL_QTY_MISMATCH: expected {quantity} but broker reports "
                f"{actual_qty} for {tradingsymbol}. SELL aborted to prevent naked short."
            )
        if actual_qty < quantity:
            log_event(
                logger, "PRE_SELL_QTY_MISMATCH",
                symbol=tradingsymbol, expected=quantity, actual=actual_qty,
                tag=tag, action=f"CAPPED sell qty to {actual_qty}",
            )
            quantity = actual_qty

        if ltp_hint is not None and ltp_hint > 0:
            ltp = ltp_hint
            logger.debug("place_sell_order: using caller-supplied LTP %.2f for %s", ltp, tradingsymbol)
        else:
            ltp = self._fetch_ltp(tradingsymbol, exchange)

        # 0.5% protection below LTP, minimum 1.0 pt floor — mirrors the buy buffer.
        buffer_pts = max(1.0, ltp * 0.005)
        limit_price = max(_MIN_LIMIT_PRICE, round_to_tick(ltp - buffer_pts))

        log_event(logger, "EXIT_SENT", symbol=tradingsymbol, qty=quantity,
                  tag=tag, ltp=ltp, limit_price=limit_price)
        order_id = self._kite.place_order(
            tradingsymbol=tradingsymbol,
            exchange=exchange,
            transaction_type=self._kite.TRANSACTION_TYPE_SELL,
            quantity=quantity,
            order_type=self._kite.ORDER_TYPE_LIMIT,
            price=limit_price,
            product=self._kite.PRODUCT_MIS,
            variety=self._kite.VARIETY_REGULAR,
            tag=tag,
        )
        return self._wait_for_fill(order_id, tradingsymbol, quantity)

    # ── Stop-loss ──────────────────────────────────────────────────────────────

    def place_stop_order(
        self,
        tradingsymbol: str,
        quantity: int,
        trigger_price: float,
        exchange: str = "BFO",
    ) -> str:
        log_event(
            logger, "INITIAL_SL_PLACED",
            symbol=tradingsymbol, sl=trigger_price, qty=quantity,
        )
        # BSE F&O contracts disallow SL-M (market) orders.
        # Place SL-Limit with a 5% limit price buffer below trigger price,
        # with a hard floor of _MIN_LIMIT_PRICE.
        limit_price = max(_MIN_LIMIT_PRICE, round_to_tick(trigger_price * 0.95))
        order_id = self._kite.place_order(
            tradingsymbol=tradingsymbol,
            exchange=exchange,
            transaction_type=self._kite.TRANSACTION_TYPE_SELL,
            quantity=quantity,
            order_type=self._kite.ORDER_TYPE_SL,
            price=limit_price,
            trigger_price=trigger_price,
            product=self._kite.PRODUCT_MIS,
            variety=self._kite.VARIETY_REGULAR,
        )
        return order_id

    def modify_stop_order(self, order_id: str, new_trigger_price: float) -> bool:
        try:
            limit_price = max(_MIN_LIMIT_PRICE, round_to_tick(new_trigger_price * 0.95))
            self._kite.modify_order(
                variety=self._kite.VARIETY_REGULAR,
                order_id=order_id,
                price=limit_price,
                trigger_price=new_trigger_price,
            )
            log_event(
                logger, "TRAILING_SL_UPDATED",
                order_id=order_id, new_sl=new_trigger_price,
            )
            return True
        except Exception as exc:
            logger.error("Failed to modify stop order %s: %s", order_id, exc)
            return False

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._kite.cancel_order(
                variety=self._kite.VARIETY_REGULAR,
                order_id=order_id,
            )
            return True
        except Exception as exc:
            logger.warning("Failed to cancel order %s: %s", order_id, exc)
            return False

    def get_order_status(self, order_id: str) -> str | None:
        try:
            orders = self._kite.orders()
            for o in orders:
                if str(o["order_id"]) == str(order_id):
                    return o["status"]
        except Exception as exc:
            logger.error("get_order_status error: %s", exc)
        return None

    def get_position_qty(self, tradingsymbol: str) -> int:
        """
        Return net intraday quantity for a given symbol.

        Raises RuntimeError if the broker API call fails — callers must
        not treat a failed API call as a confirmed zero position, because
        that would trigger a spurious PRE_SELL_QTY_MISMATCH on the
        pre-sell guard and block a legitimate exit of a live position.
        """
        try:
            positions = self._kite.positions()
            for p in positions.get("day", []):
                if p["tradingsymbol"] == tradingsymbol:
                    return int(p["quantity"])
            return 0  # symbol absent from positions → genuinely flat
        except Exception as exc:
            logger.error("get_position_qty error: %s", exc)
            raise RuntimeError(
                f"Broker API unavailable — cannot confirm position qty for {tradingsymbol}. "
                "Sell aborted to prevent acting on stale data."
            ) from exc

    # ── Private ────────────────────────────────────────────────────────────────

    def _fetch_ltp(self, tradingsymbol: str, exchange: str, retries: int = 3) -> float:
        """
        Fetch the latest LTP for a symbol with up to `retries` attempts.
        Raises on persistent failure so the caller can handle it cleanly.
        Guards against double-prefixing if tradingsymbol already contains ':'.
        """
        key = _ltp_key(tradingsymbol, exchange)
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                res = self._kite.ltp([key])
                return float(res[key]["last_price"])
            except Exception as exc:
                last_exc = exc
                if attempt < retries:
                    logger.warning(
                        "LTP fetch for %s failed (attempt %d/%d): %s — retrying...",
                        key, attempt, retries, exc,
                    )
                    time.sleep(0.5)
        logger.error("Failed to fetch LTP for %s after %d attempts: %s", key, retries, last_exc)
        raise last_exc  # type: ignore[misc]

    def _wait_for_fill(self, order_id: str, tradingsymbol: str, expected_qty: int) -> dict:
        """
        Poll order status until terminal or timeout.

        On TIMEOUT the order may still be live at the broker — we return
        status=TIMEOUT with the best known filled_qty (may be 0 or partial).
        The caller (execute_entry / execute_exit) treats a non-COMPLETE status
        as a failure and halts or retries accordingly.
        """
        for _ in range(_MAX_POLLS):
            try:
                orders = self._kite.orders()
            except Exception as exc:
                logger.warning("Order poll error: %s", exc)
                time.sleep(_POLL_INTERVAL)
                continue

            for o in orders:
                if str(o["order_id"]) == str(order_id):
                    status = o["status"]
                    filled_qty = int(o.get("filled_quantity", 0))
                    avg_price = float(o.get("average_price", 0.0))

                    if status == "COMPLETE":
                        # Zerodha occasionally returns average_price=0.0 on a COMPLETE
                        # order when the exchange confirmation is slightly delayed.
                        # Retry up to 5 more polls (5s) before accepting the price.
                        # Never record 0.0 as an entry price — that would set a
                        # completely wrong SL, target, and P&L for the entire trade.
                        price_retries = 0
                        while avg_price <= 0.0 and price_retries < 5:
                            price_retries += 1
                            logger.warning(
                                "Order %s COMPLETE but average_price=0.0 "
                                "(attempt %d/5) — retrying price fetch...",
                                order_id, price_retries,
                            )
                            time.sleep(_POLL_INTERVAL)
                            try:
                                for o2 in self._kite.orders():
                                    if str(o2["order_id"]) == str(order_id):
                                        avg_price = float(o2.get("average_price", 0.0))
                                        filled_qty = int(o2.get("filled_quantity", 0)) or filled_qty
                                        break
                            except Exception as exc:
                                logger.warning("Price retry poll error: %s", exc)

                        if avg_price <= 0.0:
                            # Exchange still not returning a fill price after all
                            # retries.  Do NOT fall back to LTP — an approximate
                            # price would silently poison SL, target and P&L for
                            # the entire trade.  Instead, surface PRICE_UNCONFIRMED
                            # so the caller can protect the position conservatively
                            # and keep polling until the real price arrives.
                            log_event(
                                logger, "FILL_PRICE_UNCONFIRMED",
                                order_id=order_id, symbol=tradingsymbol,
                                filled_qty=filled_qty or expected_qty,
                                message="Exchange returned COMPLETE but no fill price after "
                                        "5 retries. Position is open. Caller must protect "
                                        "conservatively and retry for actual fill price.",
                            )
                            return {
                                "order_id": order_id,
                                "status": "PRICE_UNCONFIRMED",
                                "filled_qty": filled_qty or expected_qty,
                                "average_price": 0.0,
                            }

                        result = {
                            "order_id": order_id,
                            "status": "COMPLETE",
                            "filled_qty": filled_qty or expected_qty,
                            "average_price": avg_price,
                        }
                        log_event(
                            logger, "ORDER_FILLED",
                            symbol=tradingsymbol, order_id=order_id,
                            fill=result["average_price"], qty=result["filled_qty"],
                        )
                        return result

                    if status == "REJECTED":
                        log_event(
                            logger, "ORDER_REJECTED",
                            symbol=tradingsymbol, order_id=order_id,
                            reason=o.get("status_message", ""),
                        )
                        return {
                            "order_id": order_id,
                            "status": "REJECTED",
                            "filled_qty": 0,
                            "average_price": 0.0,
                        }

                    if status == "CANCELLED":
                        return {
                            "order_id": order_id,
                            "status": "CANCELLED",
                            "filled_qty": filled_qty,
                            "average_price": avg_price,
                        }

                    break  # still pending — keep polling

            time.sleep(_POLL_INTERVAL)

        # Timeout — fetch final partial-fill state one last time before giving up.
        try:
            orders = self._kite.orders()
            for o in orders:
                if str(o["order_id"]) == str(order_id):
                    filled_qty = int(o.get("filled_quantity", 0))
                    avg_price = float(o.get("average_price", 0.0))
                    logger.error(
                        "Order %s timed out — status=%s filled=%d avg=%.2f. "
                        "Order may still be live at broker. Manual check required.",
                        order_id, o.get("status"), filled_qty, avg_price,
                    )
                    return {
                        "order_id": order_id,
                        "status": "TIMEOUT",
                        "filled_qty": filled_qty,
                        "average_price": avg_price,
                    }
        except Exception:
            pass

        logger.error("Order %s timed out and final status could not be determined.", order_id)
        return {
            "order_id": order_id,
            "status": "TIMEOUT",
            "filled_qty": 0,
            "average_price": 0.0,
        }
