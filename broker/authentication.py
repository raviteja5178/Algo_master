"""
Zerodha Kite Connect authentication helpers.

Usage:
  1. First run: call `generate_login_url()`, visit it, and paste the
     request_token back.  Call `complete_login(request_token)` which
     persists the access token to the .env file.
  2. Subsequent runs: KITE_ACCESS_TOKEN in .env is used directly.
     KITE_TOKEN_DATE is written alongside the token; if it doesn't match
     today's date the token is treated as stale and auto-login runs before
     even calling profile().  This catches the WebSocket 1006 case where
     Zerodha's REST API still accepts a day-old token but the streaming
     endpoint rejects it immediately.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from dotenv import set_key
from kiteconnect import KiteConnect  # type: ignore

from config import settings
from utils.logging_config import log_event

logger = logging.getLogger(__name__)


def _save_token(access_token: str) -> None:
    """Persist access_token and today's date to .env and settings."""
    today_str = date.today().isoformat()
    set_key(".env", "KITE_ACCESS_TOKEN", access_token)
    set_key(".env", "KITE_TOKEN_DATE", today_str)
    settings.KITE_ACCESS_TOKEN = access_token
    settings.KITE_TOKEN_DATE = today_str


def _token_is_stale() -> bool:
    """
    Return True if the cached token was not generated today.
    Zerodha tokens are valid for one calendar day (midnight IST rollover).
    The WebSocket endpoint rejects day-old tokens immediately even though
    the REST profile() call may still succeed briefly.
    """
    token_date = getattr(settings, "KITE_TOKEN_DATE", "")
    if not token_date:
        return True   # no date recorded — treat as stale
    try:
        return date.fromisoformat(token_date) != date.today()
    except ValueError:
        return True   # malformed date — treat as stale


def get_kite() -> KiteConnect:
    """Return an authenticated KiteConnect instance."""
    kite = KiteConnect(api_key=settings.KITE_API_KEY)

    token_valid = False

    # ── Date-based stale check (before any REST call) ─────────────────────────
    # If the token was issued on a previous calendar day, skip it entirely and
    # go straight to auto-login.  This avoids the WebSocket 1006 problem where
    # Zerodha's REST profile() still accepts a stale token but the streaming
    # endpoint drops the connection ~25 seconds after connect.
    if settings.KITE_ACCESS_TOKEN and not _token_is_stale():
        kite.set_access_token(settings.KITE_ACCESS_TOKEN)
        try:
            kite.profile()
            token_valid = True
            logger.info("KITE_ACCESS_TOKEN is valid for today — reusing cached token.")
        except Exception:
            logger.info("Cached KITE_ACCESS_TOKEN failed profile() check. Attempting automated login...")
    elif settings.KITE_ACCESS_TOKEN:
        logger.info(
            "KITE_ACCESS_TOKEN is from a previous day (KITE_TOKEN_DATE=%s) — "
            "forcing re-login to get a fresh token.",
            getattr(settings, "KITE_TOKEN_DATE", "unknown"),
        )

    if not token_valid:
        user_id = os.environ.get("KITE_USER_ID") or os.environ.get("KITE_USERNAME")
        password = os.environ.get("KITE_PASSWORD")
        totp_secret = os.environ.get("KITE_TOTP_SECRET")

        if user_id and password and totp_secret:
            try:
                from broker.auto_auth import login_and_get_access_token
                access_token = login_and_get_access_token(
                    settings.KITE_API_KEY,
                    settings.KITE_API_SECRET,
                    user_id,
                    password,
                    totp_secret,
                )
                if access_token:
                    _save_token(access_token)
                    kite.set_access_token(access_token)
                    token_valid = True
                    logger.info("Automated login successful! KITE_ACCESS_TOKEN updated in .env")
            except Exception as exc:
                logger.error("Automated login failed: %s", exc)
        else:
            logger.warning(
                "KITE_ACCESS_TOKEN is expired or invalid, and auto-login credentials "
                "(KITE_USER_ID, KITE_PASSWORD, KITE_TOTP_SECRET) are not set in .env."
            )

    return kite


def generate_login_url() -> str:
    kite = KiteConnect(api_key=settings.KITE_API_KEY)
    url = kite.login_url()
    logger.info("Login URL: %s", url)
    return url


def complete_login(request_token: str) -> str:
    """
    Exchange a one-time request_token for an access_token.
    Prints the access token so the operator can paste it into .env.
    """
    kite = KiteConnect(api_key=settings.KITE_API_KEY)
    try:
        session = kite.generate_session(request_token, api_secret=settings.KITE_API_SECRET)
    except Exception as exc:
        # Re-raise with ASCII-safe message so Windows cp1252 never crashes
        # on Unicode characters that KiteConnect embeds in error strings.
        safe_msg = str(exc).encode("ascii", errors="replace").decode("ascii")
        raise RuntimeError(f"generate_session failed: {safe_msg}") from exc
    access_token: str = session["access_token"]
    _save_token(access_token)
    log_event(logger, "AUTH_SUCCESS", user=session.get("user_name", "?"))
    logger.info("Access token obtained successfully.")
    return access_token
