"""
KiteTicker WebSocket wrapper.

Subscribes to SENSEX spot ticks (and optionally the active option token)
and dispatches price updates to registered callbacks.

Stale-feed detection: if no tick is received for STALE_TIMEOUT_SECONDS
while a position is open, the stale callback fires and the WebSocket is
automatically reconnected (up to _MAX_RECONNECT_ATTEMPTS times).

Mode note:
  Zerodha KiteTicker does NOT deliver MODE_LTP packets for INDICES-segment
  tokens (e.g. SENSEX token 265).  Index tokens must be subscribed in
  MODE_FULL (32-byte packets) or MODE_QUOTE (28-byte packets) to receive
  any ticks at all.  Tradable option tokens work fine with MODE_LTP.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from kiteconnect import KiteTicker  # type: ignore

from broker.kite_client import get_kite
from config import settings
from market.historical_data import SENSEX_TOKEN
from utils.logging_config import log_event

logger = logging.getLogger(__name__)

STALE_TIMEOUT_SECONDS = 60   # alert if no tick for this long
_MAX_RECONNECT_ATTEMPTS = 3  # reconnect attempts before giving up

# KiteTicker reconnect tuning.
# reconnect_max_delay=5 caps the exponential backoff at 5s (library minimum),
# preventing the 16–30 min blind windows seen when Zerodha drops idle sockets.
# reconnect_max_tries=300 keeps retrying for the full trading session.
_RECONNECT_MAX_DELAY = 5    # seconds — library minimum; prevents long blind windows
_RECONNECT_MAX_TRIES = 300  # ~5 hours of 1s retries — effectively unlimited

# NOTE: WS-level ping/pong is intentionally DISABLED for Zerodha.
# Zerodha's streaming server does NOT support standard RFC-6455 ping/pong frames.
# Sending an autobahn autoPingInterval ping causes the server to drop the connection
# immediately with close code 1006.  The KiteTicker library handles keepalive
# internally via its own reconnect loop — no application-level ping is needed.

# Market hours in IST (hour, minute) — stale monitor is suppressed outside this window
_MARKET_OPEN  = (9, 15)
_MARKET_CLOSE = (15, 30)

# Tokens that require MODE_FULL because they are non-tradable index tokens.
# All other tokens use MODE_LTP (smaller packet, lower bandwidth).
_INDEX_TOKENS: set[int] = {SENSEX_TOKEN}


class WebSocketClient:
    def __init__(self) -> None:
        self._kite = get_kite()
        self._ticker: KiteTicker | None = None
        self._tokens: set[int] = set()          # ALL subscribed tokens (including index)
        self._option_tokens: set[int] = set()   # tradable option tokens only (position guard)
        self._ltp_callbacks: list[Callable[[int, float], None]] = []
        self._order_update_callbacks: list[Callable[[dict], None]] = []
        self._stale_callbacks: list[Callable[[], None]] = []
        self._last_tick_time: float = 0.0         # updated by ANY token (SENSEX or option)
        self._last_option_tick_time: float = 0.0  # updated ONLY by option tokens
        self._stale_exhausted: bool = False        # True once all reconnect attempts used up
        self._stale_thread: threading.Thread | None = None
        self._running = False

    # ── Subscriptions ──────────────────────────────────────────────────────────

    def on_ltp(self, callback: Callable[[int, float], None]) -> None:
        """Register a callback(instrument_token, ltp) for each tick."""
        self._ltp_callbacks.append(callback)

    def on_order_update(self, callback: Callable[[dict], None]) -> None:
        """
        Register a callback(order_update_dict) fired on every Zerodha
        order postback.  The dict contains the full Kite order payload
        including: order_id, status, filled_quantity, average_price,
        exchange_timestamp, exchange_update_timestamp, etc.

        This is the PRIMARY fill-confirmation mechanism.  REST polling in
        OrderManager._wait_for_fill() remains as a backup.
        """
        self._order_update_callbacks.append(callback)

    def on_stale(self, callback: Callable[[], None]) -> None:
        """Register a callback fired when the feed goes stale."""
        self._stale_callbacks.append(callback)

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def option_feed_ok(self) -> bool:
        """Return True if option ticks have arrived recently (within 2× STALE_TIMEOUT_SECONDS).

        Returns True when no option token is subscribed (no position open) so the
        caller does not need to guard against that case.
        """
        if not self._option_tokens:
            return True
        return time.monotonic() - self._last_option_tick_time < STALE_TIMEOUT_SECONDS * 2

    def add_token(self, token: int) -> None:
        self._tokens.add(token)
        if token not in _INDEX_TOKENS:
            self._option_tokens.add(token)
            self._last_option_tick_time = time.monotonic()
        self._last_tick_time = time.monotonic()
        # Guard: only subscribe immediately when the WebSocket handshake is
        # complete (ticker.ws is not None).  Calling ticker.subscribe() before
        # the connection is established raises AttributeError: ws is None.
        # Tokens queued here are picked up by _on_connect when the handshake
        # completes, so nothing is lost.
        ws_ready = self._ticker is not None and getattr(self._ticker, "ws", None) is not None
        if self._ticker and self._running and ws_ready:
            self._ticker.subscribe([token])
            mode = self._ticker.MODE_FULL if token in _INDEX_TOKENS else self._ticker.MODE_LTP
            self._ticker.set_mode(mode, [token])

    def remove_token(self, token: int) -> None:
        self._tokens.discard(token)
        self._option_tokens.discard(token)
        if self._ticker and self._running:
            try:
                self._ticker.unsubscribe([token])
            except Exception:
                pass

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self, tokens: list[int]) -> None:
        if self._running:
            logger.warning(
                "WebSocketClient.start() called while already running — ignoring. "
                "KiteTicker uses Twisted internally; calling connect() twice per process "
                "raises ReactorNotRestartable."
            )
            return
        self._tokens.update(tokens)
        # Always read access token fresh from settings — it may have been
        # rotated by auto-auth since the singleton was last created.
        self._ticker = KiteTicker(
            settings.KITE_API_KEY,
            settings.KITE_ACCESS_TOKEN,
            reconnect_max_delay=_RECONNECT_MAX_DELAY,
            reconnect_max_tries=_RECONNECT_MAX_TRIES,
        )
        self._ticker.on_ticks = self._on_ticks
        self._ticker.on_connect = self._on_connect
        self._ticker.on_close = self._on_close
        self._ticker.on_error = self._on_error
        self._ticker.on_reconnect = self._on_reconnect
        self._ticker.on_order_update = self._on_order_update
        self._running = True
        self._last_tick_time = time.monotonic()
        self._last_option_tick_time = time.monotonic()
        self._start_stale_monitor()
        self._ticker.connect(threaded=True)
        log_event(logger, "WEBSOCKET_STARTED", tokens=list(self._tokens))

    def stop(self) -> None:
        self._running = False
        if self._ticker:
            try:
                self._ticker.stop()
            except Exception:
                pass

    def reconnect(self) -> None:
        """
        Force the existing KiteTicker to drop and re-establish its connection.

        A new KiteTicker instance must NOT be created here because KiteTicker uses
        Twisted internally and Twisted's reactor can only be started once per
        process.  Creating a new instance and calling connect(threaded=True) a
        second time raises ReactorNotRestartable.

        If the ticker is currently connected, close() drops the connection and
        KiteTicker's built-in reconnect loop re-runs _on_connect automatically.

        If the ticker is NOT connected (e.g. initial auth failure), calling
        close() is still safe — it will re-attempt the connection from scratch,
        which is exactly what we need when the token was stale at startup.
        """
        logger.warning("WebSocket stale — forcing reconnect (tokens=%s).", list(self._tokens))
        self._last_tick_time = time.monotonic()
        self._last_option_tick_time = time.monotonic()
        try:
            if self._ticker:
                if self._ticker.is_connected():
                    self._ticker.close()   # drop + KiteTicker auto-reconnects
                else:
                    # Not connected (e.g. auth failure at startup) — force a fresh
                    # connect attempt.  close() is still the right call: it resets
                    # KiteTicker's internal state and triggers the reconnect path.
                    logger.warning(
                        "WebSocket ticker not connected — attempting fresh connect "
                        "(token may have been stale at startup)."
                    )
                    self._ticker.close()
                log_event(logger, "WEBSOCKET_RECONNECTED", tokens=list(self._tokens))
            else:
                logger.warning("WebSocket reconnect skipped — no ticker instance.")
        except Exception as exc:
            logger.error("WebSocket reconnect failed: %s", exc)

    # ── Internal callbacks ─────────────────────────────────────────────────────

    def _on_connect(self, ws, response) -> None:  # type: ignore[no-untyped-def]
        logger.info("WebSocket connected.")
        # Reset Twisted's ReconnectingClientFactory retry counter so the backoff
        # delay starts fresh from 2s on the next disconnect — not from wherever
        # today's accumulated retries left it (which caused 16–30 min blind windows).
        try:
            if self._ticker and hasattr(self._ticker, "factory") and self._ticker.factory:
                self._ticker.factory.resetDelay()
        except Exception:
            pass
        if self._tokens:
            ws.subscribe(list(self._tokens))
            # Index tokens (non-tradable) require MODE_FULL; tradable tokens use MODE_LTP.
            index_tokens = [t for t in self._tokens if t in _INDEX_TOKENS]
            other_tokens = [t for t in self._tokens if t not in _INDEX_TOKENS]
            if index_tokens:
                ws.set_mode(ws.MODE_FULL, index_tokens)
                logger.info("WebSocket MODE_FULL set for index tokens: %s", index_tokens)
            if other_tokens:
                ws.set_mode(ws.MODE_LTP, other_tokens)
                logger.info("WebSocket MODE_LTP re-subscribed for option tokens: %s", other_tokens)
        # Restore option-token tracking set so stale monitor and tick handler
        # know which tokens belong to open positions.  This MUST run after
        # subscribe/set_mode so the set is populated before the first tick.
        for t in self._tokens:
            if t not in _INDEX_TOKENS:
                self._option_tokens.add(t)
        self._last_option_tick_time = time.monotonic()

    def _on_order_update(self, ws, message: dict) -> None:  # type: ignore[no-untyped-def]
        """
        Zerodha WebSocket order postback handler.

        Fired for every order-state change: OPEN → TRIGGER PENDING →
        COMPLETE / REJECTED / CANCELLED.  Dispatches to all registered
        order-update callbacks.

        Key fields in `message` (Zerodha Kite Connect v3):
            order_id, status, filled_quantity, average_price,
            tradingsymbol, transaction_type, order_timestamp,
            exchange_timestamp, exchange_update_timestamp,
            status_message (on REJECTED).
        """
        log_event(
            logger, "ORDER_UPDATE_RECEIVED",
            order_id=message.get("order_id"),
            status=message.get("status"),
            filled=message.get("filled_quantity"),
            avg_price=message.get("average_price"),
            symbol=message.get("tradingsymbol"),
        )
        for cb in self._order_update_callbacks:
            try:
                cb(message)
            except Exception as exc:
                logger.error("Order-update callback error: %s", exc)

    def _on_ticks(self, ws, ticks: list[dict]) -> None:  # type: ignore[no-untyped-def]
        self._last_tick_time = time.monotonic()
        for tick in ticks:
            token = tick.get("instrument_token")
            ltp = tick.get("last_price")
            if token is None or ltp is None:
                continue
            # Track option-token ticks separately so SENSEX index ticks do not
            # mask a stale option feed while a position is open.
            if token in self._option_tokens:
                self._last_option_tick_time = time.monotonic()
            for cb in self._ltp_callbacks:
                try:
                    cb(token, float(ltp))
                except Exception as exc:
                    logger.error("LTP callback error: %s", exc)

    @staticmethod
    def _is_auth_error(code, reason) -> bool:
        reason_str = str(reason).lower() if reason else ""
        return code in (403,) or any(k in reason_str for k in (
            "tokenexception", "invalid token", "token is invalid",
            "session expired", "unauthorised", "unauthorized",
            "token has been invalidated",
        ))

    def _try_refresh_token(self) -> bool:
        """
        Re-read .env from disk, update settings.KITE_ACCESS_TOKEN in memory,
        reset the Kite singleton, and validate the new token.

        The UI login flow writes a fresh token to .env but the running bot
        holds the old token in memory.  Without the re-read, rebuilding the
        Kite singleton still uses the stale in-memory value and the 403 persists.

        Returns True on success.
        """
        try:
            from pathlib import Path
            from dotenv import dotenv_values

            # Re-read .env from disk to pick up a token written by the UI.
            env_path = Path(__file__).resolve().parent.parent / ".env"
            fresh_env = dotenv_values(env_path)
            fresh_token = fresh_env.get("KITE_ACCESS_TOKEN", "").strip()
            fresh_date  = fresh_env.get("KITE_TOKEN_DATE",   "").strip()
            if fresh_token:
                settings.KITE_ACCESS_TOKEN = fresh_token
                if fresh_date:
                    settings.KITE_TOKEN_DATE = fresh_date
                logger.info(
                    "WebSocketClient: re-read .env — KITE_ACCESS_TOKEN updated in memory."
                )

            from broker import kite_client as _kc
            _kc._kite = None  # noqa: SLF001
            from broker.kite_client import get_kite
            kite = get_kite()
            kite.profile()  # validate
            # Patch the ticker so KiteTicker reconnects with the new token.
            if self._ticker is not None:
                self._ticker.access_token = settings.KITE_ACCESS_TOKEN
            logger.info("WebSocketClient: Kite token refreshed successfully.")
            return True
        except Exception as exc:
            logger.error("WebSocketClient: token refresh failed — %s", exc)
            return False

    def _on_close(self, ws, code, reason) -> None:  # type: ignore[no-untyped-def]
        log_event(logger, "WEBSOCKET_CLOSED", code=code, reason=reason)
        if self._is_auth_error(code, reason):
            logger.error(
                "WebSocket closed due to auth error (code=%s). "
                "Attempting token refresh before next reconnect...", code,
            )
            self._try_refresh_token()
        # DO NOT clear _option_tokens here.
        # Clearing it on every disconnect caused two problems:
        #   1. The stale monitor saw no option tokens → suppressed reconnect logic
        #      while a position was open and ticks were missing.
        #   2. _on_ticks stopped updating _last_option_tick_time because the
        #      token was no longer in _option_tokens — even though it was still
        #      in _tokens and ticks were flowing after reconnect.
        # _on_connect now restores _option_tokens from _tokens on every reconnect.
        # We only reset the clock so the stale monitor doesn't fire immediately
        # after a normal reconnect cycle.
        self._last_option_tick_time = time.monotonic()

    def _on_error(self, ws, code, reason) -> None:  # type: ignore[no-untyped-def]
        log_event(logger, "API_ERROR", source="websocket", code=code, reason=reason)
        if self._is_auth_error(code, reason):
            logger.error(
                "WebSocket auth error (code=%s) — attempting token refresh.", code,
            )
            self._try_refresh_token()

    def _on_reconnect(self, ws, attempts_count) -> None:  # type: ignore[no-untyped-def]
        logger.info("WebSocket reconnecting, attempt %d", attempts_count)
        # Reset both clocks so a reconnect cycle doesn't trigger the stale alarm.
        self._last_tick_time = time.monotonic()
        self._last_option_tick_time = time.monotonic()

    def _enable_auto_ping(self) -> None:
        """
        No-op — intentionally disabled.

        Zerodha's WebSocket streaming server does NOT support RFC-6455 ping/pong
        frames.  Sending any WS ping (whether via autobahn's autoPingInterval or
        a manual thread) causes the server to close the connection immediately
        with code 1006.  KiteTicker's built-in reconnect loop keeps the session
        alive without application-level pings.
        """

    def _start_stale_monitor(self) -> None:
        import datetime as _dt

        def _is_market_hours() -> bool:
            """Return True if the current IST time is within market hours."""
            try:
                from utils.time_utils import now_ist as _now_ist
                _now = _now_ist().time()
                _open  = _dt.time(_MARKET_OPEN[0],  _MARKET_OPEN[1])
                _close = _dt.time(_MARKET_CLOSE[0], _MARKET_CLOSE[1])
                return _open <= _now <= _close
            except Exception:
                return True  # fail-open: don't suppress if we can't check

        def _monitor() -> None:
            reconnect_attempts = 0
            while self._running:
                time.sleep(10)

                # Suppress stale alarms completely outside market hours (09:15–15:30 IST).
                # After market close Zerodha drops the WebSocket; there is no position to
                # protect and reconnect attempts would just waste auth budget.
                if not _is_market_hours():
                    # Outside market hours: keep clocks fresh, reset attempt counter.
                    self._last_option_tick_time = time.monotonic()
                    self._last_tick_time = time.monotonic()
                    reconnect_attempts = 0
                    self._stale_exhausted = False
                    continue

                # Only alert when there is an actively subscribed OPTION token.
                # Index tokens (e.g. SENSEX 265) never deliver ticks outside market
                # hours — guarding on _option_tokens prevents false stale alarms.
                if not self._option_tokens:
                    self._last_option_tick_time = time.monotonic()  # keep clock fresh while idle
                    reconnect_attempts = 0
                    continue
                # Use option-specific clock — SENSEX ticks must not mask a dead option feed
                elapsed = time.monotonic() - self._last_option_tick_time
                if elapsed > STALE_TIMEOUT_SECONDS:
                    log_event(logger, "STALE_FEED_DETECTED", elapsed_seconds=int(elapsed))
                    for cb in self._stale_callbacks:
                        try:
                            cb()
                        except Exception as exc:
                            logger.error("Stale callback error: %s", exc)
                    # Auto-reconnect — keep retrying indefinitely while position is open.
                    # Use exponential backoff capped at 60s: 15s, 30s, 60s, 60s, ...
                    # _MAX_RECONNECT_ATTEMPTS is the old hard cap; we now ignore it when
                    # a position is open (_option_tokens is non-empty) — giving up with
                    # an open unprotected position is never acceptable.
                    reconnect_attempts += 1
                    backoff = min(15 * (2 ** (reconnect_attempts - 1)), 60)
                    logger.warning(
                        "STALE feed with open position — reconnecting WebSocket "
                        "(attempt %d, backoff=%ds).", reconnect_attempts, backoff,
                    )
                    self.reconnect()
                    # Give the new connection time to establish before re-checking.
                    time.sleep(backoff)
                    self._stale_exhausted = False
                else:
                    reconnect_attempts = 0   # ticks are flowing — reset counter
                    self._stale_exhausted = False  # feed recovered — allow reconnects again

        self._stale_thread = threading.Thread(target=_monitor, daemon=True)
        self._stale_thread.start()
