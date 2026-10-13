"""
Tests for NATR Trailing Stop strategy (ATR 5 Min Index Study),
specifically verifying that candle color checks prevent false entries on gap-opens.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import pytz

from market.candle_builder import Candle
from strategies.natr_strategy import is_natr_ce_signal, is_natr_pe_signal

IST = pytz.timezone("Asia/Kolkata")


def _make_candles_series(
    prev_prices: list[tuple[float, float, float, float]],
    last_candle: tuple[float, float, float, float],
) -> list[Candle]:
    """
    Construct a list of Candles ending at current IST time.
    Each tuple is (open, high, low, close).
    """
    now = datetime.now(IST)
    all_tuples = prev_prices + [last_candle]
    count = len(all_tuples)
    candles = []
    for i, (o, h, l, c) in enumerate(all_tuples):
        ts = now - timedelta(minutes=5 * (count - 1 - i))
        candles.append(
            Candle(
                timestamp=ts,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=1000,
            )
        )
    return candles


class TestNatrCandleColorCheck:
    def test_ce_natr_allowed_on_green_candle(self) -> None:
        """When crossing above NATR stop and candle is GREEN (close > open) -> True."""
        # Decreasing series so NATR trailing stop is above price in a downtrend
        prev = []
        p = 72500.0
        for _ in range(29):
            prev.append((p + 10.0, p + 20.0, p - 20.0, p))
            p -= 20.0  # ends around 71920 with stop above close
        # Last candle crosses above stop and is GREEN (open=71920, close=72200)
        last = (71920.0, 72250.0, 71900.0, 72200.0)
        candles = _make_candles_series(prev, last)

        assert is_natr_ce_signal(candles) is True

    def test_ce_natr_blocked_on_red_candle(self) -> None:
        """When crossing above NATR stop but candle is RED (close <= open) -> False."""
        prev = []
        p = 72500.0
        for _ in range(29):
            prev.append((p + 10.0, p + 20.0, p - 20.0, p))
            p -= 20.0
        # Last candle has gap open to 72300, but sells off and closes at 72150 (RED)
        last = (72300.0, 72350.0, 72100.0, 72150.0)
        candles = _make_candles_series(prev, last)

        assert is_natr_ce_signal(candles) is False

    def test_pe_natr_allowed_on_red_candle(self) -> None:
        """When crossing below NATR stop and candle is RED (close < open) -> True."""
        # Increasing series so NATR trailing stop is below price in an uptrend
        prev = []
        p = 71500.0
        for _ in range(29):
            prev.append((p - 10.0, p + 20.0, p - 20.0, p))
            p += 20.0  # ends around 72080 with stop below close
        # Last candle crosses below stop and is RED (open=72080, close=71800)
        last = (72080.0, 72100.0, 71750.0, 71800.0)
        candles = _make_candles_series(prev, last)

        assert is_natr_pe_signal(candles) is True

    def test_pe_natr_blocked_on_green_candle(self) -> None:
        """When crossing below NATR stop but candle is GREEN (close >= open) -> False."""
        prev = []
        p = 71500.0
        for _ in range(29):
            prev.append((p - 10.0, p + 20.0, p - 20.0, p))
            p += 20.0
        # Last candle has gap down to 71700, but bounces and closes at 71850 (GREEN)
        last = (71700.0, 71900.0, 71650.0, 71850.0)
        candles = _make_candles_series(prev, last)

        assert is_natr_pe_signal(candles) is False
