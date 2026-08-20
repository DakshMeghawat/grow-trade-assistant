import json
from pathlib import Path

import pytest

from grow_trade_assistant.analysis.metrics import (
    build_position_metrics,
    classify_trend,
    format_inr,
    max_drawdown,
    moving_average,
    summarize_portfolio,
    volatility,
)
from grow_trade_assistant.analysis.recommendations import Action, rank_recommendations
from grow_trade_assistant.cache.store import DataStore
from grow_trade_assistant.config import Settings


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def holdings():
    return json.loads((FIXTURES / "holdings.json").read_text())["payload"]["holdings"]


@pytest.fixture
def ltp_map():
    return json.loads((FIXTURES / "ltp.json").read_text())["payload"]


@pytest.fixture
def settings(tmp_path):
    return Settings(
        groww_api_key="key",
        groww_api_secret="secret",
        groww_auth_mode="approval",
        groww_totp=None,
        groww_access_token=None,
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


def test_moving_average():
    closes = list(range(1, 51))
    assert moving_average(closes, 50) == pytest.approx(25.5)
    assert moving_average(closes, 51) is None


def test_classify_trend():
    assert classify_trend(110, 100, 90) == "uptrend"
    assert classify_trend(80, 90, 100) == "downtrend"
    assert classify_trend(100, 90, 100) == "mixed"


def test_max_drawdown():
    closes = [100, 120, 80, 90]
    assert max_drawdown(closes) == pytest.approx(33.333, rel=0.01)


def test_build_position_metrics(holdings, ltp_map):
    candles = {"RELIANCE": [{"close": 2400 + i * 10} for i in range(60)]}
    positions = build_position_metrics(holdings, ltp_map, candles)
    assert len(positions) == 2
    assert positions[0].market_value == 10 * 2650.0


def test_summarize_portfolio(holdings, ltp_map):
    candles = {h["trading_symbol"]: [{"close": h["average_price"]}] for h in holdings}
    positions = build_position_metrics(holdings, ltp_map, candles)
    summary = summarize_portfolio(1, "2026-01-01T00:00:00+00:00", positions)
    assert summary.total_value > 0
    assert abs(sum(p.weight_pct for p in summary.positions) - 100) < 0.01


def test_rank_rebalance_candidate(holdings, ltp_map, settings, tmp_path):
    candles = {h["trading_symbol"]: [{"close": h["average_price"]}] for h in holdings}
    positions = build_position_metrics(holdings, ltp_map, candles)
    for p in positions:
        p.weight_pct = 50.0 if p.trading_symbol == "RELIANCE" else 50.0
    summary = summarize_portfolio(1, "2026-01-01T00:00:00+00:00", positions)

    with DataStore(tmp_path / "test.db") as store:
        recs = rank_recommendations(summary, settings, store)
        rebalance = [r for r in recs if r.action == Action.REBALANCE_CANDIDATE]
        assert len(rebalance) >= 1


def test_format_inr():
    assert format_inr(1234.5) == "₹1,234.50"
