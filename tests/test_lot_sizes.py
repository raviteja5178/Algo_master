"""
Unit tests for configurable lot sizes across indices (SENSEX=20, NIFTY=65, FINNIFTY=60, etc.).
"""

from __future__ import annotations

import os
from unittest.mock import patch
import pytest

from config import settings
from execution.option_selector import _make_instrument, get_strike_step
from datetime import date


class TestLotSizes:
    """Test lot size resolution and configurability."""

    def test_default_lot_sizes(self) -> None:
        """Verify standard default lot sizes."""
        assert settings.get_lot_size("SENSEX") == 20
        assert settings.get_lot_size("NIFTY") == 65
        assert settings.get_lot_size("FINNIFTY") == 60
        assert settings.get_lot_size("FINIFTY") == 60
        assert settings.get_lot_size("BANKNIFTY") == 15
        assert settings.get_lot_size("BANKEX") == 15
        assert settings.get_lot_size("MIDCPNIFTY") == 120

    def test_normalize_index_name(self) -> None:
        """Verify name variations resolve to standard index keys."""
        assert settings.normalize_index_name("SENSEX") == "SENSEX"
        assert settings.normalize_index_name("BSE:SENSEX") == "SENSEX"
        assert settings.normalize_index_name("NIFTY 50") == "NIFTY"
        assert settings.normalize_index_name("NSE:NIFTY 50") == "NIFTY"
        assert settings.normalize_index_name("NIFTY50") == "NIFTY"
        assert settings.normalize_index_name("NIFTY FIN SERVICE") == "FINNIFTY"
        assert settings.normalize_index_name("FINIFTY") == "FINNIFTY"
        assert settings.normalize_index_name("NSE:FINNIFTY") == "FINNIFTY"
        assert settings.normalize_index_name("NIFTY BANK") == "BANKNIFTY"
        assert settings.normalize_index_name("NSE:NIFTY BANK") == "BANKNIFTY"
        assert settings.normalize_index_name("BANKEX") == "BANKEX"
        assert settings.normalize_index_name("BSE:BANKEX") == "BANKEX"

    def test_get_quantity_calculation(self) -> None:
        """Verify get_quantity computes lot_size * num_lots correctly."""
        assert settings.get_quantity("SENSEX", num_lots=1) == 20
        assert settings.get_quantity("SENSEX", num_lots=2) == 40
        assert settings.get_quantity("NIFTY", num_lots=1) == 65
        assert settings.get_quantity("NIFTY", num_lots=3) == 195
        assert settings.get_quantity("FINNIFTY", num_lots=1) == 60
        assert settings.get_quantity("FINNIFTY", num_lots=2) == 120

    def test_per_index_env_override(self) -> None:
        """Verify individual index env variables override lot sizes."""
        with patch.dict(os.environ, {"NIFTY_LOT_SIZE": "50", "FINNIFTY_LOT_SIZE": "40"}):
            loaded = settings._load_lot_sizes()
            assert loaded["NIFTY"] == 50
            assert loaded["FINNIFTY"] == 40
            assert loaded["SENSEX"] == 20

    def test_lot_qty_and_alias_env_override(self) -> None:
        """Verify LOT_QTY and FINIFTY alias env overrides."""
        with patch.dict(os.environ, {
            "SENSEX_LOT_QTY": "20",
            "NIFTY_LOT_QTY": "65",
            "FINIFTY_LOT_QTY": "60",
        }):
            loaded = settings._load_lot_sizes()
            assert loaded["SENSEX"] == 20
            assert loaded["NIFTY"] == 65
            assert loaded["FINNIFTY"] == 60
            assert loaded["FINIFTY"] == 60

    def test_index_lot_sizes_comma_string(self) -> None:
        """Verify comma-separated INDEX_LOT_SIZES override."""
        with patch.dict(os.environ, {"INDEX_LOT_SIZES": "SENSEX:10,NIFTY:50,FINNIFTY:40", "SENSEX_LOT_SIZE": ""}):
            loaded = settings._load_lot_sizes()
            assert loaded["SENSEX"] == 10
            assert loaded["NIFTY"] == 50
            assert loaded["FINNIFTY"] == 40

    def test_index_lot_sizes_json_string(self) -> None:
        """Verify JSON-formatted INDEX_LOT_SIZES override."""
        with patch.dict(os.environ, {"INDEX_LOT_SIZES": '{"SENSEX": 25, "NIFTY": 75, "FINNIFTY": 50}', "SENSEX_LOT_SIZE": ""}):
            loaded = settings._load_lot_sizes()
            assert loaded["SENSEX"] == 25
            assert loaded["NIFTY"] == 75
            assert loaded["FINNIFTY"] == 50

    def test_option_instrument_lot_size_fallback(self) -> None:
        """Verify _make_instrument extracts lot_size or falls back to index default."""
        exp = date(2026, 11, 5)
        # Instrument with explicit lot_size
        row1 = {
            "tradingsymbol": "NIFTY26NOV24000CE",
            "instrument_token": 1234,
            "strike": 24000,
            "lot_size": 65,
        }
        inst1 = _make_instrument(row1, exp)
        assert inst1["lot_size"] == 65

        # Instrument missing lot_size with UNDERLYING=NIFTY
        row2 = {
            "tradingsymbol": "NIFTY26NOV24000CE",
            "instrument_token": 1235,
            "strike": 24000,
        }
        with patch.object(settings, "UNDERLYING", "NIFTY"):
            inst2 = _make_instrument(row2, exp)
            assert inst2["lot_size"] == 65

    def test_strike_step_by_underlying(self) -> None:
        """Verify standard strike steps (50 for NIFTY/FINNIFTY, 100 for SENSEX/BANKNIFTY)."""
        assert get_strike_step("SENSEX") == 100
        assert get_strike_step("BANKNIFTY") == 100
        assert get_strike_step("NIFTY") == 50
        assert get_strike_step("FINNIFTY") == 50
        assert get_strike_step("FINIFTY") == 50

    def test_spot_tokens_and_exchange_symbols(self) -> None:
        """Verify spot tokens and exchange quote symbols for NIFTY and FINNIFTY."""
        from market.historical_data import get_spot_token, get_exchange_symbol
        assert get_spot_token("SENSEX") == 265
        assert get_spot_token("NIFTY") == 256265
        assert get_spot_token("NSE:NIFTY 50") == 256265
        assert get_spot_token("FINNIFTY") == 257801
        assert get_spot_token("NIFTY FIN SERVICE") == 257801

        assert get_exchange_symbol("SENSEX") == "BSE:SENSEX"
        assert get_exchange_symbol("NIFTY") == "NSE:NIFTY 50"
        assert get_exchange_symbol("FINNIFTY") == "NSE:NIFTY FIN SERVICE"
