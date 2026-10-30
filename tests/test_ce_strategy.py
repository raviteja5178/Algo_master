"""
Tests for the EMA 9/21 + RSI CE / PE entry rules.

CE: 15m Close > EMA9 > EMA21  AND  (5m EMA9 cross-up OR flat close on 5m EMA21)  AND  RSI > 55
PE: mirror image with RSI < 45.
"""

from __future__ import annotations

from datetime import datetime, date, timedelta

from market.candle_builder import Candle
from market.indicators import ema, rsi
from strategies.ce_strategy import is_ce_signal, is_global_trend_long
from strategies.pe_strategy import is_pe_signal, is_global_trend_short

_TODAY = date.today()
BASE_TIME = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 9, 15)


def _series(closes: list[float], step_min: int = 5, base: datetime = BASE_TIME) -> list[Candle]:
    out = []
    for i, c in enumerate(closes):
        out.append(Candle(base + timedelta(minutes=step_min * i), c, c + 1, c - 1, c))
    return out


def _uptrend_15m() -> list[Candle]:
    return _series([1000 + 5 * i for i in range(30)], step_min=15)


def _downtrend_15m() -> list[Candle]:
    return _series([1000 - 5 * i for i in range(30)], step_min=15)


def _ce_crossover_5m() -> list[Candle]:
    # Long rise (RSI high), small dip below EMA9, then a strong close back above EMA9.
    closes = [1000 + 4 * i for i in range(28)] + [1100, 1090, 1130]
    return _series(closes)


def _pe_crossover_5m() -> list[Candle]:
    closes = [1000 - 4 * i for i in range(28)] + [900, 910, 870]
    return _series(closes)


# ── Indicators ────────────────────────────────────────────────────────────────

class TestRSI:
    def test_all_gains_is_100(self):
        assert rsi([float(i) for i in range(20)], 14)[-1] == 100.0

    def test_all_losses_is_0(self):
        assert rsi([float(20 - i) for i in range(20)], 14)[-1] == 0.0

    def test_flat_is_50(self):
        assert rsi([10.0] * 20, 14)[-1] == 50.0

    def test_warmup_is_none(self):
        r = rsi([float(i) for i in range(20)], 14)
        assert r[13] is None and r[14] is not None


# ── 15m GLOBAL_TREND ──────────────────────────────────────────────────────────

class TestGlobalTrend:
    def test_long(self):
        assert is_global_trend_long(_uptrend_15m()) is True
        assert is_global_trend_short(_uptrend_15m()) is False

    def test_short(self):
        assert is_global_trend_short(_downtrend_15m()) is True
        assert is_global_trend_long(_downtrend_15m()) is False

    def test_no_trade_when_close_below_ema9_in_uptrend(self):
        c = _uptrend_15m()
        last = c[-1]
        c[-1] = Candle(last.timestamp, 1100, 1101, 1099, 1100)   # dip under EMA9, EMA9 still > EMA21
        assert is_global_trend_long(c) is False
        assert is_global_trend_short(c) is False

    def test_uses_ema21_not_ema20(self):
        import strategies.ce_strategy as ce, strategies.pe_strategy as pe
        assert ce.SLOW_EMA == 21 and pe.SLOW_EMA == 21


# ── CE ────────────────────────────────────────────────────────────────────────

class TestCEStrategy:
    def test_crossover_fires(self):
        c5 = _ce_crossover_5m()
        e9 = ema(c5, 9)
        assert c5[-2].close <= e9[-2] and c5[-1].close > e9[-1]   # sanity: real cross-up
        assert is_ce_signal(c5, _uptrend_15m()) is True

    def test_blocked_when_15m_not_long(self):
        assert is_ce_signal(_ce_crossover_5m(), _downtrend_15m()) is False

    def test_blocked_when_rsi_too_low(self):
        assert is_ce_signal(_ce_crossover_5m(), _uptrend_15m(), rsi_min=99.0) is False

    def test_no_trigger_without_cross_or_pullback(self):
        # Steady rise: always above EMA9 (no cross), far from EMA21 (no pullback).
        c5 = _series([1000 + 10 * i for i in range(30)])
        assert is_ce_signal(c5, _uptrend_15m(), pullback_tol_pts=1.0) is False

    def _make_pullback_series(self, dip_low_offset: float = 0.0) -> tuple:
        """
        Build a 29-candle series with a genuine EMA21 pullback.
        Returns (c5, e21_final).

        Structure:
          [0-26]  steady rise — warms up EMA9/21, establishes uptrend
          [27]    dip candle  — close above EMA9 (prev in strategy), low touches EMA21
          [28]    bounce candle — close just above EMA21 (within 10pts)

        dip_low_offset: add this to EMA21 for the dip low (0 = touches EMA21;
                        >0 = dip stays above EMA21, no genuine touch).
        """
        base_closes = [1000 + 10 * i for i in range(27)]
        c5_base = _series(base_closes)
        e9_base  = ema(c5_base, 9)
        e21_base = ema(c5_base, 21)
        e9_last  = e9_base[-1]
        e21_last = e21_base[-1]

        dip_close = e9_last + 5   # above EMA9 → condition 2 satisfied by default
        dip_low   = e21_last + dip_low_offset    # 0 → touches EMA21; >0 → stays above
        dip_ts    = BASE_TIME + timedelta(minutes=5 * 27)
        dip_candle = Candle(dip_ts, dip_close + 2, dip_close + 2, dip_low, dip_close)

        # Provisional bounce: use e21_last as anchor; refine after computing full EMA
        bounce_close_anchor = e21_last + 3
        bounce_ts = BASE_TIME + timedelta(minutes=5 * 28)
        bounce_candle = Candle(bounce_ts, bounce_close_anchor - 1,
                               bounce_close_anchor + 1, bounce_close_anchor - 1,
                               bounce_close_anchor)

        c5 = list(c5_base) + [dip_candle, bounce_candle]
        # Recompute EMA over full series and adjust bounce close to land on e21[-1]
        e21_full = ema(c5, 21)
        e21_final = e21_full[-1]
        # Set bounce close to e21_final + 3 (clearly within 10pts above EMA21)
        bounce_close = e21_final + 3
        c5[-1] = Candle(bounce_ts, bounce_close - 1, bounce_close + 1,
                        bounce_close - 1, bounce_close)
        return c5, e21_final

    def test_candle_falling_into_ema21_does_not_fire(self):
        # This series' last candle closes ~40 pts BELOW the prior close: it is
        # still falling from EMA9 to EMA21.  That is the dip, not the bounce,
        # so the pullback trigger must not fire (genuine bounces are covered in
        # test_strategy_review_fixes.TestEmaPullbackConfirmation).
        c5, _ = self._make_pullback_series()
        assert c5[-1].close < c5[-2].close
        assert is_ce_signal(c5, _uptrend_15m(), pullback_tol_pts=10.0) is False

    def test_pullback_blocked_when_prior_candle_did_not_dip_to_ema21(self):
        # Prior candle's low stays 20pts above EMA21 — no genuine touch of the level.
        c5, _ = self._make_pullback_series(dip_low_offset=20.0)
        assert is_ce_signal(c5, _uptrend_15m(), pullback_tol_pts=10.0) is False

    def test_pullback_blocked_when_prior_candle_was_below_ema9(self):
        # The dip candle (prev in the strategy = c5[-2]) must close ABOVE EMA9 for a
        # valid pullback (condition 2).  Force it to close BELOW EMA9 and confirm block.
        # We build the series normally, then mutate the dip candle's close to below EMA9.
        c5, _ = self._make_pullback_series()
        e9_full = ema(c5, 9)
        # Move dip candle close to 5pts below EMA9[-2] so condition 2 fails
        dip = c5[-2]
        e9_prev = e9_full[-2]
        c5[-2] = Candle(dip.timestamp, dip.open, dip.high, dip.low, e9_prev - 5)
        assert is_ce_signal(c5, _uptrend_15m(), pullback_tol_pts=10.0) is False

    def test_insufficient_candles(self):
        assert is_ce_signal(_series([1000.0] * 10), _series([1000.0] * 10, 15)) is False

    def test_false_on_yesterday_candle(self):
        c5 = _ce_crossover_5m()
        y = _TODAY - timedelta(days=1)
        last = c5[-1]
        c5[-1] = Candle(datetime(y.year, y.month, y.day, 10, 0), last.open, last.high, last.low, last.close)
        assert is_ce_signal(c5, _uptrend_15m()) is False


# ── EMA9 x EMA21 cross trigger (opt-in) ──────────────────────────────────────

def _ce_ema_cross_5m() -> list[Candle]:
    # Fall, then a steady rise: EMA9 crosses above EMA21 on the last candle while the
    # close stays above EMA9 (so the close-vs-EMA9 crossover does NOT fire).
    closes = [1100 - 5 * i for i in range(22)]
    closes += [closes[-1] + 6 * (i + 1) for i in range(11)]
    return _series(closes)


def _pe_ema_cross_5m() -> list[Candle]:
    closes = [1000 + 5 * i for i in range(22)]
    closes += [closes[-1] - 6 * (i + 1) for i in range(11)]
    return _series(closes)


class TestEmaCrossTrigger:
    def test_ce_series_is_a_real_ema_cross_only(self):
        c5 = _ce_ema_cross_5m()
        e9, e21 = ema(c5, 9), ema(c5, 21)
        assert e9[-2] <= e21[-2] and e9[-1] > e21[-1]
        assert not (c5[-2].close <= e9[-2] and c5[-1].close > e9[-1])

    def test_ce_off_by_default(self):
        assert is_ce_signal(_ce_ema_cross_5m(), _uptrend_15m()) is False

    def test_ce_fires_when_enabled(self):
        assert is_ce_signal(_ce_ema_cross_5m(), _uptrend_15m(), ema_cross=True) is True

    def test_ce_still_needs_15m_trend_and_rsi(self):
        assert is_ce_signal(_ce_ema_cross_5m(), _downtrend_15m(), ema_cross=True) is False
        assert is_ce_signal(_ce_ema_cross_5m(), _uptrend_15m(), rsi_min=99.0, ema_cross=True) is False

    def test_pe_series_is_a_real_ema_cross_only(self):
        c5 = _pe_ema_cross_5m()
        e9, e21 = ema(c5, 9), ema(c5, 21)
        assert e9[-2] >= e21[-2] and e9[-1] < e21[-1]
        assert not (c5[-2].close >= e9[-2] and c5[-1].close < e9[-1])

    def test_pe_off_by_default(self):
        assert is_pe_signal(_pe_ema_cross_5m(), _downtrend_15m()) is False

    def test_pe_fires_when_enabled(self):
        assert is_pe_signal(_pe_ema_cross_5m(), _downtrend_15m(), ema_cross=True) is True

    def test_pe_still_needs_15m_trend_and_rsi(self):
        assert is_pe_signal(_pe_ema_cross_5m(), _uptrend_15m(), ema_cross=True) is False
        assert is_pe_signal(_pe_ema_cross_5m(), _downtrend_15m(), rsi_max=1.0, ema_cross=True) is False

    def test_cross_ignores_15m_only_when_opted_in(self):
        assert is_ce_signal(_ce_ema_cross_5m(), _downtrend_15m(), ema_cross=True,
                            cross_without_15m=True) is True
        assert is_pe_signal(_pe_ema_cross_5m(), _uptrend_15m(), ema_cross=True,
                            cross_without_15m=True) is True
        # still RSI-gated, and a plain crossover (no EMA cross) still needs the 15m trend
        assert is_ce_signal(_ce_ema_cross_5m(), _downtrend_15m(), rsi_min=99.0, ema_cross=True,
                            cross_without_15m=True) is False
        assert is_ce_signal(_ce_crossover_5m(), _downtrend_15m(), ema_cross=True,
                            cross_without_15m=True) is False
        assert is_ce_signal(_ce_ema_cross_5m(), _downtrend_15m(), cross_without_15m=True) is False

    def test_cross_only_disables_other_triggers(self):
        # plain close-vs-EMA9 crossover fires by default but not with cross_only
        assert is_ce_signal(_ce_crossover_5m(), _uptrend_15m()) is True
        assert is_ce_signal(_ce_crossover_5m(), _uptrend_15m(), cross_only=True) is False
        assert is_pe_signal(_pe_crossover_5m(), _downtrend_15m()) is True
        assert is_pe_signal(_pe_crossover_5m(), _downtrend_15m(), cross_only=True) is False

    def test_cross_only_fires_on_ema_cross_with_confirmation(self):
        assert is_ce_signal(_ce_ema_cross_5m(), _uptrend_15m(), cross_only=True) is True
        assert is_pe_signal(_pe_ema_cross_5m(), _downtrend_15m(), cross_only=True) is True
        # confirmation still applies: 15m trend and RSI
        assert is_ce_signal(_ce_ema_cross_5m(), _downtrend_15m(), cross_only=True) is False
        assert is_ce_signal(_ce_ema_cross_5m(), _uptrend_15m(), rsi_min=99.0, cross_only=True) is False
        assert is_ce_signal(_ce_ema_cross_5m(), _downtrend_15m(), cross_only=True,
                            cross_without_15m=True) is True

# ── Signal-candle colour requirement (opt-in) ────────────────────────────────

def _with_last_open(c5: list[Candle], open_: float) -> list[Candle]:
    last = c5[-1]
    return c5[:-1] + [Candle(last.timestamp, open_, last.high, last.low, last.close)]


class TestRequireCandleColor:
    def test_ce_needs_green_signal_candle(self):
        for base in (_ce_crossover_5m(), _ce_ema_cross_5m()):
            kw = dict(ema_cross=True, require_candle_color=True)
            green = _with_last_open(base, base[-1].close - 3)
            red = _with_last_open(base, base[-1].close + 3)
            assert is_ce_signal(green, _uptrend_15m(), **kw) is True
            assert is_ce_signal(red, _uptrend_15m(), **kw) is False
            assert is_ce_signal(base, _uptrend_15m(), **kw) is False        # doji is not bullish
            # off by default: the colour is ignored
            assert is_ce_signal(red, _uptrend_15m(), ema_cross=True) is True

    def test_pe_needs_red_signal_candle(self):
        for base in (_pe_crossover_5m(), _pe_ema_cross_5m()):
            kw = dict(ema_cross=True, require_candle_color=True)
            red = _with_last_open(base, base[-1].close + 3)
            green = _with_last_open(base, base[-1].close - 3)
            assert is_pe_signal(red, _downtrend_15m(), **kw) is True
            assert is_pe_signal(green, _downtrend_15m(), **kw) is False
            assert is_pe_signal(base, _downtrend_15m(), **kw) is False
            assert is_pe_signal(green, _downtrend_15m(), ema_cross=True) is True

    def test_min_body_atr_blocks_small_bodies(self):
        # test candles have high/low = close +/- 1, so ATR is small; a 3-pt body clears 0.35 x ATR
        # only when ATR is small enough.  Use a wide ratio to force a block and a tiny one to pass.
        for base, fn, trend, sign in (
            (_ce_crossover_5m(), is_ce_signal, _uptrend_15m(), -1),
            (_pe_crossover_5m(), is_pe_signal, _downtrend_15m(), +1),
        ):
            sig = _with_last_open(base, base[-1].close + sign * 3)
            assert fn(sig, trend) is True                                  # off by default
            assert fn(sig, trend, min_body_atr=0.01) is True                # tiny threshold passes
            assert fn(sig, trend, min_body_atr=50.0) is False               # huge threshold blocks
            # applies to every trigger, including the EMA9xEMA21 cross
        ce_cross = _with_last_open(_ce_ema_cross_5m(), _ce_ema_cross_5m()[-1].close - 3)
        pe_cross = _with_last_open(_pe_ema_cross_5m(), _pe_ema_cross_5m()[-1].close + 3)
        assert is_ce_signal(ce_cross, _uptrend_15m(), ema_cross=True, min_body_atr=50.0) is False
        assert is_pe_signal(pe_cross, _downtrend_15m(), ema_cross=True, min_body_atr=50.0) is False
        assert is_ce_signal(ce_cross, _uptrend_15m(), ema_cross=True, min_body_atr=0.01) is True
        assert is_pe_signal(pe_cross, _downtrend_15m(), ema_cross=True, min_body_atr=0.01) is True







# ── PE ────────────────────────────────────────────────────────────────────────

class TestPEStrategy:
    def test_crossover_fires(self):
        c5 = _pe_crossover_5m()
        e9 = ema(c5, 9)
        assert c5[-2].close >= e9[-2] and c5[-1].close < e9[-1]
        assert is_pe_signal(c5, _downtrend_15m()) is True

    def test_blocked_when_15m_not_short(self):
        assert is_pe_signal(_pe_crossover_5m(), _uptrend_15m()) is False

    def test_blocked_when_rsi_too_high(self):
        assert is_pe_signal(_pe_crossover_5m(), _downtrend_15m(), rsi_max=1.0) is False

    def test_no_trigger_without_cross_or_pullback(self):
        c5 = _series([1000 - 10 * i for i in range(30)])
        assert is_pe_signal(c5, _downtrend_15m(), pullback_tol_pts=1.0) is False

    def test_insufficient_candles(self):
        assert is_pe_signal(_series([1000.0] * 20), _series([1000.0] * 20, 15)) is False

    def test_false_on_yesterday_candle(self):
        c5 = _pe_crossover_5m()
        y = _TODAY - timedelta(days=1)
        last = c5[-1]
        c5[-1] = Candle(datetime(y.year, y.month, y.day, 10, 0), last.open, last.high, last.low, last.close)
        assert is_pe_signal(c5, _downtrend_15m()) is False


# ── Expiry-day rollover ───────────────────────────────────────────────────────

class TestExpiryRollover:
    def _run(self, hhmm: str, rollover: str = "12:30"):
        from unittest.mock import patch
        import broker.instrument_repository as repo
        today = date.today()
        nxt = today + timedelta(days=7)
        inst = [
            {"name": "SENSEX", "segment": "BFO-OPT", "expiry": today.isoformat()},
            {"name": "SENSEX", "segment": "BFO-OPT", "expiry": nxt.isoformat()},
        ]
        h, m = map(int, hhmm.split(":"))
        fake_now = datetime(today.year, today.month, today.day, h, m)
        with patch.object(repo, "load_instruments", return_value=inst), \
             patch.object(repo.settings, "EXPIRY_MODE", "AUTO"), \
             patch.object(repo.settings, "UNDERLYING", "SENSEX"), \
             patch.object(repo.settings, "EXPIRY_DAY_ROLLOVER_TIME", rollover), \
             patch("utils.time_utils.now_ist", return_value=fake_now):
            return repo.resolve_expiry(), today, nxt

    def test_before_cutoff_uses_current_expiry(self):
        got, today, _ = self._run("12:29")
        assert got == today

    def test_after_cutoff_rolls_to_next(self):
        got, _, nxt = self._run("12:30")
        assert got == nxt

    def test_disabled(self):
        got, today, _ = self._run("14:00", rollover="")
        assert got == today
