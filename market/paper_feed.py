"""
Paper-mode live feed.

Polls the Zerodha REST quote API for the SENSEX spot LTP every second
and feeds it into the candle aggregators — exactly replicating what the
WebSocket tick handler does in LIVE/SHADOW mode.

Requires a valid KITE_API_KEY + KITE_ACCESS_TOKEN in .env.
If the API call fails (missing credentials, network), it falls back to
a no-op so the rest of the bot is unaffected.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from utils.logging_config import log_event

logger = logging.getLogger(__name__)

# BSE SENSEX spot — same token used by historical_data.py
_SENSEX_EXCHANGE_TOKEN = "BSE:SENSEX"
_POLL_INTERVAL_PRIMARY = 1.0   # seconds — used in PAPER mode (only feed)
_POLL_INTERVAL_FALLBACK = 5.0  # seconds — used in LIVE/SHADOW mode (WebSocket is primary)

# After this many consecutive auth errors, try to refresh the Kite client once.
# If refresh also fails, stop polling to avoid log spam.
_AUTH_RETRY_AFTER = 3


class PaperFeed:
    """
    Polls SENSEX LTP via REST and dispatches to registered tick callbacks.

    Usage:
        feed = PaperFeed()
        feed.on_tick(lambda token, ltp: ...)
        feed.start()
        ...
        feed.stop()
    """

    def __init__(self) -> None:
        self._callbacks: list[Callable[[int, float], None]] = []
        self._running = False
        self._thread: threading.Thread | None = None
        self._kite = None

    def on_tick(self, callback: Callable[[int, float], None]) -> None:
        self._callbacks.append(callback)

    def start(self, fallback: bool = False) -> None:
        """
        Start the feed.

        fallback=True  — WebSocket is the primary feed; PaperFeed polls every 5s
                         as a backup.  Reduces REST API load.
        fallback=False — PaperFeed is the only feed (PAPER mode); polls every 1s.
        """
        if self._running:
            return
        try:
            from broker.kite_client import get_kite
            self._kite = get_kite()
        except Exception as exc:
            logger.warning("PaperFeed: could not init Kite client (%s) — feed disabled.", exc)
            return

        self._poll_interval = _POLL_INTERVAL_FALLBACK if fallback else _POLL_INTERVAL_PRIMARY
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="paper-feed")
        self._thread.start()
        logger.info("PaperFeed started — polling SENSEX LTP every %.1fs%s",
                    self._poll_interval, " (fallback)" if fallback else "")

    def stop(self) -> None:
        self._running = False

    def is_alive(self) -> bool:
        """Return True if the polling thread is still running."""
        return self._thread is not None and self._thread.is_alive()

    # ── Internal ───────────────────────────────────────────────────────────────

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        exc_str = str(exc).lower()
        return any(k in exc_str for k in (
            "tokenexception", "invalid token", "token is invalid",
            "session expired", "unauthorised", "unauthorized",
            "403", "token has been invalidated",
        ))

    def _try_refresh_kite(self) -> bool:
        """
        Attempt to get a fresh Kite client (triggers auto-auth if credentials
        are set).  Returns True if the new client validates successfully.
        """
        try:
            # Force a new singleton by resetting the module-level cache first.
            from broker import kite_client
            kite_client._kite = None  # noqa: SLF001
            from broker.kite_client import get_kite
            self._kite = get_kite()
            # Validate immediately so we know if the refresh worked.
            self._kite.profile()
            logger.info("PaperFeed: Kite client refreshed successfully.")
            return True
        except Exception as exc:
            logger.error("PaperFeed: token refresh failed — %s", exc)
            return False

    def _loop(self) -> None:
        from market.historical_data import SENSEX_TOKEN

        poll_interval = getattr(self, "_poll_interval", _POLL_INTERVAL_PRIMARY)
        consecutive_errors = 0
        consecutive_auth_errors = 0
        _refresh_attempted = False

        try:
            while self._running:
                try:
                    quotes = self._kite.quote([_SENSEX_EXCHANGE_TOKEN])
                    ltp = quotes[_SENSEX_EXCHANGE_TOKEN]["last_price"]
                    consecutive_errors = 0
                    consecutive_auth_errors = 0
                    _refresh_attempted = False
                    for cb in self._callbacks:
                        try:
                            cb(SENSEX_TOKEN, float(ltp))
                        except Exception as exc:
                            logger.error("PaperFeed tick callback error: %s", exc)
                except Exception as exc:
                    consecutive_errors += 1
                    if self._is_auth_error(exc):
                        consecutive_auth_errors += 1
                        if consecutive_auth_errors == 1:
                            logger.error(
                                "PaperFeed: Kite session has expired or access token is invalid. "
                                "Attempting token refresh..."
                            )
                        # After a few retries, try to get a fresh client once.
                        if consecutive_auth_errors >= _AUTH_RETRY_AFTER and not _refresh_attempted:
                            _refresh_attempted = True
                            if self._try_refresh_kite():
                                consecutive_auth_errors = 0
                                consecutive_errors = 0
                            else:
                                logger.error(
                                    "PaperFeed: token refresh failed — feed paused. "
                                    "Open the dashboard and click 'Login with Zerodha' "
                                    "to re-authenticate, then restart the bot."
                                )
                                # Stop polling — auth is broken and refresh failed.
                                # The thread exits cleanly; _running stays True so
                                # is_alive() returning False signals the dead feed.
                                return
                    else:
                        if consecutive_errors == 1:
                            logger.warning("PaperFeed poll error: %s", exc)
                        elif consecutive_errors % 30 == 0:
                            logger.error("PaperFeed: %d consecutive errors — last: %s",
                                         consecutive_errors, exc)
                time.sleep(poll_interval)
        except Exception as exc:
            # Catch-all so an unexpected crash is logged rather than silently lost.
            logger.error("PaperFeed: polling thread crashed — %s", exc, exc_info=True)
