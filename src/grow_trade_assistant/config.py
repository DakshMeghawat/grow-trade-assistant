from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from grow_trade_assistant.secrets import emit_security_warnings, load_secrets_into_env

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    groww_api_key: str
    groww_api_secret: str
    groww_auth_mode: str
    groww_totp: str | None
    groww_access_token: str | None
    groww_api_base_url: str
    groww_api_version: str
    max_single_stock_weight: float
    max_sector_weight: float
    min_cash_buffer_percent: float
    rebalance_cooldown_days: int
    benchmark_symbol: str
    benchmark_exchange: str
    data_dir: Path
    reports_dir: Path
    schedule_time: str
    timezone: str
    mutual_funds_path: Path | None
    price_source: str
    fetch_news: bool
    stocks_path: Path | None = None


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill in your credentials."
        )
    return value


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def load_settings(env_file: Path | None = None, require_groww: bool = True) -> Settings:
    if env_file:
        load_dotenv(env_file, override=False)
    else:
        load_dotenv(override=False)

    # Prefer macOS Keychain (encrypted) over plain .env for credentials
    security_warnings = load_secrets_into_env()
    if security_warnings:
        emit_security_warnings(security_warnings)

    auth_mode = os.getenv("GROWW_AUTH_MODE", "approval").strip().lower()
    access_token = os.getenv("GROWW_ACCESS_TOKEN", "").strip() or None

    api_key = os.getenv("GROWW_API_KEY", "").strip()
    api_secret = os.getenv("GROWW_API_SECRET", "").strip()

    if require_groww and not access_token:
        if auth_mode == "approval" and (not api_key or not api_secret):
            raise ValueError(
                "Groww credentials not found. Store them securely with:\n"
                "  grow-assistant secrets set\n"
                "Or import a Groww CSV/XLSX (no API needed):\n"
                "  grow-assistant import holdings.xlsx --kind stocks\n"
                "  grow-assistant import mf.xlsx --kind mf\n"
                "  grow-assistant analyze --offline"
            )
        if auth_mode == "totp" and not api_key:
            raise ValueError(
                "GROWW_API_KEY not found. Run: grow-assistant secrets set"
            )

    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    reports_dir = Path(os.getenv("REPORTS_DIR", "./reports"))
    mf_path = os.getenv("MUTUAL_FUNDS_PATH", "./mutual_funds.json").strip()
    mutual_funds_path = Path(mf_path) if mf_path else None
    stocks_raw = os.getenv("STOCKS_PATH", "./stocks.json").strip()
    stocks_path = Path(stocks_raw) if stocks_raw else None

    return Settings(
        groww_api_key=api_key,
        groww_api_secret=api_secret,
        groww_auth_mode=auth_mode,
        groww_totp=os.getenv("GROWW_TOTP", "").strip() or None,
        groww_access_token=access_token,
        groww_api_base_url=os.getenv(
            "GROWW_API_BASE_URL", "https://api.groww.in"
        ).rstrip("/"),
        groww_api_version=os.getenv("GROWW_API_VERSION", "1.0"),
        max_single_stock_weight=_float("MAX_SINGLE_STOCK_WEIGHT", 15.0),
        max_sector_weight=_float("MAX_SECTOR_WEIGHT", 30.0),
        min_cash_buffer_percent=_float("MIN_CASH_BUFFER_PERCENT", 5.0),
        rebalance_cooldown_days=_int("REBALANCE_COOLDOWN_DAYS", 30),
        benchmark_symbol=os.getenv("BENCHMARK_SYMBOL", "NIFTY"),
        benchmark_exchange=os.getenv("BENCHMARK_EXCHANGE", "NSE"),
        data_dir=data_dir,
        reports_dir=reports_dir,
        schedule_time=os.getenv("SCHEDULE_TIME", "18:00"),
        timezone=os.getenv("TIMEZONE", "Asia/Kolkata"),
        mutual_funds_path=mutual_funds_path,
        price_source=os.getenv("PRICE_SOURCE", "yahoo").strip().lower(),
        fetch_news=os.getenv("FETCH_NEWS", "true").strip().lower() in ("1", "true", "yes"),
        stocks_path=stocks_path,
    )
