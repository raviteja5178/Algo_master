import pytest

from config import settings


def test_sensex_is_never_scaled():
    assert settings.index_scale("SENSEX", 82000.0) == 1.0
    assert settings.index_scale("SENSEX", 40000.0) == 1.0


def test_nifty_and_finnifty_scale_with_index_level(monkeypatch):
    monkeypatch.setattr(settings, "INDEX_SCALE_REF_LEVEL", 82000.0)
    assert settings.index_scale("NIFTY", 25300.0) == pytest.approx(25300 / 82000)
    assert settings.index_scale("FINNIFTY", 27700.0) == pytest.approx(27700 / 82000)


def test_scaled_sensex_tuned_values_for_nifty(monkeypatch):
    monkeypatch.setattr(settings, "INDEX_SCALE_REF_LEVEL", 82000.0)
    f = settings.index_scale("NIFTY", 25300.0)
    assert 10 * f == pytest.approx(3.09, abs=0.01)     # pullback tolerance
    assert 270 * f == pytest.approx(83.3, abs=0.1)     # premium floor


def test_scaling_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings, "INDEX_SCALE_REF_LEVEL", 0.0)
    assert settings.index_scale("NIFTY", 25300.0) == 1.0


@pytest.mark.parametrize("price", [None, 0, -5])
def test_missing_price_is_unscaled(price):
    assert settings.index_scale("NIFTY", price) == 1.0


def test_scale_is_clamped(monkeypatch):
    monkeypatch.setattr(settings, "INDEX_SCALE_REF_LEVEL", 82000.0)
    assert settings.index_scale("NIFTY", 1000.0) == 0.1
    assert settings.index_scale("BANKNIFTY", 500000.0) == 1.5
