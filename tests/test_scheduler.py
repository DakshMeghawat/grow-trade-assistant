import json
from pathlib import Path

import pytest
from grow_trade_assistant.scheduler import is_market_day, seconds_until_next_run
from grow_trade_assistant.config import Settings
from datetime import datetime
from zoneinfo import ZoneInfo


@pytest.fixture
def settings(tmp_path):
    return Settings(
        groww_api_key="k",
        groww_api_secret="s",
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


def test_is_market_day_weekday():
    monday = datetime(2026, 8, 17, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert is_market_day(monday) is True


def test_is_market_day_weekend():
    saturday = datetime(2026, 8, 22, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert is_market_day(saturday) is False


def test_seconds_until_next_run_positive(settings):
    assert seconds_until_next_run(settings) > 0
