"""
Zerodha Kite Connect authentication helpers.

Usage:
  1. First run: call `generate_login_url()`, visit it, and paste the
     request_token back.  Call `complete_login(request_token)` which
     persists the access token to the .env file.
  2. Subsequent runs: KITE_ACCESS_TOKEN in .env is used directly.
"""

from __future__ import annotations

import logging
import os
from dotenv import set_key
from kiteconnect import KiteConnect  # type: ignore

from config import settings
from utils.logging_config import log_event

logger = logging.getLogger(__name__)


def get_kite() -> KiteConnect:
    """Return an authenticated KiteConnect instance."""
    kite = KiteConnect(api_key=settings.KITE_API_KEY)
    
    token_valid = False
    if settings.KITE_ACCESS_TOKEN:
        kite.set_access_token(settings.KITE_ACCESS_TOKEN)
        try:
            # Validate if the current token is active by calling profile()
            kite.profile()
            token_valid = True
        except Exception:
            logger.info("Cached KITE_ACCESS_TOKEN is invalid/expired. Attempting automated login...")

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
                    # Update .env file so the token is cached for subsequent runs
                    set_key(".env", "KITE_ACCESS_TOKEN", access_token)
                    settings.KITE_ACCESS_TOKEN = access_token
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
    log_event(logger, "AUTH_SUCCESS", user=session.get("user_name", "?"))
    logger.info("Access token obtained successfully.")
    return access_token
