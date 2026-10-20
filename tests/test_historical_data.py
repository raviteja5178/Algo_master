"""Bootstrap must not seed the still-forming candle (mid-candle restart artifact)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from market import historical_data as hd


def test_is_still_forming():
    start = datetime(2026, 10, 19, 12, 15)
    assert hd.is_still_forming(start, "5minute", datetime(2026, 10, 19, 12, 15, 3))
    assert hd.is_still_forming(start, "5minute", datetime(2026, 10, 19, 12, 19, 59))
    assert not hd.is_still_forming(start, "5minute", datetime(2026, 10, 19, 12, 20))
    assert not hd.is_still_forming(start, "5minute", datetime(2026, 10, 19, 12, 21))
    assert not hd.is_still_forming(start, "bogus", datetime(2026, 10, 19, 12, 15, 3))


def _rec(h: int, m: int, close: float) -> dict:
    return {"date": datetime(2026, 10, 19, h, m), "open": close, "high": close,
            "low": close, "close": close, "volume": 0}


def test_fetch_drops_forming_candle():
    kite = MagicMock()
    kite.historical_data.return_value = [_rec(12, 5, 1.0), _rec(12, 10, 2.0), _rec(12, 15, 3.0)]
    fixed_now = hd.IST.localize(datetime(2026, 10, 19, 12, 15, 3))
    with patch.object(hd, "get_kite", return_value=kite), \
         patch.object(hd, "datetime") as dt:
        dt.now.return_value = fixed_now
        out = hd.fetch_historical_candles(265, "5minute", days_back=1)
    assert [c.close for c in out] == [1.0, 2.0]
