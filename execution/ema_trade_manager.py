"""
EMA trade manager — index-based SL / break-even / trail / target for EMA CE / PE.

All decisions are made on the SENSEX index price (like the Pivot engine), so the
stop sits exactly at the structure level instead of a premium × fixed-delta guess.
The broker protective SL (option premium) is only a disaster backstop.

  INITIAL  stop = swing low/high ∓ buffer × ATR, distance clamped to
           [min_atr, max_atr] × ATR  (fallback: fallback_atr × ATR)
  BE       best move >= be_trigger_r × risk → stop = entry + be_buffer
  TRAIL    after BE: chandelier stop = best − trail_atr_mult × ATR(14)
           and (optional) exit on a 5m close back through EMA9
  TIME     after time_stop_bars candles, still INITIAL and best < min_r × risk → exit
  TARGET   target_rr × risk reached → exit
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path

from execution.pivot_trade_manager import PivotTradeManager, _STOP_EPSILON
from utils.logging_config import log_event

logger = logging.getLogger(__name__)

_STATE_FILE = Path(__file__).resolve().parent.parent / ".ema_trade.json"
_IDX_STATE_FILE = Path(__file__).resolve().parent.parent / ".idx_trade.json"


def plan_ema_risk(
    side: str,
    entry_index: float,
    atr: float | None,
    swing_high: float | None,
    swing_low: float | None,
    *,
    swing_buffer_atr: float = 0.25,
    min_atr: float = 1.0,
    max_atr: float = 2.0,
    fallback_atr: float = 1.5,
    target_rr: float = 3.0,
    levels: Sequence[float] = (),
    min_room_r: float = 0.0,
) -> tuple[dict | None, str | None]:
    """
    Return (plan, None) or (None, block_reason).
    plan = {stop, target, risk, source, room}
    """
    if not atr or atr <= 0 or entry_index <= 0:
        return None, "ATR unavailable"
    sign = 1 if side == "CE" else -1
    swing = swing_low if side == "CE" else swing_high
    if swing is not None and (entry_index - swing) * sign > 0:
        dist = abs(entry_index - swing) + swing_buffer_atr * atr
        source = "swing"
    else:
        dist = fallback_atr * atr
        source = "atr_fallback"
    dist = min(max(dist, min_atr * atr), max_atr * atr)
    stop = round(entry_index - sign * dist, 2)
    target = round(entry_index + sign * dist * target_rr, 2)

    room = None
    ahead = [(lv - entry_index) * sign for lv in levels if lv and (lv - entry_index) * sign > 0]
    if ahead:
        room = min(ahead)
        if min_room_r > 0 and room < min_room_r * dist:
            return None, f"room {room:.1f} < {min_room_r}R ({min_room_r * dist:.1f})"
    return {"stop": stop, "target": target, "risk": round(dist, 2),
            "source": source, "room": room}, None


def plan_natr_risk(
    side: str,
    entry_index: float,
    natr_line: float | None,
    atr: float | None,
    *,
    mult: float = 3.0,
    min_atr: float = 1.0,
    target_rr: float = 3.0,
) -> tuple[dict | None, str | None]:
    """
    NATR-managed risk plan (TradingView "ATR 5 Min Index Study").

    Stop = the NATR trailing line when it sits behind entry (the trend the trade
    follows); if the line is on the wrong side (NATR still in the opposite trend)
    stop = entry ∓ mult × ATR, i.e. where the line would sit after flipping.
    Distance is floored at min_atr × ATR.  Returns (plan, None) or (None, reason).
    """
    if not atr or atr <= 0 or entry_index <= 0:
        return None, "ATR unavailable"
    sign = 1 if side == "CE" else -1
    if natr_line is not None and (entry_index - natr_line) * sign > 0:
        dist, source = entry_index - natr_line, "natr_line"
    else:
        dist, source = mult * atr, "natr_atr"
    dist = abs(dist)
    dist = max(dist, min_atr * atr)
    stop = round(entry_index - sign * dist, 2)
    target = round(entry_index + sign * dist * target_rr, 2) if target_rr > 0 else \
        round(entry_index + sign * 1e6, 2)
    return {"stop": stop, "target": target, "risk": round(dist, 2),
            "source": source, "room": None}, None


class EmaTradeManager(PivotTradeManager):
    # Exit reason per stage when the index stop is crossed, and on target.
    EXIT_REASONS = {"INITIAL": "EMA_SL_HIT", "BE": "EMA_BE_STOP", "TRAIL": "EMA_TSL_HIT",
                    "TARGET": "EMA_TARGET"}
    # NATR mode: the stop only follows the NATR line (set per candle via
    # set_natr_line); BE / chandelier / EMA9-trail / time-stop are disabled.
    # Class-level defaults keep older persisted states loadable.
    natr_mode: bool = False
    natr_line: float | None = None
    _stop_dirty: bool = False
    natr_broker_trail: bool = True

    def __init__(
        self,
        side: str,
        entry_index: float,
        stop_index: float,
        target_index: float,
        atr: float,
        option_entry: float,
        *,
        delta: float = 0.5,
        be_trigger_r: float = 1.0,
        be_buffer_pts: float = 4.0,
        trail_atr_mult: float = 2.0,
        trail_ema9_exit: bool = True,
        time_stop_bars: int = 6,
        time_stop_min_r: float = 0.5,
        hard_sl_cushion: float = 1.1,
        max_sl_pct: float = 0.30,
        natr_mode: bool = False,
        natr_broker_trail: bool = True,
    ) -> None:
        super().__init__(
            side, entry_index, stop_index, target_index, target_index, target_index,
            atr, option_entry,
            delta=delta, be_trigger_r=be_trigger_r, be_buffer_pts=be_buffer_pts,
            trail_atr_mult=trail_atr_mult, t2_trail_atr_mult=0.0,
            hard_sl_cushion=hard_sl_cushion, max_sl_pct=max_sl_pct,
        )
        self.trail_ema9_exit = trail_ema9_exit
        self.time_stop_bars = time_stop_bars
        self.time_stop_min_r = time_stop_min_r
        self.bars = 0
        self.natr_mode = natr_mode
        self.natr_line = None
        self.natr_broker_trail = natr_broker_trail

    def set_natr_line(self, line: float | None, close: float) -> bool:
        """NATR mode: ratchet the stop to the NATR line (call on each 5m close).

        Only a line that is behind price (trend side) is used — a line still on
        the wrong side of price belongs to the opposite trend.
        Returns True when the stop moved (caller should update the broker SL)."""
        if not self.natr_mode or line is None or (close - line) * self.sign <= 0:
            return False
        self.natr_line = line
        broker_stop = self.option_stop
        moved = self._move_stop(line, "TRAIL")
        if moved and not self.natr_broker_trail:
            # Index logic owns the exit; the broker SL stays at its initial
            # disaster level (a premium stop derived from a fixed delta fires
            # early once theta / IV decay eat the premium).
            self.option_stop = broker_stop
            return moved
        # the next index tick reports STOP_MOVED so main updates the broker SL
        self._stop_dirty = self._stop_dirty or moved
        return moved

    # ── every SENSEX tick ─────────────────────────────────────────────────────
    def on_index_price(self, price: float) -> tuple[str, object] | None:
        if self._fav(price) < -_STOP_EPSILON + self._fav(self.stop_index):
            reason = self.EXIT_REASONS.get(self.stage, self.EXIT_REASONS["TRAIL"])
            return ("EXIT", reason)
        if self._fav(price) >= self._fav(self.t3):
            return ("EXIT", self.EXIT_REASONS["TARGET"])

        if self._fav(price) > self._fav(self.best_index):
            self.best_index = price
        if self.natr_mode:
            if self._stop_dirty:
                self._stop_dirty = False
                return ("STOP_MOVED", self.option_stop)
            return None
        moved = False
        if self.stage == "INITIAL" and self._fav(self.best_index) >= self.be_trigger_r * self.risk:
            moved |= self._move_stop(self.entry_index + self.sign * self.be_buffer_pts, "BE")
        if self.stage in ("BE", "TRAIL") and self.trail_atr_mult > 0:
            moved |= self._move_stop(self.best_index - self.sign * self.trail_atr_mult * self.atr, "TRAIL")
        return ("STOP_MOVED", self.option_stop) if moved else None

    # ── every completed 5m candle ─────────────────────────────────────────────
    def on_candle(self, close: float, ema9: float | None) -> str | None:
        self.bars += 1
        if self.natr_mode:
            return None
        if (self.trail_ema9_exit and self.stage != "INITIAL" and ema9 is not None
                and (close - ema9) * self.sign < 0):
            log_event(logger, "EMA_TRAIL_EMA9_EXIT", side=self.side, close=close, ema9=round(ema9, 2))
            return "EMA_TRAIL_EMA9"
        if (self.time_stop_bars > 0 and self.stage == "INITIAL" and self.bars >= self.time_stop_bars
                and self._fav(self.best_index) < self.time_stop_min_r * self.risk):
            log_event(logger, "EMA_TIME_STOP", side=self.side, bars=self.bars,
                      best_r=round(self._fav(self.best_index) / self.risk, 2) if self.risk else None)
            return "EMA_TIME_STOP"
        return None

    # ── persistence (own file, separate from Pivot) ───────────────────────────
    @classmethod
    def _state_file(cls) -> Path:
        return _STATE_FILE

    def save(self, trade_id: str) -> None:
        try:
            self._state_file().write_text(json.dumps({"trade_id": trade_id, **self.__dict__}))
        except Exception as exc:
            logger.warning("%s state save failed: %s", type(self).__name__, exc)

    @classmethod
    def load(cls, trade_id: str) -> "EmaTradeManager | None":
        try:
            d = json.loads(cls._state_file().read_text())
        except Exception:
            return None
        if d.pop("trade_id", None) != trade_id:
            return None
        obj = cls.__new__(cls)
        obj.__dict__.update(d)
        return obj

    @classmethod
    def clear(cls) -> None:
        try:
            cls._state_file().unlink(missing_ok=True)
        except Exception:
            pass


class IndexTradeManager(EmaTradeManager):
    """
    Index-anchored SL / break-even / chandelier trail / target for the generic
    strategies (VWAP, ORB, NATR, ATR, PDHL, TRB, OB, MOM) — the same engine as
    EMA, without its EMA-specific exits (EMA9 close, time stop).

    Decisions are made on SENSEX ticks, so the stop is exactly the intended
    index distance instead of an option-premium distance from a fixed delta
    guess (which drifts on fast / expiry days).  The broker option SL is a
    wider backstop (hard_sl_cushion) for when the bot itself is down.
    """
    EXIT_REASONS = {"INITIAL": "IDX_SL_HIT", "BE": "IDX_BE_STOP", "TRAIL": "IDX_TSL_HIT",
                    "TARGET": "IDX_TARGET"}

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("trail_ema9_exit", False)
        kwargs.setdefault("time_stop_bars", 0)
        super().__init__(*args, **kwargs)

    @classmethod
    def _state_file(cls) -> Path:
        return _IDX_STATE_FILE
