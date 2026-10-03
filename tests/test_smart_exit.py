"""Tests for SmartExitEngine."""
import pytest
from unittest.mock import patch
from execution.smart_exit import SmartExitEngine


# ── factory helpers ───────────────────────────────────────────────────────────

def _engine(
    profit_lock_multiplier=2.0,
    time_decay_after="14:45",
    time_decay_min_pnl_pts=20.0,
    daily_loss_limit_pts=200.0,
    enable_reversal_exit=True,
    enable_ema_collapse=True,
    enable_profit_lock=True,
    enable_time_decay=True,
    enable_daily_loss_limit=True,
):
    return SmartExitEngine(
        profit_lock_multiplier=profit_lock_multiplier,
        time_decay_after=time_decay_after,
        time_decay_min_pnl_pts=time_decay_min_pnl_pts,
        daily_loss_limit_pts=daily_loss_limit_pts,
        enable_reversal_exit=enable_reversal_exit,
        enable_ema_collapse=enable_ema_collapse,
        enable_profit_lock=enable_profit_lock,
        enable_time_decay=enable_time_decay,
        enable_daily_loss_limit=enable_daily_loss_limit,
    )


def _only_profit_lock():
    """Engine with every trigger disabled except profit_lock."""
    return _engine(
        enable_reversal_exit=False, enable_ema_collapse=False,
        enable_profit_lock=True, enable_time_decay=False,
        enable_daily_loss_limit=False,
    )


def _only_reversal():
    return _engine(
        enable_reversal_exit=True, enable_ema_collapse=False,
        enable_profit_lock=False, enable_time_decay=False,
        enable_daily_loss_limit=False,
    )


def _only_daily_loss():
    return _engine(
        enable_reversal_exit=False, enable_ema_collapse=False,
        enable_profit_lock=False, enable_time_decay=False,
        enable_daily_loss_limit=True, daily_loss_limit_pts=200.0,
    )


# ── check_on_tick: reversal signal ────────────────────────────────────────────

class TestReversalSignal:

    def test_ce_exits_on_pe_signal(self):
        eng = _only_reversal()
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=210.0,
            qty=1, daily_realised_pnl_pts=0.0, pending_signal="PE",
        )
        assert result == "REVERSAL_SIGNAL"

    def test_pe_exits_on_ce_signal(self):
        eng = _only_reversal()
        result = eng.check_on_tick(
            strategy_type="PE", entry_price=200.0, option_ltp=190.0,
            qty=1, daily_realised_pnl_pts=0.0, pending_signal="CE",
        )
        assert result == "REVERSAL_SIGNAL"

    def test_same_direction_signal_no_exit(self):
        eng = _only_reversal()
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=210.0,
            qty=1, daily_realised_pnl_pts=0.0, pending_signal="CE",
        )
        assert result is None

    def test_no_pending_signal_no_exit(self):
        eng = _only_reversal()
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=210.0,
            qty=1, daily_realised_pnl_pts=0.0, pending_signal=None,
        )
        assert result is None

    def test_disabled_reversal_no_exit(self):
        eng = _engine(
            enable_reversal_exit=False, enable_ema_collapse=False,
            enable_profit_lock=False, enable_time_decay=False,
            enable_daily_loss_limit=False,
        )
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=210.0,
            qty=1, daily_realised_pnl_pts=0.0, pending_signal="PE",
        )
        assert result is None


# ── check_on_tick: profit lock ────────────────────────────────────────────────

class TestProfitLock:

    def test_fires_when_ltp_reaches_multiplier(self):
        eng = _only_profit_lock()
        # 2× entry = 400 → ltp=400 should trigger
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=400.0,
            qty=1, daily_realised_pnl_pts=0.0,
        )
        assert result == "PROFIT_LOCK"

    def test_no_fire_below_threshold(self):
        eng = _only_profit_lock()
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=350.0,
            qty=1, daily_realised_pnl_pts=0.0,
        )
        assert result is None

    def test_does_not_fire_twice(self):
        """Once profit_locked=True, trigger should not fire again."""
        eng = _only_profit_lock()
        eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=400.0,
            qty=1, daily_realised_pnl_pts=0.0,
        )
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=500.0,
            qty=1, daily_realised_pnl_pts=0.0,
        )
        assert result is None  # already locked

    def test_reset_clears_lock(self):
        eng = _only_profit_lock()
        eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=400.0,
            qty=1, daily_realised_pnl_pts=0.0,
        )
        eng.reset()
        # After reset should fire again
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=400.0,
            qty=1, daily_realised_pnl_pts=0.0,
        )
        assert result == "PROFIT_LOCK"

    def test_disabled_profit_lock_no_exit(self):
        eng = _engine(
            enable_reversal_exit=False, enable_ema_collapse=False,
            enable_profit_lock=False, enable_time_decay=False,
            enable_daily_loss_limit=False,
        )
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=1000.0,
            qty=1, daily_realised_pnl_pts=0.0,
        )
        assert result is None


# ── check_on_tick: ATR-based dynamic profit lock ─────────────────────────────

class TestProfitLockATR:
    """
    ATR-based profit lock: threshold = entry + ATR × mult.
    When profit_lock_atr_mult > 0 it overrides profit_lock_multiplier.
    """

    def _atr_engine(self, atr_mult=1.0, fixed_mult=2.0):
        return SmartExitEngine(
            profit_lock_multiplier=fixed_mult,
            profit_lock_atr_mult=atr_mult,
            enable_reversal_exit=False, enable_ema_collapse=False,
            enable_profit_lock=True, enable_time_decay=False,
            enable_daily_loss_limit=False,
        )

    def test_fires_at_entry_plus_atr(self):
        # entry=200, ATR=50, mult=1.0 → threshold=250
        eng = self._atr_engine(atr_mult=1.0)
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=250.0,
            qty=1, daily_realised_pnl_pts=0.0, entry_atr=50.0,
        )
        assert result == "PROFIT_LOCK"

    def test_does_not_fire_below_atr_threshold(self):
        # entry=200, ATR=50, mult=1.0 → threshold=250; ltp=249 → no fire
        eng = self._atr_engine(atr_mult=1.0)
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=249.0,
            qty=1, daily_realised_pnl_pts=0.0, entry_atr=50.0,
        )
        assert result is None

    def test_atr_mult_overrides_fixed_mult(self):
        # fixed mult=2.0 would require 400; ATR mult=1.0 at ATR=50 → 250
        eng = self._atr_engine(atr_mult=1.0, fixed_mult=2.0)
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=255.0,
            qty=1, daily_realised_pnl_pts=0.0, entry_atr=50.0,
        )
        # Should fire because ATR threshold (250) is used, not fixed (400)
        assert result == "PROFIT_LOCK"

    def test_falls_back_to_fixed_when_atr_is_none(self):
        # ATR mult enabled but entry_atr=None → falls back to fixed mult=1.25
        eng = self._atr_engine(atr_mult=1.0, fixed_mult=1.25)
        # ltp=251 is above ATR threshold (250) but below fixed (200*1.25=250)
        # With no ATR, only fixed applies: 200*1.25=250 → 251 fires
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=251.0,
            qty=1, daily_realised_pnl_pts=0.0, entry_atr=None,
        )
        assert result == "PROFIT_LOCK"

    def test_falls_back_to_fixed_when_atr_mult_is_zero(self):
        # profit_lock_atr_mult=0 → ATR mode disabled, use fixed mult=2.0
        eng = SmartExitEngine(
            profit_lock_multiplier=2.0,
            profit_lock_atr_mult=0.0,
            enable_reversal_exit=False, enable_ema_collapse=False,
            enable_profit_lock=True, enable_time_decay=False,
            enable_daily_loss_limit=False,
        )
        # ltp=260 is above entry+ATR=250 but below 2× entry=400 → no fire
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=260.0,
            qty=1, daily_realised_pnl_pts=0.0, entry_atr=50.0,
        )
        assert result is None

    def test_real_world_sep23_scenario(self):
        # 23-Sep: entry=225.1, ATR=54.71 (from RISK_COMPUTED_PCT log)
        # mult=1.0 → threshold = 225.1 + 54.71 = 279.81
        # The ₹290 wick would have fired this
        eng = self._atr_engine(atr_mult=1.0)
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=225.1, option_ltp=280.0,
            qty=20, daily_realised_pnl_pts=0.0, entry_atr=54.71,
        )
        assert result == "PROFIT_LOCK"

    def test_does_not_fire_twice_atr_mode(self):
        eng = self._atr_engine(atr_mult=1.0)
        eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=250.0,
            qty=1, daily_realised_pnl_pts=0.0, entry_atr=50.0,
        )
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=300.0,
            qty=1, daily_realised_pnl_pts=0.0, entry_atr=50.0,
        )
        assert result is None  # already locked

    def test_reset_re_enables_atr_lock(self):
        eng = self._atr_engine(atr_mult=1.0)
        eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=250.0,
            qty=1, daily_realised_pnl_pts=0.0, entry_atr=50.0,
        )
        eng.reset()
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=250.0,
            qty=1, daily_realised_pnl_pts=0.0, entry_atr=50.0,
        )
        assert result == "PROFIT_LOCK"

    def test_atr_mult_scales_with_volatility(self):
        # High-volatility day: ATR=80 → threshold=280; fires at 281
        eng = self._atr_engine(atr_mult=1.0)
        high_vol = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=281.0,
            qty=1, daily_realised_pnl_pts=0.0, entry_atr=80.0,
        )
        # Low-volatility day: ATR=30 → threshold=230; same ltp=231 fires
        eng2 = self._atr_engine(atr_mult=1.0)
        low_vol = eng2.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=231.0,
            qty=1, daily_realised_pnl_pts=0.0, entry_atr=30.0,
        )
        assert high_vol == "PROFIT_LOCK"
        assert low_vol == "PROFIT_LOCK"


# ── check_on_tick: hybrid max(ATR, %) profit lock ────────────────────────────

class TestProfitLockMinPct:
    """
    PROFIT_LOCK_MIN_PCT: threshold = entry × (1 + pct).
    Final threshold = max(ATR-based, %-based) — whichever is larger.
    """

    def _hybrid(self, atr_mult=1.0, min_pct=0.5, fixed_mult=2.0):
        return SmartExitEngine(
            profit_lock_multiplier=fixed_mult,
            profit_lock_atr_mult=atr_mult,
            profit_lock_min_pct=min_pct,
            enable_reversal_exit=False, enable_ema_collapse=False,
            enable_profit_lock=True, enable_time_decay=False,
            enable_daily_loss_limit=False,
        )

    def test_pct_threshold_fires(self):
        # entry=520, pct=0.5 → threshold=780; ltp=780 fires
        eng = SmartExitEngine(
            profit_lock_min_pct=0.5,
            enable_reversal_exit=False, enable_ema_collapse=False,
            enable_profit_lock=True, enable_time_decay=False,
            enable_daily_loss_limit=False,
        )
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=520.0, option_ltp=780.0,
            qty=20, daily_realised_pnl_pts=0.0,
        )
        assert result == "PROFIT_LOCK"

    def test_pct_threshold_does_not_fire_below(self):
        # entry=520, pct=0.5 → threshold=780; ltp=779 → no fire
        eng = SmartExitEngine(
            profit_lock_min_pct=0.5,
            enable_reversal_exit=False, enable_ema_collapse=False,
            enable_profit_lock=True, enable_time_decay=False,
            enable_daily_loss_limit=False,
        )
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=520.0, option_ltp=779.0,
            qty=20, daily_realised_pnl_pts=0.0,
        )
        assert result is None

    def test_pct_wins_over_atr_on_high_premium(self):
        # entry=520, ATR=55 → ATR threshold=575; pct=0.5 → 780
        # max(575, 780) = 780 — pct wins
        eng = self._hybrid(atr_mult=1.0, min_pct=0.5)
        # ltp=650 is above ATR threshold (575) but below pct threshold (780)
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=520.0, option_ltp=650.0,
            qty=20, daily_realised_pnl_pts=0.0, entry_atr=55.0,
        )
        assert result is None   # pct threshold (780) not reached yet

    def test_pct_wins_fires_at_780(self):
        # Same as above but ltp=780 now → fires
        eng = self._hybrid(atr_mult=1.0, min_pct=0.5)
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=520.0, option_ltp=780.0,
            qty=20, daily_realised_pnl_pts=0.0, entry_atr=55.0,
        )
        assert result == "PROFIT_LOCK"

    def test_atr_wins_over_pct_on_low_premium(self):
        # entry=225, ATR=55 → ATR threshold=280; pct=0.5 → 337.5
        # max(280, 337.5) = 337.5 — pct wins on low premium too
        # but ATR wins when pct is smaller: pct=0.1 → 247.5; ATR=280
        eng = self._hybrid(atr_mult=1.0, min_pct=0.1)
        # ltp=260 is above pct (247.5) but below ATR (280) → no fire
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=225.0, option_ltp=260.0,
            qty=20, daily_realised_pnl_pts=0.0, entry_atr=55.0,
        )
        assert result is None

    def test_atr_wins_fires_at_280(self):
        # Same setup: ATR threshold=280, pct(0.1)=247.5 → max=280; fires at 280
        eng = self._hybrid(atr_mult=1.0, min_pct=0.1)
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=225.0, option_ltp=280.0,
            qty=20, daily_realised_pnl_pts=0.0, entry_atr=55.0,
        )
        assert result == "PROFIT_LOCK"

    def test_real_world_sep23_with_pct_floor(self):
        # Sep-23: entry=225.1, ATR=54.71
        # ATR threshold = 225.1 + 54.71 = 279.81
        # pct=0.5 threshold = 225.1 × 1.5 = 337.65  ← wins
        # The ₹290 wick would NOT fire (below 337.65)
        # TSL would handle it (as it did in reality)
        eng = self._hybrid(atr_mult=1.0, min_pct=0.5)
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=225.1, option_ltp=290.0,
            qty=20, daily_realised_pnl_pts=0.0, entry_atr=54.71,
        )
        assert result is None   # 290 < 337.65 → no lock

    def test_real_world_high_premium_520(self):
        # entry=520, ATR=60, pct=0.5
        # ATR threshold = 520 + 60 = 580
        # pct threshold = 520 × 1.5 = 780  ← wins
        # Fires when premium hits 780 on the way to 1050
        eng = self._hybrid(atr_mult=1.0, min_pct=0.5)
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=520.0, option_ltp=780.0,
            qty=20, daily_realised_pnl_pts=0.0, entry_atr=60.0,
        )
        assert result == "PROFIT_LOCK"

    def test_pct_disabled_falls_back_to_atr(self):
        # pct=0 → only ATR candidate → threshold=280
        eng = SmartExitEngine(
            profit_lock_atr_mult=1.0, profit_lock_min_pct=0.0,
            enable_reversal_exit=False, enable_ema_collapse=False,
            enable_profit_lock=True, enable_time_decay=False,
            enable_daily_loss_limit=False,
        )
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=225.0, option_ltp=280.0,
            qty=20, daily_realised_pnl_pts=0.0, entry_atr=55.0,
        )
        assert result == "PROFIT_LOCK"

    def test_both_disabled_falls_back_to_fixed_multiplier(self):
        # atr_mult=0, pct=0 → fixed mult=2.0 → threshold=450
        eng = SmartExitEngine(
            profit_lock_multiplier=2.0,
            profit_lock_atr_mult=0.0, profit_lock_min_pct=0.0,
            enable_reversal_exit=False, enable_ema_collapse=False,
            enable_profit_lock=True, enable_time_decay=False,
            enable_daily_loss_limit=False,
        )
        # ltp=400 below 450 → no fire
        assert eng.check_on_tick(
            strategy_type="CE", entry_price=225.0, option_ltp=400.0,
            qty=20, daily_realised_pnl_pts=0.0, entry_atr=55.0,
        ) is None
        # ltp=450 at threshold → fires
        eng2 = SmartExitEngine(
            profit_lock_multiplier=2.0,
            profit_lock_atr_mult=0.0, profit_lock_min_pct=0.0,
            enable_reversal_exit=False, enable_ema_collapse=False,
            enable_profit_lock=True, enable_time_decay=False,
            enable_daily_loss_limit=False,
        )
        assert eng2.check_on_tick(
            strategy_type="CE", entry_price=225.0, option_ltp=450.0,
            qty=20, daily_realised_pnl_pts=0.0, entry_atr=55.0,
        ) == "PROFIT_LOCK"


# ── check_on_tick: daily loss limit ──────────────────────────────────────────

class TestDailyLossLimitTick:

    def test_fires_when_loss_exceeds_limit(self):
        eng = _only_daily_loss()
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=190.0,
            qty=1, daily_realised_pnl_pts=-250.0,
        )
        assert result == "DAILY_LOSS_LIMIT"

    def test_no_fire_below_limit(self):
        eng = _only_daily_loss()
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=190.0,
            qty=1, daily_realised_pnl_pts=-100.0,
        )
        assert result is None

    def test_no_fire_positive_pnl(self):
        eng = _only_daily_loss()
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=220.0,
            qty=1, daily_realised_pnl_pts=50.0,
        )
        assert result is None


# ── is_daily_loss_limit_hit() ─────────────────────────────────────────────────

class TestIsDailyLossLimitHit:

    def test_returns_true_when_exceeded(self):
        eng = _engine(daily_loss_limit_pts=200.0)
        assert eng.is_daily_loss_limit_hit(-250.0) is True

    def test_returns_false_when_within_limit(self):
        eng = _engine(daily_loss_limit_pts=200.0)
        assert eng.is_daily_loss_limit_hit(-100.0) is False

    def test_returns_false_when_zero(self):
        eng = _engine(daily_loss_limit_pts=200.0)
        assert eng.is_daily_loss_limit_hit(0.0) is False

    def test_returns_false_when_disabled(self):
        eng = _engine(enable_daily_loss_limit=False, daily_loss_limit_pts=200.0)
        assert eng.is_daily_loss_limit_hit(-999.0) is False


# ── check_on_candle: EMA collapse ────────────────────────────────────────────

class TestEmaCollapse:
    """
    check_on_candle() computes EMA9/EMA21 from candle closes internally.
    We need real Candle objects with enough data (at least 21 candles so
    EMA21 seed + 1 RMA step can be computed).
    """

    def _candles_bullish(self, n=30, base=100.0):
        """Rising candles so EMA9 stays above EMA21."""
        from datetime import datetime
        from market.candle_builder import Candle
        candles = []
        for i in range(n):
            c = base + i * 0.5   # slow uptrend
            candles.append(Candle(
                timestamp=datetime(2026, 1, 1, 9, 15),
                open=c, high=c + 2, low=c - 2, close=c,
            ))
        return candles

    def _candles_bearish(self, n=30, base=100.0):
        """Falling candles so EMA9 drops below EMA21."""
        from datetime import datetime
        from market.candle_builder import Candle
        candles = []
        for i in range(n):
            c = base - i * 2.0   # sharp downtrend
            candles.append(Candle(
                timestamp=datetime(2026, 1, 1, 9, 15),
                open=c, high=c + 1, low=c - 1, close=c,
            ))
        return candles

    def test_ce_ema_collapse_fires_on_bearish_candles(self):
        eng = _engine(
            enable_reversal_exit=False, enable_profit_lock=False,
            enable_time_decay=False, enable_daily_loss_limit=False,
        )
        candles = self._candles_bearish(n=30)
        result = eng.check_on_candle("CE", candles_5m=candles, candles_15m=[])
        assert result == "EMA_COLLAPSE"

    def test_ce_no_collapse_on_bullish_candles(self):
        eng = _engine(
            enable_reversal_exit=False, enable_profit_lock=False,
            enable_time_decay=False, enable_daily_loss_limit=False,
        )
        candles = self._candles_bullish(n=30)
        result = eng.check_on_candle("CE", candles_5m=candles, candles_15m=[])
        assert result is None

    def test_pe_ema_collapse_fires_on_bullish_candles(self):
        eng = _engine(
            enable_reversal_exit=False, enable_profit_lock=False,
            enable_time_decay=False, enable_daily_loss_limit=False,
        )
        candles = self._candles_bullish(n=30)
        result = eng.check_on_candle("PE", candles_5m=candles, candles_15m=[])
        assert result == "EMA_COLLAPSE"

    def test_no_collapse_when_disabled(self):
        eng = _engine(
            enable_reversal_exit=False, enable_ema_collapse=False,
            enable_profit_lock=False, enable_time_decay=False,
            enable_daily_loss_limit=False,
        )
        candles = self._candles_bearish(n=30)
        result = eng.check_on_candle("CE", candles_5m=candles, candles_15m=[])
        assert result is None

    def test_no_collapse_with_fewer_than_21_candles(self):
        eng = _engine(
            enable_reversal_exit=False, enable_profit_lock=False,
            enable_time_decay=False, enable_daily_loss_limit=False,
        )
        candles = self._candles_bearish(n=15)  # fewer than required 21
        result = eng.check_on_candle("CE", candles_5m=candles, candles_15m=[])
        assert result is None


# ── reset() ───────────────────────────────────────────────────────────────────

class TestReset:

    def test_reset_does_not_crash(self):
        eng = _engine()
        eng.reset()  # should not raise

    def test_reset_clears_profit_locked_flag(self):
        eng = _only_profit_lock()
        eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=400.0,
            qty=1, daily_realised_pnl_pts=0.0,
        )
        eng.reset()
        # Profit-lock should fire again after reset
        result = eng.check_on_tick(
            strategy_type="CE", entry_price=200.0, option_ltp=400.0,
            qty=1, daily_realised_pnl_pts=0.0,
        )
        assert result == "PROFIT_LOCK"
