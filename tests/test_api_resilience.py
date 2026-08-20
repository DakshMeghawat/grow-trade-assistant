from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from grow_trade_assistant.domain.provenance import (
    ClaimType,
    build_report_provenance,
    staleness_warning,
)
from grow_trade_assistant.ingestion.result import IngestionResult
from grow_trade_assistant.pipeline.stages import fetch_prices_yahoo
from grow_trade_assistant.pipeline import run_analysis
from grow_trade_assistant.providers.yahoo_finance import YahooFinanceProvider


@pytest.fixture
def settings(tmp_path):
    from grow_trade_assistant.config import Settings

    return Settings(
        groww_api_key="key",
        groww_api_secret="secret",
        groww_auth_mode="approval",
        groww_totp=None,
        groww_access_token="token",
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


def test_yahoo_total_failure_falls_back_to_avg_buy():
    holdings = [{"trading_symbol": "RELIANCE", "quantity": 10, "average_price": 2500.0}]
    yahoo = MagicMock(spec=YahooFinanceProvider)
    yahoo.get_prices.return_value = {}

    with patch("grow_trade_assistant.pipeline.stages.YahooFinanceProvider", return_value=yahoo):
        prices, ingestion, _ = fetch_prices_yahoo(["RELIANCE"], holdings, "NIFTY")

    assert prices["NSE_RELIANCE"] == 2500.0
    assert any("unavailable" in w for w in ingestion.warnings)


def test_yahoo_exception_in_offline_mode_continues(settings, tmp_path):
    import json
    from pathlib import Path

    fixtures = Path(__file__).parent / "fixtures"
    holdings = json.loads((fixtures / "holdings.json").read_text())["payload"]["holdings"]
    ltp = json.loads((fixtures / "ltp.json").read_text())["payload"]

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    from grow_trade_assistant.cache.store import DataStore

    with DataStore(settings.data_dir / "portfolio.db") as store:
        store.save_snapshot(holdings, [])
        store.cache_ltp("CASH", ltp)

    with patch("grow_trade_assistant.pipeline.stages.fetch_prices_yahoo", side_effect=RuntimeError("network down")):
        result = run_analysis(settings, offline=True)

    assert result["portfolio"]["total_value"] > 0
    assert any("skipped" in w.lower() or "network" in w.lower() for w in result["data_warnings"])


def test_staleness_warning_old_cache():
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    msg = staleness_warning(old, max_age_hours=24)
    assert msg is not None
    assert "48" in msg or "old" in msg.lower()


def test_staleness_warning_fresh_cache():
    fresh = datetime.now(timezone.utc).isoformat()
    assert staleness_warning(fresh, max_age_hours=24) is None


def test_provenance_includes_claim_types(settings, tmp_path):
    import json
    from pathlib import Path

    fixtures = Path(__file__).parent / "fixtures"
    holdings = json.loads((fixtures / "holdings.json").read_text())["payload"]["holdings"]
    ltp = json.loads((fixtures / "ltp.json").read_text())["payload"]

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    from grow_trade_assistant.cache.store import DataStore

    with DataStore(settings.data_dir / "portfolio.db") as store:
        store.save_snapshot(holdings, [])
        store.cache_ltp("CASH", ltp)
        for h in holdings:
            store.upsert_candles(
                "NSE",
                h["trading_symbol"],
                [[1704067200 + i * 86400, 2400, 2500, 2300, 2450, 1000] for i in range(60)],
            )

    mock_provider = MagicMock()
    mock_provider.get_full_data.return_value = None

    with patch("grow_trade_assistant.pipeline.stages.fetch_prices_yahoo") as mock_yahoo:
        mock_yahoo.return_value = (ltp, IngestionResult(), mock_provider)
        result = run_analysis(settings, offline=True)

    prov = result["provenance"]
    assert "claim_legend" in prov
    assert ClaimType.CALCULATED.value in prov["claim_legend"]
    assert ClaimType.LLM_INTERPRETATION.value in prov["claim_legend"]
    assert any(r["field"] == "investment_memo.stock_theses" for r in prov["records"])
