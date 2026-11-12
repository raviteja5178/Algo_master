"""
VWAP Live Signal Scanner
========================
Fetches today's SENSEX candles from Zerodha historical API, replays them
candle-by-candle, and prints every CE_VWAP / PE_VWAP signal with full
SL / TSL / Target / BE computed exactly as the live bot would.

Usage:
    python -m research.vwap_live_signals
    python -m research.vwap_live_signals --days 2      # include yesterday too
    python -m research.vwap_live_signals --date 2026-01-15

No live orders are placed. Read-only.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, date, timedelta
from typing import NamedTuple

# ── resolve project root ───────────────────────────────────────────────────────
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from broker.kite_client import get_kite
from market.historical_data import SENSEX_TOKEN, fetch_historical_candles
from market.candle_builder import Candle
from market.vwap import VWAPCalculator
from market.indicators import atr_at
from market.indicators import swing_levels
from strategies.vwap_strategy import (
    is_vwap_ce_signal, is_vwap_pe_signal,
    vwap_zscore, adx_regime_ok, vwap_cross_count, volume_spike,
    reward_to_risk_ok,
)
from execution.atr_risk import compute_risk_params
from utils.time_utils import IST


# ── colour helpers (Windows-safe fallback) ────────────────────────────────────
try:
    import colorama; colorama.init()
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"
except ImportError:
    GREEN = RED = YELLOW = CYAN = BOLD = RESET = ""


class SignalResult(NamedTuple):
    time:       str
    side:       str     # CE_VWAP | PE_VWAP
    sensex:     float   # SENSEX index close at signal
    vwap:       float
    zscore:     float | None
    adx_ok:     bool
    vol_spike:  bool
    cross_cnt:  int
    sl_pts:     float   # option premium pts
    be_pts:     float
    trail_pts:  float
    target_pts: float
    sl_mode:    str
    atr:        float | None


def _fetch_1m_today(target_date: date, warm_days: int = 5) -> list[Candle]:
    """Fetch 1m SENSEX candles from Zerodha for warm_days back through target_date."""
    kite = get_kite()
    from_dt = datetime(target_date.year, target_date.month, target_date.day, 9, 15)
    # Warm-up: go back warm_days calendar days for ATR/EMA seeding
    from_dt_warm = from_dt - timedelta(days=warm_days)
    to_dt = datetime(target_date.year, target_date.month, target_date.day, 15, 30)

    print(f"{CYAN}Fetching 1m SENSEX candles "
          f"{from_dt_warm.date()} to {to_dt.date()} from Zerodha...{RESET}")
    records = kite.historical_data(
        instrument_token=SENSEX_TOKEN,
        from_date=from_dt_warm.strftime("%Y-%m-%d %H:%M:%S"),
        to_date=to_dt.strftime("%Y-%m-%d %H:%M:%S"),
        interval="minute",
    )
    candles = []
    for r in records:
        ts = IST.localize(r["date"]) if r["date"].tzinfo is None else r["date"]
        if (ts.hour, ts.minute) < (9, 15):
            continue
        candles.append(Candle(
            timestamp=ts,
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=int(r.get("volume", 0)),
        ))
    print(f"  {len(candles)} 1m bars loaded ({len({c.timestamp.date() for c in candles})} sessions)")
    return candles


def _build_5m(candles_1m: list[Candle]) -> list[Candle]:
    """Aggregate 1m candles into 5m candles (completed only)."""
    from collections import defaultdict
    buckets: dict[datetime, list[Candle]] = defaultdict(list)
    for c in candles_1m:
        bucket_min = (c.timestamp.hour * 60 + c.timestamp.minute) // 5 * 5
        bucket_ts = c.timestamp.replace(
            hour=bucket_min // 60, minute=bucket_min % 60, second=0, microsecond=0
        )
        buckets[bucket_ts].append(c)

    result = []
    for ts in sorted(buckets):
        cs = buckets[ts]
        # only emit complete 5m buckets (exactly 5 bars — last bucket may be partial)
        if len(cs) < 5:
            continue
        result.append(Candle(
            timestamp=ts,
            open=cs[0].open,
            high=max(c.high for c in cs),
            low=min(c.low for c in cs),
            close=cs[-1].close,
            volume=sum(c.volume for c in cs),
        ))
    return result


def _build_15m(candles_1m: list[Candle]) -> list[Candle]:
    """Aggregate 1m candles into 15m candles (completed only)."""
    from collections import defaultdict
    buckets: dict[datetime, list[Candle]] = defaultdict(list)
    for c in candles_1m:
        bucket_min = (c.timestamp.hour * 60 + c.timestamp.minute) // 15 * 15
        bucket_ts = c.timestamp.replace(
            hour=bucket_min // 60, minute=bucket_min % 60, second=0, microsecond=0
        )
        buckets[bucket_ts].append(c)

    result = []
    for ts in sorted(buckets):
        cs = buckets[ts]
        if len(cs) < 15:
            continue
        result.append(Candle(
            timestamp=ts,
            open=cs[0].open,
            high=max(c.high for c in cs),
            low=min(c.low for c in cs),
            close=cs[-1].close,
            volume=sum(c.volume for c in cs),
        ))
    return result


def _compute_vwap_series(candles_5m: list[Candle]) -> dict[datetime, float]:
    """Compute running VWAP at each 5m candle close, reset each day."""
    calc = VWAPCalculator()
    result: dict[datetime, float] = {}
    for c in candles_5m:
        calc.on_candle(c)
        v = calc.value
        if v is not None:
            result[c.timestamp] = v
    return result


def scan(target_date: date, warm_days: int = 5) -> list[SignalResult]:
    """Run the full VWAP scan for target_date. Returns list of signals found."""

    # ── 1. Fetch data ─────────────────────────────────────────────────────────
    candles_1m_all = _fetch_1m_today(target_date, warm_days=warm_days)
    candles_5m_all = _build_5m(candles_1m_all)
    candles_15m_all = _build_15m(candles_1m_all)

    # today-only 5m candles for display
    today_5m = [c for c in candles_5m_all if c.timestamp.date() == target_date]
    print(f"  {len(today_5m)} completed 5m candles for {target_date}")

    if not today_5m:
        print(f"{YELLOW}No 5m candles found for {target_date}. "
              f"Market may be closed or data not yet available.{RESET}")
        return []

    # ── 2. VWAP kwargs from settings ──────────────────────────────────────────
    vwap_kwargs = dict(
        retest_lookback       = settings.VWAP_RETEST_LOOKBACK,
        min_bounce_pts        = settings.VWAP_MIN_BOUNCE_PTS,
        max_submerged_candles = settings.VWAP_MAX_SUBMERGED_CANDLES,
        slope_lookback        = settings.VWAP_SLOPE_LOOKBACK,
        mr_zscore_entry       = settings.VWAP_MR_ZSCORE_ENTRY,
        mr_adx_max            = settings.VWAP_MR_ADX_MAX,
        mr_rsi_confirm        = settings.VWAP_MR_RSI_CONFIRM,
        mr_volume_spike       = settings.VWAP_MR_VOLUME_SPIKE,
        mr_min_rr             = settings.VWAP_MR_MIN_RR,
        mr_min_score          = settings.VWAP_MR_MIN_SCORE,
        mr_vwap_cross_min     = settings.VWAP_MR_VWAP_CROSS_MIN,
    )

    # ── 3. Replay candle by candle ────────────────────────────────────────────
    signals: list[SignalResult] = []
    seen_candles: set[datetime] = set()   # prevent duplicate signals on same candle

    for i, candle in enumerate(candles_5m_all):
        if candle.timestamp.date() != target_date:
            continue
        if i < 3:
            continue   # need at least 3 prior candles for retest window

        # Window: all candles up to and including this one
        window_5m  = candles_5m_all[:i + 1]
        window_15m = [c for c in candles_15m_all if c.timestamp <= candle.timestamp]

        if len(window_15m) < 2:
            continue

        # Running VWAP up to this candle
        vwap_calc = VWAPCalculator()
        for c in window_5m:
            vwap_calc.on_candle(c)
        vwap = vwap_calc.value
        if vwap is None:
            continue

        ts_key = candle.timestamp

        # ── Check CE signal ───────────────────────────────────────────────────
        if ts_key not in seen_candles and is_vwap_ce_signal(window_5m, vwap, **vwap_kwargs):
            seen_candles.add(ts_key)
            sig = _build_result("CE_VWAP", candle, vwap, window_5m)
            signals.append(sig)
            _print_signal(sig)

        # ── Check PE signal ───────────────────────────────────────────────────
        elif ts_key not in seen_candles and is_vwap_pe_signal(window_5m, vwap, **vwap_kwargs):
            seen_candles.add(ts_key)
            sig = _build_result("PE_VWAP", candle, vwap, window_5m)
            signals.append(sig)
            _print_signal(sig)

    return signals


def _build_result(
    side: str,
    candle: Candle,
    vwap: float,
    window_5m: list[Candle],
) -> SignalResult:
    """Compute all metrics and risk params for a signal candle."""
    sensex = candle.close
    option_type = "CE" if side == "CE_VWAP" else "PE"

    # Enhanced MR diagnostics
    z = vwap_zscore(window_5m, vwap)
    adx_ok = adx_regime_ok(window_5m, settings.VWAP_MR_ADX_MAX)
    vol_ok = volume_spike(window_5m, multiplier=settings.VWAP_MR_VOLUME_SPIKE or 1.5)
    cross_cnt = vwap_cross_count(window_5m, vwap)

    # Swing levels for Mode D
    swing_high, swing_low = swing_levels(window_5m, length=settings.SWING_SL_LENGTH)

    # Risk params (exactly as the live bot computes them)
    risk = compute_risk_params(
        window_5m,
        fixed_sl         = settings.INITIAL_SL_POINTS,
        fixed_target     = settings.INITIAL_TARGET_OFFSET_POINTS,
        fixed_trail      = settings.TRAIL_STEP_POINTS,
        min_sl_pts       = settings.MIN_SL_POINTS,
        min_target_pts   = settings.MIN_TARGET_POINTS,
        min_trail_pts    = settings.MIN_TRAIL_POINTS,
        use_spot_atr     = settings.USE_SPOT_ATR_RISK,
        spot_atr_period  = settings.SPOT_ATR_PERIOD,
        spot_sl_mult     = settings.SPOT_ATR_SL_MULT,
        target_rr        = settings.SPOT_ATR_TARGET_RR,
        trail_rr         = settings.SPOT_ATR_TRAIL_RR,
        use_swing_sl     = settings.USE_SWING_SL,
        option_type      = option_type,
        sensex_ltp       = sensex,
        swing_high       = swing_high,
        swing_low        = swing_low,
        swing_sl_min_atr_mult = settings.SWING_SL_MIN_ATR_MULT,
        atm_delta        = settings.ATM_DELTA,
        be_trigger_rr    = 0.5,
    )

    return SignalResult(
        time      = candle.timestamp.strftime("%H:%M"),
        side      = side,
        sensex    = round(sensex, 2),
        vwap      = round(vwap, 2),
        zscore    = round(z, 2) if z is not None else None,
        adx_ok    = adx_ok,
        vol_spike = vol_ok,
        cross_cnt = cross_cnt,
        sl_pts    = risk.initial_sl_points,
        be_pts    = risk.break_even_trigger_points,
        trail_pts = risk.trail_step_points,
        target_pts= risk.initial_target_points,
        sl_mode   = risk.sl_mode,
        atr       = risk.atr_value,
    )


def _print_signal(s: SignalResult) -> None:
    colour = GREEN if s.side == "CE_VWAP" else RED
    arrow  = "^ LONG" if s.side == "CE_VWAP" else "v SHORT"
    sep = "-" * 64
    print(f"\n{colour}{BOLD}{sep}{RESET}")
    print(f"{colour}{BOLD}  {s.time}  {s.side}  {arrow}{RESET}")
    print(f"{colour}{sep}{RESET}")
    print(f"  {'SENSEX close':<22} {s.sensex:>10.2f}")
    print(f"  {'VWAP':<22} {s.vwap:>10.2f}  (gap {abs(s.sensex - s.vwap):.1f} pts)")
    print(f"  {'Z-score':<22} {str(s.zscore) if s.zscore is not None else 'n/a':>10}  "
          f"{'[strong ext]' if s.zscore and abs(s.zscore) >= 2 else ''}")
    print(f"  {'ADX regime ok':<22} {'yes' if s.adx_ok else 'no':>10}")
    print(f"  {'Volume spike':<22} {'yes' if s.vol_spike else 'no':>10}")
    print(f"  {'VWAP crossings today':<22} {s.cross_cnt:>10}")
    print(f"  {'ATR (5m, period=5)':<22} {str(s.atr) if s.atr else 'n/a':>10}  pts (index)")
    print(f"  {'SL mode':<22} {s.sl_mode:>10}")
    print()
    print(f"  {BOLD}{'SL':<22} {s.sl_pts:>8.1f} pts{RESET}   (option premium)")
    print(f"  {BOLD}{'Break-even trigger':<22} {s.be_pts:>8.1f} pts{RESET}")
    print(f"  {BOLD}{'TSL step':<22} {s.trail_pts:>8.1f} pts{RESET}")
    print(f"  {BOLD}{'Target':<22} {s.target_pts:>8.1f} pts{RESET}")
    print(f"{colour}{sep}{RESET}")


def _print_summary(signals: list[SignalResult], target_date: date) -> None:
    sep = "=" * 64
    print(f"\n{sep}")
    print(f"  VWAP Signal Summary  {target_date}   ({len(signals)} signal(s))")
    print(f"{sep}")
    if not signals:
        print(f"  {YELLOW}No VWAP signals fired today with current settings.{RESET}")
        print(f"\n  Tip: check VWAP_MR_* thresholds in .env -- filters may be too strict.")
        return
    print(f"  {'Time':<8} {'Side':<12} {'SENSEX':>9} {'VWAP':>9} {'Gap':>7} "
          f"{'SL':>6} {'BE':>6} {'TSL':>6} {'TGT':>6}  Mode")
    print(f"  {'-'*8} {'-'*12} {'-'*9} {'-'*9} {'-'*7} "
          f"{'-'*6} {'-'*6} {'-'*6} {'-'*6}  {'-'*9}")
    for s in signals:
        colour = GREEN if "CE" in s.side else RED
        gap = abs(s.sensex - s.vwap)
        print(f"  {colour}{s.time:<8} {s.side:<12} {s.sensex:>9.2f} {s.vwap:>9.2f} "
              f"{gap:>7.1f} {s.sl_pts:>6.1f} {s.be_pts:>6.1f} "
              f"{s.trail_pts:>6.1f} {s.target_pts:>6.1f}  {s.sl_mode}{RESET}")
    print(f"{sep}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="VWAP signal scanner using live Zerodha data")
    ap.add_argument("--date",  default=str(date.today()),
                    help="Target date YYYY-MM-DD (default: today)")
    ap.add_argument("--days",  type=int, default=5,
                    help="Warm-up days to fetch before target date (default: 5)")
    args = ap.parse_args()

    target = datetime.strptime(args.date, "%Y-%m-%d").date()

    SEP = "=" * 64
    print(f"\n{BOLD}{SEP}")
    print(f"  VWAP Live Signal Scanner  {target}")
    print(f"  TRADING_MODE : {settings.TRADING_MODE}")
    print(f"  Filters active:")
    print(f"    ADX_MAX       = {settings.VWAP_MR_ADX_MAX or 'off'}")
    print(f"    ZSCORE_ENTRY  = {settings.VWAP_MR_ZSCORE_ENTRY or 'off'}")
    print(f"    VOLUME_SPIKE  = {settings.VWAP_MR_VOLUME_SPIKE or 'off'}")
    print(f"    MIN_RR        = {settings.VWAP_MR_MIN_RR or 'off'}")
    print(f"    VWAP_CROSS    = {settings.VWAP_MR_VWAP_CROSS_MIN or 'off'}")
    print(f"    RSI_CONFIRM   = {settings.VWAP_MR_RSI_CONFIRM}")
    print(f"    MIN_SCORE     = {settings.VWAP_MR_MIN_SCORE or 'off'}")
    print(f"  Risk mode      : {'swing_sl (Mode D)' if settings.USE_SWING_SL else 'spot_atr (Mode C)'}")
    print(f"  ATR params     : period={settings.SPOT_ATR_PERIOD}, "
          f"sl_mult={settings.SPOT_ATR_SL_MULT}, "
          f"rr={settings.SPOT_ATR_TARGET_RR}, delta={settings.ATM_DELTA}")
    print(f"{SEP}{RESET}\n")

    try:
        signals = scan(target, warm_days=args.days)
    except Exception as exc:
        msg = str(exc).lower()
        if any(k in msg for k in ("token", "unauthori", "403", "session")):
            print(f"\n{RED}{BOLD}Authentication error: {exc}{RESET}")
            print(f"{YELLOW}Your Zerodha access token is expired or invalid.")
            print(f"  1. Open http://127.0.0.1:{settings.__dict__.get('DASHBOARD_PORT', 5000)}")
            print(f"  2. Click 'Login with Zerodha' and complete OAuth")
            print(f"  3. Re-run this script{RESET}")
        else:
            print(f"\n{RED}Error: {exc}{RESET}")
            raise
        sys.exit(1)

    _print_summary(signals, target)


if __name__ == "__main__":
    main()
