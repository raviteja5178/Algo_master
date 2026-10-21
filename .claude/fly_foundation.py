import pathlib

# research/backtest_report.py: use the shared costs helper
p = pathlib.Path("research/backtest_report.py")
s = p.read_text(encoding="utf-8")
start = s.index("# ── costs ──")
end = s.index("# ── enrichment ──")
s = (s[:start]
     + "# Transaction costs live in utils/costs.py (shared with the SHADOW runner).\n"
     + "from utils.costs import charges  # noqa: E402,F401\n\n\n"
     + s[end:])
p.write_text(s, encoding="utf-8")

# settings
p = pathlib.Path("config/settings.py")
s = p.read_text(encoding="utf-8")
anchor = "# ── Validation ────────────────────────────────────────────────────────────────\nALLOWED_MODES"
assert s.count(anchor) == 1
block = '''# ── Expiry-day iron butterfly (SHADOW only) ───────────────────────────────────
# Research strategy (research/output/strategy_lab/STRATEGY_REPORT.md): on SENSEX
# weekly expiry day, sell the ATM CE+PE and buy CE/PE FLY_WING_POINTS away, then
# stop at a FLY_STOP_PCT loss of the credit or exit at FLY_EXIT_TIME.  It trades
# four legs at once, which the live order path does not support, so it runs ONLY
# in SHADOW: fills are simulated at the real bid/ask, and every entry stores the
# real quotes so they can be compared with the backtest's modelled prices
# (python -m research.fly_vs_model).  ENABLE_EXPIRY_FLY with TRADING_MODE=LIVE is
# refused at startup.
#   FLY_QUANTITY          : units per leg (one SENSEX lot = 20)
#   FLY_MIN_CREDIT        : skip entry if the net credit (points) is below this
#   FLY_SKIP_DATES        : comma list of YYYY-MM-DD event days to sit out
#   FLY_EXTRA_SLIPPAGE_PTS: extra points per leg per side on top of bid/ask
ENABLE_EXPIRY_FLY: bool        = _getbool("ENABLE_EXPIRY_FLY", False)
FLY_ENTRY_TIME: str            = _get("FLY_ENTRY_TIME", "10:30")
FLY_EXIT_TIME: str             = _get("FLY_EXIT_TIME", "15:10")
FLY_WING_POINTS: int           = _getint("FLY_WING_POINTS", 1000)
FLY_STOP_PCT: float            = _getfloat("FLY_STOP_PCT", 0.5)
FLY_QUANTITY: int              = _getint("FLY_QUANTITY", 20)
FLY_MIN_CREDIT: float          = _getfloat("FLY_MIN_CREDIT", 50.0)
FLY_SKIP_DATES: str            = _get("FLY_SKIP_DATES", "")
FLY_EXTRA_SLIPPAGE_PTS: float  = _getfloat("FLY_EXTRA_SLIPPAGE_PTS", 0.0)

'''
s = s.replace(anchor, block + anchor)
v = "def validate() -> None:\n    if TRADING_MODE not in ALLOWED_MODES:"
assert v in s
s = s.replace(v, '''def validate() -> None:
    if ENABLE_EXPIRY_FLY and TRADING_MODE == "LIVE":
        raise RuntimeError(
            "ENABLE_EXPIRY_FLY is SHADOW-only: the live order path cannot place a "
            "four-leg position safely.  Set TRADING_MODE=SHADOW or disable it."
        )
    if ENABLE_EXPIRY_FLY and (FLY_WING_POINTS <= 0 or FLY_QUANTITY <= 0 or FLY_STOP_PCT <= 0):
        raise ValueError("FLY_WING_POINTS, FLY_QUANTITY and FLY_STOP_PCT must be positive.")
    if TRADING_MODE not in ALLOWED_MODES:''', 1)
p.write_text(s, encoding="utf-8")

# .env.example
p = pathlib.Path(".env.example")
s = p.read_text(encoding="utf-8")
s = s.rstrip("\r\n") + '''

# ── Expiry-day iron butterfly (SHADOW only; refused in LIVE) ──────────────────
# Sells the ATM straddle and buys wings on SENSEX expiry day; see
# research/output/strategy_lab/STRATEGY_REPORT.md.  Fills are simulated at the
# real bid/ask and stored for comparison with the model (research.fly_vs_model).
ENABLE_EXPIRY_FLY=false
FLY_ENTRY_TIME=10:30
FLY_EXIT_TIME=15:10
FLY_WING_POINTS=1000
FLY_STOP_PCT=0.5
FLY_QUANTITY=20
FLY_MIN_CREDIT=50
FLY_SKIP_DATES=
FLY_EXTRA_SLIPPAGE_PTS=0
'''
p.write_text(s, encoding="utf-8")

# DB table
p = pathlib.Path("persistence/models.py")
s = p.read_text(encoding="utf-8")
ddl_end = '''    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
"""
'''
assert s.count(ddl_end) == 1
s = s.replace(ddl_end, '''    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Expiry-day iron butterfly (SHADOW).  One row per expiry day; legs are JSON.
CREATE TABLE IF NOT EXISTS fly_trades (
    day                 TEXT PRIMARY KEY,        -- YYYY-MM-DD (IST), one fly per day
    status              TEXT NOT NULL,           -- OPEN | CLOSED | SKIPPED
    mode                TEXT NOT NULL,
    expiry              TEXT,
    entry_time          TEXT,
    spot_entry          REAL,
    vix_entry           REAL,
    legs                TEXT,                    -- JSON: symbol/strike/type/side/entry_px/bid/ask/last
    quantity            INTEGER,
    credit              REAL,                    -- net credit per unit at the simulated fills
    credit_mid          REAL,                    -- same, at mid prices (compare with the model)
    stop_value          REAL,                    -- buy-back cost that triggers the stop
    exit_time           TEXT,
    exit_reason         TEXT,                    -- STOP | TIME | TIME_STALE
    exit_legs           TEXT,                    -- JSON: symbol/exit_px
    exit_value          REAL,
    gross_pnl           REAL,
    charges             REAL,
    net_pnl             REAL,
    peak_value          REAL,                    -- highest buy-back cost seen (worst point)
    note                TEXT
);
"""
''')
s += '''

# ── Expiry-day iron butterfly (SHADOW) ─────────────────────────────────────────

def fly_get(day: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM fly_trades WHERE day = ?", (day,)).fetchone()
        return dict(row) if row else None


def fly_insert(row: dict) -> bool:
    """Insert a day's fly row. False if that day already has one (restart-safe)."""
    cols = ", ".join(row)
    marks = ", ".join(f":{k}" for k in row)
    with _conn() as con:
        cur = con.execute(f"INSERT OR IGNORE INTO fly_trades ({cols}) VALUES ({marks})", row)
        return cur.rowcount == 1


def fly_update(day: str, fields: dict) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    with _conn() as con:
        con.execute(f"UPDATE fly_trades SET {sets} WHERE day = :_day", {**fields, "_day": day})


def fly_all() -> list[dict]:
    with _conn() as con:
        return [dict(r) for r in con.execute("SELECT * FROM fly_trades ORDER BY day")]
'''
p.write_text(s, encoding="utf-8")

# trade_store facade
p = pathlib.Path("persistence/trade_store.py")
s = p.read_text(encoding="utf-8")
s = s.replace("    fetch_active_trade,\n    fetch_live_dates,",
              "    fetch_active_trade,\n    fly_all,\n    fly_get,\n    fly_insert,\n    fly_update,\n    fetch_live_dates,", 1)
s = s.replace('    "fetch_live_dates",\n]', '    "fetch_live_dates",\n    "fly_get",\n    "fly_insert",\n    "fly_update",\n    "fly_all",\n]')
p.write_text(s, encoding="utf-8")
print("ok")
