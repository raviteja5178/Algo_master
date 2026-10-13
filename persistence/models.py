"""
SQLite persistence models using plain sqlite3.
Schema is created on first run; migrations are additive only.
"""

import sqlite3
from contextlib import contextmanager
from typing import Generator

from config import settings

# ── Schema ─────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id            TEXT PRIMARY KEY,
    strategy_type       TEXT NOT NULL,           -- CE | PE
    signal_timestamp    TEXT NOT NULL,
    option_symbol       TEXT NOT NULL,
    instrument_token    INTEGER NOT NULL,
    quantity            INTEGER NOT NULL,
    entry_order_id      TEXT,
    entry_price         REAL,
    entry_time          TEXT,
    stop_order_id       TEXT,
    current_stop        REAL,
    highest_ltp         REAL,
    target_reference    REAL,
    exit_order_id       TEXT,
    exit_price          REAL,
    exit_time           TEXT,
    status              TEXT NOT NULL DEFAULT 'OPEN',  -- OPEN | CLOSED | ERROR
    realized_pnl        REAL,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    -- Shadow/paper trade detail columns (NULL for pre-existing rows)
    trade_mode          TEXT,                    -- PAPER | SHADOW | LIVE
    sl_points           REAL,                    -- initial SL in option pts at entry
    tsl_points          REAL,                    -- trailing-stop step pts at entry
    target_points       REAL,                    -- initial target pts at entry
    atr_value           REAL,                    -- ATR(14) on 5m candles at entry
    exit_reason         TEXT,                    -- TARGET_HIT | STOP_HIT | EMA_COLLAPSE | etc.
    smart_entry_flags   TEXT,                    -- JSON: which smart-entry filters passed
    smart_exit_trigger  TEXT                     -- which smart-exit rule fired (if any)
);

CREATE TABLE IF NOT EXISTS processed_signals (
    signal_id           TEXT PRIMARY KEY,        -- e.g. CE_2026-09-09_11:30
    strategy_type       TEXT NOT NULL,
    candle_timestamp    TEXT NOT NULL,
    processed_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS order_actions (
    action_id           TEXT PRIMARY KEY,        -- idempotency key
    trade_id            TEXT,
    action_type         TEXT NOT NULL,           -- ENTRY | SL_PLACE | SL_MODIFY | EXIT | CANCEL
    broker_order_id     TEXT,
    status              TEXT NOT NULL DEFAULT 'SENT',
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
"""


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    con = sqlite3.connect(settings.DB_PATH, check_same_thread=False, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── Additive migrations: add new columns to existing DBs ──────────────────────
_MIGRATIONS = [
    "ALTER TABLE trades ADD COLUMN trade_mode         TEXT",
    "ALTER TABLE trades ADD COLUMN sl_points          REAL",
    "ALTER TABLE trades ADD COLUMN tsl_points         REAL",
    "ALTER TABLE trades ADD COLUMN target_points      REAL",
    "ALTER TABLE trades ADD COLUMN atr_value          REAL",
    "ALTER TABLE trades ADD COLUMN exit_reason        TEXT",
    "ALTER TABLE trades ADD COLUMN smart_entry_flags  TEXT",
    "ALTER TABLE trades ADD COLUMN smart_exit_trigger TEXT",
    # SENSEX index-level prices for chart marker display (option prices not usable on index chart)
    "ALTER TABLE trades ADD COLUMN sensex_entry       REAL",
    "ALTER TABLE trades ADD COLUMN sensex_sl          REAL",
    "ALTER TABLE trades ADD COLUMN sensex_t1          REAL",
    "ALTER TABLE trades ADD COLUMN sensex_t2          REAL",
]


def init_db() -> None:
    """Create tables if they do not exist, then apply additive migrations."""
    with _conn() as con:
        con.executescript(_DDL)
        # Apply additive migrations — ignore "duplicate column" errors safely
        for stmt in _MIGRATIONS:
            try:
                con.execute(stmt)
            except Exception:
                pass  # column already exists — skip


# ── Trade CRUD ─────────────────────────────────────────────────────────────────

def upsert_trade(row: dict) -> None:
    cols = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row.keys())
    updates = ", ".join(
        f"{k} = excluded.{k}" for k in row.keys() if k != "trade_id"
    )
    sql = (
        f"INSERT INTO trades ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT(trade_id) DO UPDATE SET {updates}, "
        f"updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')"
    )
    with _conn() as con:
        con.execute(sql, row)


def fetch_active_trade() -> dict | None:
    """Return the most recent OPEN or PENDING trade, or None.

    PENDING rows are written atomically by claim_entry_slot_atomic() before
    the order is placed, so a concurrent process that races through the
    fetch_active_trade() check will see the row and block itself even if
    the first process hasn't received a fill yet.
    """
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM trades WHERE status IN ('OPEN','PENDING') "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def claim_entry_slot_atomic(trade_id: str, signal_type: str,
                             option_symbol: str, instrument_token: int,
                             quantity: int, signal_timestamp: str) -> bool:
    """Atomically reserve an entry slot by inserting a PENDING trade row.

    Uses INSERT OR IGNORE so only the first writer succeeds.  Returns True
    if this process claimed the slot, False if another process beat it.
    Call this BEFORE placing the broker order; on success the row is already
    visible to any concurrent fetch_active_trade() call so the second process
    will block itself before it can place a duplicate order.

    The caller must call upsert_trade(...status='OPEN') after fill to promote
    the row, or delete it on failure so the slot is released.
    """
    with _conn() as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO trades "
            "(trade_id, strategy_type, signal_timestamp, option_symbol, "
            " instrument_token, quantity, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'PENDING', "
            " strftime('%Y-%m-%dT%H:%M:%SZ','now'), "
            " strftime('%Y-%m-%dT%H:%M:%SZ','now'))",
            (trade_id, signal_type, signal_timestamp,
             option_symbol, instrument_token, quantity),
        )
        return cur.rowcount == 1


def release_entry_slot(trade_id: str) -> None:
    """Delete the PENDING row if entry failed, so the slot is freed."""
    with _conn() as con:
        con.execute(
            "DELETE FROM trades WHERE trade_id=? AND status='PENDING'",
            (trade_id,),
        )


def fetch_trade(trade_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM trades WHERE trade_id=?", (trade_id,)).fetchone()
    return dict(row) if row else None


def mark_trade_closed(trade_id: str, exit_price: float, exit_time: str, pnl: float) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE trades SET status='CLOSED', exit_price=?, exit_time=?, realized_pnl=?, "
            "updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE trade_id=?",
            (exit_price, exit_time, pnl, trade_id),
        )


def mark_trade_closed_with_reason(
    trade_id: str,
    exit_price: float,
    exit_time: str,
    pnl: float,
    exit_reason: str,
    smart_exit_trigger: str | None = None,
    highest_ltp: float | None = None,
) -> None:
    """Like mark_trade_closed but also persists exit_reason, smart_exit_trigger,
    and the final highest_ltp so the peak price is never lost on trade close."""
    with _conn() as con:
        if highest_ltp is not None:
            con.execute(
                "UPDATE trades SET status='CLOSED', exit_price=?, exit_time=?, realized_pnl=?, "
                "exit_reason=?, smart_exit_trigger=?, highest_ltp=?, "
                "updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE trade_id=?",
                (exit_price, exit_time, pnl, exit_reason, smart_exit_trigger, highest_ltp, trade_id),
            )
        else:
            con.execute(
                "UPDATE trades SET status='CLOSED', exit_price=?, exit_time=?, realized_pnl=?, "
                "exit_reason=?, smart_exit_trigger=?, "
                "updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE trade_id=?",
                (exit_price, exit_time, pnl, exit_reason, smart_exit_trigger, trade_id),
            )


def fetch_shadow_trades(date: str | None = None, limit: int = 500) -> list[dict]:
    """
    Return PAPER/SHADOW trades ordered newest-first.

    Parameters
    ----------
    date  : optional ISO date string 'YYYY-MM-DD' — filter to that calendar day
            (matched against entry_time).  Pass None for all dates.
    limit : max rows returned (default 500).
    """
    with _conn() as con:
        if date:
            rows = con.execute(
                "SELECT * FROM trades "
                "WHERE entry_order_id LIKE 'PAPER_%' AND entry_time LIKE ? "
                "ORDER BY created_at DESC LIMIT ?",
                (f"{date}%", limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM trades "
                "WHERE entry_order_id LIKE 'PAPER_%' "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def fetch_shadow_trade_dates() -> list[str]:
    """Return distinct entry dates (YYYY-MM-DD) for all PAPER/SHADOW trades, newest first."""
    with _conn() as con:
        rows = con.execute(
            "SELECT DISTINCT substr(entry_time,1,10) AS d FROM trades "
            "WHERE entry_order_id LIKE 'PAPER_%' AND entry_time IS NOT NULL "
            "ORDER BY d DESC"
        ).fetchall()
    return [r["d"] for r in rows if r["d"]]


# ── Signal de-duplication ──────────────────────────────────────────────────────

def has_processed_signal(signal_id: str) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM processed_signals WHERE signal_id=?", (signal_id,)
        ).fetchone()
    return row is not None


def record_processed_signal(signal_id: str, strategy_type: str, candle_timestamp: str) -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO processed_signals (signal_id, strategy_type, candle_timestamp) "
            "VALUES (?,?,?)",
            (signal_id, strategy_type, candle_timestamp),
        )


def claim_signal_atomic(signal_id: str, strategy_type: str, candle_timestamp: str) -> bool:
    """
    Atomically claim a signal for processing.

    Attempts to INSERT the signal_id into processed_signals.  Returns True if
    this call was the first to insert it (i.e. this process owns the signal),
    False if the row already existed (another process or a prior call already
    claimed it).

    Unlike the separate has_processed_signal() + record_processed_signal()
    pair, this is a single INSERT that wins on conflict — eliminating the
    SELECT-then-INSERT race condition that can cause duplicate orders when two
    bot processes start within milliseconds of each other.
    """
    with _conn() as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO processed_signals (signal_id, strategy_type, candle_timestamp) "
            "VALUES (?,?,?)",
            (signal_id, strategy_type, candle_timestamp),
        )
        return cur.rowcount == 1


# ── Order idempotency ──────────────────────────────────────────────────────────

def has_action(action_id: str) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM order_actions WHERE action_id=?", (action_id,)
        ).fetchone()
    return row is not None


def record_action(action_id: str, trade_id: str | None, action_type: str,
                  broker_order_id: str | None = None, status: str = "SENT") -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO order_actions "
            "(action_id, trade_id, action_type, broker_order_id, status) VALUES (?,?,?,?,?)",
            (action_id, trade_id, action_type, broker_order_id, status),
        )


def update_action_status(action_id: str, status: str, broker_order_id: str | None = None) -> None:
    with _conn() as con:
        if broker_order_id:
            con.execute(
                "UPDATE order_actions SET status=?, broker_order_id=? WHERE action_id=?",
                (status, broker_order_id, action_id),
            )
        else:
            con.execute(
                "UPDATE order_actions SET status=? WHERE action_id=?",
                (status, action_id),
            )


def fetch_today_realised_pnl() -> float:
    """
    Return the sum of realized_pnl for all CLOSED trades today (IST date).
    Returns 0.0 if no trades have been closed today.
    The pnl values stored are in option points × qty; dividing by qty gives
    per-unit pts — but for the daily loss limit we compare raw stored pnl
    (points × qty).  Callers that want per-unit pts must divide themselves.
    """
    from utils.time_utils import now_ist
    today = now_ist().date().isoformat()
    with _conn() as con:
        row = con.execute(
            "SELECT COALESCE(SUM(realized_pnl), 0.0) FROM trades "
            "WHERE status='CLOSED' AND entry_order_id != 'IMPORTED' AND exit_time LIKE ?",
            (f"{today}%",),
        ).fetchone()
    return float(row[0]) if row else 0.0


def fetch_today_pivot_trade_count(day: str) -> int:
    """
    Return the number of CE_PIVOT / PE_PIVOT trades that have been filled today.

    Counts trades whose strategy_type ends with '_PIVOT', entry_order_id is not
    'IMPORTED', and entry_time falls on the given IST date string (YYYY-MM-DD).
    Used to seed the in-memory pivot trade counter after a bot restart so the
    daily max-trades limit is not reset mid-day.
    """
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM trades "
            "WHERE strategy_type LIKE '%_PIVOT' "
            "  AND entry_order_id != 'IMPORTED' "
            "  AND (entry_time LIKE ? OR signal_timestamp LIKE ?) "
            "  AND status IN ('OPEN', 'CLOSED')",
            (f"{day}%", f"{day}%"),
        ).fetchone()
    return int(row[0]) if row else 0


def fetch_today_mom_trade_count(day: str) -> int:
    """Return the number of CE_MOM / PE_MOM trades filled on *day* (YYYY-MM-DD)."""
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM trades "
            "WHERE strategy_type LIKE '%_MOM' "
            "  AND entry_order_id != 'IMPORTED' "
            "  AND (entry_time LIKE ? OR signal_timestamp LIKE ?) "
            "  AND status IN ('OPEN', 'CLOSED')",
            (f"{day}%", f"{day}%"),
        ).fetchone()
    return int(row[0]) if row else 0


def fetch_today_side_trade_count(side: str, day: str) -> int:
    """Return the number of trades on a given side (CE or PE) filled on *day*.

    Counts every filled trade (any strategy) that starts with *side* ('CE' or
    'PE'), excluding IMPORTED entries.  Used to seed the global per-side daily
    cap after a bot restart.
    """
    prefix = f"{side}%"
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM trades "
            "WHERE strategy_type LIKE ? "
            "  AND entry_order_id != 'IMPORTED' "
            "  AND (entry_time LIKE ? OR signal_timestamp LIKE ?) "
            "  AND status IN ('OPEN', 'CLOSED')",
            (prefix, f"{day}%", f"{day}%"),
        ).fetchone()
    return int(row[0]) if row else 0
