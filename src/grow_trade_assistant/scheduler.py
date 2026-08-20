from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from grow_trade_assistant.config import Settings
from grow_trade_assistant.pipeline import run_analysis

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")


def _parse_schedule(time_str: str) -> tuple[int, int]:
    parts = time_str.split(":")
    return int(parts[0]), int(parts[1])


def is_market_day(dt: datetime | None = None) -> bool:
    """Weekday check for NSE (Mon–Fri). Holidays not modeled in v1."""
    dt = dt or datetime.now(IST)
    return dt.weekday() < 5


def seconds_until_next_run(settings: Settings) -> float:
    now = datetime.now(IST)
    hour, minute = _parse_schedule(settings.schedule_time)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    while not is_market_day(target):
        target += timedelta(days=1)
    return (target - now).total_seconds()


def run_scheduled_loop(settings: Settings) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Scheduler started. EOD reports on Indian market weekdays at %s IST.", settings.schedule_time)

    while True:
        wait = seconds_until_next_run(settings)
        logger.info("Next run in %.0f seconds.", wait)
        time.sleep(wait)
        if is_market_day():
            try:
                result = run_analysis(settings)
                logger.info("Report written: %s", result.get("report_paths"))
            except Exception:
                logger.exception("Scheduled analysis failed")
        time.sleep(60)
