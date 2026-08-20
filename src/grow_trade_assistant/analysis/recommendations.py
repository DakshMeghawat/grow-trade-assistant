from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from grow_trade_assistant.analysis.guardrails import check_concentration, within_cooldown
from grow_trade_assistant.analysis.metrics import PortfolioSummary, PositionMetrics
from grow_trade_assistant.cache.store import DataStore
from grow_trade_assistant.config import Settings


class Action(str, Enum):
    KEEP = "keep"
    MONITOR = "monitor"
    RESEARCH = "research"
    REBALANCE_CANDIDATE = "rebalance-candidate"


@dataclass
class Recommendation:
    symbol: str
    action: Action
    rank: int
    evidence: list[str]
    counterpoints: list[str]
    learning_note: str


def rank_recommendations(
    summary: PortfolioSummary,
    settings: Settings,
    store: DataStore,
) -> list[Recommendation]:
    recs: list[Recommendation] = []
    concentration = check_concentration(summary, settings)

    for p in summary.positions:
        evidence: list[str] = []
        counterpoints: list[str] = []
        action = Action.KEEP

        if p.weight_pct > settings.max_single_stock_weight:
            if within_cooldown(
                store.last_recommendation(p.trading_symbol, Action.REBALANCE_CANDIDATE.value),
                settings.rebalance_cooldown_days,
            ):
                action = Action.MONITOR
                evidence.append("Previously flagged for rebalance; in cooldown period.")
            else:
                action = Action.REBALANCE_CANDIDATE
                evidence.append(
                    f"Weight {p.weight_pct:.1f}% exceeds {settings.max_single_stock_weight:.0f}% limit."
                )
                counterpoints.append(
                    "High weight may be intentional if you have high conviction in this business."
                )
                store.record_recommendation(
                    p.trading_symbol, Action.REBALANCE_CANDIDATE.value
                )

        elif p.trend == "downtrend":
            action = Action.MONITOR
            evidence.append("Price below 50-day and 200-day averages (downtrend).")
            counterpoints.append(
                "Long-term investors sometimes add during downtrends if fundamentals remain strong."
            )

        elif p.unrealized_pnl_pct > 100:
            action = Action.RESEARCH
            evidence.append(
                f"Large unrealized gain ({p.unrealized_pnl_pct:.0f}%). "
                "Consider whether to trim for diversification."
            )
            counterpoints.append(
                "Selling winners too early can reduce long-term compounding."
            )

        elif p.volatility_30d and p.volatility_30d > 0.4:
            action = Action.MONITOR
            evidence.append(
                f"Elevated 30-day volatility ({p.volatility_30d:.0%} annualized)."
            )

        if p.max_drawdown_1y and p.max_drawdown_1y > 30:
            if action == Action.KEEP:
                action = Action.MONITOR
            evidence.append(
                f"Max drawdown over cached history: {p.max_drawdown_1y:.1f}%."
            )

        rank_score = _rank_score(action, p)
        recs.append(
            Recommendation(
                symbol=p.trading_symbol,
                action=action,
                rank=rank_score,
                evidence=evidence or ["No major flags; position looks stable for long-term hold."],
                counterpoints=counterpoints or ["Markets can change quickly; review quarterly."],
                learning_note=_learning_note(p),
            )
        )

    recs.sort(key=lambda r: r.rank, reverse=True)
    summary.concentration_warnings = concentration
    return recs


def _rank_score(action: Action, p: PositionMetrics) -> int:
    base = {
        Action.REBALANCE_CANDIDATE: 100,
        Action.RESEARCH: 70,
        Action.MONITOR: 40,
        Action.KEEP: 10,
    }[action]
    return base + int(p.weight_pct or 0)


def _learning_note(p: PositionMetrics) -> str:
    if p.ma50 and p.ma200:
        return (
            f"Moving averages smooth out daily noise. {p.trading_symbol}'s 50-day MA is "
            f"₹{p.ma50:,.0f} and 200-day MA is ₹{p.ma200:,.0f}. "
            f"Price above both often signals an uptrend, but it is not a buy/sell signal on its own."
        )
    return (
        "Moving averages need at least 50–200 days of price history. "
        "Run a few more daily reports to build this data in the local cache."
    )


def pick_featured_learning(recs: list[Recommendation]) -> str:
    for r in recs:
        if r.action in (Action.REBALANCE_CANDIDATE, Action.MONITOR):
            return r.learning_note
    return recs[0].learning_note if recs else (
        "Portfolio weight = (stock value ÷ total portfolio value) × 100. "
        "Keeping any single stock below ~15% reduces company-specific risk."
    )
