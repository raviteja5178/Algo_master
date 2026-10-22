"""
Full-system backtest: replays the PRODUCTION bot, session by session, on
historical SENSEX 1-minute data.

Nothing here re-implements trading logic.  Each session runs the same code
the live bot runs:

    main.BotContext()             state machine, PaperBroker, smart entry/exit
    main.recover_from_restart()   (no-op: every session ends flat)
    main.bootstrap_session()      candle seed, prev-day H/L/C, daily trend, pivots
    main._make_tick_handler()     candles -> evaluate_signals -> execute_entry,
                                  Pivot/EMA/Index trade managers (SL, BE, T1/T2
                                  locks, chandelier TSL, targets), smart exits,
                                  paper broker SL backstop
    main._run_eod_exit()          forced square-off at FORCE_EXIT_TIME

Only the outside world is simulated:

    Clock     datetime.now() in the bot's modules returns the simulated time.
    Kite      historical_data() serves cached bars that had COMPLETED by the
              simulated time (no look-ahead); quote()/ltp() serve the current
              simulated SENSEX price and modelled option premiums.
    Feed      every 1-minute bar becomes 4 SENSEX ticks at :00/:15/:30/:45
              (up bar O,L,H,C; down bar O,H,L,C), each followed by an option
              tick for the open position.
    Options   Black-Scholes premium per contract: strike/expiry from the real
              selector (ATM + ITM fallback, expiry-day rollover), weekly expiry
              calendar below, IV = India VIX of that minute, r = 6.5%.
    Mode      SHADOW (PaperBroker fills at the quoted premium), so every
              option-price rule (MAX_SL_PCT, premium floor, option EMA9 check,
              broker SL backstop) runs as it does in SHADOW/LIVE.

Settings come from .env, exactly as the bot would load them; --set overrides
single keys for experiments.

Usage
    python -m research.fetch_history --start 2024-01-01 --end 2026-10-16
    python -m research.system_backtest                        # full range
    python -m research.system_backtest --start 2025-01-01 --label y2025
    python -m research.system_backtest --set ENABLE_ORB_STRATEGY=false
    python -m research.system_backtest --label no_midday --block-window 11:00-12:00
    python -m research.system_backtest --label pivot_pe --skip-signals CE_PIVOT

Outputs: research/output/system_backtest/<label>/  (trades.csv, events.csv,
run_meta.json); then research.backtest_report renders REPORT.md.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import tempfile
import time as _wall
import zlib
from bisect import bisect_right
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "research" / "data"
OUT_ROOT = ROOT / "research" / "output" / "system_backtest"

MINUTE_CSV = DATA_DIR / "sensex_1m_full.csv"
DAILY_CSV = DATA_DIR / "sensex_daily_full.csv"
VIX_CSV = DATA_DIR / "india_vix_1m_full.csv"

RISK_FREE = 0.065
EXPIRY_CLOSE = dtime(15, 30)
SESSION_OPEN = dtime(9, 15)
SESSION_MIN = 375

# Option time is measured in TRADING time: decay happens during the session,
# and each close-to-open gap counts as the trading minutes that carry the same
# SENSEX variance.  Measured on Jan 2024 - Oct 2026 (gap variance / intraday
# variance x 375): a weeknight ~ 176 minutes, a weekend or holiday ~ 609.
# Calendar time (the earlier model) put most decay overnight, understating the
# intraday theta that option buyers pay and option sellers earn.
WEEKNIGHT_MIN = 176
WEEKEND_MIN = 609

# SENSEX weekly expiry weekday by period (Mon=0).  BSE moved SENSEX weeklies
# from Friday to Tuesday on 2025-01-01 and to Thursday on 2025-09-01.  A
# holiday on the expiry weekday moves expiry to the previous trading session.
EXPIRY_SCHEDULE: list[tuple[date, int]] = [
    (date(2000, 1, 1), 4),    # Friday
    (date(2025, 1, 1), 1),    # Tuesday
    (date(2025, 9, 1), 3),    # Thursday
]

# Simulated wall clock (IST-aware datetime), shared by the patches below.
_CLOCK: list[datetime] = []


# ── Simulated clock ───────────────────────────────────────────────────────────

_REAL_DATETIME = datetime


class _FakeDatetimeMeta(type):
    def __instancecheck__(cls, obj):          # real datetimes still pass isinstance()
        return isinstance(obj, _REAL_DATETIME)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, _REAL_DATETIME)


class FakeDatetime(_REAL_DATETIME, metaclass=_FakeDatetimeMeta):
    @classmethod
    def now(cls, tz=None):
        now = _CLOCK[0]
        return now.astimezone(tz) if tz is not None else now.replace(tzinfo=None)


# ── Market data ───────────────────────────────────────────────────────────────

class MarketData:
    """Cached history, indexed for fast 'what had completed by time T' lookups."""

    def __init__(self) -> None:
        for f in (MINUTE_CSV, DAILY_CSV, VIX_CSV):
            if not f.exists():
                sys.exit(f"Missing {f} — run: python -m research.fetch_history")
        m1 = pd.read_csv(MINUTE_CSV, parse_dates=["timestamp"])
        m1 = m1[(m1.timestamp.dt.time >= dtime(9, 15)) & (m1.timestamp.dt.time < dtime(15, 30))]
        self.m1 = m1.reset_index(drop=True)
        self.sessions: list[date] = sorted(self.m1.timestamp.dt.date.unique())
        self.session_set = set(self.sessions)
        self.by_day = {d: g for d, g in self.m1.groupby(self.m1.timestamp.dt.date)}

        self.bars = {"minute": self._as_records(self.m1, 1)}
        for iv, mins in (("5minute", 5), ("15minute", 15)):
            self.bars[iv] = self._as_records(self._resample(mins), mins)

        daily = pd.read_csv(DAILY_CSV, parse_dates=["date"])
        self.daily = [
            {"date": _REAL_DATETIME.combine(r.date.date(), dtime(0, 0)),
             "open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": 0,
             "_end": _REAL_DATETIME.combine(r.date.date(), dtime(15, 30))}
            for r in daily.itertuples()
        ]

        vix = pd.read_csv(VIX_CSV, parse_dates=["timestamp"])
        self.vix_ts = [t.to_pydatetime() for t in vix.timestamp]
        self.vix_val = vix.close.tolist()

    def _resample(self, mins: int) -> pd.DataFrame:
        out = []
        for _, g in self.m1.groupby(self.m1.timestamp.dt.date):
            r = (g.set_index("timestamp")
                  .resample(f"{mins}min", origin="start_day", label="left", closed="left")
                  .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
                  .dropna())
            out.append(r.reset_index())
        return pd.concat(out, ignore_index=True)

    @staticmethod
    def _as_records(df: pd.DataFrame, mins: int) -> dict:
        ts = [t.to_pydatetime() for t in df.timestamp]
        recs = [
            {"date": t, "open": o, "high": h, "low": l, "close": c, "volume": 0}
            for t, o, h, l, c in zip(ts, df.open, df.high, df.low, df.close)
        ]
        ends = [t + timedelta(minutes=mins) for t in ts]
        return {"start": ts, "end": ends, "recs": recs}

    def completed(self, interval: str, frm: datetime, to: datetime, now: datetime) -> list[dict]:
        """Bars starting in [frm, to] that had fully completed by *now* (naive IST)."""
        if interval == "day":
            return [{k: v for k, v in r.items() if k != "_end"} for r in self.daily
                    if frm <= r["date"] <= to and r["_end"] <= now]
        b = self.bars[interval]
        lo = bisect_right(b["start"], frm - timedelta(microseconds=1))
        hi = bisect_right(b["start"], to)
        return [dict(b["recs"][i]) for i in range(lo, hi) if b["end"][i] <= now]

    def vix_at(self, t: datetime) -> float:
        i = bisect_right(self.vix_ts, t) - 1
        return self.vix_val[max(i, 0)]


# ── Option model ──────────────────────────────────────────────────────────────

def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(spot: float, strike: float, years: float, vol: float, opt: str, r: float = RISK_FREE) -> float:
    """Black-Scholes premium (European), floored at intrinsic value."""
    intrinsic = max(0.0, spot - strike) if opt == "CE" else max(0.0, strike - spot)
    if years <= 0 or vol <= 0:
        return intrinsic
    sd = vol * math.sqrt(years)
    d1 = (math.log(spot / strike) + (r + 0.5 * vol * vol) * years) / sd
    d2 = d1 - sd
    if opt == "CE":
        px = spot * _ncdf(d1) - strike * math.exp(-r * years) * _ncdf(d2)
    else:
        px = strike * math.exp(-r * years) * _ncdf(-d2) - spot * _ncdf(-d1)
    return max(px, intrinsic)


def tick_round(px: float) -> float:
    return max(0.05, round(round(px / 0.05) * 0.05, 2))


class Contracts:
    """Synthetic SENSEX option chain: symbols, tokens, expiries, premiums."""

    def __init__(self, md: MarketData) -> None:
        self.md = md
        self.by_token: dict[int, dict] = {}
        self.by_symbol: dict[str, dict] = {}
        self._future_min: dict[tuple[date, date], float] = {}
        # One year of variance-time: 252 sessions plus the average gap before each.
        gaps = [self._gap_min(a, b) for a, b in zip(md.sessions, md.sessions[1:])]
        self.year_min = 252 * (SESSION_MIN + (sum(gaps) / len(gaps) if gaps else WEEKNIGHT_MIN))

    @staticmethod
    def _gap_min(prev: date, nxt: date) -> float:
        return WEEKNIGHT_MIN if (nxt - prev).days == 1 else WEEKEND_MIN

    def _sessions_after(self, d: date, until: date) -> list[date]:
        out = [s for s in self.md.sessions if d < s <= until]
        last = out[-1] if out else d
        cur = max(last, self.md.sessions[-1])
        while cur < until:                      # beyond the data: assume weekdays trade
            cur += timedelta(days=1)
            if cur.weekday() < 5 and cur > last:
                out.append(cur)
        return out

    def trading_years(self, at: datetime, expiry: date) -> float:
        """Variance-time to expiry (15:30) in years."""
        today = at.date()
        if expiry < today:
            return 0.0
        close = _REAL_DATETIME.combine(today, EXPIRY_CLOSE)
        opened = _REAL_DATETIME.combine(today, SESSION_OPEN)
        mins = max(0.0, (close - max(at, opened)).total_seconds() / 60)
        key = (today, expiry)
        fut = self._future_min.get(key)
        if fut is None:
            fut, prev = 0.0, today
            for s in self._sessions_after(today, expiry):
                fut += self._gap_min(prev, s) + SESSION_MIN
                prev = s
            self._future_min[key] = fut
        return (mins + fut) / self.year_min

    def expiry_weekday(self, d: date) -> int:
        wd = EXPIRY_SCHEDULE[0][1]
        for since, w in EXPIRY_SCHEDULE:
            if d >= since:
                wd = w
        return wd

    def expiries_from(self, d: date, n: int = 3) -> list[date]:
        out: list[date] = []
        cur = d - timedelta(days=d.weekday())        # Monday of d's week
        while len(out) < n:
            exp = cur + timedelta(days=self.expiry_weekday(cur))
            # Holiday on the expiry weekday → the previous trading session.
            if self.md.sessions[0] <= exp <= self.md.sessions[-1]:
                for _ in range(4):
                    if exp in self.md.session_set:
                        break
                    exp -= timedelta(days=1)
            if exp >= d:
                out.append(exp)
            cur += timedelta(days=7)
        return out

    def contract(self, expiry: date, strike: float, opt: str) -> dict:
        sym = f"SENSEX{expiry:%y%m%d}{int(strike)}{opt}"
        c = self.by_symbol.get(sym)
        if c is None:
            token = 10_000_000 + zlib.crc32(sym.encode()) % 900_000_000
            c = {"tradingsymbol": sym, "instrument_token": token, "strike": float(strike),
                 "expiry": expiry, "instrument_type": opt, "name": "SENSEX",
                 "segment": "BFO-OPT", "exchange": "BFO", "lot_size": 20}
            self.by_symbol[sym] = c
            self.by_token[token] = c
        return c

    def chain(self, expiry: date, opt: str, spot: float) -> list[dict]:
        atm = round(spot / 100) * 100
        return [self.contract(expiry, atm + k * 100, opt) for k in range(-15, 16)]

    def premium(self, c: dict, spot: float, at: datetime) -> float:
        """Premium of contract *c* at naive-IST time *at* with SENSEX at *spot*."""
        years = self.trading_years(at, c["expiry"])
        vol = self.md.vix_at(at) / 100.0
        return tick_round(bs_price(spot, c["strike"], years, vol, c["instrument_type"]))


# ── Fake broker-side services ─────────────────────────────────────────────────

class FakeKite:
    """The subset of KiteConnect the bot calls in SHADOW mode, served from history."""

    def __init__(self, md: MarketData, chain: Contracts, sensex_token: int) -> None:
        self.md, self.chain, self.sensex_token = md, chain, sensex_token
        self.spot = 0.0

    @staticmethod
    def _dt(v) -> datetime:
        if isinstance(v, str):
            return _REAL_DATETIME.strptime(v[:19], "%Y-%m-%d %H:%M:%S")
        return v.replace(tzinfo=None)

    def historical_data(self, instrument_token=None, from_date=None, to_date=None,
                        interval=None, *args, **kw):
        now = _CLOCK[0].replace(tzinfo=None)
        frm, to = self._dt(from_date), self._dt(to_date)
        to = min(to, now)
        if int(instrument_token) == self.sensex_token:
            return self.md.completed(interval, frm, to, now)
        c = self.chain.by_token.get(int(instrument_token))
        if c is None:
            return []
        # Option bars: the contract priced off the SENSEX bars of the same interval.
        out = []
        for b in self.md.completed(interval, frm, to, now):
            t = b["date"]
            px = {k: self.chain.premium(c, b[k], t) for k in ("open", "high", "low", "close")}
            if c["instrument_type"] == "PE":
                px["high"], px["low"] = px["low"], px["high"]
            out.append({"date": t, **px, "volume": 0})
        return out

    def _quote_one(self, key: str) -> dict:
        now = _CLOCK[0].replace(tzinfo=None)
        if key.endswith(":SENSEX"):
            return {"last_price": self.spot}
        sym = key.split(":", 1)[1]
        c = self.chain.by_symbol[sym]
        ltp = self.chain.premium(c, self.spot, now)
        spread = max(0.05, tick_round(ltp * 0.002))
        return {"last_price": ltp,
                "depth": {"buy": [{"price": max(0.05, ltp - spread), "quantity": 100}],
                          "sell": [{"price": ltp + spread, "quantity": 100}]}}

    def quote(self, keys):
        keys = [keys] if isinstance(keys, str) else keys
        return {k: self._quote_one(k) for k in keys}

    def ltp(self, keys):
        return self.quote(keys)

    def profile(self):
        return {"user_id": "BACKTEST"}

    def orders(self):
        return []

    def positions(self):
        return {"day": [], "net": []}


class DummyWS:
    """Stands in for the KiteTicker client; ticks are pushed by the harness."""
    option_feed_ok = True

    def __init__(self, *a, **k): pass
    def add_token(self, *a, **k): pass
    def remove_token(self, *a, **k): pass
    def add_flow_token(self, *a, **k): pass
    def on_ltp(self, *a, **k): pass
    def on_stale(self, *a, **k): pass
    def on_order_update(self, *a, **k): pass
    def start(self, *a, **k): pass
    def stop(self, *a, **k): pass


# ── Event capture ─────────────────────────────────────────────────────────────

class EventCapture(logging.Handler):
    """Keeps the structured log_event lines that explain signals, blocks and stop moves."""

    KEEP = ("_SIGNAL", "BLOCKED", "ENTRY_", "STOP_MOVED", "RISK_APPLIED", "EXIT",
            "STOP_HIT", "EXPIRY_ROLLOVER", "ITM_FALLBACK", "BOT_HALTED", "TRAILING_SL")

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.rows: list[dict] = []
        self.errors: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= logging.ERROR:
            self.errors.append(f"{_CLOCK[0]:%Y-%m-%d %H:%M} {record.name}: {record.getMessage()}")
        if record.msg != "[%s] %s" or not record.args:
            return
        event = str(record.args[0])
        if any(k in event for k in self.KEEP):
            self.rows.append({"time": _CLOCK[0].strftime("%Y-%m-%d %H:%M:%S"),
                              "event": event, "fields": str(record.args[1])})


# ── Harness ───────────────────────────────────────────────────────────────────

def _coerce(cur, raw: str):
    if isinstance(cur, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(cur, int):
        return int(raw)
    if isinstance(cur, float):
        return float(raw)
    if isinstance(cur, (list, tuple, set, frozenset)):
        items = [x.strip() for x in raw.split(",") if x.strip()]
        return type(cur)(items)
    return raw


def install(md: MarketData, tmp: Path, overrides: dict[str, str], mode: str = "SHADOW"):
    """Import the bot with every outside-world dependency simulated. Returns (main, kite, chain)."""
    from config import settings

    _CLOCK[:] = [_REAL_DATETIME.combine(md.sessions[0], dtime(9, 0))]

    for key, raw in overrides.items():
        if not hasattr(settings, key):
            sys.exit(f"--set {key}: unknown setting")
        setattr(settings, key, _coerce(getattr(settings, key), raw))
    settings.TRADING_MODE = mode
    settings.ENABLE_LIVE_TRADING = False
    settings.ENABLE_AI_CONFIRMATION = False
    settings.ENABLE_AI_EXIT = False
    settings.REGIME_USE_AI = False
    settings.ENABLE_ORDERFLOW_RECORDER = False
    settings.EXPIRY_MODE = "AUTO"
    settings.DB_PATH = str(tmp / "backtest_trades.db")

    import utils.time_utils as tu
    from utils.time_utils import IST
    _CLOCK[0] = IST.localize(_CLOCK[0])

    import main
    import broker.instrument_repository as repo
    import broker.kite_client as kc
    import execution.ema_trade_manager as etm
    import execution.option_selector as osel
    import execution.pivot_trade_manager as ptm
    import market.candle_aggregator as cagg
    import market.historical_data as hd
    import market.vwap as mvwap
    from persistence.trade_store import init_db

    for mod in (tu, cagg, hd, mvwap):
        mod.datetime = FakeDatetime

    chain = Contracts(md)
    kite = FakeKite(md, chain, hd.SENSEX_TOKEN)
    for mod in list(sys.modules.values()):
        if mod is not None and getattr(mod, "get_kite", None) is kc.get_kite and mod is not kc:
            mod.get_kite = lambda: kite
    kc.get_kite = lambda: kite

    def _today() -> date:
        return _CLOCK[0].date()

    def resolve_expiry() -> date:
        exps = chain.expiries_from(_today())
        if exps[0] == _today() and settings.EXPIRY_DAY_ROLLOVER_TIME:
            from utils.time_utils import is_after_or_equal, parse_time_ist
            if is_after_or_equal(_CLOCK[0].time(), parse_time_ist(settings.EXPIRY_DAY_ROLLOVER_TIME)):
                return exps[1]
        return exps[0]

    def get_sensex_options(expiry, option_type):
        return chain.chain(expiry, option_type, kite.spot)

    def is_expiry_day() -> bool:
        return chain.expiries_from(_today())[0] == _today()

    for mod in (repo, osel):
        if hasattr(mod, "resolve_expiry"):
            mod.resolve_expiry = resolve_expiry
        if hasattr(mod, "get_sensex_options"):
            mod.get_sensex_options = get_sensex_options
    repo.is_expiry_day = is_expiry_day
    repo.load_instruments = lambda *a, **k: []

    main.WebSocketClient = DummyWS
    main._write_state = lambda ctx: None
    main._write_ltp = lambda ctx: None
    ptm._STATE_FILE = tmp / "pivot_trade.json"
    etm._STATE_FILE = tmp / "ema_trade.json"
    etm._IDX_STATE_FILE = tmp / "idx_trade.json"
    main._STATE_FILE = tmp / "bot_state.json"

    init_db()
    return main, kite, chain


def _tick_path(o: float, h: float, l: float, c: float) -> list[float]:
    return [o, l, h, c] if c >= o else [o, h, l, c]


def _install_entry_filters(main, windows: list[tuple[dtime, dtime]], skip: set[str]) -> None:
    """
    Backtest-only experiments with no bot setting yet: skip entries inside
    time windows, or for named signal types.  The signal has already been
    claimed by the signal engine, exactly as when a live entry gate blocks it.
    """
    if not windows and not skip:
        return
    from utils.logging_config import log_event
    real_entry = main.execute_entry
    lg = logging.getLogger("research.system_backtest")

    def filtered_entry(ctx, signal_type, sensex_ltp, *a, **k):
        now = _CLOCK[0].time()
        why = None
        if signal_type in skip:
            why = f"signal {signal_type} skipped"
        for lo, hi in windows:
            if lo <= now < hi:
                why = f"entry window {lo:%H:%M}-{hi:%H:%M} blocked"
        if why:
            log_event(lg, "BACKTEST_FILTER_BLOCKED", signal=signal_type, reason=why)
            return None
        return real_entry(ctx, signal_type, sensex_ltp, *a, **k)

    main.execute_entry = filtered_entry


def run(md: MarketData, start: date, end: date, overrides: dict[str, str], out_dir: Path,
        block_windows: list[tuple[dtime, dtime]] | None = None,
        skip_signals: set[str] | None = None, mode: str = "SHADOW") -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="sysbt_"))
    cap = EventCapture()
    root = logging.getLogger()
    root.handlers[:] = [cap]
    root.setLevel(logging.INFO)

    main, kite, chain = install(md, tmp, overrides, mode)
    _install_entry_filters(main, block_windows or [], skip_signals or set())
    from config import settings
    from market.historical_data import SENSEX_TOKEN
    from execution.position_manager import State
    from utils.time_utils import IST, parse_time_ist

    force_exit = parse_time_ist(settings.FORCE_EXIT_TIME)
    days = [d for d in md.sessions if start <= d <= end]
    t0 = _wall.monotonic()
    halted_days: list[str] = []

    for n, day in enumerate(days, 1):
        _CLOCK[0] = IST.localize(_REAL_DATETIME.combine(day, dtime(9, 0)))
        bars = md.by_day[day]
        kite.spot = float(bars.iloc[0].open)

        ctx = main.BotContext()
        main.recover_from_restart(ctx)
        main.bootstrap_session(ctx)
        main.classify_session_regime(ctx)
        handler = main._make_tick_handler(ctx)
        eod_done = False

        for ts, o, h, l, c in zip(bars.timestamp, bars.open, bars.high, bars.low, bars.close):
            base = IST.localize(ts.to_pydatetime())
            for k, px in enumerate(_tick_path(o, h, l, c)):
                _CLOCK[0] = base + timedelta(seconds=15 * k)
                kite.spot = float(px)
                handler(SENSEX_TOKEN, float(px))
                # PAPER has no option feed: the bot prices the option off the index itself.
                if mode != "PAPER":
                    for slot in list(ctx.slots.values()):
                        if slot.instrument_token and slot.tradingsymbol in chain.by_symbol:
                            prem = chain.premium(chain.by_symbol[slot.tradingsymbol], kite.spot,
                                                 _CLOCK[0].replace(tzinfo=None))
                            handler(slot.instrument_token, prem)
                if not eod_done and _CLOCK[0].time() >= force_exit:
                    main._run_eod_exit(ctx)
                    eod_done = True

        if ctx.is_halted():
            halted_days.append(str(day))
        if n % 20 == 0 or n == len(days):
            print(f"  {n}/{len(days)} sessions  ({day})  {_wall.monotonic() - t0:.0f}s", flush=True)

    # ── collect ────────────────────────────────────────────────────────────────
    import sqlite3
    con = sqlite3.connect(settings.DB_PATH)
    trades = pd.read_sql_query("SELECT * FROM trades ORDER BY entry_time", con)
    con.close()

    out_dir.mkdir(parents=True, exist_ok=True)
    trades.to_csv(out_dir / "trades_raw.csv", index=False)
    pd.DataFrame(cap.rows).to_csv(out_dir / "events.csv", index=False)
    (out_dir / "errors.log").write_text("\n".join(cap.errors), encoding="utf-8")

    snap_keys = sorted(k for k in dir(settings) if k.isupper() and not k.startswith("_")
                       and not any(s in k for s in ("KEY", "SECRET", "TOKEN", "PASSWORD", "USER")))
    meta = {
        "start": str(days[0]) if days else None, "end": str(days[-1]) if days else None,
        "sessions": len(days), "overrides": overrides, "halted_days": halted_days, "mode": mode,
        "experiments": {
            "block_entry_windows": [f"{a:%H:%M}-{b:%H:%M}" for a, b in (block_windows or [])],
            "skip_signals": sorted(skip_signals or []),
        },
        "runtime_s": round(_wall.monotonic() - t0, 1),
        "settings": {k: (v if isinstance(v, (int, float, str, bool)) or v is None else str(v))
                     for k in snap_keys for v in [getattr(settings, k)]},
        "model": {"tick_path": "1m bar -> O,L,H,C (up) / O,H,L,C (down)",
                  "option_pricing": "Black-Scholes in trading time (weeknight = "
                                    f"{WEEKNIGHT_MIN} min, weekend = {WEEKEND_MIN} min), "
                                    "IV = India VIX (minute), r = 6.5%",
                  "expiry_schedule": [(str(d), w) for d, w in EXPIRY_SCHEDULE]},
    }
    (out_dir / "run_meta.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return meta


def main_cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=None, help="first session (default: 10th cached session)")
    ap.add_argument("--end", default=None)
    ap.add_argument("--label", default="current_config")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    ap.add_argument("--block-window", action="append", default=[], metavar="HH:MM-HH:MM",
                    help="backtest-only: no new entries in this window (repeatable)")
    ap.add_argument("--skip-signals", default="", metavar="SIG,SIG",
                    help="backtest-only: never enter these signal types, e.g. CE_PIVOT")
    ap.add_argument("--mode", choices=["SHADOW", "PAPER"], default="SHADOW",
                    help="SHADOW = modelled option premiums (default); PAPER = the bot's "
                         "PAPER mode, which prices the option as the index (delta 1)")
    ap.add_argument("--no-report", action="store_true")
    a = ap.parse_args()

    md = MarketData()
    # Leave ~2 weeks of history for the 5-day candle seed and indicator warm-up.
    start = (_REAL_DATETIME.strptime(a.start, "%Y-%m-%d").date() if a.start else md.sessions[10])
    end = _REAL_DATETIME.strptime(a.end, "%Y-%m-%d").date() if a.end else md.sessions[-1]
    overrides = dict(kv.split("=", 1) for kv in a.set)
    windows = []
    for w in a.block_window:
        lo, hi = w.split("-")
        windows.append((_REAL_DATETIME.strptime(lo, "%H:%M").time(),
                        _REAL_DATETIME.strptime(hi, "%H:%M").time()))
    skip = {x.strip() for x in a.skip_signals.split(",") if x.strip()}
    out_dir = OUT_ROOT / a.label
    print(f"System backtest {start} -> {end}  label={a.label}  overrides={overrides or 'none'}")
    meta = run(md, start, end, overrides, out_dir, windows, skip, a.mode)
    print(f"Done: {meta['sessions']} sessions in {meta['runtime_s']}s -> {out_dir}")
    if not a.no_report:
        from research.backtest_report import build_report
        path = build_report(out_dir, md)
        print(f"Report: {path}")


if __name__ == "__main__":
    main_cli()
