"""Tests for the Pine "Pivot Reversal" engine and the trail-only pivot manager."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pytest

from execution.pivot_trade_manager import PivotTradeManager
from market.candle_builder import Candle
from strategies.pivot_reversal import PineReversalEngine


def _walk(n: int, seed: int) -> list[Candle]:
    rnd = random.Random(seed)
    t = datetime(2026, 1, 5, 9, 15)
    px = 70000.0
    out: list[Candle] = []
    for _ in range(n):
        o = px + rnd.uniform(-8, 8)
        c = o + rnd.uniform(-60, 60)
        h = max(o, c) + rnd.uniform(0, 40)
        l = min(o, c) - rnd.uniform(0, 40)
        out.append(Candle(t, o, h, l, c))
        px = c
        t += timedelta(minutes=5)
    return out


def _literal_pine(candles: list[Candle], left=4, right=2, ema_len=50, rr2=2.5, atr_mult=1.5):
    """Independent, deliberately naive port of the Pine script (bar-close only)."""
    closes = [c.close for c in candles]
    k = 2 / (ema_len + 1)
    ema = [None] * len(candles)
    ema[ema_len - 1] = sum(closes[:ema_len]) / ema_len
    for i in range(ema_len, len(candles)):
        ema[i] = closes[i] * k + ema[i - 1] * (1 - k)
    tr = [None] + [max(c.high - c.low, abs(c.high - candles[i].close), abs(c.low - candles[i].close))
                   for i, c in enumerate(candles[1:])]
    atr = [None] * len(candles)
    atr[14] = sum(tr[1:15]) / 14
    for i in range(15, len(candles)):
        atr[i] = (atr[i - 1] * 13 + tr[i]) / 14

    hp = lp = None
    le = se = False
    pos = 0
    sl = t2 = None
    sigs = []
    for i, c in enumerate(candles):
        kk = i - right
        if kk - left >= 0:
            win = candles[kk - left: i + 1]
            if all(candles[j].high < candles[kk].high for j in range(kk - left, kk)) and \
               all(x.high <= candles[kk].high for x in candles[kk + 1: i + 1]):
                hp, le = candles[kk].high, True
            if all(candles[j].low > candles[kk].low for j in range(kk - left, kk)) and \
               all(x.low >= candles[kk].low for x in candles[kk + 1: i + 1]):
                lp, se = candles[kk].low, True
        if atr[i] is not None and ema[i] is not None:
            buy = le and c.high > hp and c.close > ema[i] and pos <= 0
            sell = se and c.low < lp and c.close < ema[i] and pos >= 0
            if buy:
                ent = max(c.open, hp)
                sl = lp if (lp is not None and lp < ent) else ent - atr_mult * atr[i]
                risk = max(ent - sl, 0.05)
                t2 = ent + rr2 * risk
                pos, le = 1, False
                sigs.append((c.timestamp, "CE", round(ent, 2), round(sl, 2)))
            if sell:
                ent = min(c.open, lp)
                sl = hp if (hp is not None and hp > ent) else ent + atr_mult * atr[i]
                risk = max(sl - ent, 0.05)
                t2 = ent - rr2 * risk
                pos, se = -1, False
                sigs.append((c.timestamp, "PE", round(ent, 2), round(sl, 2)))
        if pos == 1 and (c.low <= sl or c.high >= t2):
            pos = 0
        elif pos == -1 and (c.high >= sl or c.low <= t2):
            pos = 0
    return sigs


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_engine_matches_literal_pine_port(seed):
    candles = _walk(500, seed)
    expected = _literal_pine(candles)
    assert expected, "walk produced no signals â€” test would prove nothing"

    eng = PineReversalEngine(4, 2, 50, 1.5, 2.5, False, 1.5, 14)
    got = []
    for i in range(len(candles)):
        s = eng.on_bar_close(candles[: i + 1])
        if s:
            got.append((s.bar_ts, s.side, s.entry, s.stop))
    assert got == expected


def test_signals_alternate_like_the_chart():
    """Pine's virtual position makes BUY/SELL alternate until a stop/T2 resets it."""
    eng = PineReversalEngine()
    candles = _walk(600, 7)
    last = None
    for i in range(len(candles)):
        s = eng.on_bar_close(candles[: i + 1])
        if s:
            assert s.risk > 0
            last = s.side
    assert last is not None


def test_warm_up_is_silent_and_matches_incremental_state():
    candles = _walk(300, 11)
    a = PineReversalEngine()
    a.warm_up(candles)
    b = PineReversalEngine()
    for i in range(len(candles)):
        b.on_bar_close(candles[: i + 1])
    assert (a.hprice, a.lprice, a.le, a.se, a.pos) == (b.hprice, b.lprice, b.le, b.se, b.pos)


def test_duplicate_bar_close_is_ignored():
    candles = _walk(200, 3)
    eng = PineReversalEngine()
    eng.warm_up(candles)
    assert eng.on_bar_close(candles) is None


def test_missed_bar_is_replayed_not_skipped():
    candles = _walk(260, 5)
    full = PineReversalEngine()
    for i in range(len(candles)):
        full.on_bar_close(candles[: i + 1])
    gap = PineReversalEngine()
    gap.warm_up(candles[:200])
    gap.on_bar_close(candles)            # jumps 60 bars at once
    assert (gap.hprice, gap.lprice, gap.pos) == (full.hprice, full.lprice, full.pos)


def _armed_engine():
    """Engine with an armed swing low and price above a falling EMA context."""
    candles = _walk(400, 21)
    eng = PineReversalEngine()
    eng.warm_up(candles)
    return eng, candles


def test_tick_trigger_fires_once_and_blocks_bar_close_duplicate():
    eng, candles = _armed_engine()
    eng.pos = 0
    eng.se = True
    eng.lprice = candles[-1].close - 50
    eng.hprice = candles[-1].close + 300
    eng._ema_prev = candles[-1].close + 200      # price well below EMA -> shorts allowed
    ts = candles[-1].timestamp + timedelta(minutes=5)
    sig = eng.on_tick(eng.lprice - 5, eng.lprice + 20, ts)
    assert sig is not None and sig.side == "PE" and sig.source == "TICK"
    assert sig.entry == pytest.approx(eng.lprice, abs=0.01)   # min(open, level) = level
    assert eng.se is False and eng.pos == -1
    assert eng.on_tick(eng.lprice - 10, eng.lprice + 20, ts) is None   # one trade per level


def test_tick_trigger_respects_ema_filter():
    eng, candles = _armed_engine()
    eng.pos = 0
    eng.se = True
    eng.lprice = candles[-1].close - 50
    eng.hprice = candles[-1].close + 300
    eng._ema_prev = candles[-1].close - 500      # price far ABOVE EMA -> no short
    ts = candles[-1].timestamp + timedelta(minutes=5)
    assert eng.on_tick(eng.lprice - 5, eng.lprice + 20, ts) is None


# â”€â”€ trail-only manager â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _mgr(side="CE"):
    entry = 77000.0
    stop = entry - 150 if side == "CE" else entry + 150
    return PivotTradeManager(
        side, entry, stop, entry, entry, entry, 100.0, 300.0,
        delta=1.0, hard_sl_cushion=2.5, max_sl_pct=0.5, signal_risk=150.0,
        trail_only=True, trail_act_r=1.0, trail_mult=3.0,
    )


def test_trail_only_has_no_break_even_and_no_fixed_target():
    m = _mgr("CE")
    # +0.9R: nothing moves (no break-even), stop stays at the Pine stop
    assert m.on_index_price(77000 + 135) is None
    assert m.stop_index == 76850.0
    # a huge run does not trigger any fixed target exit
    for p in range(77135, 77900, 25):
        a = m.on_index_price(float(p))
        assert a is None or a[0] == "STOP_MOVED"
    assert m.stage == "TRAIL"


def test_trail_only_trails_wide_and_exits_on_pullback():
    m = _mgr("CE")
    m.on_index_price(77200.0)                  # +1.33R -> trail armed
    assert m.stop_index == pytest.approx(77200 - 3 * 100)   # best - 3xATR = 76900
    m.on_index_price(77500.0)
    assert m.stop_index == pytest.approx(77500 - 300)
    # a normal 150-pt pullback must NOT stop the trade out
    assert m.on_index_price(77350.0) is None
    action = m.on_index_price(77190.0)
    assert action == ("EXIT", "PIVOT_TSL_HIT")


def test_trail_only_stop_never_loosens_and_initial_exit_reason():
    m = _mgr("PE")
    m.on_index_price(76800.0)                  # +1.33R for a short
    s1 = m.stop_index
    m.on_index_price(76900.0)                  # retrace â€” stop must not move back
    assert m.stop_index == s1
    m2 = _mgr("CE")
    assert m2.on_index_price(76840.0) == ("EXIT", "PIVOT_SL_HIT")


def test_legacy_manager_state_without_trail_fields_still_loads():
    old = PivotTradeManager.__new__(PivotTradeManager)
    old.__dict__.update({"side": "CE"})
    assert old.trail_only is False             # class-level default


def _mgr_atr(side="PE"):
    # stale-swing case: stop 500 pts away, ATR 100 -> 1R is never reached on a 2-ATR move
    entry = 77000.0
    stop = entry + 500 if side == "PE" else entry - 500
    return PivotTradeManager(
        side, entry, stop, entry, entry, entry, 100.0, 300.0,
        delta=1.0, hard_sl_cushion=2.5, max_sl_pct=0.5, signal_risk=500.0,
        trail_only=True, trail_act_r=1.0, trail_mult=2.5,
        trail_act_atr=1.0, be_atr=1.0, be_buf_atr=0.2,
    )


def test_atr_break_even_protects_a_wide_stop_trade():
    m = _mgr_atr("PE")
    assert m.on_index_price(76890.0) == ("STOP_MOVED", m.option_stop)   # +110 pts >= 1 ATR
    assert m.stop_index == pytest.approx(77000 - 20)       # entry - 0.2 ATR (in profit)
    # a retrace now exits in profit instead of riding to the 500-pt stop
    action = m.on_index_price(76985.0)
    assert action is not None and action[0] == "EXIT"


def test_atr_trail_arms_before_1r_and_never_loosens():
    m = _mgr_atr("CE")
    m.on_index_price(77400.0)                              # +4 ATR, only 0.8R
    assert m.stop_index == pytest.approx(77400 - 2.5 * 100)   # trail beats BE stop
    s = m.stop_index
    m.on_index_price(77300.0)
    assert m.stop_index == s


# ── restart recovery ──────────────────────────────────────────────────────────

def _fire_tick_short(eng, candles):
    """Force a tick-fired PE breakout that completed bars cannot reproduce."""
    eng.pos, eng.se = 0, True
    eng.lprice = candles[-1].close - 50
    eng.hprice = candles[-1].close + 300
    eng._ema_prev = candles[-1].close + 200
    ts = candles[-1].timestamp + timedelta(minutes=5)
    sig = eng.on_tick(eng.lprice - 5, eng.lprice + 20, ts)
    assert sig is not None
    return sig


def test_restart_restores_tick_fired_state_that_warm_up_cannot_rebuild():
    candles = _walk(400, 21)
    live = PineReversalEngine()
    live.warm_up(candles)
    _fire_tick_short(live, candles)
    snap = live.snapshot()

    plain = PineReversalEngine()
    plain.warm_up(candles)
    assert plain.pos != live.pos                         # the bug: warm_up alone rewinds the engine

    restarted = PineReversalEngine()
    restarted.warm_up(candles)
    assert restarted.restore(snap, candles) is True
    assert (restarted.pos, restarted.se, restarted.le, restarted.lprice, restarted.hprice) == \
           (live.pos, live.se, live.le, live.lprice, live.hprice)


def test_restore_rolls_forward_over_bars_closed_while_down():
    candles = _walk(420, 21)
    live = PineReversalEngine()
    live.warm_up(candles[:400])
    _fire_tick_short(live, candles[:400])
    snap = live.snapshot()
    for i in range(400, 420):                            # bars the live engine saw before it died
        live.on_bar_close(candles[: i + 1])
    restarted = PineReversalEngine()
    restarted.warm_up(candles)
    assert restarted.restore(snap, candles) is True
    assert (restarted.pos, restarted.se, restarted.le) == (live.pos, live.se, live.le)
    assert restarted.on_bar_close(candles) is None       # roll-forward is silent / already processed


def test_restore_rejects_previous_session_and_changed_settings():
    candles = _walk(400, 21)
    eng = PineReversalEngine()
    eng.warm_up(candles)
    snap = eng.snapshot()
    next_day = [Candle(c.timestamp + timedelta(days=1), c.open, c.high, c.low, c.close) for c in candles]
    other = PineReversalEngine()
    other.warm_up(next_day)
    assert other.restore(snap, next_day) is False        # stale session: keep warm_up's state
    assert PineReversalEngine(left=3).restore(snap, candles) is False   # different params
    assert other.restore({}, candles) is False
    assert other.restore({**snap, "last_ts": "garbage"}, candles) is False
    assert other.restore({k: v for k, v in snap.items() if k != "pos"}, candles) is False


def test_pine_gate_candle_color_and_rejection_wick(monkeypatch):
    from main import _pine_gate_reason, BotContext
    from strategies.pivot_reversal import PineSignal
    import config.settings as s

    monkeypatch.setattr(s, "PIVOT_NO_FRIDAY", False)
    monkeypatch.setattr(s, "PIVOT_NO_NEW_ENTRY_AFTER", "")
    monkeypatch.setattr(s, "PIVOT_PINE_SKIP_LULLS", False)
    monkeypatch.setattr(s, "PIVOT_PINE_MAX_CHASE_ATR", 0.0)
    monkeypatch.setattr(s, "PIVOT_PINE_MAX_RISK_ATR", 0.0)
    import main
    monkeypatch.setattr(main, "pivot_day_cap_reason", lambda day, und: None)
    monkeypatch.setattr(main, "side_block_reason", lambda side, day, und: None)

    ctx = BotContext.__new__(BotContext)
    ctx.underlying = "SENSEX"
    from market.candle_aggregator import CandleAggregator
    ctx.agg_5m = CandleAggregator(5)

    ts = datetime(2026, 11, 12, 12, 15)
    # Green hammer candle: Open=100, High=105, Low=70, Close=102
    # lower_wick = 30, range = 35 -> wick_pct = 85.7%
    hammer = Candle(ts, 100, 105, 70, 102)
    ctx.agg_5m.seed([hammer])

    sig_pe = PineSignal(
        side="PE", bar_ts=ts, entry=100.0, stop=120.0,
        risk=20.0, atr=20.0, level=100.0, source="tick",
    )

    # 1. Require candle color: PE on green candle should be blocked
    monkeypatch.setattr(s, "PIVOT_PINE_REQUIRE_CANDLE_COLOR", True)
    monkeypatch.setattr(s, "PIVOT_PINE_MAX_REJECTION_WICK_PCT", 0.0)
    monkeypatch.setattr(s, "PIVOT_PINE_MAX_REJECTION_WICK_ATR", 0.0)
    reason = _pine_gate_reason(ctx, sig_pe, 98.0)
    assert reason is not None
    assert "candle not bearish" in reason

    # 2. Rejection wick pct: PE with 85.7% lower wick should be blocked if limit is 0.35
    monkeypatch.setattr(s, "PIVOT_PINE_REQUIRE_CANDLE_COLOR", False)
    monkeypatch.setattr(s, "PIVOT_PINE_MAX_REJECTION_WICK_PCT", 0.35)
    reason = _pine_gate_reason(ctx, sig_pe, 98.0)
    assert reason is not None
    assert "lower rejection wick" in reason

    # 3. Rejection wick ATR: lower wick is 30 pts, ATR is 20 pts (1.5x ATR). Blocked if limit is 0.5x ATR
    monkeypatch.setattr(s, "PIVOT_PINE_MAX_REJECTION_WICK_PCT", 0.0)
    monkeypatch.setattr(s, "PIVOT_PINE_MAX_REJECTION_WICK_ATR", 0.5)
    reason = _pine_gate_reason(ctx, sig_pe, 98.0)
    assert reason is not None
    assert "lower rejection wick" in reason

    # 4. When all guards pass / disabled
    monkeypatch.setattr(s, "PIVOT_PINE_REQUIRE_CANDLE_COLOR", False)
    monkeypatch.setattr(s, "PIVOT_PINE_MAX_REJECTION_WICK_PCT", 0.0)
    monkeypatch.setattr(s, "PIVOT_PINE_MAX_REJECTION_WICK_ATR", 0.0)
    assert _pine_gate_reason(ctx, sig_pe, 98.0) is None
