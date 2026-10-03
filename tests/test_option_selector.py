"""
Tests for the ATM option selector and ITM fallback.
Uses a mock instrument list — no real Zerodha connection needed.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from execution.option_selector import select_atm_candidates, select_atm_option


_EXPIRY = date(2026, 9, 18)

# Instruments covering strikes 79000–80000 for both CE and PE.
_FAKE_INSTRUMENTS = [
    {"tradingsymbol": "SENSEX26SEP79000CE", "instrument_token": 1001, "strike": 79000,
     "expiry": "2026-09-18", "name": "SENSEX", "instrument_type": "CE",
     "segment": "BFO-OPT", "exchange": "BFO", "lot_size": 20},
    {"tradingsymbol": "SENSEX26SEP79500CE", "instrument_token": 1002, "strike": 79500,
     "expiry": "2026-09-18", "name": "SENSEX", "instrument_type": "CE",
     "segment": "BFO-OPT", "exchange": "BFO", "lot_size": 20},
    {"tradingsymbol": "SENSEX26SEP80000CE", "instrument_token": 1003, "strike": 80000,
     "expiry": "2026-09-18", "name": "SENSEX", "instrument_type": "CE",
     "segment": "BFO-OPT", "exchange": "BFO", "lot_size": 20},
    {"tradingsymbol": "SENSEX26SEP79000PE", "instrument_token": 2001, "strike": 79000,
     "expiry": "2026-09-18", "name": "SENSEX", "instrument_type": "PE",
     "segment": "BFO-OPT", "exchange": "BFO", "lot_size": 20},
    {"tradingsymbol": "SENSEX26SEP79500PE", "instrument_token": 2002, "strike": 79500,
     "expiry": "2026-09-18", "name": "SENSEX", "instrument_type": "PE",
     "segment": "BFO-OPT", "exchange": "BFO", "lot_size": 20},
    {"tradingsymbol": "SENSEX26SEP80000PE", "instrument_token": 2003, "strike": 80000,
     "expiry": "2026-09-18", "name": "SENSEX", "instrument_type": "PE",
     "segment": "BFO-OPT", "exchange": "BFO", "lot_size": 20},
]


def _mock_load(_force=False):
    return _FAKE_INSTRUMENTS


# ── Existing ATM selection tests (behaviour unchanged) ────────────────────────

class TestOptionSelector:
    def test_atm_ce_nearest(self) -> None:
        with patch("broker.instrument_repository.load_instruments", side_effect=_mock_load):
            result = select_atm_option(79300, "CE", _EXPIRY)
        assert result["strike"] == 79500  # nearest to 79300 among 79000, 79500, 80000

    def test_atm_ce_exact_match(self) -> None:
        with patch("broker.instrument_repository.load_instruments", side_effect=_mock_load):
            result = select_atm_option(79500, "CE", _EXPIRY)
        assert result["strike"] == 79500

    def test_atm_pe_nearest(self) -> None:
        with patch("broker.instrument_repository.load_instruments", side_effect=_mock_load):
            result = select_atm_option(79100, "PE", _EXPIRY)
        assert result["strike"] == 79000  # 79000 is 100 away; 79500 is 400 away

    def test_returns_correct_fields(self) -> None:
        with patch("broker.instrument_repository.load_instruments", side_effect=_mock_load):
            result = select_atm_option(79500, "CE", _EXPIRY)
        assert "tradingsymbol" in result
        assert "instrument_token" in result
        assert "expiry" in result
        assert "lot_size" in result

    def test_raises_on_no_instruments(self) -> None:
        with patch("broker.instrument_repository.load_instruments", return_value=[]):
            with pytest.raises(ValueError):
                select_atm_option(79500, "CE", _EXPIRY)


# ── ITM candidate list tests ──────────────────────────────────────────────────

class TestSelectAtmCandidates:
    """Tests for select_atm_candidates — the ordered ATM + ITM fallback list."""

    def test_ce_first_candidate_is_atm(self) -> None:
        with patch("broker.instrument_repository.load_instruments", side_effect=_mock_load):
            candidates = select_atm_candidates(79300, "CE", _EXPIRY)
        # ATM for 79300 CE = 79500 (nearest)
        assert candidates[0]["strike"] == 79500

    def test_ce_itm_fallback_is_lower_strike(self) -> None:
        """For CE, ITM means lower strike (lower strike = deeper in the money for a call)."""
        with patch("broker.instrument_repository.load_instruments", side_effect=_mock_load):
            candidates = select_atm_candidates(79300, "CE", _EXPIRY)
        # CE: ATM=79500, ITM step 1 = 79500-100=79400 (not in fake data) → 79000
        # With step_size=100 and only 79000/79500/80000 in fake data, next available is 79000
        strikes = [c["strike"] for c in candidates]
        # All strikes must be ≤ ATM for CE (deeper ITM = lower)
        atm = candidates[0]["strike"]
        for c in candidates[1:]:
            assert c["strike"] < atm

    def test_pe_first_candidate_is_atm(self) -> None:
        with patch("broker.instrument_repository.load_instruments", side_effect=_mock_load):
            candidates = select_atm_candidates(79300, "PE", _EXPIRY)
        # ATM for 79300 PE = 79000 (nearest: 79000 is 300 away, 79500 is 200 away) → 79500
        # 79300 is 200 from 79500 and 300 from 79000, so ATM = 79500
        assert candidates[0]["strike"] == 79500

    def test_pe_itm_fallback_is_higher_strike(self) -> None:
        """For PE, ITM means higher strike (higher strike = deeper in the money for a put)."""
        with patch("broker.instrument_repository.load_instruments", side_effect=_mock_load):
            candidates = select_atm_candidates(79300, "PE", _EXPIRY)
        atm = candidates[0]["strike"]
        for c in candidates[1:]:
            assert c["strike"] > atm

    def test_candidates_list_only_includes_existing_strikes(self) -> None:
        """Only strikes present in the instrument master appear in candidates."""
        with patch("broker.instrument_repository.load_instruments", side_effect=_mock_load):
            candidates = select_atm_candidates(79300, "CE", _EXPIRY, steps=5)
        # Only 79000, 79500, 80000 exist — CE ITM goes lower, so from 79500: 79400 missing,
        # 79300 missing, ... only 79000 present
        strikes = {c["strike"] for c in candidates}
        assert all(s in {79000.0, 79500.0, 80000.0} for s in strikes)

    def test_steps_zero_returns_only_atm(self) -> None:
        with patch("broker.instrument_repository.load_instruments", side_effect=_mock_load):
            candidates = select_atm_candidates(79500, "CE", _EXPIRY, steps=0)
        assert len(candidates) == 1
        assert candidates[0]["strike"] == 79500

    def test_raises_on_no_instruments(self) -> None:
        with patch("broker.instrument_repository.load_instruments", return_value=[]):
            with pytest.raises(ValueError):
                select_atm_candidates(79500, "CE", _EXPIRY)

    def test_no_duplicates_in_candidates(self) -> None:
        with patch("broker.instrument_repository.load_instruments", side_effect=_mock_load):
            candidates = select_atm_candidates(79500, "CE", _EXPIRY)
        strikes = [c["strike"] for c in candidates]
        assert len(strikes) == len(set(strikes))

    def test_returns_correct_typed_dicts(self) -> None:
        with patch("broker.instrument_repository.load_instruments", side_effect=_mock_load):
            candidates = select_atm_candidates(79500, "CE", _EXPIRY)
        for c in candidates:
            assert "tradingsymbol" in c
            assert "instrument_token" in c
            assert "strike" in c
            assert "expiry" in c
            assert "exchange" in c
            assert "lot_size" in c


# ── Sep 30 regression: 14:10 PE OTM → ITM fallback scenario ──────────────────

class TestItmFallbackRegressionSep30:
    """
    Reproduces the Sep 30 14:10 scenario:
      SENSEX=72787.51, nearest PE strike=72800 (OTM).
      Candidate list should include 72900PE (one step ITM) as fallback.
    """

    _SEP30_INSTRUMENTS = [
        {"tradingsymbol": "SENSEX26O0172700PE", "instrument_token": 3001, "strike": 72700,
         "expiry": "2026-10-01", "name": "SENSEX", "instrument_type": "PE",
         "segment": "BFO-OPT", "exchange": "BFO", "lot_size": 20},
        {"tradingsymbol": "SENSEX26O0172800PE", "instrument_token": 3002, "strike": 72800,
         "expiry": "2026-10-01", "name": "SENSEX", "instrument_type": "PE",
         "segment": "BFO-OPT", "exchange": "BFO", "lot_size": 20},
        {"tradingsymbol": "SENSEX26O0172900PE", "instrument_token": 3003, "strike": 72900,
         "expiry": "2026-10-01", "name": "SENSEX", "instrument_type": "PE",
         "segment": "BFO-OPT", "exchange": "BFO", "lot_size": 20},
        {"tradingsymbol": "SENSEX26O0173000PE", "instrument_token": 3004, "strike": 73000,
         "expiry": "2026-10-01", "name": "SENSEX", "instrument_type": "PE",
         "segment": "BFO-OPT", "exchange": "BFO", "lot_size": 20},
    ]

    _EXPIRY_SEP30 = date(2026, 10, 1)

    def _load(self, _force=False):
        return self._SEP30_INSTRUMENTS

    def test_atm_is_72800_pe(self) -> None:
        with patch("broker.instrument_repository.load_instruments", side_effect=self._load):
            candidates = select_atm_candidates(72787.51, "PE", self._EXPIRY_SEP30)
        assert candidates[0]["strike"] == 72800.0

    def test_itm_fallback_is_72900_pe(self) -> None:
        """72900PE is one step ITM (higher strike) from the 72800 ATM."""
        with patch("broker.instrument_repository.load_instruments", side_effect=self._load):
            candidates = select_atm_candidates(72787.51, "PE", self._EXPIRY_SEP30)
        assert len(candidates) >= 2
        assert candidates[1]["strike"] == 72900.0

    def test_itm_fallback_step2_is_73000_pe(self) -> None:
        """Two steps ITM: 72800 → 72900 → 73000."""
        with patch("broker.instrument_repository.load_instruments", side_effect=self._load):
            candidates = select_atm_candidates(72787.51, "PE", self._EXPIRY_SEP30, steps=2)
        strikes = [c["strike"] for c in candidates]
        assert 73000.0 in strikes

    def test_tradingsymbols_match_strikes(self) -> None:
        with patch("broker.instrument_repository.load_instruments", side_effect=self._load):
            candidates = select_atm_candidates(72787.51, "PE", self._EXPIRY_SEP30)
        assert candidates[0]["tradingsymbol"] == "SENSEX26O0172800PE"
        assert candidates[1]["tradingsymbol"] == "SENSEX26O0172900PE"
