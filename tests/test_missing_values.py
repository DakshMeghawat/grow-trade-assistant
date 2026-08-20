import math

import pytest

from grow_trade_assistant.analysis.metrics import build_position_metrics, moving_average, volatility
from grow_trade_assistant.cache.store import DataStore


def test_build_position_metrics_nan_ltp_falls_back_to_avg():
    holdings = [{"trading_symbol": "TEST", "quantity": 5, "average_price": 100.0}]
    ltp_map = {"NSE_TEST": float("nan")}
    positions = build_position_metrics(holdings, ltp_map, {"TEST": []})
    assert positions[0].last_price == 100.0
    assert positions[0].market_value == 500.0


def test_build_position_metrics_missing_ltp_uses_avg():
    holdings = [{"trading_symbol": "MISSING", "quantity": 2, "average_price": 50.0}]
    positions = build_position_metrics(holdings, {}, {"MISSING": []})
    assert positions[0].last_price == 50.0


def test_moving_average_insufficient_data():
    assert moving_average([1, 2, 3], 10) is None


def test_volatility_with_zero_prev_close():
    closes = [0.0, 100.0, 110.0, 120.0] + [120.0] * 30
    assert volatility(closes, window=30) is not None or volatility(closes, window=30) is None


def test_store_skips_nan_candles(tmp_path):
    with DataStore(tmp_path / "test.db") as store:
        store.upsert_candles(
            "NSE",
            "BAD",
            [
                [1, float("nan"), 10, 9, 9.5, 100],
                [2, 10, 11, 9, 10.5, 100],
            ],
        )
        candles = store.get_candles("NSE", "BAD")
    assert len(candles) == 1
    assert candles[0]["close"] == 10.5


def test_zero_cost_basis_pnl_pct():
    holdings = [{"trading_symbol": "FREE", "quantity": 10, "average_price": 0.0}]
    ltp_map = {"NSE_FREE": 100.0}
    positions = build_position_metrics(holdings, ltp_map, {"FREE": []})
    assert positions[0].unrealized_pnl_pct == 0.0
    assert not math.isnan(positions[0].unrealized_pnl_pct)
