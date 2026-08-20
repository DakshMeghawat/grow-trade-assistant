from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from grow_trade_assistant.analysis.benchmark_comparison import compare_portfolio_to_benchmark
from grow_trade_assistant.analysis.deep_analysis import (
    deep_analysis_to_dict,
    run_deep_analysis,
)
from grow_trade_assistant.analysis.investment_memo import build_investment_memo
from grow_trade_assistant.analysis.metrics import (
    build_position_metrics,
    compare_snapshots,
    format_inr,
    summarize_portfolio,
)
from grow_trade_assistant.analysis.performance import compute_performance_metrics
from grow_trade_assistant.analysis.recommendations import (
    pick_featured_learning,
    rank_recommendations,
)
from grow_trade_assistant.backtest.config import BacktestValidationPlan
from grow_trade_assistant.cache.store import DataStore
from grow_trade_assistant.config import Settings
from grow_trade_assistant.domain.provenance import build_report_provenance, staleness_warning
from grow_trade_assistant.pipeline.stages import (
    ingest_ancillary,
    ingest_holdings,
    ingest_prices,
)
from grow_trade_assistant.report.deep_renderer import render_deep_markdown
from grow_trade_assistant.report.renderer import write_reports

logger = logging.getLogger(__name__)


def _ist_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata"))


def run_analysis(settings: Settings, offline: bool = False) -> dict[str, Any]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    db_path = settings.data_dir / "portfolio.db"

    with DataStore(db_path) as store:
        previous = store.get_previous_snapshot()
        prev_ltps = store.get_cached_ltp("CASH")
        data_warnings: list[str] = []

        holdings_stage = ingest_holdings(settings, store, offline)
        data_warnings.extend(holdings_stage.ingestion.warnings)

        prices_stage = ingest_prices(
            settings, store, holdings_stage, prev_ltps, offline
        )
        data_warnings.extend(prices_stage.ingestion.warnings)

        holdings = holdings_stage.holdings
        snapshot_id = holdings_stage.snapshot_id
        captured_at = holdings_stage.captured_at
        ltp_map = prices_stage.ltp_map
        stock_market_data = prices_stage.stock_market_data
        yahoo = prices_stage.yahoo

        candles_by_symbol = {
            h["trading_symbol"]: store.get_candles("NSE", h["trading_symbol"])
            for h in holdings
        }

        position_metrics = build_position_metrics(holdings, ltp_map, candles_by_symbol)
        summary = summarize_portfolio(snapshot_id, captured_at, position_metrics)
        recommendations = rank_recommendations(summary, settings, store)

        ancillary = ingest_ancillary(settings, holdings_stage.symbols, offline)
        data_warnings.extend(ancillary.ingestion.warnings)
        mf_holdings = ancillary.mf_holdings
        news = ancillary.news

        deep = run_deep_analysis(
            summary,
            recommendations,
            stock_market_data,
            mf_holdings,
            news,
            settings.max_single_stock_weight,
        )
        memo = build_investment_memo(
            summary,
            mf_holdings,
            deep.combined_value,
            deep.stocks_cost,
            deep.mf_cost,
            deep.mf_value,
        )

        ltp_fetched_at = store.get_ltp_fetched_at("CASH")
        stale = staleness_warning(ltp_fetched_at)
        if stale:
            data_warnings.append(stale)

        benchmark_perf = None
        bench_data = stock_market_data.get(settings.benchmark_symbol)
        if bench_data and bench_data.return_1y_pct is not None:
            bench_candles = store.get_candles("NSE", settings.benchmark_symbol, limit=400)
            if not bench_candles and yahoo:
                bench_candles_raw = yahoo.candles_for_store(settings.benchmark_symbol)
                if bench_candles_raw:
                    store.upsert_candles("NSE", settings.benchmark_symbol, bench_candles_raw)
                    bench_candles = store.get_candles("NSE", settings.benchmark_symbol, limit=400)
            if bench_candles:
                bench_closes = [c["close"] for c in bench_candles]
                perf = compute_performance_metrics(bench_closes, risk_free_rate_annual=0.07)
                benchmark_perf = {
                    "symbol": settings.benchmark_symbol,
                    "claim_type": "calculated",
                    "source": "Yahoo Finance daily closes",
                    **{k: v for k, v in perf.__dict__.items() if not k.startswith("_")},
                }

        benchmark_comparison = compare_portfolio_to_benchmark(
            summary, stock_market_data, settings.benchmark_symbol
        )

        changes = compare_snapshots(
            summary,
            previous["holdings"] if previous else None,
            prev_ltps if previous else None,
        )

        ingestion_summary = {
            "holdings": holdings_stage.ingestion.to_dict(),
            "prices": prices_stage.ingestion.to_dict(),
            "ancillary": ancillary.ingestion.to_dict(),
        }

        report_payload: dict[str, Any] = {
            "generated_at": _ist_now().isoformat(),
            "snapshot_id": snapshot_id,
            "portfolio": {
                "total_value": summary.total_value,
                "total_cost": summary.total_cost,
                "total_unrealized_pnl": summary.total_unrealized_pnl,
                "total_unrealized_pnl_pct": summary.total_unrealized_pnl_pct,
                "positions": [
                    {
                        **asdict(p),
                        "bought_price": p.average_price,
                        "sell_price": p.last_price,
                    }
                    for p in summary.positions
                ],
            },
            "deep_analysis": deep_analysis_to_dict(deep),
            "investment_memo": memo,
            "changes_since_last": changes,
            "data_warnings": data_warnings,
            "ingestion": ingestion_summary,
            "concentration_warnings": summary.concentration_warnings,
            "recommendations": [
                {
                    "symbol": r.symbol,
                    "action": r.action.value,
                    "rank": r.rank,
                    "evidence": r.evidence,
                    "counterpoints": r.counterpoints,
                }
                for r in recommendations
            ],
            "learning_note": pick_featured_learning(recommendations),
            "data_sources": {
                "broker": "Groww API or imported Groww CSV/XLSX",
                "prices": "Yahoo Finance (NSE .NS tickers)",
                "mutual_funds": "MFApi.in",
                "news": "Google News RSS",
                "limitations": [
                    "Research/education only — not financial advice",
                    "No order placement",
                    "Sell price = today's market/NAV (mark-to-market), not a completed sell order",
                    "MF holdings must be configured in mutual_funds.json",
                    "News headlines are automated — verify before acting",
                    "Suggested buys are research candidates, not recommendations to purchase",
                ],
            },
            "analysis_method": [
                "Holdings come from Groww API or an imported Groww CSV/Excel (qty + bought price).",
                "Bought price = your average buy price (stocks) or average NAV (mutual funds).",
                "Sell price (today) = Yahoo LTP for stocks, MFApi NAV for funds — what you would get if you exited now. This is not a booked sell.",
                "Invested = qty × bought price. Current = qty × sell price today. P&L = current − invested.",
                "Technical indicators (MA, RSI, MACD, ATR) are calculated deterministically from cached OHLCV.",
                "Deep analysis scores concentration, trend, drawdown, and 1Y return — review-only notes.",
            ],
            "checklist": [
                "Did any single stock or sector exceed your limits?",
                "Are you overweight direct stocks vs mutual funds for your goals?",
                "Do MF categories overlap with your direct stock sectors?",
                "Are trim candidates driven by concentration, not short-term noise?",
                "Have you verified news headlines and 1Y returns independently?",
            ],
            "benchmark_performance": benchmark_perf,
            "benchmark_comparison": benchmark_comparison,
            "backtest_validation_plan": BacktestValidationPlan().to_dict(),
            "provenance": build_report_provenance(
                generated_at=_ist_now().isoformat(),
                benchmark_symbol=settings.benchmark_symbol,
                has_groww=any(
                    s["source"] == "groww_api" and s["status"] == "ok"
                    for s in ingestion_summary["holdings"]["sources"]
                ),
                has_yahoo=any(
                    s["source"] == "yahoo_finance" for s in ingestion_summary["prices"]["sources"]
                ),
                has_mf=bool(mf_holdings),
                has_news=bool(news),
            ),
        }

        md = render_deep_markdown(report_payload, format_inr)
        paths = write_reports(settings.reports_dir, report_payload, md)
        report_payload["report_paths"] = {k: str(v) for k, v in paths.items()}
        return report_payload
