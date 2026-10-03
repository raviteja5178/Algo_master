"""
Tests for WebSocketClient — option_feed_ok property and _stale_exhausted flag.

These tests bypass the live Kite/broker plumbing entirely by constructing the
client via object.__new__ and seeding only the instance attributes under test.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from market.websocket_client import (
    WebSocketClient,
    STALE_TIMEOUT_SECONDS,
    _MAX_RECONNECT_ATTEMPTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client() -> WebSocketClient:
    """
    Build a WebSocketClient without calling __init__ (which dials out to Kite).
    Populate exactly the attributes the tested code uses.
    """
    client = object.__new__(WebSocketClient)
    client._kite = MagicMock()
    client._ticker = MagicMock()
    client._tokens: set[int] = set()
    client._option_tokens: set[int] = set()
    client._ltp_callbacks: list = []
    client._order_update_callbacks: list = []
    client._stale_callbacks: list = []
    client._last_tick_time: float = time.monotonic()
    client._last_option_tick_time: float = time.monotonic()
    client._stale_exhausted: bool = False
    client._stale_thread = None
    client._running = False
    return client


def _add_option_token(client: WebSocketClient, token: int = 99999) -> int:
    """Register a non-index option token without touching the live ticker."""
    client._tokens.add(token)
    client._option_tokens.add(token)
    client._last_option_tick_time = time.monotonic()
    return token


# ---------------------------------------------------------------------------
# option_feed_ok tests
# ---------------------------------------------------------------------------

class TestOptionFeedOk:
    def test_returns_true_when_no_option_token_subscribed(self):
        """With no open position (no option token), feed is considered OK."""
        client = _client()
        assert client.option_feed_ok is True

    def test_returns_true_when_tick_is_recent(self):
        """Tick arrived well within the generous 2× window."""
        client = _client()
        _add_option_token(client)
        client._last_option_tick_time = time.monotonic()
        assert client.option_feed_ok is True

    def test_returns_false_when_last_tick_is_old(self):
        """Tick arrived more than 2× STALE_TIMEOUT_SECONDS ago → feed dead."""
        client = _client()
        _add_option_token(client)
        client._last_option_tick_time = time.monotonic() - (STALE_TIMEOUT_SECONDS * 2 + 1)
        assert client.option_feed_ok is False

    def test_boundary_just_inside_window(self):
        """Tick at STALE_TIMEOUT_SECONDS - 1 (well within 2× window) → still OK."""
        client = _client()
        _add_option_token(client)
        client._last_option_tick_time = time.monotonic() - (STALE_TIMEOUT_SECONDS - 1)
        assert client.option_feed_ok is True

    def test_boundary_just_outside_window(self):
        """Tick at 2× STALE_TIMEOUT_SECONDS + 1 second → feed dead."""
        client = _client()
        _add_option_token(client)
        client._last_option_tick_time = time.monotonic() - (STALE_TIMEOUT_SECONDS * 2 + 1)
        assert client.option_feed_ok is False

    def test_feed_ok_recovers_after_new_tick(self):
        """After a dead period, a new tick arriving restores option_feed_ok."""
        client = _client()
        _add_option_token(client)
        client._last_option_tick_time = time.monotonic() - (STALE_TIMEOUT_SECONDS * 2 + 5)
        assert client.option_feed_ok is False  # dead

        client._last_option_tick_time = time.monotonic()
        assert client.option_feed_ok is True   # recovered


# ---------------------------------------------------------------------------
# _stale_exhausted tests
# ---------------------------------------------------------------------------

class TestStaleExhausted:
    def test_initially_false(self):
        client = _client()
        assert client._stale_exhausted is False

    def test_retries_beyond_max_reconnect_attempts(self):
        """
        The stale monitor must keep retrying indefinitely while a position is
        open — it must NOT stop reconnecting after _MAX_RECONNECT_ATTEMPTS.
        After the old hard cap is exceeded, reconnect() must still be called.
        """
        client = _client()
        _add_option_token(client)
        client._last_option_tick_time = time.monotonic() - (STALE_TIMEOUT_SECONDS + 1)
        client._running = True

        reconnect_calls: list[int] = []
        client.reconnect = lambda: reconnect_calls.append(1)  # type: ignore[method-assign]

        # Run for _MAX_RECONNECT_ATTEMPTS + 2 stale cycles and confirm reconnect
        # is still called on every cycle (not stopped at the old cap).
        target_cycles = _MAX_RECONNECT_ATTEMPTS + 2
        cycle: dict[str, int] = {"n": 0}

        def fake_sleep(seconds: float) -> None:
            cycle["n"] += 1
            # Keep feed stale
            client._last_option_tick_time = time.monotonic() - (STALE_TIMEOUT_SECONDS + 1)
            # Each stale cycle = sleep(10) + sleep(backoff) = 2 sleep calls.
            if cycle["n"] >= target_cycles * 2:
                client._running = False

        with patch("market.websocket_client.time.sleep", side_effect=fake_sleep), \
             patch("utils.time_utils.now_ist") as mock_now:
            import datetime as _dt
            from utils.time_utils import IST
            mock_now.return_value = _dt.datetime(2026, 9, 29, 10, 0, 0, tzinfo=IST)
            client._start_stale_monitor()
            client._stale_thread.join(timeout=5)

        # Must have reconnected on every cycle — old cap does not apply
        assert len(reconnect_calls) >= target_cycles
        # _stale_exhausted stays False — we never give up
        assert client._stale_exhausted is False

    def test_stale_callback_fires_on_every_stale_cycle(self):
        """
        The stale callback fires on every stale detection cycle, not just once.
        (The old exhaustion guard that suppressed subsequent callbacks is removed.)
        """
        client = _client()
        _add_option_token(client)
        client._last_option_tick_time = time.monotonic() - (STALE_TIMEOUT_SECONDS + 1)
        client._running = True
        client.reconnect = lambda: None  # type: ignore[method-assign]

        stale_calls: list[int] = []
        client.on_stale(lambda: stale_calls.append(1))

        target_cycles = 4
        cycle: dict[str, int] = {"n": 0}

        def fake_sleep(seconds: float) -> None:
            cycle["n"] += 1
            client._last_option_tick_time = time.monotonic() - (STALE_TIMEOUT_SECONDS + 1)
            if cycle["n"] >= target_cycles * 2:
                client._running = False

        with patch("market.websocket_client.time.sleep", side_effect=fake_sleep), \
             patch("utils.time_utils.now_ist") as mock_now:
            import datetime as _dt
            from utils.time_utils import IST
            mock_now.return_value = _dt.datetime(2026, 9, 29, 10, 0, 0, tzinfo=IST)
            client._start_stale_monitor()
            client._stale_thread.join(timeout=5)

        # One callback fire per stale cycle
        assert len(stale_calls) == target_cycles

    def test_stale_exhausted_resets_when_feed_recovers(self):
        """
        When ticks resume after exhaustion, _stale_exhausted is cleared so
        future outages can trigger reconnects again.
        """
        client = _client()
        _add_option_token(client)
        # Simulate post-exhaustion state
        client._stale_exhausted = True
        client._running = True
        client.reconnect = lambda: None  # type: ignore[method-assign]

        # Feed is healthy
        client._last_option_tick_time = time.monotonic()

        cycle: dict[str, int] = {"n": 0}

        def fake_sleep(seconds: float) -> None:
            cycle["n"] += 1
            if cycle["n"] >= 2:
                client._running = False

        with patch("market.websocket_client.time.sleep", side_effect=fake_sleep):
            client._start_stale_monitor()
            client._stale_thread.join(timeout=5)

        assert client._stale_exhausted is False
