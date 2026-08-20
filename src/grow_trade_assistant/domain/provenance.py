from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ClaimType(str, Enum):
    """How a value in a report should be interpreted."""

    REPORTED = "reported"  # From broker, exchange, regulator, or fund house
    CALCULATED = "calculated"  # Deterministic formula on reported inputs
    MODEL_PREDICTION = "model_prediction"  # Forecast from a quantitative model
    LLM_INTERPRETATION = "llm_interpretation"  # Narrative synthesis — not a fact


@dataclass(frozen=True)
class DataProvenance:
    field: str
    claim_type: ClaimType
    source: str
    source_url: str | None = None
    fetched_at: str | None = None
    as_of_date: str | None = None
    raw_ref: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["claim_type"] = self.claim_type.value
        return d


def staleness_warning(fetched_at: str | None, max_age_hours: float = 24.0) -> str | None:
    """Return a warning if cached data exceeds max_age_hours."""
    if not fetched_at:
        return "Price timestamp unknown — treat as potentially stale."
    try:
        ts = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        if age_h > max_age_hours:
            return f"Cached price is {age_h:.1f}h old (>{max_age_hours:.0f}h threshold)."
    except ValueError:
        return "Price timestamp unparseable — treat as potentially stale."
    return None


def build_report_provenance(
    *,
    generated_at: str,
    benchmark_symbol: str,
    has_groww: bool,
    has_yahoo: bool,
    has_mf: bool,
    has_news: bool,
) -> dict[str, Any]:
    """Standard provenance block attached to every report JSON."""
    records: list[DataProvenance] = [
        DataProvenance(
            field="portfolio.holdings",
            claim_type=ClaimType.REPORTED,
            source="Groww API or imported Groww CSV/XLSX",
            source_url="https://groww.in/trade-api/docs/curl",
            fetched_at=generated_at,
            notes="Quantity and average buy price from broker snapshot.",
        ),
        DataProvenance(
            field="portfolio.positions[].last_price",
            claim_type=ClaimType.REPORTED,
            source="Yahoo Finance NSE (.NS) with optional Groww LTP overlay",
            source_url="https://ranaroussi.github.io/yfinance/",
            fetched_at=generated_at,
            notes="Mark-to-market; not a executed trade price.",
        ),
        DataProvenance(
            field="portfolio.positions[].ma50|ma200|volatility|drawdown",
            claim_type=ClaimType.CALCULATED,
            source="grow_trade_assistant.analysis.metrics",
            fetched_at=generated_at,
            notes="Computed from cached daily OHLCV candles.",
        ),
        DataProvenance(
            field="deep_analysis.benchmark_return_1y",
            claim_type=ClaimType.CALCULATED,
            source=f"Yahoo Finance ({benchmark_symbol})",
            source_url="https://github.com/ranaroussi/yfinance",
            notes="Point-in-time 1Y return from daily closes; not backtested.",
        ),
        DataProvenance(
            field="investment_memo.stock_theses",
            claim_type=ClaimType.LLM_INTERPRETATION,
            source="Cursor-maintained SYMBOL_BRIEFS (static)",
            notes="Education only. Verify against filings and primary sources.",
        ),
        DataProvenance(
            field="recommendations",
            claim_type=ClaimType.CALCULATED,
            source="grow_trade_assistant.analysis.recommendations",
            notes="Rule engine on concentration, trend, cooldown — not predictive.",
        ),
    ]
    if has_mf:
        records.append(
            DataProvenance(
                field="deep_analysis.mutual_funds",
                claim_type=ClaimType.REPORTED,
                source="MFApi.in NAV",
                source_url="https://www.mfapi.in/",
                fetched_at=generated_at,
                notes="NAV and scheme metadata; units from mutual_funds.json.",
            )
        )
    if has_news:
        records.append(
            DataProvenance(
                field="deep_analysis.news",
                claim_type=ClaimType.REPORTED,
                source="Google News RSS",
                source_url="https://news.google.com/",
                notes="Headlines only — verify publication date and primary source.",
            )
        )
    if not has_groww:
        records.append(
            DataProvenance(
                field="portfolio.holdings",
                claim_type=ClaimType.REPORTED,
                source="Imported file or SQLite cache (Groww API unavailable)",
                notes="May not reflect same-day broker state.",
            )
        )
    return {
        "claim_legend": {ct.value: ct.name.replace("_", " ").title() for ct in ClaimType},
        "records": [r.to_dict() for r in records],
        "disclaimer": (
            "Nothing in this report is a guarantee of future returns or financial advice. "
            "Model predictions (when present) include uncertainty; LLM interpretations are "
            "synthesis only and must be verified against primary sources."
        ),
    }
