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
    day = None
    for i, c in enumerate(candles):
        if day is not None and c.timestamp.date() != day:
            pos, sl, t2 = 0, None, None     # new session starts flat; swing levels carry
        day = c.timestamp.date()
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


def test_new_session_starts_flat_but_keeps_yesterdays_swing_levels():
    """day_reset=True: a virtual short left open overnight must not block the next day's first break."""
    candles = _walk(300, 21)
    eng = PineReversalEngine(day_reset=True)
    eng.warm_up(candles)
    eng.pos, eng.v_sl, eng.v_t2 = -1, 1e9, -1e9          # stale short: stop/T2 never hit
    eng.se, eng.lprice = True, candles[-1].close - 40
    eng.hprice, eng._ema_prev = candles[-1].close + 300, candles[-1].close + 200
    same_day = candles[-1].timestamp
    assert eng.on_tick(eng.lprice - 5, eng.lprice + 20, same_day) is None   # same session: blocked
    nxt = same_day + timedelta(days=1)
    sig = eng.on_tick(eng.lprice - 5, eng.lprice + 20, nxt)
    assert sig is not None and sig.side == "PE" and sig.level == eng.lprice  # next session: fires
    assert eng.hprice == candles[-1].close + 300                              # levels carried


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
    before = (eng.pos, eng.le, eng.se, eng.v_sl, eng.v_t2)
    sig = eng.on_tick(eng.lprice - 5, eng.lprice + 20, ts)
    assert sig is not None and sig.side == "PE" and sig.source == "TICK"
    assert sig.entry == pytest.approx(eng.lprice, abs=0.01)   # min(open, level) = level
    assert (eng.pos, eng.le, eng.se, eng.v_sl, eng.v_t2) == before   # a tick PREVIEW never commits Pine state
    assert eng.on_tick(eng.lprice - 10, eng.lprice + 20, ts) is None   # one preview per level per bar


def test_tick_trigger_respects_ema_filter():
    eng, candles = _armed_engine()
    eng.pos = 0
    eng.se = True
    eng.lprice = candles[-1].close - 50
    eng.hprice = candles[-1].close + 300
    eng._ema_prev = candles[-1].close - 500      # price far ABOVE EMA -> no short
    ts = candles[-1].timestamp + timedelta(minutes=5)
    assert eng.on_tick(eng.lprice - 5, eng.lprice + 20, ts) is None

def _short_swing():
    """Engine in a live PE swing (pos -1, stop above) with a downward EMA context."""
    eng, candles = _armed_engine()
    eng.pos = 0
    eng.se = True
    eng.lprice = candles[-1].close - 50
    eng.hprice = candles[-1].close + 300
    eng._ema_prev = candles[-1].close + 200
    ts = candles[-1].timestamp + timedelta(minutes=5)
    sig = eng.on_tick(eng.lprice - 5, eng.lprice + 20, ts)
    assert sig.side == "PE"
    eng._open("PE", sig.entry, sig.level, eng._atr_prev, ts, "BAR_CLOSE")   # the bar close commits it
    return eng, sig, ts


def test_reentry_fires_once_per_side_inside_live_swing():
    eng, sig, ts = _short_swing()
    best = sig.entry - 100                       # trade ran 100 pts, exited on the floor
    assert eng.arm_reentry("PE", best)
    assert eng.pos == -1 and eng.se is False     # Pine's own state is untouched
    assert eng.on_reentry_tick(best + 20, ts) is None       # pulled back: wait
    re = eng.on_reentry_tick(best - 5, ts)                   # new low past the best
    assert re is not None and re.side == "PE" and re.source == "REENTRY"
    assert re.stop == sig.stop
    assert eng.on_reentry_tick(best - 9, ts) is None         # one attempt per 5m bar
    eng.confirm_reentry()
    assert not eng.arm_reentry("PE", best - 50)              # only ONE re-entry per side/swing


def test_reentry_cancelled_when_pine_stop_hit_or_direction_flips():
    eng, sig, ts = _short_swing()
    best = sig.entry - 100
    eng.arm_reentry("PE", best)
    assert eng.on_reentry_tick(sig.stop + 5, ts) is None     # above Pine stop: swing over
    assert eng.reentry is None
    eng, sig, ts = _short_swing()
    eng.arm_reentry("PE", sig.entry - 100)
    eng._ema_prev = 0.0                                      # price now above EMA: shorts disallowed
    assert eng.on_reentry_tick(sig.entry - 105, ts) is None


def test_reentry_not_armed_after_swing_ended_and_fresh_signal_resets_allowance():
    eng, sig, ts = _short_swing()
    eng.pos = 0                                              # Pine stop/T2 already ended the swing
    assert not eng.arm_reentry("PE", sig.entry - 100)
    eng, sig, ts = _short_swing()
    eng.arm_reentry("PE", sig.entry - 100)
    eng.confirm_reentry()
    assert eng._re_used["PE"]
    eng.pos, eng.se = 0, True                                # new TradingView signal = new swing
    eng.lprice = sig.entry - 400
    eng._open("PE", eng.lprice, eng.lprice, eng._atr_prev, ts, "BAR_CLOSE")
    assert eng._re_used["PE"] is False


def test_reentry_state_survives_snapshot_restore():
    eng, sig, ts = _short_swing()
    eng.arm_reentry("PE", sig.entry - 100)
    snap = eng.snapshot()
    assert snap["reentry"]["side"] == "PE" and snap["re_used"] == {"CE": False, "PE": False}


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

# ── pivot-grid floor lock ─────────────────────────────────────────────────────

from market.historical_data import compute_pivot_levels
from strategies.pivot_reversal import grid_targets


def _grid_mgr(side="PE", exit_at=2, ladder=None):
    entry = 28165.0
    stop = entry + 107.0 if side == "PE" else entry - 107.0
    sgn = 1 if side == "CE" else -1
    t1, t2, t3 = entry + sgn * 120, entry + sgn * 205, entry + sgn * 340
    return PivotTradeManager(
        side, entry, stop, t1, t2, t3, 30.0, 260.0,
        delta=0.5, hard_sl_cushion=2.5, max_sl_pct=0.5, signal_risk=107.0,
        grid_mode=True, grid_exit_at=exit_at, grid_buffer=6.0, grid_levels=ladder,
    )


def test_grid_targets_pick_next_three_levels_in_trade_direction():
    lv = compute_pivot_levels(28350.95, 27994.75, 28195.0)       # fib grid
    t = grid_targets(lv, "PE", 28165.4, atr=31.6, min_gap_atr=0.5)
    assert t == (lv.s1, lv.s2, lv.s3)                            # P sits above a PE entry
    t = grid_targets(lv, "CE", 28015.73, atr=34.4, min_gap_atr=0.5)
    assert t == (lv.s1, lv.pivot, lv.r1)                         # S1 is 28 pts above entry -> kept
    assert grid_targets(lv, "CE", lv.r5, atr=30.0) is None       # no room left


def test_grid_stop_untouched_until_t1_then_flips_to_t1_minus_buffer():
    m = _grid_mgr("PE")
    assert m.on_index_price(28100.0) is None                     # +65: no BE, no trail
    assert m.stop_index == pytest.approx(28272.0)
    assert m.on_index_price(28045.0) == ("STOP_MOVED", m.option_stop)   # T1 (28045) touched
    assert m.stop_index == pytest.approx(28045.0 + 6.0) and m.stage == "T1"
    assert m.on_index_price(28048.0) is None                     # pullback that holds the 28051 floor
    assert m.on_index_price(28060.0) == ("EXIT", "PIVOT_TSL_HIT")  # through the floor -> out


def test_grid_pullback_through_floor_exits_and_target_two_exits_at_t2():
    m = _grid_mgr("PE")
    m.on_index_price(28040.0)
    assert m.on_index_price(28060.0) == ("EXIT", "PIVOT_TSL_HIT")
    m = _grid_mgr("PE")
    m.on_index_price(28040.0)
    assert m.on_index_price(27960.0) == ("EXIT", "PIVOT_TARGET_T2")
    m = _grid_mgr("CE")
    assert m.on_index_price(28165.0 + 205) == ("EXIT", "PIVOT_TARGET_T2")


def test_grid_exit_at_three_locks_t2_floor_and_exits_at_t3():
    m = _grid_mgr("CE", exit_at=3)
    m.on_index_price(28165.0 + 125)                              # T1
    assert m.stage == "T1" and m.stop_index == pytest.approx(28165.0 + 120 - 6.0)
    m.on_index_price(28165.0 + 210)                              # T2
    assert m.stage == "T2" and m.stop_index == pytest.approx(28165.0 + 205 - 6.0)
    assert m.on_index_price(28165.0 + 345) == ("EXIT", "PIVOT_TARGET_T3")


def test_grid_ladder_locks_every_level_with_no_hard_exit():
    e = 28165.0
    lad = [e - 120, e - 205, e - 340, e - 450]                    # PE: S1, S2, S3, S4
    m = _grid_mgr("PE", exit_at=0, ladder=lad)
    m.on_index_price(e - 125)                                     # clears L1
    assert m.stop_index == pytest.approx(e - 120 + 6.0)
    m.on_index_price(e - 210)                                     # clears L2 - no exit at T2
    assert m.stop_index == pytest.approx(e - 205 + 6.0)
    m.on_index_price(e - 345)                                     # clears L3 (T3) - still no exit
    assert m.stop_index == pytest.approx(e - 340 + 6.0)
    m.on_index_price(e - 455)                                     # clears L4 beyond T3
    assert m.stop_index == pytest.approx(e - 450 + 6.0)
    assert m.on_index_price(e - 430) == ("EXIT", "PIVOT_TSL_HIT")  # pullback through the floor


def test_grid_ladder_pullback_after_l2_exits_at_l2_floor():
    e = 28165.0
    lad = [e + 120, e + 205, e + 340]                             # CE
    m = _grid_mgr("CE", exit_at=0, ladder=lad)
    m.on_index_price(e + 210)                                     # L1 + L2 cleared in one jump
    assert m.stop_index == pytest.approx(e + 205 - 6.0)
    assert m.on_index_price(e + 195) == ("EXIT", "PIVOT_TSL_HIT")


def test_grid_initial_stop_still_exits_as_sl_hit():
    m = _grid_mgr("PE")
    assert m.on_index_price(28290.0) == ("EXIT", "PIVOT_SL_HIT")

def _grid_be_mgr(side="CE", pct=0.5):
    m = _grid_mgr(side, exit_at=0)
    m.grid_be_pct = pct
    return m


def test_grid_be_off_by_default_keeps_initial_stop():
    m = _grid_mgr("CE", exit_at=0)
    assert m.on_index_price(28165.0 + 100) is None                # 83% of the way to T1, no BE
    assert m.stop_index == pytest.approx(28165.0 - 107.0)


def test_grid_be_moves_stop_to_entry_at_half_way_to_t1():
    m = _grid_be_mgr("CE")                                         # T1 = entry + 120 -> trigger +60
    assert m.on_index_price(28165.0 + 59) is None
    assert m.on_index_price(28165.0 + 60) == ("STOP_MOVED", m.option_stop)
    assert m.stop_index == pytest.approx(28165.0) and m.stage == "BE"
    assert m.on_index_price(28165.0 - 5) == ("EXIT", "PIVOT_BE_STOP")


def test_grid_be_works_for_pe_and_then_level_floor_takes_over():
    e = 28165.0
    m = _grid_be_mgr("PE")
    m.on_index_price(e - 61)
    assert m.stop_index == pytest.approx(e) and m.stage == "BE"
    m.on_index_price(e - 125)                                      # T1 cleared -> T1 floor, higher than BE
    assert m.stop_index == pytest.approx(e - 120 + 6.0) and m.stage == "T1"


def test_grid_be_uses_best_price_not_current_price():
    m = _grid_be_mgr("CE")
    m.on_index_price(28165.0 + 70)                                 # BE armed on the spike
    assert m.stop_index == pytest.approx(28165.0)
    m.on_index_price(28165.0 + 20)                                 # pullback does not loosen it
    assert m.stop_index == pytest.approx(28165.0)


def test_grid_be_state_without_field_loads_as_off():
    m = _grid_mgr("CE")
    d = dict(m.__dict__)
    d.pop("grid_be_pct", None)
    obj = PivotTradeManager.__new__(PivotTradeManager)
    obj.__dict__.update(d)
    assert obj.grid_be_pct == 0.0






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
    eng._open("PE", sig.entry, sig.level, eng._atr_prev, ts, "BAR_CLOSE")   # committed at bar close
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

def _carry_setup(day_reset: bool):
    """Engine holding a live long from 'yesterday' with an armed CE level broken on the next session."""
    candles = _walk(300, 21)
    eng = PineReversalEngine(day_reset=day_reset)
    eng.warm_up(candles)
    last = candles[-1]
    eng.pos, eng.v_sl, eng.v_t1, eng.v_t2 = 1, last.close - 1e6, last.close + 1e6, last.close + 1e6
    eng.le, eng.hprice = True, last.close + 20
    eng.lprice = last.close - 400
    eng._ema_prev = last.close - 500                      # price above EMA -> longs allowed
    return eng, last, last.timestamp + timedelta(days=1)


def test_day_reset_false_carries_virtual_position_overnight_like_the_chart():
    eng, last, nxt = _carry_setup(day_reset=False)
    assert eng.on_tick(eng.hprice + 5, eng.hprice - 5, nxt) is None     # pos still long -> CE blocked
    assert eng.pos == 1 and eng.v_sl is not None
    # same data with the reset on would have fired the CE (phantom trade the chart never shows)
    eng2, _, nxt2 = _carry_setup(day_reset=True)
    sig = eng2.on_tick(eng2.hprice + 5, eng2.hprice - 5, nxt2)
    assert sig is not None and sig.side == "CE"


def test_armed_reentry_survives_overnight_when_day_reset_false():
    eng, last, nxt = _carry_setup(day_reset=False)
    best = last.close + 30                                # yesterday's trade peaked here, exited on its floor
    assert eng.arm_reentry("CE", best)
    assert eng.on_reentry_tick(best - 5, nxt) is None     # below yesterday's best: wait
    re = eng.on_reentry_tick(best + 5, nxt + timedelta(minutes=5))
    assert re is not None and re.side == "CE" and re.source == "REENTRY"
    # with the reset on, the armed re-entry is dropped at the session boundary
    eng2, last2, nxt2 = _carry_setup(day_reset=True)
    eng2.arm_reentry("CE", last2.close + 30)
    assert eng2.on_reentry_tick(last2.close + 35, nxt2) is None
    assert eng2.reentry is None


def test_restore_accepts_previous_session_snapshot_only_without_day_reset():
    candles = _walk(400, 21)
    eng = PineReversalEngine(day_reset=False)
    eng.warm_up(candles[:350])
    eng.pos, eng.v_sl, eng.v_t2 = 1, 1.0, 1e9
    snap = eng.snapshot()
    # same-session or not, a snapshot from the same candle set restores when the reset is off
    again = PineReversalEngine(day_reset=False)
    again.warm_up(candles)
    assert again.restore(snap, candles) is True
    assert snap["fp"] != PineReversalEngine(day_reset=True).snapshot()["fp"]   # setting change invalidates it




def test_pine_gate_blocks_entries_before_start_time(monkeypatch):
    import main
    import config.settings as s
    from main import _pine_gate_reason, BotContext
    from strategies.pivot_reversal import PineSignal

    monkeypatch.setattr(s, "PIVOT_NO_FRIDAY", False)
    monkeypatch.setattr(s, "PIVOT_NO_NEW_ENTRY_AFTER", "")
    monkeypatch.setattr(s, "PIVOT_PINE_SKIP_LULLS", False)
    monkeypatch.setattr(s, "PIVOT_PINE_MAX_CHASE_ATR", 0.0)
    monkeypatch.setattr(s, "PIVOT_PINE_MAX_RISK_ATR", 0.0)
    monkeypatch.setattr(s, "PIVOT_PINE_REQUIRE_CANDLE_COLOR", False)
    monkeypatch.setattr(s, "PIVOT_PINE_MAX_REJECTION_WICK_PCT", 0.0)
    monkeypatch.setattr(s, "PIVOT_PINE_MAX_REJECTION_WICK_ATR", 0.0)
    monkeypatch.setattr(main, "pivot_day_cap_reason", lambda day, und: None)
    monkeypatch.setattr(main, "side_block_reason", lambda side, day, und: None)
    ctx = BotContext.__new__(BotContext)
    ctx.underlying = "SENSEX"
    from market.candle_aggregator import CandleAggregator
    ctx.agg_5m = CandleAggregator(5)
    sig = PineSignal(side="CE", bar_ts=datetime(2026, 11, 19, 9, 15), entry=100.0, stop=80.0,
                     risk=20.0, atr=20.0, level=100.0, source="TICK")

    def _at(h, m):
        monkeypatch.setattr(main, "now_ist", lambda: datetime(2026, 11, 19, h, m, 30))

    monkeypatch.setattr(s, "PIVOT_NO_ENTRY_BEFORE", "09:20")
    _at(9, 15)
    assert _pine_gate_reason(ctx, sig, 100.0) == "before 09:20"
    _at(9, 19)
    assert _pine_gate_reason(ctx, sig, 100.0) == "before 09:20"
    _at(9, 20)
    assert _pine_gate_reason(ctx, sig, 100.0) is None
    monkeypatch.setattr(s, "PIVOT_NO_ENTRY_BEFORE", "")            # off -> no restriction
    _at(9, 15)
    assert _pine_gate_reason(ctx, sig, 100.0) is None


def test_pine_gate_candle_color_and_rejection_wick(monkeypatch):
    from main import _pine_gate_reason, BotContext
    from strategies.pivot_reversal import PineSignal
    import config.settings as s

    monkeypatch.setattr(s, "PIVOT_NO_ENTRY_BEFORE", "")
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


def _carry_engine(carry=True):
    eng, last, nxt = _carry_setup(day_reset=False)
    eng.carry = carry
    eng._pos_day = last.timestamp.date()
    eng._day = last.timestamp.date()
    eng._day_hi, eng._day_lo = last.close + 30, last.close - 80   # yesterday's range
    return eng, last, nxt


def test_carry_arms_one_continuation_entry_that_needs_a_break_of_yesterdays_extreme():
    eng, last, nxt = _carry_engine()
    eng.on_tick(last.close, last.close, nxt)                   # session roll
    assert eng.reentry and eng.reentry["carry"] and eng.reentry["side"] == "CE"
    assert eng.reentry["best"] == last.close + 30
    assert eng.on_reentry_tick(last.close + 10, nxt) is None   # not past yesterday's high: no continuation
    re = eng.on_reentry_tick(last.close + 35, nxt + timedelta(minutes=5))
    assert re is not None and re.side == "CE" and re.source == "REENTRY"
    eng.confirm_reentry()
    assert eng._re_used["CE"] is False                         # carry does not eat the in-swing re-entry


def test_carry_stays_unarmed_when_swing_is_over_or_carry_off():
    eng, last, nxt = _carry_engine()
    eng.pos = 0
    eng.on_tick(last.close, last.close, nxt)
    assert eng.reentry is None
    eng, last, nxt = _carry_engine(carry=False)
    eng.on_tick(last.close, last.close, nxt)
    assert eng.reentry is None


def test_carry_continuation_is_dropped_when_pine_stop_is_hit_or_ema_disagrees():
    eng, last, nxt = _carry_engine()
    eng.on_tick(last.close, last.close, nxt)
    eng.reentry["stop"] = last.close + 100                     # price already through the Pine stop -> swing over
    assert eng.on_reentry_tick(last.close + 35, nxt) is None and eng.reentry is None
    eng, last, nxt = _carry_engine()
    eng.on_tick(last.close, last.close, nxt)
    eng._ema_prev = last.close + 1000                          # price below EMA -> longs disallowed
    assert eng.on_reentry_tick(last.close + 35, nxt) is None


def test_todays_own_break_fires_while_bot_flat_even_though_yesterdays_swing_is_still_long():
    eng, last, nxt = _carry_engine()
    eng.bot_flat = True
    before = (eng.pos, eng.le, eng.v_sl, eng.v_t2)
    sig = eng.on_tick(eng.hprice + 5, eng.hprice - 5, nxt)
    assert sig is not None and sig.side == "CE" and sig.source == "RESIGNAL"
    assert (eng.pos, eng.le, eng.v_sl, eng.v_t2) == before     # Pine's own stop / T2 stay the chart's
    eng, last, nxt = _carry_engine()
    eng.bot_flat = False                                       # bot already holding: Pine rule applies
    assert eng.on_tick(eng.hprice + 5, eng.hprice - 5, nxt) is None


def test_same_session_swing_still_blocks_same_side_break_like_the_chart():
    eng, last, nxt = _carry_engine()
    eng.bot_flat = True
    eng._pos_day = nxt.date()                                  # position opened TODAY
    assert eng.on_tick(eng.hprice + 5, eng.hprice - 5, nxt) is None


def test_resignal_allows_same_session_same_side_break_when_bot_flat():
    eng, last, nxt = _carry_engine()
    eng.resignal = 'any'
    eng.bot_flat = True
    eng._pos_day = nxt.date()                                  # opened earlier TODAY, bot exited on its trail
    before = (eng.pos, eng.le, eng.v_sl, eng.v_t2)
    sig = eng.on_tick(eng.hprice + 5, eng.hprice - 5, nxt)
    assert sig is not None and sig.side == "CE" and sig.source == "RESIGNAL"
    assert (eng.pos, eng.le, eng.v_sl, eng.v_t2) == before     # chart state untouched by the extra entry
    eng.confirm_tick(sig)                                      # order filled -> this level is used up
    eng._tick_seen = set()
    assert eng.on_tick(eng.hprice + 8, eng.hprice - 5, nxt) is None
    eng, last, nxt = _carry_engine()
    eng.resignal, eng.bot_flat, eng._pos_day = 'any', False, nxt.date()
    assert eng.on_tick(eng.hprice + 5, eng.hprice - 5, nxt) is None   # bot holding a trade: blocked

def test_resignal_best_needs_a_break_past_the_previous_trades_best_price():
    eng, last, nxt = _carry_engine()
    eng.resignal, eng.bot_flat, eng._pos_day = 'best', True, nxt.date()
    px = eng.hprice + 5
    assert eng.on_tick(px, px - 10, nxt) is None               # no exit recorded yet -> blocked
    eng.note_exit("CE", px + 40)                               # previous trade peaked above this break
    assert eng.on_tick(px, px - 10, nxt) is None               # break is inside the old range -> chop, blocked
    eng.note_exit("CE", px - 20)                               # previous trade peaked below this break
    sig = eng.on_tick(px, px - 10, nxt)
    assert sig is not None and sig.side == "CE" and sig.source == "RESIGNAL"
    assert eng._last_best["CE"] == px - 20                     # Pine state untouched: best kept until a real new swing


def test_resignal_setting_values_are_normalised_and_off_by_default():
    n = PineReversalEngine.norm_resignal
    assert [n(v) for v in ("off", "best", "ANY", True, "true", "", None, "junk")] == \
        ["off", "best", "any", "any", "any", "off", "off", "off"]
    eng = PineReversalEngine()
    assert eng.resignal == "off" and eng.snapshot()["last_best"] == {"CE": None, "PE": None}


def test_unconfirmed_tick_preview_leaves_no_trace_when_bar_closes_without_a_signal():
    """The 20 Nov phantom: a gap tick below the swing low, bar closes ABOVE the EMA -> no chart signal."""
    eng, candles = _armed_engine()
    eng.pos, eng.se, eng.le = 0, True, False
    eng.lprice = candles[-1].close - 50
    eng.hprice = candles[-1].close + 300
    eng._ema_prev = candles[-1].close + 200                    # live price below EMA -> preview allowed
    ts = candles[-1].timestamp + timedelta(minutes=5)
    sig = eng.on_tick(eng.lprice - 5, eng.lprice + 20, ts)
    assert sig is not None and sig.side == "PE"
    c = candles[-1]
    wick = Candle(ts, c.close, c.close + 1500, eng.lprice - 5, c.close + 1000)   # pierces the level, closes far above EMA
    out = eng.on_bar_close(list(candles) + [wick])
    assert out is None and eng.pos == 0 and eng.se is True     # chart has no signal -> engine is untouched


def _short_break_setup():
    """Armed swing low sitting just above the real EMA; a bar that pierces it and closes below the EMA."""
    eng, candles = _armed_engine()
    ema0 = eng._ema_prev
    eng.pos, eng.se, eng.le = 0, True, False
    eng.lprice, eng.hprice = ema0 + 20, ema0 + 320
    ts = candles[-1].timestamp + timedelta(minutes=5)
    bar = Candle(ts, ema0 + 25, ema0 + 25, ema0 - 10, ema0 - 5)
    return eng, candles, bar, ts, ema0


def test_bar_close_commits_the_same_signal_and_never_double_trades_after_a_fill():
    eng, candles, bar, ts, ema0 = _short_break_setup()
    sig = eng.on_tick(ema0 - 2, eng.lprice + 5, ts)
    assert sig is not None and sig.source == "TICK" and sig.side == "PE"
    eng.confirm_tick(sig)                                       # the order went out on the tick
    assert eng.on_bar_close(list(candles) + [bar]) is None      # bar close does NOT trade it again ...
    assert eng.pos == -1 and eng.se is False                    # ... but Pine state is committed now

    eng2, candles2, bar2, ts2, _ = _short_break_setup()
    sig2 = eng2.on_bar_close(list(candles2) + [bar2])           # nothing was ordered on the tick
    assert sig2 is not None and sig2.side == "PE" and sig2.source == "BAR_CLOSE"
    assert eng2.pos == -1 and sig2.stop == sig.stop and sig2.entry == sig.entry


def test_snapshot_carries_extra_used_and_tick_taken():
    eng, last, nxt = _carry_engine()
    eng.bot_flat = True
    sig = eng.on_tick(eng.hprice + 5, eng.hprice - 5, nxt)
    eng.confirm_tick(sig)
    snap = eng.snapshot()
    assert snap["extra_used"] and snap["tick_taken"]
    assert snap["fp"] != PineReversalEngine(day_reset=False).snapshot()["fp"]
