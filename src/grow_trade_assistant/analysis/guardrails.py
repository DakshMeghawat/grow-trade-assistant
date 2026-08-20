from __future__ import annotations

from datetime import datetime, timezone

from grow_trade_assistant.analysis.metrics import PortfolioSummary, PositionMetrics
from grow_trade_assistant.config import Settings


def check_concentration(
    summary: PortfolioSummary, settings: Settings
) -> list[str]:
    warnings: list[str] = []
    for p in summary.positions:
        if p.weight_pct > settings.max_single_stock_weight:
            warnings.append(
                f"{p.trading_symbol} is {p.weight_pct:.1f}% of portfolio "
                f"(limit: {settings.max_single_stock_weight:.0f}%). "
                "High single-stock concentration increases risk if that company underperforms."
            )
    return warnings


def within_cooldown(
    store_last: str | None, cooldown_days: int
) -> bool:
    if not store_last:
        return False
    last = datetime.fromisoformat(store_last)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - last
    return delta.days < cooldown_days
