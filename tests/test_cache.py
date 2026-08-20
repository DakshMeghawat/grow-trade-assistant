import json
from pathlib import Path

import pytest

from grow_trade_assistant.cache.store import DataStore


def test_snapshot_roundtrip(tmp_path):
    with DataStore(tmp_path / "test.db") as store:
        holdings = [{"trading_symbol": "RELIANCE", "quantity": 10}]
        positions = []
        sid = store.save_snapshot(holdings, positions)
        latest = store.get_latest_snapshot()
        assert latest is not None
        assert latest["id"] == sid
        assert latest["holdings"][0]["trading_symbol"] == "RELIANCE"


def test_ltp_cache(tmp_path):
    with DataStore(tmp_path / "test.db") as store:
        store.cache_ltp("CASH", {"NSE_RELIANCE": 2500.0})
        cached = store.get_cached_ltp("CASH")
        assert cached["NSE_RELIANCE"] == 2500.0


def test_candle_upsert_and_read(tmp_path):
    with DataStore(tmp_path / "test.db") as store:
        candles = [[1704067200, 100, 110, 90, 105, 1000]]
        store.upsert_candles("NSE", "RELIANCE", candles)
        result = store.get_candles("NSE", "RELIANCE")
        assert len(result) == 1
        assert result[0]["close"] == 105


def test_recommendation_history(tmp_path):
    with DataStore(tmp_path / "test.db") as store:
        store.record_recommendation("RELIANCE", "rebalance-candidate")
        last = store.last_recommendation("RELIANCE", "rebalance-candidate")
        assert last is not None
