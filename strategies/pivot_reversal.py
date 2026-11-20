"""
Pivot Reversal engine — a line-for-line port of the TradingView Pine script
"Pivot Reversal + SL & Targets [Visual]" (Pine v6).

Pine rules reproduced exactly
-----------------------------
* swh = ta.pivothigh(left, right) / swl = ta.pivotlow(left, right).  A pivot at
  bar k is only known `right` bars later.  A new swing high sets ``hprice`` and
  arms ``le`` ("long enabled"); a new swing low sets ``lprice`` and arms ``se``.
* BUY  = le and high > hprice and close > EMA(50) and pos <= 0
  SELL = se and low  < lprice and close < EMA(50) and pos >= 0
  A fired signal clears its own arm flag (``le`` / ``se``), so every swing level
  can trigger AT MOST ONE trade — this is what removes the repeated "false"
  signals the old swing mode produced.
* ``pos`` is Pine's own virtual position.  It only returns to 0 when Pine's
  virtual stop (opposite swing level, or ATR stop) or virtual T2 is hit, so a
  second BUY cannot fire while the chart is still "long" — exactly like the
  chart.  An opposite signal flips the position (reversal).
* entry = max(open, hprice) for BUY, min(open, lprice) for SELL — the BREAKOUT
  LEVEL, not the bar close.
* stop = opposite swing level (or entry -/+ atrMult*ATR when useAtrSl or the
  level is missing), risk = max(|entry - stop|, mintick), T1/T2 = entry +/-
  rr * risk.

Entry timing
------------
``on_bar_close`` is the literal Pine bar-close evaluation.  ``on_tick`` is the
real-time equivalent TradingView shows on the live bar: the signal is taken the
moment price breaks the level while price is on the correct side of the live
EMA, instead of waiting for the bar to close (which is up to 5 minutes and
~70 index points late).  Both paths share the same state, so one level can
never fire twice.

Interpretation notes (where the Pine reference is silent)
---------------------------------------------------------
* Pivot test: the centre bar must be strictly beyond every LEFT bar and at
  least as extreme as every RIGHT bar.  Strict-left stops a run of identical
  (flat / frozen) candles from creating a pivot on every bar.
* If the swing-level stop is on the wrong side of the entry (possible after a
  gap), the ATR stop is used instead of a zero-risk trade.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from market.candle_builder import Candle
from market.indicators import atr as atr_series, ema as ema_series

logger = logging.getLogger(__name__)

MINTICK = 0.05  # SENSEX index tick — Pine's syminfo.mintick floor on risk


def grid_ladder(levels, side: str, entry: float, atr: float,
                min_gap_atr: float = 0.0) -> list[float]:
    """Every pivot-grid level ahead of ``entry`` in the trade direction, nearest first.

    CE -> P/R1..R5 above entry (ascending), PE -> P/S1..S5 below (descending).
    Levels closer than ``min_gap_atr`` x ATR are skipped so a level the price is
    already sitting on is not used as "Target 1".
    """
    names = ("pivot", "r1", "r2", "r3", "r4", "r5", "s1", "s2", "s3", "s4", "s5")
    grid = sorted({float(getattr(levels, n, 0.0) or 0.0) for n in names} - {0.0})
    gap = max(0.0, min_gap_atr) * max(0.0, atr)
    if side == "CE":
        return [lv for lv in grid if lv >= entry + max(gap, MINTICK)]
    return sorted((lv for lv in grid if lv <= entry - max(gap, MINTICK)), reverse=True)


def grid_targets(levels, side: str, entry: float, atr: float,
                 min_gap_atr: float = 0.0) -> tuple[float, float, float] | None:
    """Next three pivot-grid levels ahead of ``entry`` (T1, T2, T3).

    Returns None when fewer than three levels remain (caller falls back to ATR trail).
    """
    ahead = grid_ladder(levels, side, entry, atr, min_gap_atr)
    return (ahead[0], ahead[1], ahead[2]) if len(ahead) >= 3 else None


@dataclass(frozen=True)
class PineSignal:
    side: str          # "CE" (Pine BUY) | "PE" (Pine SELL)
    entry: float       # Pine entry reference: max(open, hprice) / min(open, lprice)
    stop: float        # Pine stop (opposite swing level or ATR stop)
    risk: float        # |entry - stop|, floored at MINTICK
    atr: float         # ATR(atr_period) used for the fallback stop / skip guard
    level: float       # the swing level that was broken
    bar_ts: datetime   # start of the 5m bar the signal belongs to
    source: str        # "TICK" | "BAR_CLOSE"


class PineReversalEngine:
    def __init__(
        self,
        left: int = 4,
        right: int = 2,
        ema_len: int = 50,
        rr_t1: float = 1.5,
        rr_t2: float = 2.5,
        use_atr_sl: bool = False,
        atr_mult: float = 1.5,
        atr_period: int = 14,
        day_reset: bool = True,
    ) -> None:
        # True  = each session starts flat (bot-only behaviour).
        # False = the virtual position carries across sessions like the TradingView chart.
        self.day_reset = day_reset
        self.left = max(1, int(left))
        self.right = max(1, int(right))
        self.ema_len = int(ema_len)
        self.rr_t1 = rr_t1
        self.rr_t2 = rr_t2
        self.use_atr_sl = use_atr_sl
        self.atr_mult = atr_mult
        self.atr_period = atr_period
        self._k = 2.0 / (self.ema_len + 1) if self.ema_len > 0 else 0.0

        # Pine `var` state
        self.hprice: float | None = None
        self.lprice: float | None = None
        self.le = False
        self.se = False
        self.pos = 0                       # 1 long, -1 short, 0 flat (virtual)
        self.v_sl: float | None = None
        self.v_t1: float | None = None
        self.v_t2: float | None = None

        # one in-swing re-entry per side (see arm_reentry)
        self.reentry: dict | None = None
        self._re_used = {"CE": False, "PE": False}
        self._re_try_bar: datetime | None = None

        self._day = None                      # session date of the last bar seen
        self._ema_prev: float | None = None   # EMA at the last completed bar
        self._atr_prev: float | None = None   # ATR at the last completed bar
        self._last_ts: datetime | None = None
        self._index = -1

    @classmethod
    def from_settings(cls, settings) -> "PineReversalEngine":
        return cls(
            left=settings.PIVOT_PINE_LEFT,
            right=settings.PIVOT_PINE_RIGHT,
            ema_len=settings.PIVOT_PINE_EMA,
            rr_t1=settings.PIVOT_PINE_RR_T1,
            rr_t2=settings.PIVOT_PINE_RR_T2,
            use_atr_sl=settings.PIVOT_PINE_USE_ATR_SL,
            atr_mult=settings.PIVOT_PINE_ATR_MULT,
            atr_period=settings.PIVOT_ATR_PERIOD,
            day_reset=settings.PIVOT_PINE_DAY_RESET,
        )

    # ── public API ────────────────────────────────────────────────────────────
    def warm_up(self, candles: Sequence[Candle]) -> None:
        """Replay history to rebuild Pine's `var` state.  Emits nothing."""
        self._reset()
        if not candles:
            return
        ema_arr = self._ema(candles)
        atr_arr = atr_series(candles, self.atr_period)
        for i in range(len(candles)):
            self._step(candles, i, ema_arr[i], atr_arr[i], "BAR_CLOSE")
        self._finish(candles, ema_arr, atr_arr)

    def snapshot(self) -> dict:
        """JSON-able copy of Pine's `var` state, for restart recovery.

        warm_up() can only rebuild what completed bars imply.  A tick-fired
        breakout (or one the entry gate then blocked) flips `pos`/`le`/`se`
        intrabar and is NOT reproducible from candles, so a restart used to
        rewind the engine and change which entries fire afterwards.
        """
        return {
            "fp": self._fingerprint(),
            "hprice": self.hprice, "lprice": self.lprice,
            "le": self.le, "se": self.se, "pos": self.pos,
            "v_sl": self.v_sl, "v_t1": self.v_t1, "v_t2": self.v_t2,
            "reentry": self.reentry, "re_used": dict(self._re_used),
            "last_ts": self._last_ts.isoformat() if self._last_ts else None,
        }

    def restore(self, snap: dict, candles: Sequence[Candle]) -> bool:
        """Re-apply a snapshot taken by the previous process, then roll it
        forward over the completed bars that closed since (silently - a late
        signal is never traded).  Call after warm_up(); returns False and leaves
        the warm_up state untouched when the snapshot is unusable.

        Only a snapshot from the SAME session as the newest bar is accepted:
        an older one is just what warm_up already rebuilt from history.
        """
        if not snap or not candles or snap.get("fp") != self._fingerprint():
            return False
        try:
            last_ts = datetime.fromisoformat(snap["last_ts"])
            first, newest = candles[0].timestamp, candles[-1].timestamp
            if not (first <= last_ts <= newest):
                return False
            # With the daily reset on, only a same-session snapshot is usable (an older
            # one is just what warm_up already rebuilt).  Without it the position and an
            # armed re-entry legitimately carry overnight, so an earlier session is fine.
            if self.day_reset and last_ts.date() != newest.date():
                return False
            new = {k: snap[k] for k in ("hprice", "lprice", "le", "se", "pos",
                                        "v_sl", "v_t1", "v_t2")}
        except (KeyError, TypeError, ValueError):
            return False
        self.hprice, self.lprice = new["hprice"], new["lprice"]
        self.le, self.se, self.pos = bool(new["le"]), bool(new["se"]), int(new["pos"])
        self.v_sl, self.v_t1, self.v_t2 = new["v_sl"], new["v_t1"], new["v_t2"]
        self.reentry = snap.get("reentry")
        self._re_used = {"CE": False, "PE": False, **(snap.get("re_used") or {})}
        ema_arr = self._ema(candles)
        atr_arr = atr_series(candles, self.atr_period)
        for i, c in enumerate(candles):
            if c.timestamp > last_ts:
                self._step(candles, i, ema_arr[i], atr_arr[i], "BAR_CLOSE")
        self._finish(candles, ema_arr, atr_arr)
        return True

    # ── in-swing re-entry (one per side per swing) ────────────────────────────
    def arm_reentry(self, side: str, best: float) -> bool:
        """Arm ONE re-entry after the real trade exited on a trail / grid floor /
        break-even while Pine's swing is still alive (virtual position still on
        ``side`` and the Pine stop not hit).  Re-entry fires when price makes a new
        extreme beyond ``best`` (the trade's best price) - see on_reentry_tick.
        Pine's own state (pos / le / se) is untouched, so fresh signals still
        follow the TradingView rules exactly.
        """
        sign = 1 if side == "CE" else -1
        if self._re_used[side] or self.pos != sign or self.v_sl is None:
            return False
        self.reentry = {"side": side, "best": float(best), "stop": float(self.v_sl)}
        return True

    def on_reentry_tick(self, price: float, bar_ts: datetime | None) -> PineSignal | None:
        """Emit the armed re-entry (at most one attempt per 5m bar).

        Does NOT consume it - the caller calls confirm_reentry() once the order
        was really placed, so a blocked attempt (gate, cap) is retried next bar.
        """
        r = self.reentry
        if r is None or price <= 0 or self._atr_prev is None or bar_ts is None:
            return None
        self._roll_day(bar_ts)
        r = self.reentry                       # _roll_day clears it on a new session
        if r is None:
            return None
        side, sign = r["side"], (1 if r["side"] == "CE" else -1)
        if self.pos != sign or (price - r["stop"]) * sign <= 0:
            self.reentry = None                # swing over: Pine stop hit / flipped
            return None
        if self.ema_len > 0:
            if self._ema_prev is None:
                return None
            ema_live = self._k * price + (1.0 - self._k) * self._ema_prev
            if (price <= ema_live) if sign == 1 else (price >= ema_live):
                return None                    # direction no longer agrees
        if (price - r["best"]) * sign <= 0 or self._re_try_bar == bar_ts:
            return None
        self._re_try_bar = bar_ts
        return PineSignal(
            side=side, entry=round(price, 2), stop=round(r["stop"], 2),
            risk=round(max(abs(price - r["stop"]), MINTICK), 2),
            atr=round(self._atr_prev, 2), level=r["best"], bar_ts=bar_ts, source="REENTRY",
        )

    def confirm_reentry(self) -> None:
        """The re-entry order went through: this swing has used its one re-entry."""
        if self.reentry is not None:
            self._re_used[self.reentry["side"]] = True
        self.reentry = None

    def _fingerprint(self) -> list:
        return [self.left, self.right, self.ema_len, self.rr_t1, self.rr_t2,
                self.use_atr_sl, self.atr_mult, self.atr_period, self.day_reset]

    def on_bar_close(self, candles: Sequence[Candle]) -> PineSignal | None:
        """Evaluate the newly completed bar (candles[-1]) exactly as Pine does.

        Any earlier bar the engine has not seen yet (a missed callback) is
        replayed silently first, so Pine's pivot/arm/position state never skips
        a bar.  Only the newest bar can emit a signal.
        """
        if not candles:
            return None
        last = candles[-1]
        if self._last_ts is not None and last.timestamp <= self._last_ts:
            return None   # already processed (seed overlap / duplicate callback)
        ema_arr = self._ema(candles)
        atr_arr = atr_series(candles, self.atr_period)
        n = len(candles)
        start = 0
        if self._last_ts is not None:
            while start < n and candles[start].timestamp <= self._last_ts:
                start += 1
        for i in range(start, n - 1):
            self._step(candles, i, ema_arr[i], atr_arr[i], "BAR_CLOSE")
        sig = self._step(candles, n - 1, ema_arr[-1], atr_arr[-1], "BAR_CLOSE")
        self._finish(candles, ema_arr, atr_arr)
        return sig

    def on_tick(self, price: float, bar_open: float, bar_ts: datetime | None) -> PineSignal | None:
        """Real-time breakout trigger on the forming bar."""
        if price <= 0 or self._atr_prev is None or bar_ts is None:
            return None
        self._roll_day(bar_ts)
        if self.ema_len > 0:
            if self._ema_prev is None:
                return None
            ema_live = self._k * price + (1.0 - self._k) * self._ema_prev
            long_ok = price > ema_live
            short_ok = price < ema_live
        else:
            long_ok = short_ok = True
        open_ = bar_open if bar_open and bar_open > 0 else price

        if (self.le and self.hprice is not None and price > self.hprice
                and long_ok and self.pos <= 0):
            return self._open("CE", max(open_, self.hprice), self.hprice,
                              self._atr_prev, bar_ts, "TICK")
        if (self.se and self.lprice is not None and price < self.lprice
                and short_ok and self.pos >= 0):
            return self._open("PE", min(open_, self.lprice), self.lprice,
                              self._atr_prev, bar_ts, "TICK")
        return None

    # ── internals ─────────────────────────────────────────────────────────────
    def _reset(self) -> None:
        self.hprice = self.lprice = None
        self.le = self.se = False
        self.pos = 0
        self._day = None
        self.v_sl = self.v_t1 = self.v_t2 = None
        self.reentry = None
        self._re_used = {"CE": False, "PE": False}
        self._re_try_bar = None
        self._ema_prev = self._atr_prev = None
        self._last_ts = None
        self._index = -1

    def _ema(self, candles: Sequence[Candle]) -> list[float | None]:
        if self.ema_len <= 0:
            return [None] * len(candles)
        return ema_series(candles, self.ema_len)

    def _finish(self, candles, ema_arr, atr_arr) -> None:
        self._ema_prev = ema_arr[-1]
        self._atr_prev = atr_arr[-1]
        self._last_ts = candles[-1].timestamp
        self._index = len(candles) - 1

    def _pivots(self, candles: Sequence[Candle], i: int) -> None:
        k = i - self.right
        lo = k - self.left
        if lo < 0:
            return
        ch, cl = candles[k].high, candles[k].low
        is_ph = is_pl = True
        for j in range(lo, i + 1):
            if j == k:
                continue
            if j < k:   # left bars: centre must be strictly beyond
                if candles[j].high >= ch:
                    is_ph = False
                if candles[j].low <= cl:
                    is_pl = False
            else:       # right bars: centre must be at least as extreme
                if candles[j].high > ch:
                    is_ph = False
                if candles[j].low < cl:
                    is_pl = False
            if not is_ph and not is_pl:
                return
        if is_ph:
            self.hprice, self.le = ch, True
        if is_pl:
            self.lprice, self.se = cl, True

    def _roll_day(self, ts: datetime) -> None:
        """New session.

        Swing levels and the le / se arm flags always carry over (a level consumed
        yesterday stays consumed, so a stale level cannot re-fire on the same side).

        day_reset=True : start FLAT - the virtual position, its stop/targets and any
        armed re-entry are dropped, so a trade that never hit stop/T2 before the close
        cannot block the first break of the new day.
        day_reset=False: the virtual position carries over exactly like the TradingView
        chart (Pine's `var` state never resets at the session boundary), and so does an
        armed in-swing re-entry.
        """
        day = ts.date()
        if self.day_reset and self._day is not None and day != self._day:
            self.pos = 0
            self.v_sl = self.v_t1 = self.v_t2 = None
            self.reentry = None
        self._day = day

    def _step(self, candles, i, ema_i, atr_i, source) -> PineSignal | None:
        bar = candles[i]
        self._roll_day(bar.timestamp)
        self._pivots(candles, i)
        sig: PineSignal | None = None

        ready = atr_i is not None and (self.ema_len <= 0 or ema_i is not None)
        if ready:
            long_ok = self.ema_len <= 0 or bar.close > ema_i
            short_ok = self.ema_len <= 0 or bar.close < ema_i
            pos0 = self.pos     # Pine computes both signals before either executes
            buy = (self.le and self.hprice is not None and bar.high > self.hprice
                   and long_ok and pos0 <= 0)
            sell = (self.se and self.lprice is not None and bar.low < self.lprice
                    and short_ok and pos0 >= 0)
            if buy:
                sig = self._open("CE", max(bar.open, self.hprice), self.hprice,
                                 atr_i, bar.timestamp, source)
            if sell:
                sig = self._open("PE", min(bar.open, self.lprice), self.lprice,
                                 atr_i, bar.timestamp, source)

        # Pine exit checking (same bar as the entry is checked too)
        if self.pos == 1 and self.v_sl is not None and (
                bar.low <= self.v_sl or bar.high >= self.v_t2):
            self.pos = 0
            self.reentry = None            # swing finished
        elif self.pos == -1 and self.v_sl is not None and (
                bar.high >= self.v_sl or bar.low <= self.v_t2):
            self.pos = 0
            self.reentry = None
        return sig

    def _open(self, side: str, entry: float, level: float, atr_val: float,
              ts: datetime, source: str) -> PineSignal:
        self._re_used[side] = False        # a fresh Pine signal = a new swing
        if self.reentry is not None and self.reentry["side"] == side:
            self.reentry = None
        if side == "CE":
            swing = self.lprice
            if self.use_atr_sl or swing is None or swing >= entry:
                stop = entry - self.atr_mult * atr_val
            else:
                stop = swing
            risk = max(entry - stop, MINTICK)
            self.v_t1 = entry + self.rr_t1 * risk
            self.v_t2 = entry + self.rr_t2 * risk
            self.pos = 1
            self.le = False
        else:
            swing = self.hprice
            if self.use_atr_sl or swing is None or swing <= entry:
                stop = entry + self.atr_mult * atr_val
            else:
                stop = swing
            risk = max(stop - entry, MINTICK)
            self.v_t1 = entry - self.rr_t1 * risk
            self.v_t2 = entry - self.rr_t2 * risk
            self.pos = -1
            self.se = False
        self.v_sl = stop
        return PineSignal(
            side=side, entry=round(entry, 2), stop=round(stop, 2),
            risk=round(risk, 2), atr=round(atr_val, 2), level=level,
            bar_ts=ts, source=source,
        )
