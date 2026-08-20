from __future__ import annotations

from typing import Any

from grow_trade_assistant.analysis.metrics import PortfolioSummary
from grow_trade_assistant.providers.yahoo_finance import StockMarketData


def compare_portfolio_to_benchmark(
    summary: PortfolioSummary,
    stock_market_data: dict[str, StockMarketData],
    benchmark_symbol: str,
) -> dict[str, Any] | None:
    """
    Weighted 1Y stock return vs benchmark 1Y return.
    Uses current portfolio weights — educational snapshot, not a backtest.
    """
    bench = stock_market_data.get(benchmark_symbol)
    if not bench or bench.return_1y_pct is None:
        return None

    weighted_return = 0.0
    weight_sum = 0.0
    symbols_with_data = 0
    for p in summary.positions:
        sd = stock_market_data.get(p.trading_symbol)
        if sd and sd.return_1y_pct is not None:
            weighted_return += p.weight_pct * sd.return_1y_pct
            weight_sum += p.weight_pct
            symbols_with_data += 1

    if symbols_with_data == 0:
        return None

    portfolio_1y = weighted_return / weight_sum if weight_sum else None
    alpha = (portfolio_1y - bench.return_1y_pct) if portfolio_1y is not None else None

    return {
        "claim_type": "calculated",
        "benchmark_symbol": benchmark_symbol,
        "benchmark_return_1y_pct": bench.return_1y_pct,
        "portfolio_weighted_return_1y_pct": portfolio_1y,
        "alpha_vs_benchmark_pct": alpha,
        "symbols_with_1y_data": symbols_with_data,
        "coverage_pct": weight_sum,
        "notes": (
            "Point-in-time weighted average of Yahoo 1Y returns using today's weights. "
            "Not a backtested portfolio return — holdings may have changed over the year."
        ),
        "counterpoints": [
            "Does not reflect when you bought each name.",
            "Survivorship: only current holdings included.",
            "Past performance is not indicative of future results.",
        ],
    }
