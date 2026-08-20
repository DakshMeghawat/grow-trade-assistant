import pytest

from grow_trade_assistant.analysis.benchmark_comparison import compare_portfolio_to_benchmark
from grow_trade_assistant.analysis.metrics import PortfolioSummary, PositionMetrics
from grow_trade_assistant.providers.yahoo_finance import StockMarketData


def _summary() -> PortfolioSummary:
    positions = [
        PositionMetrics(
            trading_symbol="A",
            exchange="NSE",
            quantity=10,
            average_price=100,
            last_price=110,
            market_value=1100,
            cost_basis=1000,
            unrealized_pnl=100,
            unrealized_pnl_pct=10,
            weight_pct=60,
        ),
        PositionMetrics(
            trading_symbol="B",
            exchange="NSE",
            quantity=5,
            average_price=200,
            last_price=180,
            market_value=900,
            cost_basis=1000,
            unrealized_pnl=-100,
            unrealized_pnl_pct=-10,
            weight_pct=40,
        ),
    ]
    return PortfolioSummary(
        snapshot_id=1,
        captured_at="2026-01-01",
        total_value=2000,
        total_cost=2000,
        total_unrealized_pnl=0,
        total_unrealized_pnl_pct=0,
        positions=positions,
    )


def test_benchmark_comparison_alpha():
    summary = _summary()
    market_data = {
        "NIFTY": StockMarketData(
            symbol="NIFTY",
            last_price=24000,
            previous_close=23900,
            return_1y_pct=12.0,
            return_3y_pct=30.0,
            volatility_30d=15.0,
            week_52_high=25000,
            week_52_low=20000,
            ma50=23000,
            ma200=22000,
        ),
        "A": StockMarketData(
            symbol="A",
            last_price=110,
            previous_close=108,
            return_1y_pct=20.0,
            return_3y_pct=50.0,
            volatility_30d=20.0,
            week_52_high=120,
            week_52_low=80,
            ma50=105,
            ma200=95,
        ),
        "B": StockMarketData(
            symbol="B",
            last_price=180,
            previous_close=175,
            return_1y_pct=5.0,
            return_3y_pct=10.0,
            volatility_30d=18.0,
            week_52_high=220,
            week_52_low=150,
            ma50=190,
            ma200=185,
        ),
    }
    result = compare_portfolio_to_benchmark(summary, market_data, "NIFTY")
    assert result is not None
    # 0.6*20 + 0.4*5 = 14
    assert result["portfolio_weighted_return_1y_pct"] == pytest.approx(14.0)
    assert result["alpha_vs_benchmark_pct"] == pytest.approx(2.0)
    assert result["claim_type"] == "calculated"
