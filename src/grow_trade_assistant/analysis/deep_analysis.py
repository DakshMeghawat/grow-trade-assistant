from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from grow_trade_assistant.analysis.metrics import PortfolioSummary, format_inr
from grow_trade_assistant.analysis.recommendations import Recommendation
from grow_trade_assistant.analysis.sectors import CORE_DIVERSIFIERS, SECTOR_CANDIDATES, SECTOR_MAP
from grow_trade_assistant.providers.mfapi import MutualFundHolding
from grow_trade_assistant.providers.news import NewsItem
from grow_trade_assistant.providers.yahoo_finance import StockMarketData


@dataclass
class Suggestion:
    bucket: str
    asset_type: str
    name: str
    invested: float
    current: float
    pnl: float
    pnl_pct: float
    weight_pct: float
    why: str
    suggestion: str
    counter: str


@dataclass
class StrategyVerdict:
    headline: str
    score: int  # 0-100 diversification health
    strengths: list[str]
    weaknesses: list[str]
    actions_keep: list[str]
    actions_trim: list[str]
    actions_research: list[str]
    actions_consider_buy: list[str]
    mf_notes: list[str]
    reallocation_plan: list[str]
    suggestions: list[Suggestion] = field(default_factory=list)


@dataclass
class DeepAnalysisResult:
    stock_market_data: dict[str, StockMarketData]
    sector_weights: dict[str, float]
    mutual_funds: list[MutualFundHolding]
    combined_value: float
    stocks_value: float
    mf_value: float
    stocks_weight_pct: float
    mf_weight_pct: float
    stocks_cost: float
    mf_cost: float
    combined_cost: float
    combined_pnl: float
    combined_pnl_pct: float
    news: dict[str, list[NewsItem]]
    strategy: StrategyVerdict
    benchmark_return_1y: float | None = None


def run_deep_analysis(
    summary: PortfolioSummary,
    recommendations: list[Recommendation],
    stock_data: dict[str, StockMarketData],
    mf_holdings: list[MutualFundHolding],
    news: dict[str, list[NewsItem]],
    settings_max_weight: float,
) -> DeepAnalysisResult:
    stocks_value = summary.total_value
    stocks_cost = summary.total_cost
    mf_value = sum(m.market_value for m in mf_holdings)
    mf_cost = sum(m.cost_basis for m in mf_holdings)
    combined = stocks_value + mf_value
    combined_cost = stocks_cost + mf_cost
    combined_pnl = combined - combined_cost
    combined_pnl_pct = (combined_pnl / combined_cost * 100) if combined_cost else 0.0
    stocks_pct = (stocks_value / combined * 100) if combined else 100.0
    mf_pct = (mf_value / combined * 100) if combined else 0.0

    sector_values: dict[str, float] = {}
    for p in summary.positions:
        sector = SECTOR_MAP.get(p.trading_symbol, "Other")
        sector_values[sector] = sector_values.get(sector, 0) + p.market_value
    for m in mf_holdings:
        cat = m.category.split(" - ")[0] if " - " in m.category else m.category
        sector_values[f"MF: {cat}"] = sector_values.get(f"MF: {cat}", 0) + m.market_value

    sector_weights = {
        k: (v / combined * 100) if combined else 0 for k, v in sorted(sector_values.items(), key=lambda x: -x[1])
    }

    benchmark = stock_data.get("^NSEI") or stock_data.get("NIFTY")
    bench_ret = benchmark.return_1y_pct if benchmark else None

    strategy = _build_strategy(
        summary, recommendations, stock_data, mf_holdings,
        sector_weights, stocks_pct, mf_pct, settings_max_weight, bench_ret,
        combined,
    )

    return DeepAnalysisResult(
        stock_market_data=stock_data,
        sector_weights=sector_weights,
        mutual_funds=mf_holdings,
        combined_value=combined,
        stocks_value=stocks_value,
        mf_value=mf_value,
        stocks_weight_pct=stocks_pct,
        mf_weight_pct=mf_pct,
        stocks_cost=stocks_cost,
        mf_cost=mf_cost,
        combined_cost=combined_cost,
        combined_pnl=combined_pnl,
        combined_pnl_pct=combined_pnl_pct,
        news=news,
        strategy=strategy,
        benchmark_return_1y=bench_ret,
    )


def _build_strategy(
    summary: PortfolioSummary,
    recommendations: list[Recommendation],
    stock_data: dict[str, StockMarketData],
    mf_holdings: list[MutualFundHolding],
    sector_weights: dict[str, float],
    stocks_pct: float,
    mf_pct: float,
    max_weight: float,
    bench_ret: float | None,
    combined: float,
) -> StrategyVerdict:
    keep: list[str] = []
    trim: list[str] = []
    research: list[str] = []
    consider_buy: list[str] = []
    strengths: list[str] = []
    weaknesses: list[str] = []
    mf_notes: list[str] = []
    reallocation: list[str] = []
    suggestions: list[Suggestion] = []

    for p in summary.positions:
        rec = next((r for r in recommendations if r.symbol == p.trading_symbol), None)
        action = rec.action.value if rec else "keep"
        total_weight = (p.market_value / combined * 100) if combined else p.weight_pct
        why = (rec.evidence[0] if rec and rec.evidence else "No major flags vs your rules.")
        counter = (rec.counterpoints[0] if rec and rec.counterpoints else "Review quarterly; this is not a trade order.")
        line = (
            f"{p.trading_symbol}: invested {format_inr(p.cost_basis)} → current {format_inr(p.market_value)} "
            f"({p.unrealized_pnl_pct:+.1f}%), {total_weight:.1f}% of total"
        )

        if action == "rebalance-candidate" or total_weight > max_weight:
            bucket = "trim"
            suggestion = (
                f"Plan a gradual trim toward ~{max_weight:.0f}% of total (not a one-day dump). "
                f"Current weight {total_weight:.1f}% is concentration risk."
            )
            trim.append(f"TRIM/REVIEW {line} — {why}")
        elif action in ("monitor", "research") or p.unrealized_pnl_pct <= -12:
            bucket = "monitor"
            suggestion = (
                "Do not panic-sell on mark-to-market. Recheck thesis, news, and whether you would still buy this business."
            )
            research.append(f"MONITOR {line} — {why}")
        else:
            bucket = "keep"
            suggestion = "Keep as a long-term holding unless concentration or thesis changes."
            keep.append(f"KEEP {line}")

        suggestions.append(
            Suggestion(
                bucket=bucket,
                asset_type="stock",
                name=p.trading_symbol,
                invested=p.cost_basis,
                current=p.market_value,
                pnl=p.unrealized_pnl,
                pnl_pct=p.unrealized_pnl_pct,
                weight_pct=total_weight,
                why=why,
                suggestion=suggestion,
                counter=counter,
            )
        )

    # Sector concentration
    for sector, weight in sector_weights.items():
        if weight > 30 and not sector.startswith("MF:"):
            weaknesses.append(f"{sector} is {weight:.1f}% of total portfolio — high concentration")
            reallocation.append(f"Reduce {sector} exposure gradually; target under 25% per sector")

    # MF analysis
    mf_cats: dict[str, int] = {}
    if mf_holdings:
        strengths.append(
            f"Mutual funds: invested {format_inr(sum(m.cost_basis for m in mf_holdings))} → "
            f"current {format_inr(sum(m.market_value for m in mf_holdings))} ({mf_pct:.1f}% of portfolio)"
        )
        for m in mf_holdings:
            cat = (m.category or "Uncategorised")
            mf_cats[cat] = mf_cats.get(cat, 0) + 1
            total_w = (m.market_value / combined * 100) if combined else 0
            note = (
                f"{m.name[:48]}: invested {format_inr(m.cost_basis)} → current {format_inr(m.market_value)} "
                f"({m.unrealized_pnl_pct:+.1f}%)"
            )
            if m.return_1y_pct is not None:
                note += f"; scheme 1Y {m.return_1y_pct:+.1f}%"
            mf_notes.append(note)
            if m.unrealized_pnl_pct < -10:
                bucket = "monitor"
                why = f"Holding is {m.unrealized_pnl_pct:.1f}% below your invested amount."
                suggestion = "Stay the course if this is a core SIP; review only if the mandate or your goal changed."
                research.append(f"MONITOR MF {note}")
            else:
                bucket = "keep"
                why = f"{cat} — core/satellite holding with P&L {m.unrealized_pnl_pct:+.1f}% vs cost."
                suggestion = "Continue SIPs if this matches your time horizon; avoid chasing last year's 1Y return."
                keep.append(f"KEEP MF {note}")
            suggestions.append(
                Suggestion(
                    bucket=bucket,
                    asset_type="mf",
                    name=m.name,
                    invested=m.cost_basis,
                    current=m.market_value,
                    pnl=m.unrealized_pnl,
                    pnl_pct=m.unrealized_pnl_pct,
                    weight_pct=total_w,
                    why=why,
                    suggestion=suggestion,
                    counter="Past NAV/1Y return is not a guarantee of future results.",
                )
            )
        overlap = [c for c, n in mf_cats.items() if n >= 2 and "mid" in c.lower()]
        if overlap:
            weaknesses.append("Multiple mid-cap funds overlap — similar stocks can hide concentration.")
            reallocation.append("Keep one primary mid-cap fund; use the other only if style is clearly different.")
    else:
        weaknesses.append("No mutual funds configured — import a Groww MF CSV/XLSX for the full picture")
        consider_buy.append("Add a Nifty 50 / Total Market index fund as the core (import or mf add)")

    if stocks_pct > 85 and not mf_holdings:
        weaknesses.append(f"Direct stocks are {stocks_pct:.1f}% of portfolio — limited MF diversification")
        reallocation.append("Consider allocating 20-40% to diversified mutual funds for long-term core holding")

    present_sectors = {SECTOR_MAP.get(p.trading_symbol, "Other") for p in summary.positions}
    for sector, candidates in SECTOR_CANDIDATES.items():
        if sector not in present_sectors:
            consider_buy.append(
                f"Research {sector} via a diversified fund or {', '.join(candidates[:2])} — missing in direct stocks"
            )
            suggestions.append(
                Suggestion(
                    bucket="consider",
                    asset_type="idea",
                    name=f"{sector} exposure",
                    invested=0,
                    current=0,
                    pnl=0,
                    pnl_pct=0,
                    weight_pct=0,
                    why=f"{sector} is not represented in your direct equity holdings.",
                    suggestion=f"Prefer a broad fund over buying more single stocks. Research candidates: {', '.join(candidates[:2])}.",
                    counter="Skipping a sector is fine if you already cover it via Flexi/Index MFs.",
                )
            )

    for div in CORE_DIVERSIFIERS[:1]:
        consider_buy.append(f"Consider: {div['name']} — {div['reason']}")

    # Diversification score
    score = 100
    for p in summary.positions:
        tw = (p.market_value / combined * 100) if combined else p.weight_pct
        if tw > max_weight:
            score -= 15
        if tw > max_weight * 2:
            score -= 15
    if mf_pct < 10:
        score -= 10
    if len(summary.positions) < 8:
        score -= 10
    score = max(0, min(100, score))

    if score >= 70:
        headline = "Reasonably diversified — watch a few concentration points"
    elif score >= 45:
        headline = "Useful core (especially MFs), but stock concentration still needs a plan"
    else:
        headline = "Concentration is the main risk — invested vs current looks fine, sizing does not"

    if bench_ret is not None:
        strengths.append(f"Benchmark (Nifty) 1Y return: {bench_ret:+.1f}% (Yahoo Finance)")

    return StrategyVerdict(
        headline=headline,
        score=score,
        strengths=strengths or ["Holdings loaded successfully"],
        weaknesses=weaknesses or ["No major structural issues vs your stated limits"],
        actions_keep=keep,
        actions_trim=trim,
        actions_research=research,
        actions_consider_buy=consider_buy,
        mf_notes=mf_notes,
        reallocation_plan=reallocation,
        suggestions=suggestions,
    )


def deep_analysis_to_dict(result: DeepAnalysisResult) -> dict[str, Any]:
    return {
        "combined_value": result.combined_value,
        "stocks_value": result.stocks_value,
        "mf_value": result.mf_value,
        "stocks_weight_pct": result.stocks_weight_pct,
        "mf_weight_pct": result.mf_weight_pct,
        "stocks_cost": result.stocks_cost,
        "mf_cost": result.mf_cost,
        "combined_cost": result.combined_cost,
        "combined_pnl": result.combined_pnl,
        "combined_pnl_pct": result.combined_pnl_pct,
        "benchmark_return_1y": result.benchmark_return_1y,
        "sector_weights": result.sector_weights,
        "stock_market_data": {k: asdict(v) for k, v in result.stock_market_data.items()},
        "mutual_funds": [
            {
                **asdict(m),
                "bought_price": m.avg_nav,
                "sell_price": m.current_nav,
            }
            for m in result.mutual_funds
        ],
        "news": {
            sym: [{"title": n.title, "link": n.link, "published": n.published} for n in items]
            for sym, items in result.news.items()
        },
        "strategy": asdict(result.strategy),
    }
