"""
EOD (End-of-Day) forced square-off manager.

At or after FORCE_EXIT_TIME (default 15:15 IST):
  1. Do not allow new entries.
  2. Exit any open strategy position.
  3. Cancel any pending stop/target orders.
  4. Verify broker position qty = 0.  The broker position is the truth.
     If qty != 0 after a COMPLETE fill, the trade is NOT marked closed —
     the caller must transition to EXIT_PENDING / HALTED and reconcile.
  5. Persist final trade state only when broker confirms qty == 0.
"""

from __future__ import annotations

import logging

from config import settings
from utils.logging_config import log_event
from utils.time_utils import is_after_or_equal, now_ist, parse_time_ist

logger = logging.getLogger(__name__)


class EODManager:
    def __init__(self, broker, trade_store) -> None:  # type: ignore[type-arg]
        self._broker = broker
        self._store = trade_store
        self._force_exit_time = parse_time_ist(settings.FORCE_EXIT_TIME)
        self._executed_today = False

    def is_force_exit_time(self) -> bool:
        return is_after_or_equal(now_ist().time(), self._force_exit_time)

    def run_eod_exit(
        self,
        tradingsymbol: str,
        quantity: int,
        trade_id: str,
        stop_order_id: str | None,
        entry_price: float,
        max_retries: int = 3,
    ) -> bool:
        """
        Force-close the open position and reconcile.
        Returns True if position is confirmed closed.
        """
        if self._executed_today:
            logger.info("EOD exit already executed for %s today.", trade_id)
            return True

        log_event(
            logger, "FORCED_EOD_EXIT",
            trade_id=trade_id, symbol=tradingsymbol, qty=quantity,
        )

        # Cancel any pending SL order first
        if stop_order_id:
            self._broker.cancel_order(stop_order_id)
            logger.info("Cancelled stop order %s before EOD exit.", stop_order_id)

        # Attempt market SELL
        for attempt in range(1, max_retries + 1):
            try:
                result = self._broker.place_sell_order(
                    tradingsymbol=tradingsymbol,
                    quantity=quantity,
                    tag="EOD_EXIT",
                )
                if result["status"] == "COMPLETE":
                    exit_price = result["average_price"]
                    # ── Broker position is the truth ───────────────────────────
                    remaining = self._broker.get_position_qty(tradingsymbol)
                    if remaining != 0:
                        log_event(
                            logger, "EOD_EXIT_RECONCILE_FAIL",
                            trade_id=trade_id, symbol=tradingsymbol,
                            remaining_qty=remaining,
                            message="Broker still holds position after COMPLETE fill. "
                                    "Trade NOT marked closed — caller must reconcile.",
                        )
                        return False
                    pnl = (exit_price - entry_price) * result["filled_qty"]
                    from utils.time_utils import now_ist
                    self._store.mark_trade_closed(
                        trade_id=trade_id,
                        exit_price=exit_price,
                        exit_time=now_ist().isoformat(),
                        pnl=pnl,
                    )
                    log_event(
                        logger, "EXIT_FILLED",
                        trade_id=trade_id, symbol=tradingsymbol,
                        exit_price=exit_price, pnl=pnl, reason="EOD",
                    )
                    self._executed_today = True
                    return True
            except Exception as exc:
                logger.error("EOD exit attempt %d failed: %s", attempt, exc)

        logger.error("EOD exit failed for %s after %d attempts.", trade_id, max_retries)
        return False
