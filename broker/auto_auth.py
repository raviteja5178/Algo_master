"""
Automated Zerodha Kite Connect login.

Uses pyotp to generate 2FA pin and requests to perform browser login,
bypassing manual daily login urls.
"""

from __future__ import annotations

import logging
import urllib.parse
import pyotp  # type: ignore[import-untyped]
import requests
from kiteconnect import KiteConnect  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


def login_and_get_access_token(
    api_key: str,
    api_secret: str,
    user_id: str,
    password: str,
    totp_secret: str,
) -> str:
    """
    Automate the 4-step login sequence to get a fresh KITE_ACCESS_TOKEN.

    SAFETY GUARD: Set AUTO_LOGIN_ENABLED=false in .env to disable all
    automated login attempts (e.g. while fixing TOTP secret) and prevent
    burning 2FA attempt counts.
    """
    import os as _os
    from dotenv import dotenv_values as _dv
    from pathlib import Path as _Path
    _env_file = _Path(__file__).resolve().parent.parent / ".env"
    _env = _dv(_env_file)
    if _env.get("AUTO_LOGIN_ENABLED", "true").strip("'\"").lower() == "false":
        raise RuntimeError(
            "AUTO_LOGIN_ENABLED=false in .env - automated login is disabled. "
            "Set AUTO_LOGIN_ENABLED=true after fixing KITE_TOTP_SECRET."
        )

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    })

    # Step 1: Submit username and password to get request_id
    logger.info("Auto-login Step 1: Submitting credentials for user %s...", user_id)
    login_url = "https://kite.zerodha.com/api/login"
    login_data = {
        "user_id": user_id,
        "password": password,
        "type": "user_id"
    }
    response = session.post(login_url, data=login_data)
    try:
        res_json = response.json()
    except Exception as exc:
        raise RuntimeError(f"Step 1 failed to parse response JSON: {response.text}") from exc

    if res_json.get("status") != "success":
        raise RuntimeError(f"Step 1 Login failed: {res_json.get('message', 'Unknown error')}")

    request_id = res_json["data"]["request_id"]

    # Step 2: Determine 2FA type directly from Step 1 response, then submit TOTP.
    # Zerodha tells us exactly which type the account uses — use that first,
    # then fall back to the other type if needed.
    # "app_code" — TOTP via authenticator app (Google Authenticator / Authy)
    # "totp"     — same concept, used by some account configurations
    # We always generate the pin fresh with totp.now() right before the POST.
    logger.info("Auto-login Step 2: Generating TOTP pin and completing 2FA...")
    totp_secret_clean = totp_secret.replace(" ", "").strip()
    try:
        totp = pyotp.TOTP(totp_secret_clean)
    except Exception as exc:
        raise ValueError(f"Invalid TOTP Secret format: {exc}. Ensure you are entering the static master key.") from exc

    # Build ordered list: server-preferred type first, then alternatives
    server_type  = res_json["data"].get("twofa_type", "app_code")
    server_types = res_json["data"].get("twofa_types", [server_type])
    # Deduplicated list: server's preferred type first, then any others we know about
    _all_types = list(dict.fromkeys([server_type] + list(server_types) + ["app_code", "totp"]))

    twofa_url = "https://kite.zerodha.com/api/twofa"
    res_json2 = None
    for twofa_type in _all_types:
        totp_pin = totp.now()   # fresh pin every attempt
        response2 = session.post(twofa_url, data={
            "request_id": request_id,
            "twofa_value": totp_pin,
            "user_id": user_id,
            "twofa_type": twofa_type,
        })
        try:
            res_json2 = response2.json()
        except Exception as exc:
            raise RuntimeError(f"Step 2 failed to parse response JSON: {response2.text}") from exc

        if res_json2.get("status") == "success":
            logger.info("Auto-login Step 2: 2FA succeeded with twofa_type=%s", twofa_type)
            break

        msg = res_json2.get("message", "").lower()
        logger.warning("Auto-login Step 2: twofa_type=%s failed: %s", twofa_type, res_json2.get("message"))

        # Hard-stop on lockout — do not burn more attempts
        if "lock" in msg or "attempt" in msg:
            break
        # Continue trying other types for non-critical rejections
        continue

    if res_json2 is None or res_json2.get("status") != "success":
        raise RuntimeError(f"Step 2 2FA failed: {res_json2.get('message', 'Unknown error') if res_json2 else 'no response'}")

    # Step 3: Trigger OAuth redirect to extract request_token.
    #
    # IMPORTANT: must use allow_redirects=False on EVERY hop here.
    # Zerodha's connect/login redirects through an intermediate /connect/finish
    # endpoint which *consumes* the request_token server-side.  If requests
    # follows that redirect automatically (allow_redirects=True), the token is
    # spent before we call generate_session() and Zerodha returns:
    #   "Error generating request_token. Try re-initiating login."
    #
    # Correct flow:
    #   GET /connect/login  -> 302 to /connect/finish?request_token=...
    #   GET /connect/finish -> 302 to <redirect_uri>?request_token=...  ← extract here
    logger.info("Auto-login Step 3: Authorizing app and fetching request_token...")
    connect_url = f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"

    # Hop 1: /connect/login  → /connect/finish?...
    r3a = session.get(connect_url, allow_redirects=False)
    hop1_location = r3a.headers.get("Location", "")

    if not hop1_location:
        raise RuntimeError(
            "Step 3 failed: /connect/login did not redirect. "
            "Check that your Kite app Redirect URL is set (e.g. 'http://127.0.0.1') "
            f"and that the login session is still active. Response: {r3a.text[:300]}"
        )

    # Hop 2: /connect/finish?...  → <redirect_uri>?request_token=...
    finish_url = hop1_location if hop1_location.startswith("http") \
        else f"https://kite.zerodha.com{hop1_location}"

    r3b = session.get(finish_url, allow_redirects=False)
    redirect_url = r3b.headers.get("Location", "")

    if not redirect_url:
        # Some app configs skip the finish step and put request_token on hop1
        redirect_url = hop1_location

    parsed_url = urllib.parse.urlparse(redirect_url)
    params = urllib.parse.parse_qs(parsed_url.query)

    # Check for an error response embedded in the redirect URL
    if params.get("error") or params.get("error_type"):
        error_msg = params.get("message", params.get("error", ["Unknown error"]))[0]
        raise RuntimeError(
            f"Step 3 OAuth error from Zerodha: {error_msg}. "
            "Verify KITE_API_KEY and Redirect URL in the Kite developer console."
        )

    request_tokens = params.get("request_token")
    if not request_tokens:
        raise RuntimeError(
            f"Could not extract request_token from redirect URL: {redirect_url}. "
            "Check that your Kite app Redirect URL is configured correctly "
            "(e.g. 'http://127.0.0.1') on the Kite developer console."
        )

    request_token = request_tokens[0]
    logger.info("Auto-login Step 3: request_token obtained successfully.")

    # Step 4: Exchange request_token for access_token
    logger.info("Auto-login Step 4: Exchanging request_token for KITE_ACCESS_TOKEN...")
    kite = KiteConnect(api_key=api_key)
    session_data = kite.generate_session(request_token, api_secret=api_secret)
    access_token: str = session_data["access_token"]
    return access_token
