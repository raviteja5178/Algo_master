"""
SENSEX Auto-Trader Web Dashboard
=================================
Flask API + static frontend for monitoring and controlling the bot.

Endpoints
---------
GET  /                          → dashboard HTML
GET  /api/status                → bot state, active trade summary, config
GET  /api/trades                → all trades (OPEN + CLOSED)
GET  /api/trades/active         → active OPEN trade only
GET  /api/orders                → order_actions log
GET  /api/candles               → live candle + indicator state
GET  /api/pnl                   → realised P&L timeseries
POST /api/bot/start             → start bot subprocess
POST /api/bot/stop              → stop bot subprocess
GET  /api/env                   → current .env settings (non-secret)
POST /api/env                   → update .env settings
GET  /api/zerodha/positions     → live Zerodha positions
GET  /api/zerodha/orders        → live Zerodha open orders
POST /api/zerodha/import        → import an open position into trades.db
POST /api/auth/login            → automated login (user_id+password+totp), starts bot, returns profile
POST /api/auth/logout           → clears token, stops bot
GET  /api/auth/profile          → returns kite.profile() for the logged-in user
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Force UTF-8 output on Windows so any Unicode in error messages or
# Zerodha API responses never triggers a cp1252 codec crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from flask import Flask, Response, jsonify, render_template, request

# ── Path setup ────────────────────────────────────────────────────────────────
# ui/ is one level below the project root; add root to sys.path so we can
# import persistence, config, etc. directly.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlite3

from dotenv import dotenv_values, set_key

ENV_FILE = ROOT / ".env"
DB_FILE_DEFAULT = ROOT / "trades.db"

app = Flask(__name__, template_folder="templates")

# Force UTF-8 for Jinja2 template loading so Unicode characters in HTML
# (tick marks, arrows, etc.) never cause a codec crash on Windows.
app.config["TEMPLATES_AUTO_RELOAD"] = True
# Disable Jinja2's template bytecode cache so template file changes on disk
# are reflected immediately without restarting the server.
app.jinja_env.auto_reload = True

# Tell Flask/Werkzeug to always use UTF-8 when encoding response bodies.
# Without this, on Windows the default charmap (cp1252) is used and any
# Unicode character in an error message or template will raise UnicodeEncodeError.
app.config["JSON_AS_ASCII"] = False

import jinja2 as _jinja2
app.jinja_loader = _jinja2.FileSystemLoader(
    str(Path(__file__).parent / "templates"), encoding="utf-8"
)


@app.after_request
def _force_utf8(response):
    """Ensure every response is sent as UTF-8 and never cached by the browser.
    Without no-cache headers the browser serves the old HTML page from disk
    cache even after the server-side template has been updated."""
    ct = response.content_type or ""
    if "text/" in ct and "charset" not in ct:
        response.content_type = ct.rstrip(";").strip() + "; charset=utf-8"
    # Prevent browser from caching HTML pages so template changes are instant.
    if "text/html" in ct:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.errorhandler(Exception)
def _handle_unhandled(exc):
    """Convert any unhandled exception to a plain UTF-8 HTML page.
    Prevents Werkzeug's debugger HTML (which contains Unicode) from being
    written through the cp1252 console stream on Windows."""
    import traceback as _tb
    safe_msg = str(exc).encode("ascii", errors="xmlcharrefreplace").decode("ascii")
    html = (
        "<h3>Internal Server Error</h3>"
        f"<p>{safe_msg}</p>"
        "<pre style='font-size:11px;color:#666'>"
        + _tb.format_exc().encode("ascii", errors="replace").decode("ascii")
        + "</pre>"
        "<a href='/'>Back to Dashboard</a>"
    )
    return Response(html, status=500, mimetype="text/html; charset=utf-8")

# ── Token Status Caching for UI Login ──────────────────────────────────────────
_token_status_cache = {
    "is_valid": None,  # True, False, or None
    "last_check": 0.0,
    "login_url": None,
    "api_key_configured": False
}

# ── Session-level authentication gate ─────────────────────────────────────────
# Tracks whether the user has explicitly logged in during THIS server process
# lifetime.  A valid token in .env alone is NOT enough — the user must perform
# an explicit login action (OAuth callback, submit token, or auto-login) to set
# this flag.  This prevents page-refresh auto-login, which is a security issue:
# anyone opening the URL would land straight in the dashboard without consent.
_session_authenticated: bool = False

def _check_token_validity_cached():
    import time
    from config import settings
    
    now = time.time()
    # Check validity every 60 seconds (or if never checked)
    if _token_status_cache["is_valid"] is None or (now - _token_status_cache["last_check"] > 60.0):
        _token_status_cache["api_key_configured"] = bool(settings.KITE_API_KEY)
        _token_status_cache["last_check"] = now
        
        if not settings.KITE_API_KEY:
            _token_status_cache["is_valid"] = False
            _token_status_cache["login_url"] = None
            return _token_status_cache
            
        # Call profile() to check token validity
        try:
            from broker.kite_client import get_kite
            kite = get_kite()
            if settings.KITE_ACCESS_TOKEN:
                kite.profile()
                _token_status_cache["is_valid"] = True
            else:
                _token_status_cache["is_valid"] = False
        except Exception:
            _token_status_cache["is_valid"] = False
            
        # Build the Kite login URL
        try:
            from broker.authentication import generate_login_url
            _token_status_cache["login_url"] = generate_login_url()
        except Exception:
            _token_status_cache["login_url"] = f"https://kite.trade/connect/login?api_key={settings.KITE_API_KEY}&v=3"
            
    return _token_status_cache


# ── Bot subprocess management ─────────────────────────────────────────────────

_bot_proc: subprocess.Popen | None = None
_bot_lock = threading.Lock()
_BOT_LOG = ROOT / "bot.log"
_BOT_PID_FILE = ROOT / ".bot.pid"


def _start_bot_proc() -> bool:
    """Launch main.py as a subprocess. Returns True if started, False if already running."""
    global _bot_proc
    if _is_bot_running():
        return False
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "main.py")],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with _bot_lock:
        _bot_proc = proc
    _write_pid(proc.pid)
    return True


def _watchdog() -> None:
    """
    Background thread: every 30 s, if the Kite token is valid but the bot
    is not running, auto-restart it.  This keeps the bot alive across Flask
    restarts, crashes, and initial dashboard loads where the token is already
    persisted in .env.
    """
    import time
    time.sleep(5)  # give Flask a moment to finish starting
    while True:
        try:
            tok = _check_token_validity_cached()
            if tok.get("is_valid") and not _is_bot_running():
                _start_bot_proc()
        except Exception:
            pass
        time.sleep(30)


def _read_log_tail(n: int = 50) -> list[str]:
    """Read the last n lines of bot.log directly from disk."""
    if not _BOT_LOG.exists():
        return []
    try:
        with open(_BOT_LOG, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [l.rstrip() for l in lines[-n:]]
    except Exception:
        return []


def _write_pid(pid: int) -> None:
    try:
        _BOT_PID_FILE.write_text(str(pid))
    except Exception:
        pass


def _read_pid() -> int | None:
    try:
        return int(_BOT_PID_FILE.read_text().strip())
    except Exception:
        return None


def _clear_pid() -> None:
    try:
        _BOT_PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _pid_is_alive(pid: int) -> bool:
    """Return True if the process with the given PID is still running."""
    try:
        import psutil
        p = psutil.Process(pid)
        return p.is_running() and p.status() != "zombie"
    except Exception:
        pass
    # Fallback without psutil: send signal 0 (Unix) or use tasklist (Windows)
    try:
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)  # PROCESS_QUERY_INFORMATION
        if handle:
            import ctypes.wintypes
            code = ctypes.wintypes.DWORD()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return code.value == 259  # STILL_ACTIVE
    except Exception:
        pass
    return False


def _is_bot_running() -> bool:
    """Check in-memory handle, then PID file, then recent log activity."""
    global _bot_proc
    # In-memory handle (same Flask process lifecycle)
    with _bot_lock:
        if _bot_proc is not None:
            _bot_proc.poll()
            if _bot_proc.returncode is None:
                return True
    # PID file (survives Flask restarts)
    pid = _read_pid()
    if pid and _pid_is_alive(pid):
        return True
    # PID file is stale — clean it up
    if pid:
        _clear_pid()
    # Fallback: if bot.log was written to within the last 5 minutes,
    # the bot is running externally (started from terminal, not via UI).
    if _BOT_LOG.exists():
        import time as _time
        age_secs = _time.time() - _BOT_LOG.stat().st_mtime
        if age_secs < 300:  # 5 minutes
            return True
    return False


def _stop_bot() -> bool:
    """Terminate bot process via in-memory handle or PID file. Returns True if killed."""
    global _bot_proc
    killed = False
    with _bot_lock:
        if _bot_proc is not None:
            _bot_proc.poll()
            if _bot_proc.returncode is None:
                _bot_proc.terminate()
                killed = True
            _bot_proc = None
    # Also kill via PID file in case Flask was restarted
    pid = _read_pid()
    if pid and _pid_is_alive(pid):
        try:
            import signal as _signal
            os.kill(pid, _signal.SIGTERM)
            killed = True
        except Exception:
            try:
                subprocess.call(["taskkill", "/PID", str(pid), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                killed = True
            except Exception:
                pass
    _clear_pid()
    return killed


def _db_path() -> str:
    env = dotenv_values(ENV_FILE)
    return str(ROOT / env.get("DB_PATH", "trades.db"))


def _conn():
    db = _db_path()
    if not Path(db).exists():
        return None
    con = sqlite3.connect(db, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


# ── API: status ───────────────────────────────────────────────────────────────

@app.get("/api/status")
def api_status():
    env = dotenv_values(ENV_FILE)

    bot_running = _is_bot_running()

    active_trade = None
    con = _conn()
    if con:
        row = con.execute(
            "SELECT * FROM trades WHERE status='OPEN' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row:
            active_dict = dict(row)
            # Auto-reconcile with Zerodha in LIVE mode if position is already closed at broker
            if env.get("TRADING_MODE") == "LIVE":
                try:
                    kite = _get_kite_safe()
                    if kite:
                        positions = kite.positions().get("net", [])
                        matching = next((p for p in positions if p.get("tradingsymbol") == active_dict["option_symbol"]), None)
                        actual_qty = int(matching.get("quantity", 0)) if matching else 0
                        if actual_qty == 0:
                            # Position is closed at broker — auto close in DB
                            exit_price = float(active_dict.get("entry_price", 0.0))
                            try:
                                orders = kite.orders()
                                sells = [
                                    o for o in orders
                                    if o.get("tradingsymbol") == active_dict["option_symbol"]
                                    and o.get("transaction_type") == "SELL"
                                    and o.get("status") == "COMPLETE"
                                ]
                                if sells:
                                    exit_price = float(sells[-1].get("average_price", exit_price))
                            except Exception:
                                pass
                            pnl = (exit_price - float(active_dict.get("entry_price", 0.0))) * int(active_dict.get("quantity", 20))
                            now_str = datetime.now(timezone.utc).isoformat()
                            con.execute(
                                "UPDATE trades SET status='CLOSED', exit_price=?, exit_time=?, realized_pnl=?, "
                                "updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE trade_id=?",
                                (exit_price, now_str, pnl, active_dict["trade_id"]),
                            )
                            con.commit()
                            active_dict = None
                except Exception:
                    pass
            active_trade = active_dict
        con.close()

    # Get cached token status for UI login modal
    tok_status = _check_token_validity_cached()
    # Apply session gate — same rule as /api/auth/token-status
    _effective_token_valid = tok_status["is_valid"] and _session_authenticated

    # Regime — read last REGIME_CLASSIFIED event from log tail
    regime_label = None
    regime_atr_mult = None
    regime_min_pct = None
    try:
        import re as _re
        log_lines = _read_log_tail(200)
        for line in reversed(log_lines):
            if "REGIME_CLASSIFIED" in line:
                m = _re.search(r'regime=(\w+)', line)
                if m:
                    regime_label = m.group(1)
                ma = _re.search(r'atr_mult=([\d.]+)', line)
                if ma:
                    regime_atr_mult = ma.group(1)
                mp = _re.search(r'min_pct=([\d.]+)', line)
                if mp:
                    regime_min_pct = mp.group(1)
                break
    except Exception:
        pass

    return jsonify({
        "bot_running": bot_running,
        "trading_mode": env.get("TRADING_MODE", "PAPER"),
        "active_trade": active_trade,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "token_valid": _effective_token_valid,
        "api_key_configured": tok_status["api_key_configured"],
        "login_url": tok_status["login_url"],
        "config": {
            "underlying": env.get("UNDERLYING", "SENSEX"),
            "quantity": env.get("QUANTITY", "20"),
            "initial_sl": env.get("INITIAL_SL_POINTS", "30"),
            "break_even": env.get("BREAK_EVEN_TRIGGER_POINTS", "30"),
            "trail_step": env.get("TRAIL_STEP_POINTS", "10"),
            "force_exit": env.get("FORCE_EXIT_TIME", "15:15"),
            "expiry": env.get("CONFIGURED_EXPIRY", ""),
        },
        "ai": {
            "regime": regime_label,
            "regime_atr_mult": regime_atr_mult,
            "regime_min_pct": regime_min_pct,
            "regime_classifier_on": env.get("ENABLE_REGIME_CLASSIFIER", "false").strip("'\"").lower() == "true",
            "regime_use_ai": env.get("REGIME_USE_AI", "false").strip("'\"").lower() == "true",
            "profit_lock_atr_mult": env.get("PROFIT_LOCK_ATR_MULT", "0.0"),
            "profit_lock_min_pct": env.get("PROFIT_LOCK_MIN_PCT", "0.0"),
            "smart_entry_ema_gap": env.get("SMART_ENTRY_MIN_EMA_GAP_PTS", "0"),
            "smart_entry_gap_widening": env.get("SMART_ENTRY_REQUIRE_EMA_GAP_WIDENING", "false").strip("'\"").lower() == "true",
            "smart_entry_body_ratio": env.get("SMART_ENTRY_MIN_BODY_ATR_RATIO", "0"),
            "smart_entry_slope": env.get("SMART_ENTRY_REQUIRE_EMA_SLOPE", "false").strip("'\"").lower() == "true",
            "smart_entry_cooldown": env.get("SMART_ENTRY_COOLDOWN_CANDLES", "0"),
            "option_feed_ok": None,  # populated by bot state file if available
        },
        "log_tail": _read_log_tail(50),
    })


# ── API: trades ───────────────────────────────────────────────────────────────

@app.get("/api/trades")
def api_trades():
    con = _conn()
    if not con:
        return jsonify([])
    rows = con.execute(
        "SELECT * FROM trades ORDER BY created_at DESC LIMIT 200"
    ).fetchall()
    con.close()
    return jsonify([dict(r) for r in rows])


@app.get("/api/trades/active")
def api_active_trade():
    con = _conn()
    if not con:
        return jsonify(None)
    row = con.execute(
        "SELECT * FROM trades WHERE status='OPEN' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    con.close()
    return jsonify(dict(row) if row else None)


# ── API: order actions ────────────────────────────────────────────────────────

@app.get("/api/orders")
def api_orders():
    con = _conn()
    if not con:
        return jsonify([])
    rows = con.execute(
        "SELECT * FROM order_actions ORDER BY created_at DESC LIMIT 300"
    ).fetchall()
    con.close()
    return jsonify([dict(r) for r in rows])


# ── API: candle state (written by bot process to a JSON file) ─────────────────

_STATE_FILE = ROOT / ".bot_state.json"


@app.get("/api/position/ltp")
def api_position_ltp():
    """Return live LTP for the currently open option position directly from Zerodha."""
    con = _conn()
    if not con:
        return jsonify({"ltp": None, "symbol": None})
    row = con.execute(
        "SELECT option_symbol, instrument_token FROM trades WHERE status='OPEN' "
        "ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    con.close()
    if not row:
        return jsonify({"ltp": None, "symbol": None})
    symbol = row["option_symbol"]
    kite = _get_kite_safe()
    if not kite:
        return jsonify({"ltp": None, "symbol": symbol})
    try:
        q = kite.quote([f"BFO:{symbol}"])
        ltp = q.get(f"BFO:{symbol}", {}).get("last_price")
        return jsonify({"ltp": ltp, "symbol": symbol})
    except Exception as exc:
        return jsonify({"ltp": None, "symbol": symbol, "error": str(exc)})


@app.get("/api/ltp")
def api_ltp():
    """Lightweight endpoint: returns only the current SENSEX LTP and timestamp.
    Polled every second by the UI for real-time price display."""
    if not _STATE_FILE.exists():
        return jsonify({"ltp": None, "updated_at": None})
    try:
        with open(_STATE_FILE, "r") as f:
            data = json.load(f)
        return jsonify({"ltp": data.get("ltp"), "updated_at": data.get("updated_at")})
    except Exception:
        return jsonify({"ltp": None, "updated_at": None})


@app.get("/api/candles")
def api_candles():
    """Return the last N completed 5m and 15m candles plus current indicators."""
    if not _STATE_FILE.exists():
        return jsonify({"candles_5m": [], "candles_15m": [], "ltp": None, "signals": []})
    try:
        with open(_STATE_FILE, "r") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception:
        return jsonify({"candles_5m": [], "candles_15m": [], "ltp": None, "signals": []})


# ── API: historical chart data ────────────────────────────────────────────────

@app.get("/api/chart")
def api_chart():
    """
    Return OHLCV candles from Zerodha historical API for charting.

    Query params:
      interval  : minute | 5minute | 15minute | 60minute | day  (default: 5minute)
      from_date : YYYY-MM-DD  (default: today)
      to_date   : YYYY-MM-DD  (default: today)

    Returns JSON array of {t, o, h, l, c, v} sorted oldest-first.
    """
    from datetime import date as _date, timedelta as _td
    interval  = request.args.get("interval",  "5minute")
    from_str  = request.args.get("from_date", str(_date.today()))
    to_str    = request.args.get("to_date",   str(_date.today()))

    _VALID_INTERVALS = {"minute", "3minute", "5minute", "10minute", "15minute",
                        "30minute", "60minute", "day", "week", "month"}
    if interval not in _VALID_INTERVALS:
        return jsonify({"error": f"Invalid interval '{interval}'"}), 400

    try:
        from_dt = datetime.strptime(from_str, "%Y-%m-%d")
        to_dt   = datetime.strptime(to_str,   "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        return jsonify({"error": "Invalid date format — use YYYY-MM-DD"}), 400

    kite = _get_kite_safe()
    if not kite:
        return jsonify({"error": "Not authenticated"}), 401

    # Zerodha per-request candle limits (conservative, well inside their caps):
    #   intraday  → 60 days per call
    #   day/week/month → 400 days per call  (avoids the 2000-candle hard limit)
    from datetime import timedelta as _td
    _CHUNK_DAYS = {
        "minute": 3, "3minute": 7, "5minute": 30, "10minute": 30,
        "15minute": 30, "30minute": 60, "60minute": 60,
        "day": 400, "week": 400, "month": 400,
    }
    chunk = _td(days=_CHUNK_DAYS.get(interval, 60))

    try:
        from market.historical_data import SENSEX_TOKEN
        records = []
        cur_from = from_dt
        while cur_from < to_dt:
            cur_to = min(cur_from + chunk, to_dt)
            batch = kite.historical_data(
                instrument_token=SENSEX_TOKEN,
                from_date=cur_from.strftime("%Y-%m-%d %H:%M:%S"),
                to_date=cur_to.strftime("%Y-%m-%d %H:%M:%S"),
                interval=interval,
            )
            records.extend(batch)
            cur_from = cur_to + _td(seconds=1)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    # Intraday intervals: filter to market hours only (09:15–15:30 IST)
    _INTRADAY = {"minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute"}
    is_intraday = interval in _INTRADAY

    from utils.time_utils import IST

    candles = []
    for r in records:
        ts = r["date"]
        if hasattr(ts, "hour"):
            # Zerodha may return naive (treated as IST) or UTC-aware datetimes.
            # Always convert to IST before comparing hours/minutes.
            if ts.tzinfo is None:
                ts = IST.localize(ts)          # naive → IST
            else:
                ts = ts.astimezone(IST)        # UTC-aware (or any tz) → IST

            if is_intraday:
                h, m = ts.hour, ts.minute
                # Drop pre-market (before 09:15) and post-market (after 15:30) IST
                if (h, m) < (9, 15) or (h, m) > (15, 30):
                    continue

        t = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        candles.append({
            "t": t,
            "o": float(r["open"]),
            "h": float(r["high"]),
            "l": float(r["low"]),
            "c": float(r["close"]),
            "v": int(r.get("volume") or 0),
        })
    return jsonify(candles)


# ── API: chart signal markers (entry / SL / T1 / T2) ────────────────────────

@app.get("/api/chart/signals")
def api_chart_signals():
    """
    Return today's trades as chart signal markers with SL, T1, T2 levels.

    Query params:
      date : YYYY-MM-DD  (default: today IST)

    Each row:
      { time, direction, strategy, entry, sl, t1, t2, status, exit_price, exit_time }
    """
    from datetime import date as _date
    day = request.args.get("date", str(_date.today()))
    con = _conn()
    if not con:
        return jsonify([])
    try:
        rows = con.execute(
            "SELECT strategy_type, entry_time, entry_price, current_stop, "
            "target_reference, sl_points, target_points, status, "
            "exit_price, exit_time, exit_reason, "
            "sensex_entry, sensex_sl, sensex_t1, sensex_t2 "
            "FROM trades "
            "WHERE entry_time LIKE ? "
            "ORDER BY entry_time ASC LIMIT 100",
            (f"{day}%",),
        ).fetchall()
    finally:
        con.close()

    result = []
    for r in rows:
        r = dict(r)
        entry = r.get("entry_price") or 0
        sl = r.get("current_stop")
        t1 = r.get("target_reference")
        tgt_pts = r.get("target_points") or 0
        t2 = round(entry + 2 * tgt_pts, 2) if entry and tgt_pts else None
        stype = r.get("strategy_type") or ""
        direction = "CE" if stype.upper().startswith("CE") else "PE"
        parts = stype.split("_", 1)
        label = parts[1] if len(parts) > 1 else stype
        # SENSEX index-level prices (populated for new trades; None for old rows)
        sx_entry = r.get("sensex_entry")
        sx_sl    = r.get("sensex_sl")
        sx_t1    = r.get("sensex_t1")
        sx_t2    = r.get("sensex_t2")
        result.append({
            "time":         r.get("entry_time"),
            "direction":    direction,
            "strategy":     label,
            "entry":        entry,
            "sl":           round(sl, 2) if sl is not None else None,
            "t1":           round(t1, 2) if t1 is not None else None,
            "t2":           t2,
            "status":       r.get("status"),
            "exit_price":   r.get("exit_price"),
            "exit_time":    r.get("exit_time"),
            "exit_reason":  r.get("exit_reason"),
            # SENSEX index-level — use these for chart markers on index candle chart
            "sensex_entry": round(sx_entry, 2) if sx_entry is not None else None,
            "sensex_sl":    round(sx_sl,    2) if sx_sl    is not None else None,
            "sensex_t1":    round(sx_t1,    2) if sx_t1    is not None else None,
            "sensex_t2":    round(sx_t2,    2) if sx_t2    is not None else None,
        })
    return jsonify(result)


# ── API: pnl timeseries (for chart) ──────────────────────────────────────────

@app.get("/api/pnl")
def api_pnl():
    con = _conn()
    if not con:
        return jsonify([])
    rows = con.execute(
        "SELECT exit_time, realized_pnl, strategy_type, option_symbol "
        "FROM trades WHERE status='CLOSED' AND exit_time IS NOT NULL "
        "ORDER BY exit_time ASC LIMIT 200"
    ).fetchall()
    con.close()
    return jsonify([dict(r) for r in rows])


# ── API: shadow / paper trade results ────────────────────────────────────────

@app.get("/api/shadow/trades")
def api_shadow_trades():
    """
    Return PAPER/SHADOW trades with full risk detail.
    Only rows whose entry_order_id starts with 'PAPER_' are true simulated trades.

    Query params:
      date : YYYY-MM-DD — filter by entry date (IST).  Omit for all dates.
    """
    date_filter = request.args.get("date", "").strip() or None
    con = _conn()
    if not con:
        return jsonify([])
    try:
        if date_filter:
            rows = con.execute(
                "SELECT * FROM trades "
                "WHERE entry_order_id LIKE 'PAPER_%' AND entry_time LIKE ? "
                "ORDER BY created_at DESC LIMIT 500",
                (f"{date_filter}%",),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM trades "
                "WHERE entry_order_id LIKE 'PAPER_%' "
                "ORDER BY created_at DESC LIMIT 500",
            ).fetchall()
    finally:
        con.close()
    return jsonify([dict(r) for r in rows])


@app.get("/api/shadow/trades/<trade_id>")
def api_shadow_trade_detail(trade_id: str):
    """Return a single PAPER/SHADOW trade by trade_id."""
    con = _conn()
    if not con:
        return jsonify(None), 404
    row = con.execute(
        "SELECT * FROM trades WHERE trade_id=? AND entry_order_id LIKE 'PAPER_%'",
        (trade_id,),
    ).fetchone()
    con.close()
    return jsonify(dict(row) if row else None), (200 if row else 404)


@app.get("/api/shadow/dates")
def api_shadow_dates():
    """Return distinct entry dates (YYYY-MM-DD) for PAPER/SHADOW trades, newest first."""
    con = _conn()
    if not con:
        return jsonify([])
    rows = con.execute(
        "SELECT DISTINCT substr(entry_time,1,10) AS d FROM trades "
        "WHERE entry_order_id LIKE 'PAPER_%' AND entry_time IS NOT NULL "
        "ORDER BY d DESC"
    ).fetchall()
    con.close()
    return jsonify([r["d"] for r in rows if r["d"]])


@app.get("/api/shadow/active")
def api_shadow_active():
    """
    Return the currently OPEN shadow/paper trade merged with live bot state.

    Combines:
      - DB row (entry price, SL pts, TSL pts, target pts, current_stop, highest_ltp)
      - .bot_state.json (live SENSEX LTP, bot_state machine state)
      - Zerodha REST quote for the active option symbol (live option LTP)

    The frontend polls this every 2 s to drive the live order tracker panel.
    """
    con = _conn()
    if not con:
        return jsonify(None)
    row = con.execute(
        "SELECT * FROM trades "
        "WHERE entry_order_id LIKE 'PAPER_%' AND status='OPEN' "
        "ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    con.close()
    if not row:
        return jsonify(None)

    trade = dict(row)

    # Merge live state from bot_state.json
    ltp = None
    bot_state = None
    if _STATE_FILE.exists():
        try:
            with open(_STATE_FILE, "r") as f:
                st = json.load(f)
            ltp = st.get("ltp")
            bot_state = st.get("bot_state")
            trade["updated_at"] = st.get("updated_at")
            # active_trade block from bot contains live current_stop + highest_ltp
            at = st.get("active_trade")
            if at:
                if at.get("current_stop") is not None:
                    trade["current_stop"]   = at["current_stop"]
                if at.get("highest_ltp") is not None:
                    trade["highest_ltp"]    = at["highest_ltp"]
                if at.get("target") is not None:
                    trade["target_reference"] = at["target"]
        except Exception:
            pass

    trade["live_ltp"]  = ltp
    trade["bot_state"] = bot_state

    # Fetch live option LTP from Zerodha REST so the shadow P&L reflects the
    # actual option premium rather than the SENSEX spot price.
    # Only attempted when symbol is available; silently skipped on any error.
    option_symbol = trade.get("option_symbol")
    trade["option_ltp"] = None
    if option_symbol:
        try:
            kite = _get_kite_safe()
            if kite:
                q = kite.quote([f"BFO:{option_symbol}"])
                opt_ltp = q.get(f"BFO:{option_symbol}", {}).get("last_price")
                if opt_ltp is not None:
                    trade["option_ltp"] = float(opt_ltp)
        except Exception:
            pass

    return jsonify(trade)


@app.get("/shadow")
def shadow_results_page():
    return render_template("shadow_results.html")


# ── API: bot control ──────────────────────────────────────────────────────────

@app.post("/api/bot/start")
def api_bot_start():
    if _is_bot_running():
        return jsonify({"ok": False, "error": "Bot already running"}), 400
    _start_bot_proc()
    pid = _read_pid()
    return jsonify({"ok": True, "pid": pid})


@app.post("/api/bot/stop")
def api_bot_stop():
    if not _is_bot_running():
        return jsonify({"ok": False, "error": "Bot is not running"}), 400
    killed = _stop_bot()
    return jsonify({"ok": killed})


# ── API: env config ───────────────────────────────────────────────────────────

# Keys that are safe to expose to the UI (exclude secrets)
_SAFE_KEYS = {
    "TRADING_MODE", "ENABLE_LIVE_TRADING", "UNDERLYING", "QUANTITY",
    "INITIAL_SL_POINTS", "BREAK_EVEN_TRIGGER_POINTS", "TRAIL_STEP_POINTS",
    "INITIAL_TARGET_OFFSET_POINTS", "TARGET_TRAIL_STEP_POINTS",
    "FORCE_EXIT_TIME", "NO_NEW_ENTRY_AFTER", "TIMEZONE",
    "EXPIRY_MODE", "CONFIGURED_EXPIRY", "DB_PATH", "LOG_LEVEL",
    "KITE_TOTP_SECRET", "KITE_USER_ID", "KITE_USERNAME",
    "ENABLE_EMA_STRATEGY", "ENABLE_ORB_STRATEGY",
    "ENABLE_MOMENTUM_PHASE", "MOMENTUM_MIN_BODY_PTS",
    "MOMENTUM_WINDOW_START", "MOMENTUM_WINDOW_END",
    # Order Block strategy
    "ENABLE_OB_STRATEGY", "OB_SWING_LENGTH", "OB_MAX_ATR_MULT",
    "OB_ATR_PERIOD", "OB_MAX_BLOCKS", "OB_INVALIDATION",
    # TRB strategy
    "ENABLE_TRB_STRATEGY", "TRB_CANDLE_START_TIME", "TRB_CANDLE_DURATION_MINS",
    "TRB_MIN_BODY_RATIO", "TRB_BUFFER_ATR_MULT",
    # VWAP Retest strategy
    "ENABLE_VWAP_STRATEGY", "VWAP_RETEST_LOOKBACK", "VWAP_MIN_BOUNCE_PTS",
    # PDHL Breakout strategy
    "ENABLE_PDHL_STRATEGY", "PDHL_BUFFER_PTS",
    # NATR Trailing Stop strategy
    "ENABLE_NATR_STRATEGY", "NATR_PERIOD", "NATR_MULT",
    # ATR Copilot strategy
    "ENABLE_ATR_COPILOT_STRATEGY", "ATR_COPILOT_PERIOD", "ATR_COPILOT_EMA_PERIOD",
    "ATR_COPILOT_BAND_MULT", "ATR_COPILOT_MIN_RR", "ATR_COPILOT_LONG_MIN_RR",
    # Smart Entry filters
    "SMART_ENTRY_MIN_BODY_ATR_RATIO", "SMART_ENTRY_REQUIRE_EMA_SLOPE",
    "SMART_ENTRY_COOLDOWN_CANDLES", "SMART_ENTRY_MIN_EMA_GAP_PTS",
    "SMART_ENTRY_REQUIRE_EMA_GAP_WIDENING", "SMART_ENTRY_REQUIRE_15M_TREND",
    "SMART_ENTRY_SQUEEZE_BYPASS", "SMART_ENTRY_SQUEEZE_CANDLES",
    "SMART_ENTRY_SQUEEZE_BODY_ATR_RATIO",
    # Spot ATR risk (Mode C/D)
    "USE_SPOT_ATR_RISK", "SPOT_ATR_PERIOD", "SPOT_ATR_SL_MULT",
    "SPOT_ATR_TARGET_RR", "SPOT_ATR_TRAIL_RR",
    # Smart exit
    "ENABLE_SMART_EXIT", "ENABLE_REVERSAL_EXIT", "ENABLE_EMA_COLLAPSE_EXIT",
    "ENABLE_PROFIT_LOCK_EXIT", "ENABLE_TIME_DECAY_EXIT", "ENABLE_DAILY_LOSS_LIMIT",
    "PROFIT_LOCK_MULTIPLIER", "TIME_DECAY_EXIT_AFTER",
    "TIME_DECAY_MIN_PNL_PTS", "DAILY_LOSS_LIMIT_PTS",
}

_EDITABLE_KEYS = {
    "TRADING_MODE", "QUANTITY", "INITIAL_SL_POINTS", "BREAK_EVEN_TRIGGER_POINTS",
    "TRAIL_STEP_POINTS", "INITIAL_TARGET_OFFSET_POINTS", "FORCE_EXIT_TIME",
    "NO_NEW_ENTRY_AFTER", "CONFIGURED_EXPIRY", "EXPIRY_MODE", "LOG_LEVEL",
    "ENABLE_LIVE_TRADING", "KITE_TOTP_SECRET",
    "ENABLE_EMA_STRATEGY", "ENABLE_ORB_STRATEGY",
    "ENABLE_MOMENTUM_PHASE", "MOMENTUM_MIN_BODY_PTS",
    "MOMENTUM_WINDOW_START", "MOMENTUM_WINDOW_END",
    # Order Block strategy
    "ENABLE_OB_STRATEGY", "OB_SWING_LENGTH", "OB_MAX_ATR_MULT",
    "OB_ATR_PERIOD", "OB_MAX_BLOCKS", "OB_INVALIDATION",
    # TRB strategy
    "ENABLE_TRB_STRATEGY", "TRB_CANDLE_START_TIME", "TRB_CANDLE_DURATION_MINS",
    "TRB_MIN_BODY_RATIO", "TRB_BUFFER_ATR_MULT",
    # VWAP Retest strategy
    "ENABLE_VWAP_STRATEGY", "VWAP_RETEST_LOOKBACK", "VWAP_MIN_BOUNCE_PTS",
    # PDHL Breakout strategy
    "ENABLE_PDHL_STRATEGY", "PDHL_BUFFER_PTS",
    # NATR Trailing Stop strategy
    "ENABLE_NATR_STRATEGY", "NATR_PERIOD", "NATR_MULT",
    # ATR Copilot strategy
    "ENABLE_ATR_COPILOT_STRATEGY", "ATR_COPILOT_PERIOD", "ATR_COPILOT_EMA_PERIOD",
    "ATR_COPILOT_BAND_MULT", "ATR_COPILOT_MIN_RR", "ATR_COPILOT_LONG_MIN_RR",
    # Smart Entry filters
    "SMART_ENTRY_MIN_BODY_ATR_RATIO", "SMART_ENTRY_REQUIRE_EMA_SLOPE",
    "SMART_ENTRY_COOLDOWN_CANDLES", "SMART_ENTRY_MIN_EMA_GAP_PTS",
    "SMART_ENTRY_REQUIRE_EMA_GAP_WIDENING", "SMART_ENTRY_REQUIRE_15M_TREND",
    "SMART_ENTRY_SQUEEZE_BYPASS", "SMART_ENTRY_SQUEEZE_CANDLES",
    "SMART_ENTRY_SQUEEZE_BODY_ATR_RATIO",
    # Spot ATR risk (Mode C/D)
    "USE_SPOT_ATR_RISK", "SPOT_ATR_PERIOD", "SPOT_ATR_SL_MULT",
    "SPOT_ATR_TARGET_RR", "SPOT_ATR_TRAIL_RR",
    # Smart exit
    "ENABLE_SMART_EXIT", "ENABLE_REVERSAL_EXIT", "ENABLE_EMA_COLLAPSE_EXIT",
    "ENABLE_PROFIT_LOCK_EXIT", "ENABLE_TIME_DECAY_EXIT", "ENABLE_DAILY_LOSS_LIMIT",
    "PROFIT_LOCK_MULTIPLIER", "TIME_DECAY_EXIT_AFTER",
    "TIME_DECAY_MIN_PNL_PTS", "DAILY_LOSS_LIMIT_PTS",
}


@app.get("/api/env")
def api_env_get():
    env = dotenv_values(ENV_FILE)
    result = {k: v for k, v in env.items() if k in _SAFE_KEYS}
    # Add a safe flag so the UI knows the password is stored (without exposing it)
    result["KITE_PASSWORD_SET"] = bool(env.get("KITE_PASSWORD", "").strip())
    return jsonify(result)


@app.post("/api/env")
def api_env_post():
    try:
        from config import settings
        from dotenv import load_dotenv
        data: dict = request.get_json(force=True) or {}
        updated = {}
        for key, value in data.items():
            if key not in _EDITABLE_KEYS:
                continue
            set_key(str(ENV_FILE), key, str(value))
            os.environ[key] = str(value)
            updated[key] = value

        # Reload settings in memory so the Flask process immediately picks them up
        load_dotenv(override=True)
        # Manually sync key attributes to settings module
        for key, val in updated.items():
            if hasattr(settings, key):
                orig_type = type(getattr(settings, key))
                try:
                    if orig_type is bool:
                        cast_val = str(val).lower() in ("true", "1", "yes")
                    elif orig_type is int:
                        cast_val = int(val)
                    elif orig_type is float:
                        cast_val = float(val)
                    else:
                        cast_val = str(val)
                    setattr(settings, key, cast_val)
                except Exception:
                    pass
        return jsonify({"ok": True, "updated": updated})
    except Exception as exc:
        import traceback
        return jsonify({"ok": False, "error": str(exc), "detail": traceback.format_exc()}), 500


# ── API: live Zerodha positions + orders ──────────────────────────────────────

def _get_kite_safe():
    """Return an authenticated KiteConnect instance, or None on failure."""
    try:
        from broker.kite_client import get_kite
        return get_kite()
    except Exception:
        return None


@app.get("/api/zerodha/positions")
def api_zerodha_positions():
    """Fetch live day positions directly from Zerodha."""
    kite = _get_kite_safe()
    if not kite:
        return jsonify({"error": "Kite client unavailable — check API key/token"}), 503
    try:
        day = kite.positions().get("day", [])
        # Enrich with computed fields
        for p in day:
            p["pnl"] = p.get("pnl", 0)
            p["unrealised"] = p.get("unrealised", 0)
        return jsonify(day)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/zerodha/orders")
def api_zerodha_orders():
    """Fetch today's orders from Zerodha."""
    kite = _get_kite_safe()
    if not kite:
        return jsonify({"error": "Kite client unavailable"}), 503
    try:
        orders = kite.orders()
        return jsonify(orders)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/zerodha/import")
def api_zerodha_import():
    """
    Import an existing open Zerodha position into trades.db so the bot
    can take over trailing stop management on next start.

    Body JSON:
    {
        "tradingsymbol": "SENSEX2691075100CE",
        "entry_price":   294.25,
        "highest_ltp":   310.00,   // optional, defaults to entry_price
        "sl_points":     30,       // optional, from .env
        "be_points":     30,       // optional, from .env
        "trail_points":  10,       // optional, from .env
        "target_pts":    50        // optional, from .env
    }
    """
    import uuid as _uuid
    from dotenv import dotenv_values as _dv
    from utils.price_utils import round_to_tick as _rtt
    from persistence.models import init_db as _init, upsert_trade as _upsert, fetch_active_trade as _fat
    from broker.instrument_repository import find_instrument, load_instruments
    from utils.time_utils import IST as _IST

    data: dict = request.get_json(force=True) or {}
    symbol = data.get("tradingsymbol", "").strip()
    if not symbol:
        return jsonify({"ok": False, "error": "tradingsymbol is required"}), 400

    # Check no active trade exists
    _init()
    active = _fat()
    if active:
        return jsonify({
            "ok": False,
            "error": f"Active trade already exists: {active['trade_id']} ({active['option_symbol']}). "
                     "Close it first."
        }), 409

    # Fetch position from Zerodha to verify qty
    kite = _get_kite_safe()
    if not kite:
        return jsonify({"ok": False, "error": "Kite client unavailable"}), 503

    try:
        positions = kite.positions().get("day", [])
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Could not fetch positions: {exc}"}), 500

    pos = next((p for p in positions if p["tradingsymbol"] == symbol), None)
    if not pos:
        return jsonify({"ok": False, "error": f"'{symbol}' not found in today's positions"}), 404

    qty = int(pos.get("quantity", 0))
    if qty <= 0:
        return jsonify({"ok": False, "error": f"'{symbol}' has qty={qty} — nothing to import"}), 400

    ltp_now = float(pos.get("last_price", 0))

    # Strategy type from symbol suffix
    strategy_type = "CE" if symbol.endswith("CE") else "PE"

    # Risk params — body overrides .env
    env = dotenv_values(ENV_FILE)
    entry_price  = float(data.get("entry_price",  pos.get("average_price", ltp_now)))
    highest_ltp  = float(data.get("highest_ltp",  max(ltp_now, entry_price)))
    sl_points    = float(data.get("sl_points",    env.get("INITIAL_SL_POINTS", 30)))
    be_points    = float(data.get("be_points",    env.get("BREAK_EVEN_TRIGGER_POINTS", 30)))
    trail_points = float(data.get("trail_points", env.get("TRAIL_STEP_POINTS", 10)))
    target_pts   = float(data.get("target_pts",   env.get("INITIAL_TARGET_OFFSET_POINTS", 50)))

    # Compute current stop based on highest_ltp
    current_stop = _rtt(entry_price - sl_points)
    target_ref   = entry_price + target_pts
    if highest_ltp >= entry_price + be_points:
        above_be     = highest_ltp - (entry_price + be_points)
        steps        = int(above_be // trail_points)
        current_stop = _rtt(entry_price + steps * trail_points)
        target_ref   = (entry_price + target_pts) + steps * trail_points

    # Look up instrument token
    try:
        load_instruments()
        instrument = find_instrument(symbol)
        token = int(instrument["instrument_token"]) if instrument else 0
    except Exception:
        token = 0

    if token == 0:
        return jsonify({"ok": False, "error": f"Instrument token not found for '{symbol}'"}), 404

    # Write to DB
    now_str  = datetime.now(timezone.utc).isoformat()
    trade_id = f"TRADE_{strategy_type}_IMPORTED_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{_uuid.uuid4().hex[:6]}"
    _upsert({
        "trade_id":         trade_id,
        "strategy_type":    strategy_type,
        "signal_timestamp": now_str,
        "option_symbol":    symbol,
        "instrument_token": token,
        "quantity":         qty,
        "entry_order_id":   "IMPORTED",
        "entry_price":      entry_price,
        "entry_time":       now_str,
        "stop_order_id":    None,
        "current_stop":     current_stop,
        "highest_ltp":      highest_ltp,
        "target_reference": target_ref,
        "status":           "OPEN",
    })

    return jsonify({
        "ok":           True,
        "trade_id":     trade_id,
        "symbol":       symbol,
        "qty":          qty,
        "entry_price":  entry_price,
        "current_stop": current_stop,
        "highest_ltp":  highest_ltp,
        "target_ref":   target_ref,
        "message":      "Position imported. Set TRADING_MODE=LIVE and start the bot to activate."
    })


# ── Root ──────────────────────────────────────────────────────────────────────

@app.route("/favicon.ico")
def favicon():
    # Gracefully handle browser favicon requests without 404 logging
    return "", 204


def _handle_request_token(request_token: str):
    """
    Shared logic: exchange a Zerodha request_token for an access_token,
    save it to .env, sync settings, and reset the token cache.
    Returns (access_token, None) on success or (None, error_str) on failure.
    """
    try:
        from broker.authentication import complete_login
        access_token = complete_login(request_token)

        set_key(str(ENV_FILE), "KITE_ACCESS_TOKEN", access_token)
        os.environ["KITE_ACCESS_TOKEN"] = access_token

        from config import settings
        from dotenv import load_dotenv
        load_dotenv(override=True)
        settings.KITE_ACCESS_TOKEN = access_token

        # Reset the KiteConnect singleton so the next call to get_kite()
        # creates a fresh instance with the new access token.
        # Without this, get_kite() returns the old stale instance and
        # profile() continues to fail → banner never hides.
        import broker.kite_client as _kc
        _kc._kite = None

        global _token_status_cache, _session_authenticated
        _token_status_cache["is_valid"] = True
        _token_status_cache["last_check"] = 0.0  # force re-validation on next poll
        _session_authenticated = True  # explicit login action performed

        return access_token, None
    except Exception as exc:
        return None, str(exc)


@app.get("/")
def index():
    """Dashboard. Also handles Zerodha OAuth redirect when redirect URL = http://127.0.0.1:5000"""
    result = _handle_oauth_return()
    if result is not None:
        return result
    return render_template("index.html")


# ── Catch-all OAuth callback routes ──────────────────────────────────────────
# Zerodha will redirect to whichever URL is registered in the Kite developer
# console.  We register handlers for every common variant so the app works
# regardless of which one you have configured.

def _handle_oauth_return():
    """Shared handler for any route that receives a Zerodha OAuth callback."""
    from flask import redirect as _redirect

    request_token = request.args.get("request_token")
    status        = request.args.get("status", "")

    if status and status != "success":
        html = (
            f"<h3>Zerodha Login Failed</h3><p>Status: {status}</p>"
            "<a href='/'>Back to Dashboard</a>"
        )
        return Response(html, status=400, mimetype="text/html; charset=utf-8")

    if not request_token:
        # No token — this is a normal page visit, not a callback
        return None  # signal: not a callback

    _, err = _handle_request_token(request_token)
    if err:
        # Encode err as ASCII-safe so Windows cp1252 never chokes on
        # Unicode characters that Zerodha may embed in error messages.
        safe_err = err.encode("ascii", errors="xmlcharrefreplace").decode("ascii")
        html = (
            f"<h3>Authentication Error</h3><p>{safe_err}</p>"
            "<a href='/'>Back to Dashboard</a>"
        )
        return Response(html, status=400, mimetype="text/html; charset=utf-8")

    # Auto-start bot
    if not _is_bot_running():
        try:
            global _bot_proc
            proc = subprocess.Popen(
                [sys.executable, str(ROOT / "main.py")],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with _bot_lock:
                _bot_proc = proc
            _write_pid(proc.pid)
        except Exception:
            pass

    return _redirect("/")


@app.get("/callback")
def kite_callback():
    """Zerodha OAuth callback — configure Redirect URL as http://127.0.0.1:5000/callback"""
    result = _handle_oauth_return()
    if result is None:
        from flask import redirect as _redirect
        return _redirect("/")
    return result


@app.get("/auth")
def kite_auth():
    """Alt callback path — configure Redirect URL as http://127.0.0.1:5000/auth"""
    result = _handle_oauth_return()
    if result is None:
        from flask import redirect as _redirect
        return _redirect("/")
    return result


@app.get("/strategies")
def strategies_page():
    return render_template("strategies.html")


@app.post("/api/auth/submit")
def api_auth_submit():
    import urllib.parse
    data = request.get_json(force=True) or {}
    token_or_url = data.get("token_or_url", "").strip()
    if not token_or_url:
        return jsonify({"ok": False, "error": "No token or URL provided"}), 400

    # Extract request_token if they pasted the full redirect URL
    if "request_token=" in token_or_url:
        parsed = urllib.parse.urlparse(token_or_url)
        params = urllib.parse.parse_qs(parsed.query)
        request_token = params.get("request_token", [None])[0]
    else:
        request_token = token_or_url

    if not request_token:
        return jsonify({"ok": False, "error": "Could not parse request_token from input"}), 400

    access_token, err = _handle_request_token(request_token)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, "access_token": access_token})


@app.get("/api/auth/token-status")
def api_auth_token_status():
    """
    Lightweight endpoint the UI polls on page load and after login.

    Security gate: returns token_valid=True ONLY when:
      1. The Zerodha access token is valid (kite.profile() succeeds), AND
      2. The user has explicitly logged in during this server session
         (_session_authenticated is True).

    This prevents page-refresh auto-login: a valid token persisted in .env
    from a previous session will NOT bypass the login screen.
    """
    global _session_authenticated
    tok = _check_token_validity_cached()
    # If not session-authenticated, always report as not logged in so the
    # UI shows the login screen — regardless of what's in .env.
    effective_valid = tok["is_valid"] and _session_authenticated
    return jsonify({
        "token_valid": effective_valid,
        "api_key_configured": tok["api_key_configured"],
        "login_url": tok["login_url"],
    })


@app.get("/api/auth/login-url")
def api_auth_login_url():
    """
    Always returns a FRESH Kite Connect login URL.
    Never cached — Zerodha's sess_id is single-use and expires quickly.
    """
    from config import settings
    if not settings.KITE_API_KEY:
        return jsonify({"ok": False, "error": "KITE_API_KEY not configured in .env"}), 400
    try:
        from broker.authentication import generate_login_url
        url = generate_login_url()
        return jsonify({"ok": True, "login_url": url})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/auth/finish")
def api_auth_finish():
    """
    Complete the Zerodha OAuth handshake by replaying /connect/finish
    server-side using the browser's Zerodha session cookies.

    The browser sends:
      { "sess_id": "...", "kite_cookies": {"kf_session": "...", ...} }

    We hit https://kite.zerodha.com/connect/finish?api_key=...&sess_id=...
    with those cookies (simulating the authenticated browser) to get the
    redirect URL containing request_token, then exchange it for access_token.
    """
    import urllib.parse as _up
    import requests as _req
    from config import settings
    from dotenv import load_dotenv

    data = request.get_json(force=True) or {}
    sess_id      = data.get("sess_id", "").strip()
    kite_cookies = data.get("kite_cookies", {})

    if not sess_id:
        return jsonify({"ok": False, "error": "sess_id is required"}), 400

    api_key    = settings.KITE_API_KEY
    api_secret = settings.KITE_API_SECRET
    if not api_key or not api_secret:
        return jsonify({"ok": False, "error": "KITE_API_KEY / KITE_API_SECRET not set in .env"}), 400

    finish_url = f"https://kite.zerodha.com/connect/finish?api_key={api_key}&sess_id={sess_id}"

    sess = _req.Session()
    sess.headers.update({
        "User-Agent": request.headers.get("User-Agent", "Mozilla/5.0"),
        "Referer": "https://kite.zerodha.com/",
        "Accept": "text/html,application/xhtml+xml,*/*",
    })

    # Plant the browser's Zerodha cookies into our requests session
    for name, value in kite_cookies.items():
        sess.cookies.set(name, value, domain=".zerodha.com")

    try:
        r = sess.get(finish_url, allow_redirects=False, timeout=15)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Network error: {exc}"}), 500

    redirect_loc = r.headers.get("Location", "")

    if not redirect_loc:
        body = r.text[:400] if r.text else "(empty)"
        return jsonify({
            "ok": False,
            "error": f"Zerodha did not redirect (HTTP {r.status_code}). "
                     f"The sess_id may be expired — try logging in again. Response: {body}"
        }), 400

    parsed     = _up.urlparse(redirect_loc)
    params     = _up.parse_qs(parsed.query)

    if params.get("error") or params.get("error_type"):
        msg = params.get("message", params.get("error", ["Unknown error"]))[0]
        return jsonify({"ok": False, "error": f"Zerodha error: {msg}"}), 400

    tokens = params.get("request_token")
    if not tokens:
        return jsonify({
            "ok": False,
            "error": f"No request_token in redirect: {redirect_loc[:200]}"
        }), 400

    request_token = tokens[0]

    # Exchange request_token → access_token
    access_token, err = _handle_request_token(request_token)
    if err:
        return jsonify({"ok": False, "error": err}), 400

    # Fetch profile
    profile = {}
    try:
        from broker.kite_client import get_kite
        kite = get_kite()
        profile = kite.profile()
    except Exception:
        pass

    # Auto-start bot
    if not _is_bot_running():
        try:
            global _bot_proc
            proc = subprocess.Popen(
                [sys.executable, str(ROOT / "main.py")],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with _bot_lock:
                _bot_proc = proc
            _write_pid(proc.pid)
        except Exception:
            pass

    return jsonify({"ok": True, "profile": profile})


@app.post("/api/auth/login")
def api_auth_login():
    """
    Automated login endpoint.

    Accepts JSON: {user_id, password, totp?}
    - user_id   : required
    - password  : required (falls back to KITE_PASSWORD in .env if blank)
    - totp      : optional — if omitted, auto-generated from KITE_TOTP_SECRET in .env
                  If Zerodha returns a CAPTCHA/2FA error, the response sets
                  need_totp=true so the UI can prompt the user for their live code.
    """
    from config import settings
    from dotenv import load_dotenv

    data     = request.get_json(force=True) or {}
    user_id  = data.get("user_id",  "").strip()
    password = data.get("password", "").strip()
    totp     = data.get("totp",     "").strip()

    # Fall back to .env values if the UI sent empty strings
    env_vals = dotenv_values(ENV_FILE)
    if not user_id:
        user_id = env_vals.get("KITE_USER_ID", "") or env_vals.get("KITE_USERNAME", "")
    if not password:
        password = env_vals.get("KITE_PASSWORD", "")
    if not totp:
        totp = env_vals.get("KITE_TOTP_SECRET", "")

    if not user_id:
        return jsonify({"ok": False, "error": "Zerodha User ID is required"}), 400
    if not password:
        return jsonify({"ok": False, "error": "Password is required (set KITE_PASSWORD in .env or enter it above)"}), 400

    api_key    = settings.KITE_API_KEY
    api_secret = settings.KITE_API_SECRET
    if not api_key or not api_secret:
        return jsonify({"ok": False, "error": "KITE_API_KEY / KITE_API_SECRET not configured in .env"}), 400

    try:
        from broker.auto_auth import login_and_get_access_token
        access_token = login_and_get_access_token(api_key, api_secret, user_id, password, totp)
    except Exception as exc:
        err_str = str(exc)
        # Detect CAPTCHA / 2FA challenges — tell the UI to show the TOTP input
        low = err_str.lower()
        if any(kw in low for kw in ("captcha", "twofa", "2fa", "totp", "invalid twofa")):
            return jsonify({"ok": False, "error": err_str, "need_totp": True}), 401
        return jsonify({"ok": False, "error": err_str}), 401

    # Persist the new access token
    set_key(str(ENV_FILE), "KITE_ACCESS_TOKEN", access_token)
    os.environ["KITE_ACCESS_TOKEN"] = access_token
    load_dotenv(override=True)
    settings.KITE_ACCESS_TOKEN = access_token

    # Reset KiteConnect singleton so it picks up the new token
    import broker.kite_client as _kc
    _kc._kite = None

    # Reset token cache so status is re-validated on next poll
    global _token_status_cache, _session_authenticated
    _token_status_cache["is_valid"]   = True
    _token_status_cache["last_check"] = 0.0
    _session_authenticated = True  # explicit login action performed

    # Fetch profile for the UI
    profile = {}
    try:
        from broker.kite_client import get_kite
        kite = get_kite()
        profile = kite.profile()
    except Exception:
        pass

    # Auto-start the bot
    try:
        _start_bot_proc()
    except Exception:
        pass

    return jsonify({"ok": True, "profile": profile})


@app.post("/api/auth/logout")
def api_auth_logout():
    """
    Logout: stops the bot, clears KITE_ACCESS_TOKEN from .env,
    and resets the KiteConnect singleton + token cache.
    """
    # Stop bot first
    _stop_bot()

    # Clear access token from .env and memory
    set_key(str(ENV_FILE), "KITE_ACCESS_TOKEN", "")
    os.environ["KITE_ACCESS_TOKEN"] = ""

    from config import settings
    from dotenv import load_dotenv
    load_dotenv(override=True)
    settings.KITE_ACCESS_TOKEN = ""

    # Reset KiteConnect singleton
    import broker.kite_client as _kc
    _kc._kite = None

    # Force token re-check → will return invalid
    global _token_status_cache, _session_authenticated
    _token_status_cache["is_valid"]   = False
    _token_status_cache["last_check"] = 0.0
    _session_authenticated = False  # user explicitly logged out — require re-login

    return jsonify({"ok": True})


@app.get("/api/auth/profile")
def api_auth_profile():
    """Return the authenticated user's Zerodha profile."""
    try:
        from broker.kite_client import get_kite
        kite = get_kite()
        profile = kite.profile()
        return jsonify({"ok": True, "profile": profile})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 401


# ── Watchdog: auto-start bot when token is valid ─────────────────────────────
_wd = threading.Thread(target=_watchdog, daemon=True, name="bot-watchdog")
_wd.start()

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
