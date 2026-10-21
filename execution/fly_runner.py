"""
SHADOW runner for the expiry-day iron butterfly (strategies/expiry_fly.py).

Runs beside the single-leg trading flow without touching it: its own DB table
(fly_trades), no shared state machine, no orders.  Call tick() every few
seconds from the bot's main loop.

    entry   FLY_ENTRY_TIME (within a 30-minute window) on a SENSEX expiry day
    stop    mid-priced buy-back cost >= credit * (1 + FLY_STOP_PCT)
    exit    FLY_EXIT_TIME, otherwise
    fills   simulated at the real bid/ask of every leg; the quotes are stored
            with the trade so research.fly_vs_model can compare them with the
            backtest's modelled prices

It refuses to run in LIVE (config.settings.validate() also blocks the combination).
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import date, datetime, time as dtime, timedelta

from config import settings
from notifications.notifier import notify
from persistence.trade_store import fly_get, fly_insert, fly_update
from strategies import expiry_fly as fly
from utils.costs import charges
from utils.logging_config import log_event
from utils.time_utils import now_ist, parse_time_ist

logger = logging.getLogger(__name__)

ENTRY_GRACE_MIN = 30          # later than this after FLY_ENTRY_TIME the day is skipped
STALE_EXIT_GRACE_MIN = 15     # quotes still failing this long after the exit time -> close on last marks
POLL_SECONDS = 5.0


class ExpiryFlyRunner:
    def __init__(self, kite_fn, options_fn, expiry_fn, spot_fn, now_fn=now_ist) -> None:
        """
        kite_fn     -> object with quote([...]) (broker.kite_client.get_kite)
        options_fn  (expiry: date, 'CE'|'PE') -> instrument dicts (strike, tradingsymbol)
        expiry_fn   () -> True when today is a SENSEX weekly expiry day
        spot_fn     () -> latest SENSEX price (0 when unknown)
        """
        if settings.TRADING_MODE == "LIVE":
            raise RuntimeError("ExpiryFlyRunner is SHADOW-only and refuses to run in LIVE.")
        self._kite_fn, self._options_fn = kite_fn, options_fn
        self._expiry_fn, self._spot_fn, self._now = expiry_fn, spot_fn, now_fn
        self._day: str | None = None
        self._row: dict | None = None
        self._finished = False
        self._last_poll = float("-inf")
        self._last_quotes: dict[str, fly.Quote] | None = None

    # ── public ────────────────────────────────────────────────────────────────
    def tick(self) -> None:
        if not settings.ENABLE_EXPIRY_FLY:
            return
        now = self._now()
        day = str(now.date())
        if day != self._day:
            self._start_day(day)
        if self._finished:
            return
        mono = _time.monotonic()
        if mono - self._last_poll < POLL_SECONDS:
            return
        self._last_poll = mono
        if self._row is None:
            self._try_enter(now)
        elif self._row.get("status") == "OPEN":
            self._monitor(now)

    # ── day lifecycle ─────────────────────────────────────────────────────────
    def _start_day(self, day: str) -> None:
        self._day, self._row, self._finished = day, None, False
        self._last_quotes = None
        existing = fly_get(day)
        if existing:
            self._row = existing
            self._finished = existing["status"] != "OPEN"
            if existing["status"] == "OPEN":
                log_event(logger, "FLY_RESUMED", day=day, credit=existing.get("credit"))
            return
        if day in {d.strip() for d in settings.FLY_SKIP_DATES.split(",") if d.strip()}:
            self._record_skip(day, "date listed in FLY_SKIP_DATES")
        elif not self._safe_is_expiry():
            self._finished = True               # ordinary day: nothing to do, nothing stored

    def _safe_is_expiry(self) -> bool:
        try:
            return bool(self._expiry_fn())
        except Exception as exc:
            logger.warning("Expiry-day check failed (%s); treating today as a normal day.", exc)
            return False

    def _record_skip(self, day: str, why: str) -> None:
        fly_insert({"day": day, "status": "SKIPPED", "mode": settings.TRADING_MODE, "note": why})
        log_event(logger, "FLY_SKIPPED", day=day, reason=why)
        notify("FLY_SKIPPED", day=day, reason=why)
        self._row, self._finished = {"day": day, "status": "SKIPPED"}, True

    # ── entry ─────────────────────────────────────────────────────────────────
    def _try_enter(self, now: datetime) -> None:
        entry_t = parse_time_ist(settings.FLY_ENTRY_TIME)
        entry_dt = datetime.combine(now.date(), entry_t, tzinfo=now.tzinfo)
        if now < entry_dt:
            return
        if now > entry_dt + timedelta(minutes=ENTRY_GRACE_MIN):
            self._record_skip(self._day, f"missed entry window ({settings.FLY_ENTRY_TIME} + {ENTRY_GRACE_MIN} min)")
            return
        spot = float(self._spot_fn() or 0)
        if spot <= 0:
            return
        strikes = fly.pick_strikes(spot, settings.FLY_WING_POINTS)
        try:
            symbols = self._resolve(strikes, now.date())
            quotes = self._quotes(symbols)
        except Exception as exc:
            logger.warning("Fly entry data unavailable (%s) - will retry.", exc)
            return
        if not (quotes["SC"].usable_for_sell() and quotes["SP"].usable_for_sell()
                and quotes["LC"].usable_for_buy() and quotes["LP"].usable_for_buy()):
            logger.warning("Fly entry quotes incomplete - will retry.")
            return
        extra = settings.FLY_EXTRA_SLIPPAGE_PTS
        fills = fly.entry_fills(quotes, extra)
        credit = fly.net_credit(fills)
        credit_mid = round(quotes["SC"].mid + quotes["SP"].mid - quotes["LC"].mid - quotes["LP"].mid, 2)
        if credit < settings.FLY_MIN_CREDIT:
            self._record_skip(self._day, f"credit {credit:.1f} below FLY_MIN_CREDIT {settings.FLY_MIN_CREDIT:g}")
            return
        legs = [{"leg": k, "symbol": symbols[k], "strike": strikes[k][0], "type": strikes[k][1],
                 "side": "SELL" if k.startswith("S") else "BUY", "entry_px": fills[k],
                 "bid": quotes[k].bid, "ask": quotes[k].ask, "last": quotes[k].last}
                for k in fly.LEGS]
        row = {
            "day": self._day, "status": "OPEN", "mode": settings.TRADING_MODE,
            "expiry": str(now.date()), "entry_time": now.isoformat(), "spot_entry": spot,
            "vix_entry": self._vix(), "legs": json.dumps(legs), "quantity": settings.FLY_QUANTITY,
            "credit": round(credit, 2), "credit_mid": credit_mid,
            "stop_value": fly.stop_level(credit, settings.FLY_STOP_PCT), "peak_value": 0.0,
        }
        if not fly_insert(row):
            self._start_day(self._day)           # another process/restart already entered
            return
        self._row = row
        self._last_quotes = quotes
        log_event(logger, "FLY_ENTERED", day=self._day, spot=spot, credit=round(credit, 2),
                  credit_mid=credit_mid, stop=row["stop_value"], qty=row["quantity"],
                  strikes={k: strikes[k][0] for k in fly.LEGS})
        notify("FLY_ENTERED", day=self._day, credit=round(credit, 2), stop=row["stop_value"])

    def _resolve(self, strikes: dict, expiry: date) -> dict[str, str]:
        out: dict[str, str] = {}
        cache: dict[str, dict[int, str]] = {}
        for leg, (strike, opt) in strikes.items():
            if opt not in cache:
                cache[opt] = {int(float(i["strike"])): i["tradingsymbol"]
                              for i in self._options_fn(expiry, opt)}
            sym = cache[opt].get(int(strike))
            if not sym:
                raise LookupError(f"no {opt} instrument at strike {strike} for {expiry}")
            out[leg] = sym
        return out

    def _quotes(self, symbols: dict[str, str]) -> dict[str, fly.Quote]:
        keys = {leg: f"BFO:{sym}" for leg, sym in symbols.items()}
        raw = self._kite_fn().quote(list(keys.values()))
        return {leg: fly.Quote.from_kite(raw[key]) for leg, key in keys.items()}

    def _vix(self) -> float | None:
        try:
            return float(self._kite_fn().quote(["NSE:INDIA VIX"])["NSE:INDIA VIX"]["last_price"])
        except Exception:
            return None

    # ── monitoring and exit ───────────────────────────────────────────────────
    def _monitor(self, now: datetime) -> None:
        row = self._row
        legs = json.loads(row["legs"])
        symbols = {l["leg"]: l["symbol"] for l in legs}
        exit_dt = datetime.combine(now.date(), parse_time_ist(settings.FLY_EXIT_TIME), tzinfo=now.tzinfo)
        try:
            quotes = self._quotes(symbols)
            self._last_quotes = quotes
        except Exception as exc:
            quotes = None
            logger.warning("Fly quote fetch failed (%s).", exc)
        if quotes is None:
            if now >= exit_dt + timedelta(minutes=STALE_EXIT_GRACE_MIN):
                marks = self._last_quotes or {
                    l["leg"]: fly.Quote(l["bid"], l["ask"], l["last"]) for l in legs}
                self._close(now, marks, "TIME_STALE", legs)
            return
        value = fly.mid_value(quotes)
        if value > (row.get("peak_value") or 0):
            row["peak_value"] = round(value, 2)
            fly_update(self._day, {"peak_value": row["peak_value"]})
        if value >= row["stop_value"]:
            self._close(now, quotes, "STOP", legs)
        elif now >= exit_dt:
            self._close(now, quotes, "TIME", legs)

    def _close(self, now: datetime, quotes: dict[str, fly.Quote], reason: str, legs: list[dict]) -> None:
        row = self._row
        extra = settings.FLY_EXTRA_SLIPPAGE_PTS
        out = fly.exit_fills(quotes, extra)
        exit_value = round(fly.buyback_cost(out), 2)
        qty = int(row["quantity"])
        gross = fly.pnl(row["credit"], exit_value, qty)
        entry = {l["leg"]: l["entry_px"] for l in legs}
        day = date.fromisoformat(self._day)
        cost = round(sum(
            charges(buy_px=out[k], sell_px=entry[k], qty=qty, day=day) if k.startswith("S")
            else charges(buy_px=entry[k], sell_px=out[k], qty=qty, day=day)
            for k in fly.LEGS), 2)
        fields = {
            "status": "CLOSED", "exit_time": now.isoformat(), "exit_reason": reason,
            "exit_legs": json.dumps([{"leg": k, "exit_px": out[k]} for k in fly.LEGS]),
            "exit_value": exit_value, "gross_pnl": gross, "charges": cost,
            "net_pnl": round(gross - cost, 2),
        }
        fly_update(self._day, fields)
        row.update(fields)
        self._finished = True
        log_event(logger, "FLY_CLOSED", day=self._day, reason=reason, credit=row["credit"],
                  exit_value=exit_value, gross=gross, charges=cost, net=fields["net_pnl"])
        notify("FLY_CLOSED", day=self._day, reason=reason, net=fields["net_pnl"])
