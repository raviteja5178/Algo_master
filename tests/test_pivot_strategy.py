"""Tests for Pivot strategy (Mode A + Mode B) and PivotTradeManager (T1→T2→T3)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from execution.pivot_trade_manager import PivotTradeManager
from market.candle_builder import Candle
from market.historical_data import PivotLevels, compute_pivot_levels
from strategies.pivot_strategy import find_pivot_setup

# ── Shared fixture helpers ────────────────────────────────────────────────────

# H=1100 L=900 C=1050  →  P=(1100+900+1050)/3=1016.67
# R1=2P-L=1133.33  R2=P+(H-L)=1216.67  R3=H+2(P-L)=1149.33
# S1=2P-H=933.33   S2=P-(H-L)=816.67   S3=L-2(H-P)=699.33
# Use round numbers instead for simplicity:
# H=1100 L=900 C=1000  → P=(1100+900+1000)/3=1000
# R1=2*1000-900=1100  R2=1000+(1100-900)=1200  R3=1100+2*(1000-900)=1300
# S1=2*1000-1100=900  S2=1000-(1100-900)=800   S3=900-2*(1100-1000)=700
PV = PivotLevels(
    pivot=1000.0, r1=1100.0, r2=1200.0, r3=1300.0,
    s1=900.0, s2=800.0, s3=700.0,
    prev_high=1100, prev_low=900, prev_close=999,
)

# For PE tests: prev_close > Pivot
PV_PE = PivotLevels(
    pivot=1000.0, r1=1100.0, r2=1200.0, r3=1300.0,
    s1=900.0, s2=800.0, s3=700.0,
    prev_high=1100, prev_low=900, prev_close=1001,
)


def _make_candle(dt: datetime, close: float, rng: float = 6.0, open_: float | None = None) -> Candle:
    """Create a candle with symmetric wicks (±rng/2) unless close is near 1000."""
    o = open_ if open_ is not None else close
    return Candle(dt, o, close + rng / 2, close - rng / 2, close)


def _series_open_direction(
    open_price: float,
    closes: list[float],
    rng: float = 6.0,
    yesterday_close: float = 990.0,
) -> list[Candle]:
    """
    Yesterday: 20 flat candles at yesterday_close.
    Today: candles starting 09:15, each 5 minutes apart.
    First candle's OPEN is open_price (mimics the day's open).
    """
    y = date.today() - timedelta(days=1)
    out = [
        Candle(datetime(y.year, y.month, y.day, 9, 15) + timedelta(minutes=5 * i),
               yesterday_close, yesterday_close + rng / 2, yesterday_close - rng / 2, yesterday_close)
        for i in range(20)
    ]
    t = date.today()
    for i, c in enumerate(closes):
        ts = datetime(t.year, t.month, t.day, 9, 15) + timedelta(minutes=5 * i)
        prev_c = closes[i - 1] if i > 0 else open_price
        out.append(Candle(ts, open_price if i == 0 else prev_c,
                          c + rng / 2, c - rng / 2, c))
    return out


def _series_rejection(
    pre_candles: list[tuple[float, float, float, float]],  # (open, high, low, close)
    sustain_closes: list[float],
    rng: float = 6.0,
) -> list[Candle]:
    """
    Yesterday: 20 flat candles.
    Today:
      - pre_candles: explicit OHLC tuples (these probe the Pivot zone)
      - sustain_closes: symmetric candles above/below Pivot
    """
    y = date.today() - timedelta(days=1)
    out = [
        Candle(datetime(y.year, y.month, y.day, 9, 15) + timedelta(minutes=5 * i),
               990, 993, 987, 990)
        for i in range(20)
    ]
    t = date.today()
    idx = 0
    for o, h, l, c in pre_candles:
        ts = datetime(t.year, t.month, t.day, 9, 15) + timedelta(minutes=5 * idx)
        out.append(Candle(ts, o, h, l, c))
        idx += 1
    for c in sustain_closes:
        ts = datetime(t.year, t.month, t.day, 9, 15) + timedelta(minutes=5 * idx)
        out.append(Candle(ts, c, c + rng / 2, c - rng / 2, c))
        idx += 1
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Mode A — Open-Direction Sustain
# ─────────────────────────────────────────────────────────────────────────────

class TestModeA:
    def test_ce_open_above_fires_in_window(self):
        """Open > Pivot, 2 sustain candles at 09:15/09:20 (within window) → CE fires."""
        candles = _series_open_direction(open_price=1010, closes=[1005, 1008])
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="OPEN_DIRECTION",
                             min_today_candles=0)
        assert s is not None and s.side == "CE" and s.mode == "OPEN_DIRECTION"
        assert s.t1 == 1100 and s.t2 == 1200 and s.t3 == 1300

    def test_pe_open_below_fires_in_window(self):
        """Open < Pivot, 2 sustain candles below Pivot within window → PE fires."""
        candles = _series_open_direction(open_price=990, closes=[995, 992])
        s = find_pivot_setup(candles, PV_PE, sustain_candles=2, pivot_mode="OPEN_DIRECTION",
                             min_today_candles=0)
        assert s is not None and s.side == "PE" and s.mode == "OPEN_DIRECTION"
        assert s.t1 == 900 and s.t2 == 800 and s.t3 == 700

    def test_ce_open_below_pivot_does_not_fire(self):
        """Open below Pivot → Mode A CE must not fire even if candles are above."""
        candles = _series_open_direction(open_price=990, closes=[1005, 1008])
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="OPEN_DIRECTION",
                             min_today_candles=0)
        assert s is None

    def test_mode_a_does_not_fire_outside_window(self):
        """Mode A must be silent after the 09:15–09:30 window closes."""
        y = date.today() - timedelta(days=1)
        t = date.today()
        out = [Candle(datetime(y.year, y.month, y.day, 9, 15) + timedelta(minutes=5 * i),
                      990, 993, 987, 990) for i in range(20)]
        # Today: first candle at 09:15, then 6 more candles up to 09:45
        closes = [1005, 1008, 1010, 1012, 1014, 1016, 1018]
        for i, c in enumerate(closes):
            ts = datetime(t.year, t.month, t.day, 9, 15) + timedelta(minutes=5 * i)
            out.append(Candle(ts, 1010 if i == 0 else closes[i - 1],
                              c + 3, c - 3, c))
        s = find_pivot_setup(out, PV, sustain_candles=2, pivot_mode="OPEN_DIRECTION",
                             min_today_candles=0)
        # Last 2 candles are at 09:40/09:45 — outside the 09:15–09:30 window
        assert s is None

    def test_mode_a_wick_pierces_blocked(self):
        """Sustain candle with close above Pivot but low wick below Pivot → blocked."""
        y = date.today() - timedelta(days=1)
        t = date.today()
        out = [Candle(datetime(y.year, y.month, y.day, 9, 15) + timedelta(minutes=5 * i),
                      990, 993, 987, 990) for i in range(20)]
        # open=1010 (above Pivot), c1=1005 ok, c2=1010 but low=995 (pierces Pivot)
        out.append(Candle(datetime(t.year, t.month, t.day, 9, 15), 1010, 1010, 1002, 1005))
        out.append(Candle(datetime(t.year, t.month, t.day, 9, 20), 1005, 1015, 995, 1010))
        s = find_pivot_setup(out, PV, sustain_candles=2, pivot_mode="OPEN_DIRECTION",
                             min_today_candles=0)
        assert s is None


# ─────────────────────────────────────────────────────────────────────────────
# Mode B — Pivot-Rejection Retest
# ─────────────────────────────────────────────────────────────────────────────

class TestModeB:
    def test_ce_rejection_from_below(self):
        """
        Open below Pivot, price climbs toward Pivot (probe high near Pivot),
        before candle close is below Pivot, then 2 sustain candles close above Pivot.
        → CE_PIVOT, mode=REJECTION.
        """
        # Pre: open=980, price climbs, probe high touches 1002 (into Pivot zone), close=998
        # Before-sustain candle close: 998 < Pivot → fresh CE
        # Sustain: close 1005, 1008 both above Pivot
        candles = _series_rejection(
            pre_candles=[(980, 1002, 978, 998)],   # high=1002 probes Pivot zone
            sustain_closes=[998, 1005, 1008],        # before=998<P, sustain=[1005,1008]
        )
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="REJECTION",
                             rejection_zone_atr=0.5, min_today_candles=0)
        assert s is not None and s.side == "CE" and s.mode == "REJECTION"
        assert s.t1 == 1100 and s.t2 == 1200 and s.t3 == 1300

    def test_pe_rejection_from_above(self):
        """
        Open above Pivot, price drops toward Pivot (probe low near Pivot),
        before candle close above Pivot, then 2 sustain candles close below Pivot.
        → PE_PIVOT, mode=REJECTION.
        """
        # Pre: open=1020, price drops, probe low=998 (into Pivot zone), close=1002
        # Before-sustain close: 1002 > Pivot → fresh PE
        # Sustain: close 995, 992 both below Pivot
        candles = _series_rejection(
            pre_candles=[(1020, 1022, 998, 1002)],   # low=998 probes Pivot zone
            sustain_closes=[1002, 995, 992],           # before=1002>P, sustain=[995,992]
        )
        s = find_pivot_setup(candles, PV_PE, sustain_candles=2, pivot_mode="REJECTION",
                             rejection_zone_atr=0.5, min_today_candles=0)
        assert s is not None and s.side == "PE" and s.mode == "REJECTION"
        assert s.t1 == 900 and s.t2 == 800 and s.t3 == 700

    def test_rejection_no_probe_blocks(self):
        """Price never reached the Pivot zone → probe condition fails → no signal."""
        # Pre candle high=980 — way below Pivot=1000, zone_half=0.3*ATR≈3
        candles = _series_rejection(
            pre_candles=[(960, 980, 958, 975)],
            sustain_closes=[975, 1005, 1008],
        )
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="REJECTION",
                             rejection_zone_atr=0.3, min_today_candles=0)
        assert s is None

    def test_rejection_fresh_check_blocks_when_before_on_same_side(self):
        """
        Probe happened, but the candle immediately before the sustain window
        is ABOVE Pivot for CE → not a fresh cross from below → blocked.
        """
        # before close = 1003 (above Pivot) — not fresh for CE
        candles = _series_rejection(
            pre_candles=[(980, 1002, 978, 998)],
            sustain_closes=[1003, 1005, 1008],  # before=1003 > P → CE fresh fails
        )
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="REJECTION",
                             rejection_zone_atr=0.5, min_today_candles=0)
        assert s is None

    def test_rejection_mode_requires_candle_before_window(self):
        """Mode B needs at least 1 candle before the sustain window (n+1 guard).
        When only sustain_candles candles exist today (n < n+1) the function
        returns None immediately."""
        # Only n=2 today candles — len(today)==2 < n+1=3 → blocked by guard
        candles = _series_rejection(
            pre_candles=[],
            sustain_closes=[1005, 1008],
        )
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="REJECTION",
                             rejection_zone_atr=0.5, min_today_candles=0)
        assert s is None


# ─────────────────────────────────────────────────────────────────────────────
# BOTH mode
# ─────────────────────────────────────────────────────────────────────────────

class TestBothMode:
    def test_both_prefers_mode_a_in_window(self):
        """When Mode A fires, Mode B is not needed; result has mode=OPEN_DIRECTION."""
        candles = _series_open_direction(open_price=1010, closes=[1005, 1008])
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="BOTH",
                             min_today_candles=0)
        assert s is not None and s.mode == "OPEN_DIRECTION"

    def test_both_falls_through_to_mode_b(self):
        """Mode A blocked (open below Pivot) → Mode B fires if probe + sustain present."""
        candles = _series_rejection(
            pre_candles=[(980, 1002, 978, 998)],
            sustain_closes=[998, 1005, 1008],
        )
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="BOTH",
                             rejection_zone_atr=0.5, min_today_candles=0)
        assert s is not None and s.mode == "REJECTION"


# ─────────────────────────────────────────────────────────────────────────────
# Mode C — Cross-and-Acceptance
# ─────────────────────────────────────────────────────────────────────────────

# Oct-9 shape: open below P, two closes below P (with wicks above), a cross
# candle that closes above P but wicks back below, then clean candles above.
_OCT9_PRE = [
    (990, 1004, 988, 995),    # opens below P, wick above, closes below
    (995, 1002, 990, 996),    # closes below P
    (996, 1010, 994, 1008),   # CROSS: closes above P, low 994 < P (dirty)
]


class TestModeC:
    def test_oct9_shape_fires_on_first_clean_window(self):
        candles = _series_rejection(_OCT9_PRE, [1012, 1015])
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="BOTH",
                             min_today_candles=0, enable_acceptance=True)
        assert s is not None and s.side == "CE" and s.mode == "ACCEPTANCE"
        assert s.entry == 1015 and s.t1 == 1100
        assert s.stop < 1009   # below lowest low of clean window (1012-3=1009)

    def test_modes_a_and_b_miss_oct9_shape(self):
        """Regression: without Mode C the Oct-9 shape produces no signal."""
        candles = _series_rejection(_OCT9_PRE, [1012, 1015])
        assert find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="BOTH",
                                min_today_candles=0) is None

    def test_window_with_dirty_cross_candle_does_not_fire(self):
        """Window = [cross candle, 1012] → cross candle wick below P → not clean."""
        candles = _series_rejection(_OCT9_PRE, [1012])
        assert find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="BOTH",
                                min_today_candles=0, enable_acceptance=True) is None

    def test_fires_only_once_per_cross(self):
        candles = _series_rejection(_OCT9_PRE, [1012, 1015, 1018])
        assert find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="BOTH",
                                min_today_candles=0, enable_acceptance=True) is None

    def test_new_cross_fires_again(self):
        """Close back below P, then a fresh clean acceptance → new signal."""
        candles = _series_rejection(
            _OCT9_PRE + [(1012, 1015, 1009, 1012), (1012, 1013, 990, 995)],
            [1006, 1010],
        )
        # pivot_mode="NONE" isolates Mode C (B would also legitimately fire here)
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="NONE",
                             min_today_candles=0, enable_acceptance=True)
        assert s is not None and s.side == "CE" and s.mode == "ACCEPTANCE"

    def test_open_below_cross_on_first_candle(self):
        """No candle ever closed below P, but the day OPENED below P → reference = open."""
        candles = _series_rejection([(990, 1008, 988, 1005)], [1010, 1015])
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="BOTH",
                             min_today_candles=0, enable_acceptance=True)
        assert s is not None and s.side == "CE" and s.mode == "ACCEPTANCE"

    def test_open_above_never_below_does_not_fire_acceptance(self):
        """Gap-up day that never crossed: no wrong side → Mode C silent (A handles opens)."""
        candles = _series_rejection([(1010, 1014, 1004, 1008)], [1012, 1015, 1018])
        assert find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="REJECTION",
                                min_today_candles=0, enable_acceptance=True) is None

    def test_pe_mirror(self):
        pre = [
            (1010, 1012, 996, 1005),
            (1005, 1010, 998, 1004),
            (1004, 1006, 990, 992),    # cross down, high 1006 > P (dirty)
        ]
        candles = _series_rejection(pre, [988, 985])
        s = find_pivot_setup(candles, PV_PE, sustain_candles=2, pivot_mode="BOTH",
                             min_today_candles=0, enable_acceptance=True)
        assert s is not None and s.side == "PE" and s.mode == "ACCEPTANCE"
        assert s.t1 == 900

    def test_room_filter_applies(self):
        candles = _series_rejection(_OCT9_PRE, [1012, 1015])
        assert find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="BOTH",
                                min_today_candles=0, enable_acceptance=True,
                                min_room_r=50.0) is None


# ─────────────────────────────────────────────────────────────────────────────
# Level Bounce / Rejection (S/R)
# ─────────────────────────────────────────────────────────────────────────────

class TestBounce:
    # ATR from yesterday's 6-pt-range candles ≈ 6 → zone 0.5×ATR ≈ 3 pts.

    def test_ce_support_bounce_at_pivot(self):
        """Above P, pull back, wick into P, bullish close back above → CE BOUNCE."""
        candles = _series_rejection(
            [(1020, 1022, 1012, 1015), (1015, 1016, 1008, 1010),
             (1010, 1018, 999, 1016)],   # wick to 999, bullish close 1016
            [],
        )
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="NONE",
                             min_today_candles=0, bounce_zone_atr=0.5)
        assert s is not None and s.side == "CE" and s.mode == "BOUNCE"
        assert (s.t1, s.t2, s.t3) == (1100, 1200, 1300)
        assert s.stop < 999

    def test_pe_resistance_rejection_at_r1(self):
        """Below R1, rally, wick into R1, bearish close back below → PE BOUNCE."""
        candles = _series_rejection(
            [(1080, 1088, 1078, 1085), (1085, 1092, 1083, 1090),
             (1090, 1102, 1082, 1084)],  # wick to 1102, bearish close 1084
            [],
        )
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="NONE",
                             min_today_candles=0, bounce_zone_atr=0.5)
        assert s is not None and s.side == "PE" and s.mode == "BOUNCE"
        assert (s.t1, s.t2, s.t3) == (1000, 900, 800)
        assert s.stop > 1102

    def test_no_bounce_without_confirming_body(self):
        """Wick into P but bearish close (still above P) → no signal."""
        candles = _series_rejection(
            [(1020, 1022, 1012, 1015), (1015, 1016, 1008, 1012),
             (1012, 1013, 999, 1003)],
            [],
        )
        assert find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="NONE",
                                min_today_candles=0, bounce_zone_atr=0.5) is None

    def test_close_through_level_is_not_bounce(self):
        """Candle closes below P → breakdown, not a support bounce."""
        candles = _series_rejection(
            [(1020, 1022, 1012, 1015), (1015, 1016, 1008, 1010),
             (1004, 1006, 990, 998)],
            [],
        )
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="NONE",
                             min_today_candles=0, bounce_zone_atr=0.5)
        assert s is None or s.side != "CE"

    # ── quality filters ──────────────────────────────────────────────────
    _CE_BOUNCE = [(1020, 1022, 1012, 1015), (1015, 1016, 1008, 1010),
                  (1010, 1018, 999, 1016)]   # signal: range 19, lower wick 11

    def _run(self, pre, **kw):
        return find_pivot_setup(_series_rejection(pre, []), PV, sustain_candles=2,
                                pivot_mode="NONE", min_today_candles=0,
                                bounce_zone_atr=0.5, **kw)

    def test_range_filter(self):
        assert self._run(self._CE_BOUNCE, bounce_min_range_atr=1.0) is not None
        assert self._run(self._CE_BOUNCE, bounce_min_range_atr=50.0) is None

    def test_wick_filter(self):
        assert self._run(self._CE_BOUNCE, bounce_min_wick_pct=0.5) is not None   # 11/19=0.58
        assert self._run(self._CE_BOUNCE, bounce_min_wick_pct=0.7) is None

    def test_trend_filter_blocks_ce_below_ema(self):
        # yesterday's EMA ~990 → CE entry 1016 is above → allowed
        assert self._run(self._CE_BOUNCE, bounce_trend_ema=21) is not None
        # strong prior trend from 1100 keeps EMA above entry → blocked
        high_pre = [(1100, 1102, 1098, 1100)] * 20 + self._CE_BOUNCE
        assert self._run(high_pre, bounce_trend_ema=21) is None

    def test_confirm_next(self):
        # signal candle alone → no entry yet
        assert self._run(self._CE_BOUNCE, bounce_confirm_next=True) is None
        # next candle closes above signal high (1018) → CE at 1020
        s = self._run(self._CE_BOUNCE + [(1016, 1022, 1014, 1020)], bounce_confirm_next=True)
        assert s is not None and s.side == "CE" and s.mode == "BOUNCE" and s.entry == 1020
        # next candle fails to break the high → no entry
        assert self._run(self._CE_BOUNCE + [(1016, 1017, 1012, 1014)],
                         bounce_confirm_next=True) is None

    def test_disabled_by_default(self):
        candles = _series_rejection(
            [(1020, 1022, 1012, 1015), (1015, 1016, 1008, 1010),
             (1010, 1018, 999, 1016)],
            [],
        )
        assert find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="NONE",
                                min_today_candles=0) is None




# ─────────────────────────────────────────────────────────────────────────────
# PivotLevels R3/S3 computation sanity check
# ─────────────────────────────────────────────────────────────────────────────

class TestPivotLevelFormulas:
    def test_fibonacci_formula(self):
        # H=72884.25, L=71676.10, C=71924.68
        # P = 72161.68, Range = 1208.15
        pl = compute_pivot_levels(72884.25, 71676.10, 71924.68, formula="FIBONACCI")
        assert pl.pivot == pytest.approx(72161.68, abs=0.01)
        assert pl.r1 == pytest.approx(72161.68 + 0.382 * 1208.15, abs=0.01)
        assert pl.r2 == pytest.approx(72161.68 + 0.618 * 1208.15, abs=0.01)
        assert pl.r3 == pytest.approx(72161.68 + 1.000 * 1208.15, abs=0.01)
        assert pl.s1 == pytest.approx(72161.68 - 0.382 * 1208.15, abs=0.01)
        assert pl.s2 == pytest.approx(72161.68 - 0.618 * 1208.15, abs=0.01)
        assert pl.s3 == pytest.approx(72161.68 - 1.000 * 1208.15, abs=0.01)

    def test_traditional_formula(self):
        # H=1100, L=900, C=1000 -> P=1000
        pl = compute_pivot_levels(1100, 900, 1000, formula="TRADITIONAL")
        assert pl.pivot == 1000.0
        assert pl.r1 == 1100.0
        assert pl.r2 == 1200.0
        assert pl.r3 == 1300.0
        assert pl.s1 == 900.0
        assert pl.s2 == 800.0
        assert pl.s3 == 700.0


# ─────────────────────────────────────────────────────────────────────────────
# min_today_candles guard
# ─────────────────────────────────────────────────────────────────────────────

class TestMinTodayCandles:
    def test_blocked_before_min(self):
        candles = _series_open_direction(open_price=1010, closes=[1005, 1008])
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="OPEN_DIRECTION",
                             min_today_candles=6)
        assert s is None   # only 2 today candles < 6

    def test_allowed_at_min(self):
        candles = _series_open_direction(open_price=1010, closes=[1005, 1008])
        s = find_pivot_setup(candles, PV, sustain_candles=2, pivot_mode="OPEN_DIRECTION",
                             min_today_candles=2)
        assert s is not None


# ─────────────────────────────────────────────────────────────────────────────
# PivotTradeManager — T1 / T2 / T3 multi-stage TSL
# ─────────────────────────────────────────────────────────────────────────────

def _ce_mgr(**kw) -> PivotTradeManager:
    """entry=1010, stop=990, T1=1100, T2=1200, T3=1300, ATR=10, option=200."""
    return PivotTradeManager(
        "CE", 1010, 990, 1100, 1200, 1300, 10, 200,
        delta=0.4, be_trigger_r=1.0, be_buffer_pts=5,
        t1_lock_pct=0.5, t2_lock_pct=0.5,
        trail_atr_mult=1.0, t2_trail_atr_mult=0.75,
        hard_sl_cushion=1.25, max_sl_pct=0.5, **kw
    )


class TestPivotTradeManager:
    # ── constructor accepts t3 ──────────────────────────────────────────────
    def test_t3_stored(self):
        m = _ce_mgr()
        assert m.t3 == 1300

    # ── stop hit ────────────────────────────────────────────────────────────
    def test_initial_sl_hit(self):
        m = _ce_mgr()
        assert m.on_index_price(989) == ("EXIT", "PIVOT_SL_HIT")

    def test_sl_not_triggered_at_epsilon_boundary(self):
        m = _ce_mgr()
        assert m.on_index_price(990) is None

    # ── break-even ──────────────────────────────────────────────────────────
    def test_break_even_after_1r(self):
        m = _ce_mgr()
        act = m.on_index_price(1031)   # +21 > 1R=20
        assert act and act[0] == "STOP_MOVED" and m.stage == "BE"
        assert m.stop_index == 1015    # entry + be_buffer_pts
        assert m.on_index_price(1014) == ("EXIT", "PIVOT_BE_STOP")

    # ── T1 lock + chandelier (same as before) ───────────────────────────────
    def test_t1_lock_fires_on_t1_tick(self):
        m = _ce_mgr()
        result = m.on_index_price(1101)   # T1 touched
        assert m.stage == "T1"
        # lock = 1010 + 0.5*(1100-1010) = 1055
        assert m.stop_index == pytest.approx(1055.0)
        assert result == ("STOP_MOVED", m.option_stop)

    def test_chandelier_fires_on_next_tick(self):
        m = _ce_mgr()
        m.on_index_price(1101)   # T1 lock tick
        m.on_index_price(1101)   # chandelier: 1101 - 1*10 = 1091
        assert m.stop_index == pytest.approx(1091.0)

    def test_t1_trails_after_advance(self):
        m = _ce_mgr()
        m.on_index_price(1101)   # T1 lock
        m.on_index_price(1101)   # chandelier → stop=1091
        m.on_index_price(1150)   # chandelier: 1150-10=1140
        assert m.stop_index == pytest.approx(1140)
        m.on_index_price(1120)   # pullback — stop never retreats
        assert m.stop_index == pytest.approx(1140)
        assert m.on_index_price(1139) == ("EXIT", "PIVOT_TSL_HIT")

    # ── T2 lock + tighter trail ─────────────────────────────────────────────
    def test_t2_lock_fires_on_t2_tick(self):
        m = _ce_mgr()
        # Advance through T1
        m.on_index_price(1101)   # T1 lock tick
        m.on_index_price(1101)   # chandelier
        assert m.stage == "T1"
        # Now hit T2
        result = m.on_index_price(1201)
        assert m.stage == "T2"
        # lock = T1 + 0.5*(T2-T1) = 1100 + 0.5*100 = 1150
        # fav(T1) = 90, fav(T2) = 190 → diff = 100  → lock contribution = 0.5*100 = 50
        # lock = T1 + sign*t2_lock_pct*abs(fav(T2)-fav(T1))
        #       = 1100 + 1*0.5*abs(190-90) = 1100 + 50 = 1150
        assert m.stop_index == pytest.approx(1150.0)
        assert result == ("STOP_MOVED", m.option_stop)

    def test_t2_trail_uses_tighter_multiplier(self):
        m = _ce_mgr()
        m.on_index_price(1101)   # T1 lock
        m.on_index_price(1101)   # chandelier → T1 stage
        m.on_index_price(1201)   # T2 lock tick → T2 stage (stop=1150)
        # Next tick: chandelier with t2_trail_atr_mult=0.75
        # best=1201, trail = 1201 - 0.75*10 = 1193.5 > 1150 → moves
        m.on_index_price(1201)
        assert m.stop_index == pytest.approx(1193.5)

    def test_t3_exit(self):
        m = _ce_mgr()
        m.on_index_price(1101)
        m.on_index_price(1201)
        assert m.on_index_price(1300) == ("EXIT", "PIVOT_TARGET_T3")

    def test_stop_only_ratchets_up(self):
        m = _ce_mgr()
        stops = []
        for p in (1031, 1060, 1101, 1101, 1150, 1201, 1201, 1250, 1220, 1260):
            m.on_index_price(p)
            stops.append(m.option_stop)
        assert stops == sorted(stops)

    # ── PE mirror ────────────────────────────────────────────────────────────
    def test_pe_t3_exit(self):
        m = PivotTradeManager("PE", 990, 1010, 900, 800, 700, 10, 200,
                              t2_lock_pct=0.5, t2_trail_atr_mult=0.75)
        m.on_index_price(899)   # T1 lock
        m.on_index_price(799)   # T2 lock
        assert m.on_index_price(700) == ("EXIT", "PIVOT_TARGET_T3")

    def test_pe_t2_lock(self):
        m = PivotTradeManager("PE", 990, 1010, 900, 800, 700, 10, 200,
                              t2_lock_pct=0.5, t2_trail_atr_mult=0.75)
        m.on_index_price(899)   # T1: lock = 990 - 0.5*90 = 945
        m.on_index_price(899)   # chandelier tick
        m.on_index_price(799)   # T2 lock tick
        assert m.stage == "T2"
        # lock = T1 + sign*t2_lock_pct*|fav(T2)-fav(T1)|
        #       = 900 + (-1)*0.5*|(-190)-(-90)| = 900 - 50 = 850
        assert m.stop_index == pytest.approx(850.0)

    # ── signal_risk override ─────────────────────────────────────────────────
    def test_signal_risk_overrides_slippage(self):
        m = PivotTradeManager("CE", 1015, 990, 1100, 1200, 1300, 10, 200,
                              be_trigger_r=1.0, signal_risk=20)
        assert m.risk == 20
        act = m.on_index_price(1036)
        assert act and act[0] == "STOP_MOVED" and m.stage == "BE"

    # ── ATR / delta refresh ──────────────────────────────────────────────────
    def test_update_atr(self):
        m = _ce_mgr()
        m.on_index_price(1101)   # T1 lock
        m.on_index_price(1101)   # chandelier → 1091
        m.update_atr(20)
        m.on_index_price(1150)   # chandelier: 1150-20=1130 (not 1140)
        assert m.stop_index == pytest.approx(1130.0)

    def test_update_delta(self):
        m = _ce_mgr()
        m.on_index_price(1031)
        stop_before = m.option_stop
        m.update_delta(0.55)
        m.on_index_price(1101)
        assert m.option_stop > stop_before

    def test_update_atr_ignores_invalid(self):
        m = _ce_mgr()
        m.update_atr(0)
        assert m.atr == 10
        m.update_atr(-5)
        assert m.atr == 10

    def test_update_delta_ignores_invalid(self):
        m = _ce_mgr()
        m.update_delta(0)
        assert m.delta == 0.4
        m.update_delta(1.5)
        assert m.delta == 0.4

    # ── persistence ──────────────────────────────────────────────────────────
    def test_save_load_roundtrip(self, tmp_path, monkeypatch):
        import execution.pivot_trade_manager as ptm
        monkeypatch.setattr(ptm, "_STATE_FILE", tmp_path / "p.json")
        m = _ce_mgr()
        m.on_index_price(1031)
        m.save("T1")
        r = PivotTradeManager.load("T1")
        assert r is not None and r.stop_index == m.stop_index and r.stage == "BE"
        assert PivotTradeManager.load("OTHER") is None


# ─────────────────────────────────────────────────────────────────────────────
# Mode A — Open-Direction quality filters (Oct 9 regression)
# ─────────────────────────────────────────────────────────────────────────────

class TestModeAQualityFilters:
    """
    Regression tests for the three OD quality filters added to fix the
    Oct 9 PE_PIVOT false signal.

    Oct 9 facts (scaled to the test pivot=1000):
      Pivot  = 1000
      ATR    = 114  → scaled ATR = 100
      Open   = 990  → gap = 10 pts = 0.10×ATR  (very close to Pivot)
      First candle: open=990, high=1000 (touches Pivot), close=990
        upper wick = 1000 − 990 = 10 pts = 0.10×ATR
        body: 990 == 990 → doji (no bearish body)

    With legacy defaults all filters are OFF → PE fires.
    Enabling each filter independently must block the trade.
    """

    # Scaled test pivot  (Pivot=1000, ATR≈100)
    _PV = PivotLevels(
        pivot=1000.0, r1=1100.0, r2=1200.0, r3=1300.0,
        s1=900.0, s2=800.0, s3=700.0,
        prev_high=1100, prev_low=900, prev_close=1001,
    )

    def _oct9_candles(self) -> list[Candle]:
        """
        Reproduce Oct 9 candle structure at test scale.

        Oct 9 actual data (scaled):
          First candle (09:15): open=990, high=999.9 (just below Pivot), close=990  (doji)
            upper wick = 999.9 − 990 = 9.9 pts ≈ 0.10×ATR
          Second candle (09:20, sustain[0]): close=992, high=998 (below Pivot)
          Third candle (09:25, sustain[1]): close=990, high=997 (below Pivot)

        NOTE: high must be STRICTLY < Pivot (1000) for the sustained check to pass.
        On Oct 9 the real first candle's high was 71871.28, Pivot was 71871.65 — a
        difference of only 0.37 pts (strictly below).  We mirror that: high=999.9.
        The key signals are:
          - open within the noise band of Pivot (gap=10 pts = 0.10×ATR) → gap filter
          - doji body (open==close) → first_candle_confirm filter
          - large upper wick reaching near Pivot → wick filter
        """
        from datetime import date, timedelta
        y = date.today() - timedelta(days=1)
        t = date.today()
        # 20 yesterday candles with range=200 so ATR(14)≈100
        out = [
            Candle(
                datetime(y.year, y.month, y.day, 9, 15) + timedelta(minutes=5 * i),
                980, 1080, 880, 980,  # range=200 → ATR≈100
            )
            for i in range(20)
        ]
        # First today candle: open=990, high=999.9 (just below Pivot), close=990 (doji)
        # Upper wick = 999.9 − 990 = 9.9 pts ≈ 0.10×ATR — models the Pivot probe
        out.append(Candle(datetime(t.year, t.month, t.day, 9, 15), 990, 999.9, 985, 990))
        # Second today candle (sustain[0]): below Pivot, high<1000
        out.append(Candle(datetime(t.year, t.month, t.day, 9, 20), 990, 998, 985, 992))
        return out

    def test_legacy_defaults_fire(self):
        """With all filters OFF (defaults), PE fires — baseline must hold."""
        candles = self._oct9_candles()
        s = find_pivot_setup(candles, self._PV, sustain_candles=2,
                             pivot_mode="OPEN_DIRECTION", min_today_candles=0)
        assert s is not None and s.side == "PE", (
            "Baseline broken: expected PE to fire with all OD filters OFF"
        )

    def test_min_od_gap_atr_blocks_near_pivot_open(self):
        """
        Open=990 is 10 pts from Pivot=1000.
        With ATR≈100, gap=0.10×ATR.
        Setting min_od_gap_atr=0.4 requires gap >= 40 pts → blocked.
        """
        candles = self._oct9_candles()
        s = find_pivot_setup(candles, self._PV, sustain_candles=2,
                             pivot_mode="OPEN_DIRECTION", min_today_candles=0,
                             min_od_gap_atr=0.4)
        assert s is None, "PE should be blocked: open is within 0.4×ATR of Pivot"

    def test_min_od_gap_atr_allows_far_open(self):
        """
        Open=950 is 50 pts from Pivot=1000.
        The 20 yesterday candles (range=200) produce ATR≈176.
        Using min_od_gap_atr=0.2 → required gap = 0.2×176 ≈ 35 pts.
        gap=50 pts > 35 pts → allowed.
        Also uses min_today_candles=0 so the room filter passes
        (entry=952, S1=900, room=52 > risk≈17 → valid setup).
        """
        from datetime import date, timedelta
        y = date.today() - timedelta(days=1)
        t = date.today()
        out = [
            Candle(
                datetime(y.year, y.month, y.day, 9, 15) + timedelta(minutes=5 * i),
                980, 1080, 880, 980,
            )
            for i in range(20)
        ]
        # open=950, between S1(900) and Pivot(1000), tiny upper wick, bearish body
        out.append(Candle(datetime(t.year, t.month, t.day, 9, 15), 950, 952, 940, 948))
        out.append(Candle(datetime(t.year, t.month, t.day, 9, 20), 948, 953, 937, 945))
        s = find_pivot_setup(out, self._PV, sustain_candles=2,
                             pivot_mode="OPEN_DIRECTION", min_today_candles=0,
                             min_od_gap_atr=0.2)
        assert s is not None and s.side == "PE", (
            "PE should fire: open is 50 pts (>0.2×ATR) from Pivot"
        )

    def test_first_candle_confirm_blocks_doji(self):
        """
        First candle is a doji (open==close=990).
        first_candle_confirm=True requires close < open for PE → blocked.
        """
        candles = self._oct9_candles()
        s = find_pivot_setup(candles, self._PV, sustain_candles=2,
                             pivot_mode="OPEN_DIRECTION", min_today_candles=0,
                             first_candle_confirm=True)
        assert s is None, "PE should be blocked: first candle is a doji, not bearish"

    def test_first_candle_confirm_allows_bearish_first_candle(self):
        """
        First candle is bearish (close=985 < open=990).
        first_candle_confirm=True should allow the PE.
        """
        from datetime import date, timedelta
        y = date.today() - timedelta(days=1)
        t = date.today()
        out = [
            Candle(
                datetime(y.year, y.month, y.day, 9, 15) + timedelta(minutes=5 * i),
                980, 1080, 880, 980,
            )
            for i in range(20)
        ]
        # First candle: clearly bearish (close < open), no upper wick near Pivot
        out.append(Candle(datetime(t.year, t.month, t.day, 9, 15), 990, 991, 980, 985))
        # Sustain candle: below Pivot
        out.append(Candle(datetime(t.year, t.month, t.day, 9, 20), 985, 990, 978, 983))
        # Open = 990 < Pivot=1000, gap=10 (no gap filter applied here)
        s = find_pivot_setup(out, self._PV, sustain_candles=2,
                             pivot_mode="OPEN_DIRECTION", min_today_candles=0,
                             first_candle_confirm=True)
        assert s is not None and s.side == "PE", (
            "PE should fire: first candle is bearish and confirms the direction"
        )

    def test_max_first_wick_atr_blocks_bullish_probe(self):
        """
        First candle: open=990, high=999.9, close=990.
        Upper wick = 999.9 − 990 = 9.9 pts.  ATR≈174.
        wick/ATR = 9.9/174 ≈ 0.057.
        Setting max_first_wick_atr=0.05 → max_wick=0.05×174≈8.7 pts < 9.9 → blocked.
        """
        candles = self._oct9_candles()
        s = find_pivot_setup(candles, self._PV, sustain_candles=2,
                             pivot_mode="OPEN_DIRECTION", min_today_candles=0,
                             max_first_wick_atr=0.05)
        assert s is None, (
            "PE should be blocked: first candle upper wick reaches Pivot (bullish probe)"
        )

    def test_max_first_wick_atr_allows_small_wick(self):
        """
        First candle has a tiny upper wick (high=992, close=990 → wick=2 pts ≈ 0.02×ATR).
        max_first_wick_atr=0.08 allows this (2 < 8 pts) → PE should fire.
        """
        from datetime import date, timedelta
        y = date.today() - timedelta(days=1)
        t = date.today()
        out = [
            Candle(
                datetime(y.year, y.month, y.day, 9, 15) + timedelta(minutes=5 * i),
                980, 1080, 880, 980,
            )
            for i in range(20)
        ]
        # First candle: tiny upper wick (high=992), bearish body
        out.append(Candle(datetime(t.year, t.month, t.day, 9, 15), 990, 992, 982, 988))
        # Sustain candle: below Pivot
        out.append(Candle(datetime(t.year, t.month, t.day, 9, 20), 988, 993, 981, 985))
        s = find_pivot_setup(out, self._PV, sustain_candles=2,
                             pivot_mode="OPEN_DIRECTION", min_today_candles=0,
                             max_first_wick_atr=0.08)
        assert s is not None and s.side == "PE", (
            "PE should fire: first candle upper wick is tiny (0.02×ATR), below threshold"
        )

    def test_all_three_filters_together_block_oct9(self):
        """
        All three filters combined must block the Oct 9 scenario.
        Uses the same thresholds as the individual block tests:
          min_od_gap_atr=0.4  → gap=10 pts < 0.4×174≈70 pts → blocked
          first_candle_confirm=True → doji body → blocked
          max_first_wick_atr=0.05 → wick=9.9 pts > 0.05×174≈8.7 pts → blocked
        Any one of the three is sufficient to block; all three together is belt-and-braces.
        """
        candles = self._oct9_candles()
        s = find_pivot_setup(candles, self._PV, sustain_candles=2,
                             pivot_mode="OPEN_DIRECTION", min_today_candles=0,
                             min_od_gap_atr=0.4,
                             first_candle_confirm=True,
                             max_first_wick_atr=0.05)
        assert s is None, "PE should be blocked by combined OD quality filters"

    def test_filters_do_not_affect_mode_b(self):
        """
        OD filters must not affect Mode B (REJECTION).
        A valid rejection setup must still fire even when all OD filters are set
        to their strictest values.
        """
        from datetime import date, timedelta
        y = date.today() - timedelta(days=1)
        t = date.today()
        out = [
            Candle(
                datetime(y.year, y.month, y.day, 9, 15) + timedelta(minutes=5 * i),
                980, 1080, 880, 980,
            )
            for i in range(20)
        ]
        # Today candles: price came from above, probed Pivot zone, now rejecting down
        # pre_candle: starts above Pivot (1010), low dips into zone (1002 ≤ 1000 + 0.3×ATR)
        out.append(Candle(datetime(t.year, t.month, t.day, 9, 15), 1010, 1015, 1002, 1008))  # above Pivot
        out.append(Candle(datetime(t.year, t.month, t.day, 9, 20), 1008, 1010, 990, 1005))   # probe: low=990, before=1008>1000
        # sustain candles: now clearly below Pivot (rejection confirmed)
        out.append(Candle(datetime(t.year, t.month, t.day, 9, 25), 995, 998, 989, 992))
        out.append(Candle(datetime(t.year, t.month, t.day, 9, 30), 992, 996, 986, 990))
        s = find_pivot_setup(out, self._PV, sustain_candles=2,
                             pivot_mode="REJECTION", min_today_candles=0,
                             rejection_zone_atr=0.3,
                             # All OD filters at strictest — must have no effect on Mode B
                             min_od_gap_atr=1.0,
                             first_candle_confirm=True,
                             max_first_wick_atr=0.01)
        assert s is not None and s.side == "PE" and s.mode == "REJECTION", (
            "Mode B REJECTION must be unaffected by OD quality filter settings"
        )
