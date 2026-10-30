"""
Test CPR and FVG calculations in ui/app.py.
Verifies that today's in-progress daily candle is excluded, ensuring CPR
and Pivot levels remain static based strictly on the previous completed trading day.
"""

from datetime import datetime, timedelta
import pytest
from unittest.mock import MagicMock, patch
import pytz

from utils.time_utils import IST


def test_api_fvg_excludes_today_forming_candle():
    from ui.app import app

    now_ist = datetime.now(IST)
    today = now_ist.date()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)
    three_days_ago = today - timedelta(days=3)

    # Mock Zerodha daily candles: 3 completed days + 1 live/forming candle for today
    mock_candles = [
        {"date": datetime(three_days_ago.year, three_days_ago.month, three_days_ago.day), "open": 71000, "high": 71500, "low": 70800, "close": 71200, "volume": 1000},
        {"date": datetime(day_before.year, day_before.month, day_before.day), "open": 71200, "high": 71800, "low": 71100, "close": 71600, "volume": 1200},
        # Yesterday (last completed trading session): High=72000, Low=71000, Close=71500
        {"date": datetime(yesterday.year, yesterday.month, yesterday.day), "open": 71600, "high": 72000.0, "low": 71000.0, "close": 71500.0, "volume": 1500},
        # Today (in-progress live candle with fluctuating prices): High=73000, Low=70000, Close=72500
        {"date": datetime(today.year, today.month, today.day), "open": 71500, "high": 73000.0, "low": 70000.0, "close": 72500.0, "volume": 500},
    ]

    mock_kite = MagicMock()
    mock_kite.historical_data.return_value = mock_candles

    with patch("ui.app._get_kite_safe", return_value=mock_kite):
        client = app.test_client()
        res = client.get("/api/fvg")
        assert res.status_code == 200
        data = res.get_json()

        assert "error" not in data
        assert data["prev_ohlc"]["date"] == str(yesterday)
        assert data["prev_ohlc"]["high"] == 72000.0
        assert data["prev_ohlc"]["low"] == 71000.0
        assert data["prev_ohlc"]["close"] == 71500.0

        # CPR calculated from yesterday: H=72000, L=71000, C=71500
        # P = (72000 + 71000 + 71500) / 3 = 71500.0
        # BC = (72000 + 71000) / 2 = 71500.0
        # TC = 2 * 71500 - 71500 = 71500.0
        cpr = data["cpr"]
        assert cpr["pivot"] == 71500.0
        assert cpr["bc"] == 71500.0
        assert cpr["tc"] == 71500.0
