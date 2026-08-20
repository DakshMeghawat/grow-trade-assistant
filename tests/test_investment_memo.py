from grow_trade_assistant.analysis.investment_memo import build_investment_memo
from grow_trade_assistant.analysis.metrics import PositionMetrics, summarize_portfolio


def test_memo_prioritises_hdfc_when_concentrated():
    p = PositionMetrics(
        trading_symbol="HDFCBANK",
        exchange="NSE",
        quantity=100,
        average_price=800,
        last_price=720,
        market_value=72000,
        cost_basis=80000,
        unrealized_pnl=-8000,
        unrealized_pnl_pct=-10,
        weight_pct=80,
    )
    summary = summarize_portfolio(1, "t", [p])
    memo = build_investment_memo(summary, [], 72000, 80000, 0, 0)
    titles = " ".join(s["title"] for s in memo["this_quarter"])
    assert "HDFC" in titles
    assert memo["stock_theses"][0]["name"] == "HDFCBANK"
    assert "Bought" in memo["stock_theses"][0]["bought"] or "₹" in memo["stock_theses"][0]["bought"]
