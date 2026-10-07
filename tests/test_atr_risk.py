"""Tests for ATR indicator and compute_risk_params()."""
import pytest
from datetime import datetime
from market.candle_builder import Candle
from market.indicators import atr, atr_at
from execution.atr_risk import compute_risk_params, RiskParams


# ── helpers ──────────────────────────────────────────────────────────────────

_TS = datetime(2026, 1, 1, 9, 15)


def _c(high, low, close):
    """Build a Candle with a fixed timestamp."""
    return Candle(timestamp=_TS, open=close, high=float(high), low=float(low), close=float(close))


def _flat(n=20, base=100.0, spread=10.0):
    """n identical candles: H=base+spread, L=base-spread, C=base."""
    return [_c(base + spread, base - spread, base) for _ in range(n)]


# ── atr() ─────────────────────────────────────────────────────────────────────

class TestAtrIndicator:

    def test_returns_none_list_when_too_few_candles(self):
        # atr() needs n >= period+1 candles; period=14 → need at least 15
        candles = _flat(n=5)
        result = atr(candles, period=14)
        assert all(v is None for v in result)

    def test_length_matches_input(self):
        candles = _flat(n=30)
        result = atr(candles, period=14)
        assert len(result) == 30

    def test_exactly_period_plus_one_candles_gives_one_value(self):
        """With exactly period+1=15 candles, only index 14 should be non-None."""
        candles = _flat(n=15, spread=10.0)
        result = atr(candles, period=14)
        # All except last should be None
        assert all(v is None for v in result[:-1])
        assert result[-1] is not None

    def test_first_period_entries_are_none(self):
        """Indices 0..period-1 should be None."""
        candles = _flat(n=30, spread=10.0)
        result = atr(candles, period=14)
        for i in range(14):
            assert result[i] is None, f"index {i} should be None"

    def test_flat_candles_atr_equals_spread_times_two(self):
        """All candles H=120, L=80 → TR=40 constantly → ATR=40."""
        candles = _flat(n=30, base=100.0, spread=20.0)
        result = atr(candles, period=14)
        last = result[-1]
        assert last is not None
        assert abs(last - 40.0) < 0.1

    def test_wilder_smoothing_rises_with_higher_volatility(self):
        """Start with spread=5, then switch to spread=30; ATR should increase."""
        low_vol  = _flat(n=20, spread=5.0)
        high_vol = _flat(n=15, spread=30.0)
        candles  = low_vol + high_vol
        result   = atr(candles, period=14)
        atr_mid  = result[19]   # end of low-vol phase
        atr_end  = result[-1]   # after high-vol phase
        assert atr_mid is not None
        assert atr_end is not None
        assert atr_end > atr_mid

    def test_period_one_returns_true_range(self):
        """
        ATR(period=1) needs 2 candles (period+1): prev + current.
        TR of current = max(high-low, |high-prev_close|, |low-prev_close|).
        prev: H=101,L=99,C=100 → current: H=110,L=90,C=100 → TR=20.
        """
        prev = _c(high=101, low=99, close=100)
        curr = _c(high=110, low=90,  close=100)
        result = atr([prev, curr], period=1)
        assert result[-1] is not None
        assert abs(result[-1] - 20.0) < 0.01

    def test_uses_previous_candle_for_gap_calculation(self):
        """
        prev_close=100, current H=105, L=103 → C=104.
        TR = max(2, 5, 3) = 5  (gap captured via abs(high-prev_close)).
        """
        prev   = _c(high=102, low=98, close=100)
        curr   = _c(high=105, low=103, close=104)
        result = atr([prev, curr], period=1)
        assert result[-1] is not None
        assert abs(result[-1] - 5.0) < 0.01


class TestAtrAt:

    def test_returns_none_for_empty(self):
        assert atr_at([], period=14) is None

    def test_returns_last_atr_value(self):
        candles = _flat(n=30, spread=10.0)
        val = atr_at(candles, period=14)
        assert val is not None
        assert abs(val - 20.0) < 0.1

    def test_returns_none_when_too_few(self):
        candles = _flat(n=5)
        assert atr_at(candles, period=14) is None


# ── compute_risk_params() ─────────────────────────────────────────────────────

class TestComputeRiskParams:

    def test_fallback_when_no_candles(self):
        """Empty candle list → ATR unavailable → fixed fallback."""
        params = compute_risk_params(
            candles_5m=[],
            use_spot_atr=False,   # disable Mode C so we hit fixed fallback
            fixed_sl=50.0, fixed_target=80.0, fixed_trail=15.0,
        )
        assert isinstance(params, RiskParams)
        assert params.initial_sl_points == 50.0
        assert params.initial_target_points == 80.0
        assert params.trail_step_points == 15.0
        assert params.atr_value is None

    def test_fallback_when_atr_unavailable(self):
        """Too few candles → ATR = None → fallback to fixed values."""
        candles = _flat(n=5)
        params = compute_risk_params(
            candles_5m=candles,
            use_spot_atr=False,   # force fixed path
            fixed_sl=50.0, fixed_target=80.0, fixed_trail=15.0,
        )
        assert params.atr_value is None
        assert params.initial_sl_points == 50.0
        assert params.initial_target_points == 80.0

    def test_mode_c_spot_atr_params_computed(self):
        """Mode C: SENSEX spot ATR-based params are returned."""
        candles = _flat(n=30, spread=10.0)   # ATR(5) ≈ 20 index pts
        params = compute_risk_params(
            candles_5m=candles,
            use_spot_atr=True,
            spot_atr_period=5,
            spot_sl_mult=2.5,
            target_rr=1.2,
            trail_rr=0.5,
            fixed_sl=50.0, fixed_target=80.0, fixed_trail=15.0,
        )
        assert params.atr_value is not None
        # SL = ATR × 2.5 × 0.4 (delta); must be at least min_sl floor
        assert params.initial_sl_points >= 20.0
        assert params.initial_target_points >= 30.0
        assert params.trail_step_points >= 5.0

    def test_mode_c_rr_matches_target_rr(self):
        """Mode C: target / SL ratio must equal target_rr (within floor tolerance)."""
        candles = _flat(n=30, spread=50.0)   # high ATR so floors don't dominate
        params = compute_risk_params(
            candles_5m=candles,
            use_spot_atr=True,
            spot_atr_period=5,
            spot_sl_mult=2.5,
            target_rr=1.2,
            trail_rr=0.5,
            min_sl_pts=0.0, min_target_pts=0.0, min_trail_pts=0.0,
        )
        rr = params.initial_target_points / params.initial_sl_points
        assert abs(rr - 1.2) < 0.05, f"R:R={rr:.2f}, expected ~1.2"

    def test_mode_c_sl_price_always_positive(self):
        """Mode C: SL price (entry - SL_pts) must always be > 0."""
        candles = _flat(n=30, spread=100.0)   # high ATR
        for entry in [100.0, 150.0, 200.0, 500.0]:
            params = compute_risk_params(
                candles_5m=candles,
                use_spot_atr=True,
                spot_atr_period=5,
                spot_sl_mult=2.5,
                entry_price=entry,
                max_sl_pct=0.35,
            )
            sl_price = entry - params.initial_sl_points
            assert sl_price > 0, f"SL price {sl_price} for entry={entry}"

    def test_mode_c_atr_based_params_computed(self):
        """Mode C: with sufficient candles ATR value is returned."""
        candles = _flat(n=30, spread=10.0)
        params = compute_risk_params(
            candles_5m=candles,
            use_spot_atr=True,
            spot_atr_period=5,
            fixed_sl=50.0, fixed_target=80.0, fixed_trail=15.0,
            entry_price=0.0,
        )
        assert params.atr_value is not None
        assert params.initial_sl_points >= 20.0
        assert params.initial_target_points >= 30.0
        assert params.trail_step_points >= 5.0

    def test_break_even_is_half_sl(self):
        """BE = 0.5 × SL in Mode C and fixed fallback."""
        candles = _flat(n=30, spread=50.0)
        # Mode C
        p_c = compute_risk_params(
            candles_5m=candles,
            use_spot_atr=True,
            spot_atr_period=5, spot_sl_mult=2.5, target_rr=1.2, trail_rr=0.5,
            min_sl_pts=0.0, min_target_pts=0.0, min_trail_pts=0.0,
            fixed_sl=50.0, fixed_target=80.0, fixed_trail=15.0,
        )
        assert abs(p_c.break_even_trigger_points - p_c.initial_sl_points * 0.5) < 0.1
        # Fixed fallback
        p_fixed = compute_risk_params(
            candles_5m=candles, use_spot_atr=False,
            fixed_sl=50.0, fixed_target=80.0, fixed_trail=15.0,
        )
        assert p_fixed.break_even_trigger_points <= p_fixed.initial_sl_points

    def test_min_sl_floor_applied(self):
        """Even with tiny ATR, SL must not fall below min_sl_pts."""
        candles = _flat(n=30, spread=1.0)   # tiny ATR
        p = compute_risk_params(
            candles_5m=candles,
            use_spot_atr=True,
            spot_atr_period=5, spot_sl_mult=2.5,
            min_sl_pts=20.0,
            fixed_sl=50.0, fixed_target=80.0, fixed_trail=15.0,
        )
        assert p.initial_sl_points >= 20.0

    def test_break_even_is_half_sl_in_fallback(self):
        """Fallback (no candles): BE = 0.5 × fixed_sl."""
        params = compute_risk_params(
            candles_5m=[],
            use_spot_atr=False,
            fixed_sl=60.0, fixed_target=90.0, fixed_trail=20.0,
        )
        assert params.break_even_trigger_points == 30.0

    def test_mode_c_sl_ceiling_prevents_negative_sl_price(self):
        """Mode C: volatile day — SL ceiling keeps SL price positive."""
        candles = _flat(n=30, spread=75.0)   # ATR≈150 → sl_pts = 150×2.5×0.4 = 150
        params = compute_risk_params(
            candles_5m=candles,
            use_spot_atr=True,
            spot_atr_period=5, spot_sl_mult=2.5,
            fixed_sl=50.0, fixed_target=80.0, fixed_trail=15.0,
            entry_price=200.0,
            max_sl_pct=0.35,
        )
        sl_price = 200.0 - params.initial_sl_points
        assert sl_price > 0, f"SL price {sl_price} must be positive"
        assert params.initial_sl_points <= 200.0 * 0.35



# ── swing_levels() ────────────────────────────────────────────────────────────

class TestSwingLevels:
    """Tests for the improved swing_levels() with reference_price support."""

    def _make_candles(self, prices: list[tuple[float, float, float]]) -> list:
        """Build candles from (high, low, close) tuples."""
        from market.candle_builder import Candle
        from datetime import datetime, timedelta
        base = datetime(2026, 1, 1, 9, 15)
        return [
            Candle(timestamp=base + timedelta(minutes=5 * i),
                   open=c, high=h, low=l, close=c)
            for i, (h, l, c) in enumerate(prices)
        ]

    def test_returns_none_none_when_too_few_candles(self):
        from market.indicators import swing_levels
        candles = self._make_candles([(110, 90, 100)] * 5)
        h, l = swing_levels(candles, length=10)
        assert h is None and l is None

    def test_legacy_mode_returns_most_recent_pivot(self):
        """Without reference_price, returns the most-recent pivot of each type."""
        from market.indicators import swing_levels
        # Build: flat base, then a clear pivot high, then back to flat
        base = [(100, 90, 95)] * 12
        # Pivot high at index 12: higher than next 10
        base += [(130, 90, 95)]    # spike
        base += [(100, 90, 95)] * 12  # confirmation
        candles = self._make_candles(base)
        h, l = swing_levels(candles, length=10, reference_price=None)
        assert h is not None
        assert h == 130.0

    def test_reference_price_returns_nearest_high_above(self):
        """With reference_price, swing_high is the NEAREST high ABOVE price."""
        from market.indicators import swing_levels
        # Build candles with two pivot highs: 110 and 140.
        # At reference_price=100, both are above — nearest is 110.
        # length=3 for simplicity
        data = (
            [(100, 80, 90)] * 4 +
            [(110, 80, 90)] +        # pivot high candidate 1
            [(100, 80, 90)] * 4 +
            [(140, 80, 90)] +        # pivot high candidate 2
            [(100, 80, 90)] * 4
        )
        candles = self._make_candles(data)
        h, l = swing_levels(candles, length=3, reference_price=100.0)
        assert h is not None
        assert h == 110.0  # nearest high above 100

    def test_reference_price_returns_nearest_low_below(self):
        """With reference_price, swing_low is the NEAREST low BELOW price."""
        from market.indicators import swing_levels
        # Two distinct pivot lows: 60 (further) and 83 (nearest to reference 100).
        # Use consistent base low=85 so the 60 and 83 spikes stand out clearly.
        data = (
            [(100, 85, 90)] * 4 +
            [(100, 60, 90)] +        # pivot low candidate 1 (low=60, further below 100)
            [(100, 85, 90)] * 4 +
            [(100, 83, 90)] +        # pivot low candidate 2 (low=83, nearest below 100)
            [(100, 85, 90)] * 4
        )
        candles = self._make_candles(data)
        h, l = swing_levels(candles, length=3, reference_price=100.0)
        assert l is not None
        assert l == 83.0  # nearest low below 100 (not 60)

    def test_no_high_above_returns_none(self):
        """If all pivot highs are below reference_price, swing_high is None."""
        from market.indicators import swing_levels
        data = (
            [(80, 60, 70)] * 4 +
            [(80, 60, 70)] +
            [(80, 60, 70)] * 4
        )
        candles = self._make_candles(data)
        # reference_price=200 → no pivot high above 200
        h, _ = swing_levels(candles, length=3, reference_price=200.0)
        assert h is None

    def test_no_low_below_returns_none(self):
        """If all pivot lows are above reference_price, swing_low is None."""
        from market.indicators import swing_levels
        data = (
            [(100, 80, 90)] * 4 +
            [(100, 80, 90)] +
            [(100, 80, 90)] * 4
        )
        candles = self._make_candles(data)
        # reference_price=50 → no pivot low below 50
        _, l = swing_levels(candles, length=3, reference_price=50.0)
        assert l is None


# ── Mode D (swing SL) in compute_risk_params() ────────────────────────────────

class TestModeDSwingSL:

    def _flat(self, n=20, base=100.0, spread=10.0):
        from market.candle_builder import Candle
        from datetime import datetime
        ts = datetime(2026, 1, 1, 9, 15)
        return [Candle(timestamp=ts, open=base, high=base + spread,
                       low=base - spread, close=base) for _ in range(n)]

    def test_mode_d_pe_uses_swing_high(self):
        """PE: SL = (swing_high − sensex_ltp) × 0.4."""
        candles = self._flat(n=20, spread=10.0)
        params = compute_risk_params(
            candles,
            use_swing_sl=True,
            use_spot_atr=False,
            option_type="PE",
            sensex_ltp=80_000.0,
            swing_high=80_100.0,   # 100 pts above → option SL = 100 × 0.4 = 40
            swing_low=None,
            min_sl_pts=20.0, min_target_pts=20.0, min_trail_pts=5.0,
            target_rr=1.5, trail_rr=0.5,
        )
        assert params.sl_mode == "swing_sl"
        assert abs(params.initial_sl_points - 40.0) < 0.5
        assert abs(params.initial_target_points - 60.0) < 1.0   # 40 × 1.5
        assert abs(params.trail_step_points - 20.0) < 0.5       # 40 × 0.5
        assert abs(params.break_even_trigger_points - 20.0) < 0.5  # 40 × 0.5

    def test_mode_d_ce_uses_swing_low(self):
        """CE: SL = (sensex_ltp − swing_low) × 0.4."""
        candles = self._flat(n=20, spread=10.0)
        params = compute_risk_params(
            candles,
            use_swing_sl=True,
            use_spot_atr=False,
            option_type="CE",
            sensex_ltp=80_000.0,
            swing_high=None,
            swing_low=79_850.0,    # 150 pts below → option SL = 150 × 0.4 = 60
            min_sl_pts=20.0, min_target_pts=20.0, min_trail_pts=5.0,
            target_rr=1.5, trail_rr=0.5,
        )
        assert params.sl_mode == "swing_sl"
        assert abs(params.initial_sl_points - 60.0) < 0.5
        assert abs(params.initial_target_points - 90.0) < 1.0   # 60 × 1.5

    def test_mode_d_fallback_to_mode_c_when_no_swing(self):
        """Mode D with no valid swing level → falls back to Mode C."""
        candles = self._flat(n=30, spread=10.0)
        params = compute_risk_params(
            candles,
            use_swing_sl=True,
            use_spot_atr=True,
            option_type="CE",
            sensex_ltp=80_000.0,
            swing_high=None,       # no swing levels available
            swing_low=None,
            spot_atr_period=5,
            spot_sl_mult=2.5,
            target_rr=1.5, trail_rr=0.5,
        )
        assert params.sl_mode == "spot_atr"   # fell back to Mode C
        assert params.atr_value is not None

    def test_mode_d_fallback_when_swing_low_above_ltp(self):
        """Mode D: swing_low must be BELOW sensex_ltp to be valid for CE."""
        candles = self._flat(n=20, spread=10.0)
        params = compute_risk_params(
            candles,
            use_swing_sl=True,
            use_spot_atr=True,
            option_type="CE",
            sensex_ltp=80_000.0,
            swing_high=None,
            swing_low=80_100.0,   # ABOVE ltp — invalid for CE
            spot_atr_period=5, spot_sl_mult=2.5,
            target_rr=1.5, trail_rr=0.5,
        )
        # Should not use swing_low=80100 (above ltp), falls back to Mode C
        assert params.sl_mode in ("spot_atr", "fixed")

    def test_mode_d_sl_ceiling_applied(self):
        """Mode D: if swing SL exceeds max_sl_pct, it is capped."""
        candles = self._flat(n=20, spread=10.0)
        # swing_high 500 pts above → raw option SL = 500 × 0.4 = 200
        # entry_price=200, max_sl_pct=0.35 → ceiling = 70 → SL capped at 70
        params = compute_risk_params(
            candles,
            use_swing_sl=True,
            use_spot_atr=False,
            option_type="PE",
            sensex_ltp=80_000.0,
            swing_high=80_500.0,
            swing_low=None,
            entry_price=200.0,
            max_sl_pct=0.35,
            target_rr=1.5, trail_rr=0.5,
        )
        assert params.sl_mode == "swing_sl"
        assert params.initial_sl_points <= 200.0 * 0.35 + 0.5  # within ceiling

    def test_mode_d_sl_mode_field_is_swing_sl(self):
        """RiskParams.sl_mode is 'swing_sl' when Mode D fires."""
        candles = self._flat(n=20, spread=5.0)
        params = compute_risk_params(
            candles,
            use_swing_sl=True, use_spot_atr=False,
            option_type="PE", sensex_ltp=80_000.0,
            swing_high=80_080.0, swing_low=None,
            min_sl_pts=5.0, min_target_pts=5.0, min_trail_pts=1.0,
        )
        assert params.sl_mode == "swing_sl"

    def test_mode_c_sl_mode_field_is_spot_atr(self):
        """RiskParams.sl_mode is 'spot_atr' when Mode C fires."""
        candles = self._flat(n=30, spread=10.0)
        params = compute_risk_params(
            candles,
            use_swing_sl=False, use_spot_atr=True,
            spot_atr_period=5, spot_sl_mult=2.5, target_rr=1.5, trail_rr=0.5,
        )
        assert params.sl_mode == "spot_atr"

    def test_fixed_fallback_sl_mode_field_is_fixed(self):
        """RiskParams.sl_mode is 'fixed' in the fixed fallback path."""
        params = compute_risk_params(
            candles_5m=[],
            use_swing_sl=False, use_spot_atr=False,
            fixed_sl=50.0, fixed_target=80.0, fixed_trail=15.0,
        )
        assert params.sl_mode == "fixed"


# ── Mode D adequacy guard (swing_sl_min_atr_mult) ─────────────────────────────

class TestModeDAdequacyGuard:
    """
    swing_sl_min_atr_mult > 0 → reject Mode D when the swing is too close to
    entry relative to ATR, and fall through to Mode C instead.
    """

    def _volatile_candles(self, n: int = 25, spread: float = 90.0) -> list:
        """Candles with ATR ≈ spread (large-range bars simulate high-volatility day)."""
        from market.candle_builder import Candle
        from datetime import datetime
        ts = datetime(2026, 1, 1, 9, 15)
        return [Candle(timestamp=ts, open=100.0, high=100.0 + spread,
                       low=100.0 - spread, close=100.0) for _ in range(n)]

    def test_swing_too_close_falls_through_to_mode_c(self):
        """
        Swing only 44 pts away, ATR ≈ 90, mult=0.6 → min_required = 54 pts.
        44 < 54 → Mode D rejected → Mode C used.
        Mirrors today's SENSEX26O0872900CE trade.
        """
        candles = self._volatile_candles(n=25, spread=90.0)
        params = compute_risk_params(
            candles,
            use_swing_sl=True,
            use_spot_atr=True,
            option_type="CE",
            sensex_ltp=80_000.0,
            swing_low=79_956.0,         # only 44 pts below entry
            swing_high=None,
            spot_atr_period=5,
            spot_sl_mult=3.0,
            target_rr=1.5,
            trail_rr=0.5,
            swing_sl_min_atr_mult=0.6,  # require swing ≥ ATR×0.6
            min_sl_pts=20.0, min_target_pts=30.0, min_trail_pts=5.0,
        )
        assert params.sl_mode == "spot_atr"   # fell through to Mode C

    def test_swing_far_enough_uses_mode_d(self):
        """
        ATR(5) on spread=90 candles = 180 (H-L = 180 per bar, Wilder-smoothed).
        min_required = 180 × 0.6 = 108 pts.
        Swing 250 pts below entry → 250 >= 108 → Mode D accepted.
        """
        candles = self._volatile_candles(n=25, spread=90.0)
        params = compute_risk_params(
            candles,
            use_swing_sl=True,
            use_spot_atr=True,
            option_type="CE",
            sensex_ltp=80_000.0,
            swing_low=79_750.0,         # 250 pts below entry (> ATR×0.6=108)
            swing_high=None,
            spot_atr_period=5,
            spot_sl_mult=3.0,
            target_rr=1.5,
            trail_rr=0.5,
            swing_sl_min_atr_mult=0.6,
            min_sl_pts=20.0, min_target_pts=30.0, min_trail_pts=5.0,
        )
        assert params.sl_mode == "swing_sl"   # Mode D accepted

    def test_disabled_at_zero_always_uses_mode_d(self):
        """
        swing_sl_min_atr_mult=0 → guard disabled, Mode D always wins even for
        a tiny swing (original behaviour unchanged).
        """
        candles = self._volatile_candles(n=25, spread=90.0)
        params = compute_risk_params(
            candles,
            use_swing_sl=True,
            use_spot_atr=True,
            option_type="CE",
            sensex_ltp=80_000.0,
            swing_low=79_956.0,         # only 44 pts away
            swing_high=None,
            spot_atr_period=5,
            spot_sl_mult=3.0,
            target_rr=1.5,
            trail_rr=0.5,
            swing_sl_min_atr_mult=0.0,  # guard disabled
            min_sl_pts=20.0, min_target_pts=30.0, min_trail_pts=5.0,
        )
        assert params.sl_mode == "swing_sl"   # no guard → Mode D used

    def test_pe_swing_high_too_close_falls_through(self):
        """PE mirror: swing_high only 44 pts above entry on ATR-90 day → Mode C."""
        candles = self._volatile_candles(n=25, spread=90.0)
        params = compute_risk_params(
            candles,
            use_swing_sl=True,
            use_spot_atr=True,
            option_type="PE",
            sensex_ltp=80_000.0,
            swing_high=80_044.0,        # only 44 pts above entry
            swing_low=None,
            spot_atr_period=5,
            spot_sl_mult=3.0,
            target_rr=1.5,
            trail_rr=0.5,
            swing_sl_min_atr_mult=0.6,
            min_sl_pts=20.0, min_target_pts=30.0, min_trail_pts=5.0,
        )
        assert params.sl_mode == "spot_atr"

    def test_calm_day_small_swing_still_valid(self):
        """
        On a calm day (ATR ≈ 10), even a 10-pt swing passes mult=0.6:
        min_required = 10 × 0.6 = 6 pts, swing = 20 pts → Mode D accepted.
        """
        from market.candle_builder import Candle
        from datetime import datetime
        ts = datetime(2026, 1, 1, 9, 15)
        calm = [Candle(timestamp=ts, open=100.0, high=105.0,
                       low=95.0, close=100.0) for _ in range(25)]
        params = compute_risk_params(
            calm,
            use_swing_sl=True,
            use_spot_atr=True,
            option_type="CE",
            sensex_ltp=80_000.0,
            swing_low=79_980.0,         # 20 pts below entry, ATR ≈ 10
            swing_high=None,
            spot_atr_period=5,
            spot_sl_mult=2.5,
            target_rr=1.5,
            trail_rr=0.5,
            swing_sl_min_atr_mult=0.6,
            min_sl_pts=5.0, min_target_pts=5.0, min_trail_pts=1.0,
        )
        assert params.sl_mode == "swing_sl"
