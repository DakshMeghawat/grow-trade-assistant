import json
from pathlib import Path

import pytest

from grow_trade_assistant.analysis.metrics import build_position_metrics, summarize_portfolio
from grow_trade_assistant.report.renderer import render_markdown_report, write_reports


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_payload():
    holdings = json.loads((FIXTURES / "holdings.json").read_text())["payload"]["holdings"]
    ltp = json.loads((FIXTURES / "ltp.json").read_text())["payload"]
    candles = {h["trading_symbol"]: [{"close": h["average_price"]}] for h in holdings}
    positions = build_position_metrics(holdings, ltp, candles)
    summary = summarize_portfolio(42, "2026-08-19T12:00:00+00:00", positions)
    return {
        "generated_at": "2026-08-19T18:30:00+05:30",
        "snapshot_id": 42,
        "portfolio": {
            "total_value": summary.total_value,
            "total_cost": summary.total_cost,
            "total_unrealized_pnl": summary.total_unrealized_pnl,
            "total_unrealized_pnl_pct": summary.total_unrealized_pnl_pct,
            "positions": [
                {
                    "trading_symbol": p.trading_symbol,
                    "quantity": p.quantity,
                    "last_price": p.last_price,
                    "market_value": p.market_value,
                    "weight_pct": p.weight_pct,
                    "unrealized_pnl_pct": p.unrealized_pnl_pct,
                    "trend": p.trend,
                }
                for p in summary.positions
            ],
        },
        "changes_since_last": ["First report"],
        "concentration_warnings": [],
        "recommendations": [],
        "learning_note": "Test learning note about portfolio weight.",
        "data_sources": {
            "broker": "Groww API",
            "fundamentals": "placeholder",
            "limitations": ["Test limitation"],
        },
        "checklist": ["Review concentration"],
    }


def test_render_markdown_contains_sections(sample_payload):
    md = render_markdown_report(sample_payload, lambda x: f"₹{x:,.2f}")
    assert "# Portfolio Report" in md
    assert "## Portfolio Health" in md
    assert "## Learning Note" in md
    assert "Disclaimer" in md
    assert "RELIANCE" in md


def test_write_reports(tmp_path, sample_payload):
    md = render_markdown_report(sample_payload, lambda x: f"₹{x:,.2f}")
    paths = write_reports(tmp_path, sample_payload, md)
    assert paths["markdown"].exists()
    assert paths["json"].exists()
    saved = json.loads(paths["json"].read_text())
    assert saved["snapshot_id"] == 42
