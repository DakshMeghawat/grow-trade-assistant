import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from grow_trade_assistant.config import Settings
from grow_trade_assistant.pipeline import run_analysis


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        groww_api_key="test_key",
        groww_api_secret="test_secret",
        groww_auth_mode="approval",
        groww_totp=None,
        groww_access_token="fake_token_for_tests",
        groww_api_base_url="https://api.groww.in",
        groww_api_version="1.0",
        max_single_stock_weight=15.0,
        max_sector_weight=30.0,
        min_cash_buffer_percent=5.0,
        rebalance_cooldown_days=30,
        benchmark_symbol="NIFTY",
        benchmark_exchange="NSE",
        data_dir=tmp_path / "data",
        reports_dir=tmp_path / "reports",
        schedule_time="18:00",
        timezone="Asia/Kolkata",
        mutual_funds_path=None,
        price_source="yahoo",
        fetch_news=False,
    )


def test_offline_analysis(settings):
    holdings = json.loads((FIXTURES / "holdings.json").read_text())["payload"]["holdings"]
    positions = json.loads((FIXTURES / "positions.json").read_text())["payload"]["positions"]
    ltp = json.loads((FIXTURES / "ltp.json").read_text())["payload"]

    db_path = settings.data_dir / "portfolio.db"
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    from grow_trade_assistant.cache.store import DataStore

    with DataStore(db_path) as store:
        store.save_snapshot(holdings, positions)
        store.cache_ltp("CASH", ltp)
        for h in holdings:
            store.upsert_candles(
                "NSE",
                h["trading_symbol"],
                [[1704067200 + i * 86400, 2400, 2500, 2300, 2450, 1000] for i in range(60)],
            )

    result = run_analysis(settings, offline=True)
    assert result["snapshot_id"] >= 1
    assert result["portfolio"]["total_value"] > 0
    assert Path(result["report_paths"]["markdown"]).exists()
