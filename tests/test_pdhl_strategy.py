"""Tests for the Previous Day High/Low (PDHL) Breakout strategy."""
from __future__ import annotations

from datetime import datetime, date
import pytest

from market.candle_builder import Candle
from strategies.pdhl_strategy import is_pdhl_ce_signal, is_pdhl_pe_signal

_TODAY = date.today()


def _ts(h: int, m: int) -> datetime:
    return datetime(_TODAY.year, _TODAY.month, _TODAY.day, h, m)


def _candle(h: int, m: int, o: float, hi: float, lo: float, c: float) -> Candle:
    return Candle(_ts(h, m), open=o, high=hi, low=lo, close=c)


# ── is_pdhl_ce_signal ─────────────────────────────────────────────────────────

class TestPDHLCESignal:

    def test_ce_clean_breakout(self):
        pdh = 74000.0
        # prev close at/below PDH, current close above PDH and above prev high
        prev = _candle(10, 0, 73990, 74000, 73970, 73995)
        curr = _candle(10, 5, 73995, 74060, 73993, 74050)
        assert is_pdhl_ce_signal([prev, curr], pdh) is True

    def test_ce_no_breakout(self):
        pdh = 74000.0
        prev = _candle(10, 0, 73990, 74000, 73970, 73995)
        curr = _candle(10, 5, 73995, 74010, 73993, 73998)  # close below PDH
        assert is_pdhl_ce_signal([prev, curr], pdh) is False

    def test_ce_not_fresh_crossover(self):
        pdh = 74000.0
        # prev already above PDH → not a fresh crossover
        prev = _candle(10, 0, 74000, 74050, 73995, 74020)
        curr = _candle(10, 5, 74020, 74080, 74015, 74060)
        assert is_pdhl_ce_signal([prev, curr], pdh) is False

    def test_ce_no_momentum(self):
        pdh = 74000.0
        prev = _candle(10, 0, 73990, 74040, 73970, 73995)  # high=74040
        curr = _candle(10, 5, 73995, 74045, 73993, 74030)  # close=74030 < prev high=74040
        assert is_pdhl_ce_signal([prev, curr], pdh) is False

    def test_ce_pdh_none(self):
        prev = _candle(10, 0, 73990, 74000, 73970, 73995)
        curr = _candle(10, 5, 73995, 74060, 73993, 74050)
        assert is_pdhl_ce_signal([prev, curr], None) is False

    def test_ce_with_buffer(self):
        pdh = 74000.0
        prev = _candle(10, 0, 73990, 74000, 73970, 73995)
        curr = _candle(10, 5, 73995, 74060, 73993, 74010)
        # close=74010, PDH=74000, buffer=20 → level=74020, 74010 < 74020 → blocked
        assert is_pdhl_ce_signal([prev, curr], pdh, buffer_pts=20) is False
        # buffer=5 → level=74005, 74010 > 74005 → passes (if momentum ok)
        curr2 = _candle(10, 5, 73995, 74015, 73993, 74010)
        prev2 = _candle(10, 0, 73990, 74005, 73970, 73995)
        assert is_pdhl_ce_signal([prev2, curr2], pdh, buffer_pts=5) is True

    def test_ce_too_few_candles(self):
        pdh = 74000.0
        curr = _candle(10, 5, 73995, 74060, 73993, 74050)
        assert is_pdhl_ce_signal([curr], pdh) is False


# ── is_pdhl_pe_signal ─────────────────────────────────────────────────────────

class TestPDHLPESignal:

    def test_pe_clean_breakout(self):
        pdl = 73500.0
        prev = _candle(10, 0, 73510, 73530, 73500, 73505)
        curr = _candle(10, 5, 73505, 73508, 73440, 73450)
        assert is_pdhl_pe_signal([prev, curr], pdl) is True

    def test_pe_no_breakout(self):
        pdl = 73500.0
        prev = _candle(10, 0, 73510, 73530, 73500, 73505)
        curr = _candle(10, 5, 73505, 73510, 73495, 73502)  # close above PDL
        assert is_pdhl_pe_signal([prev, curr], pdl) is False

    def test_pe_not_fresh_crossover(self):
        pdl = 73500.0
        # prev already below PDL
        prev = _candle(10, 0, 73490, 73498, 73460, 73470)
        curr = _candle(10, 5, 73470, 73475, 73420, 73430)
        assert is_pdhl_pe_signal([prev, curr], pdl) is False

    def test_pe_no_momentum(self):
        pdl = 73500.0
        prev = _candle(10, 0, 73510, 73530, 73460, 73505)  # low=73460
        curr = _candle(10, 5, 73505, 73510, 73462, 73465)  # close=73465 > prev low=73460
        assert is_pdhl_pe_signal([prev, curr], pdl) is False

    def test_pe_pdl_none(self):
        prev = _candle(10, 0, 73510, 73530, 73500, 73505)
        curr = _candle(10, 5, 73505, 73508, 73440, 73450)
        assert is_pdhl_pe_signal([prev, curr], None) is False

    def test_pe_with_buffer(self):
        pdl = 73500.0
        prev = _candle(10, 0, 73510, 73530, 73500, 73505)
        curr = _candle(10, 5, 73505, 73508, 73440, 73490)
        # close=73490, PDL=73500, buffer=20 → level=73480, 73490 > 73480 → blocked
        assert is_pdhl_pe_signal([prev, curr], pdl, buffer_pts=20) is False
