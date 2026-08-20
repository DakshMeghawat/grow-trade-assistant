import pytest

from grow_trade_assistant.features.indicators import (
    atr,
    compute_technical_features,
    macd,
    moving_average,
    rsi,
)


def _sample_candles(n: int = 100, base: float = 100.0) -> list[dict[str, float]]:
    candles = []
    for i in range(n):
        c = base + i * 0.5
        candles.append({"open": c - 0.2, "high": c + 1, "low": c - 1, "close": c})
    return candles


def test_rsi_bounds():
    closes = [c["close"] for c in _sample_candles(30)]
    value = rsi(closes, 14)
    assert value is not None
    assert 0 <= value <= 100


def test_macd_returns_tuple():
    closes = [c["close"] for c in _sample_candles(60)]
    m, s, h = macd(closes)
    assert m is not None
    assert s is not None
    assert h == pytest.approx(m - s, rel=1e-6)


def test_atr_from_ohlc():
    candles = _sample_candles(20)
    value = atr(candles, 14)
    assert value is not None
    assert value > 0


def test_compute_technical_features_populates_all():
    candles = _sample_candles(300)
    closes = [c["close"] for c in candles]
    f = compute_technical_features(closes, candles)
    assert f.ma50 is not None
    assert f.ma200 is not None
    assert f.rsi14 is not None
    assert f.macd is not None
    assert f.atr14 is not None


def test_moving_average_matches_features():
    closes = [c["close"] for c in _sample_candles(60)]
    assert moving_average(closes, 50) == pytest.approx(
        compute_technical_features(closes).ma50
    )
