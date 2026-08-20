from pathlib import Path

from grow_trade_assistant.groww_import import parse_groww_file
from grow_trade_assistant.report.deep_renderer import render_deep_markdown


def test_parse_groww_stocks_csv(tmp_path: Path):
    csv = tmp_path / "stocks.csv"
    csv.write_text(
        "Trading Symbol,Quantity,Average Price,Invested Value\n"
        "HDFCBANK,105,774.43,81315.15\n"
        "RELIANCE,26,1322.42,34382.92\n",
        encoding="utf-8",
    )
    result = parse_groww_file(csv, kind="stocks")
    symbols = {h["trading_symbol"] for h in result.stocks}
    assert symbols == {"HDFCBANK", "RELIANCE"}
    hdfc = next(h for h in result.stocks if h["trading_symbol"] == "HDFCBANK")
    assert hdfc["quantity"] == 105
    assert abs(hdfc["invested_value"] - 81315.15) < 0.01


def test_parse_groww_mf_csv_merges_folios(tmp_path: Path, monkeypatch):
    csv = tmp_path / "mf.csv"
    csv.write_text(
        "Scheme Name,Category,Sub-category,Folio No.,Units,Invested Value\n"
        "JM Flexicap Fund Direct Plan Growth,Equity,Flexi Cap,1,57.108,5999.72\n"
        "JM Flexicap Fund Direct Plan Growth,Equity,Flexi Cap,2,181.174,19998.84\n",
        encoding="utf-8",
    )

    def fake_search(query, limit=8):
        return [{"scheme_code": "120492", "name": "JM Flexicap Fund (Direct) - Growth Option"}]

    monkeypatch.setattr("grow_trade_assistant.mf_config.search_schemes", fake_search)
    result = parse_groww_file(csv, kind="mf")
    assert len(result.mutual_funds) == 1
    fund = result.mutual_funds[0]
    assert abs(fund["units"] - 238.282) < 0.001
    assert fund["scheme_code"] == "120492"


def test_report_has_invested_vs_current_and_suggestions():
    payload = {
        "generated_at": "2026-08-20T10:00:00+05:30",
        "snapshot_id": 1,
        "portfolio": {
            "total_value": 2000,
            "total_cost": 1800,
            "total_unrealized_pnl": 200,
            "total_unrealized_pnl_pct": 11.1,
            "positions": [
                {
                    "trading_symbol": "HDFCBANK",
                    "quantity": 2,
                    "average_price": 700,
                    "cost_basis": 1400,
                    "last_price": 720,
                    "market_value": 1440,
                    "unrealized_pnl": 40,
                    "unrealized_pnl_pct": 2.9,
                    "weight_pct": 72.0,
                }
            ],
        },
        "deep_analysis": {
            "combined_value": 3000,
            "combined_cost": 2500,
            "combined_pnl": 500,
            "combined_pnl_pct": 20.0,
            "stocks_value": 2000,
            "stocks_cost": 1800,
            "mf_value": 1000,
            "mf_cost": 700,
            "stocks_weight_pct": 66.7,
            "mf_weight_pct": 33.3,
            "stock_market_data": {},
            "mutual_funds": [
                {
                    "name": "Parag Parikh Flexi Cap",
                    "units": 10,
                    "avg_nav": 70,
                    "cost_basis": 700,
                    "current_nav": 100,
                    "market_value": 1000,
                    "unrealized_pnl": 300,
                    "unrealized_pnl_pct": 42.9,
                    "return_1y_pct": 5.0,
                }
            ],
            "sector_weights": {"Financials": 48.0},
            "strategy": {
                "headline": "Test headline",
                "score": 40,
                "strengths": ["MF core is working"],
                "weaknesses": ["HDFC too large"],
                "suggestions": [
                    {
                        "bucket": "trim",
                        "asset_type": "stock",
                        "name": "HDFCBANK",
                        "invested": 1400,
                        "current": 1440,
                        "pnl": 40,
                        "pnl_pct": 2.9,
                        "weight_pct": 48.0,
                        "why": "Weight exceeds 15%",
                        "suggestion": "Trim gradually",
                        "counter": "Conviction hold is valid",
                    }
                ],
                "reallocation_plan": ["Reduce bank concentration"],
            },
            "news": {},
        },
        "learning_note": "Weight equals position value divided by total.",
        "checklist": ["Check concentration"],
        "data_sources": {"broker": "import", "limitations": []},
    }
    md = render_deep_markdown(payload, lambda x: f"₹{x:,.2f}")
    assert "This quarter" in md or "Investment memo" in md
    assert "Bought price" in md
    assert "Sell price (today)" in md
    assert "Suggestion report" in md
    assert "HDFCBANK" in md
    assert "Parag Parikh" in md
    assert "**Why:** Weight exceeds 15%" in md
