from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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
from grow_trade_assistant.analysis.recommendations import (
    pick_featured_learning,
    rank_recommendations,
)
from grow_trade_assistant.cache.store import DataStore
from grow_trade_assistant.config import Settings
from grow_trade_assistant.groww_client import GrowwClient
from grow_trade_assistant.groww_import import load_stocks_file
from grow_trade_assistant.providers.mfapi import MFApiClient, load_mutual_fund_config
from grow_trade_assistant.providers.news import GoogleNewsRSS
from grow_trade_assistant.providers.yahoo_finance import YahooFinanceProvider
from grow_trade_assistant.report.deep_renderer import render_deep_markdown
from grow_trade_assistant.report.renderer import write_reports

logger = logging.getLogger(__name__)


def _ist_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata"))


def _fetch_prices_yahoo(
    symbols: list[str],
    holdings: list[dict[str, Any]],
    benchmark: str,
) -> tuple[dict[str, float], list[str], dict[str, Any]]:
    """Fetch live prices from Yahoo Finance; fallback to avg buy price."""
    warnings: list[str] = []
    yahoo = YahooFinanceProvider()
    all_symbols = list(dict.fromkeys(symbols + [benchmark]))
    prices = yahoo.get_prices(all_symbols)

    avg_by_symbol = {h["trading_symbol"]: float(h.get("average_price", 0)) for h in holdings}
    for sym in symbols:
        key = f"NSE_{sym}"
        if key not in prices:
            avg = avg_by_symbol.get(sym)
            if avg:
                prices[key] = avg
                warnings.append(f"Yahoo price unavailable for {sym}; using avg buy ₹{avg:,.2f}")

    if prices:
        warnings.insert(0, f"Live prices sourced from Yahoo Finance ({len(prices)} symbols)")
    return prices, warnings, yahoo


def _sync_yahoo_candles(yahoo: YahooFinanceProvider, store: DataStore, symbols: list[str]) -> None:
    for symbol in symbols:
        if len(store.get_candles("NSE", symbol, limit=200)) >= 200:
            continue
        candles = yahoo.candles_for_store(symbol)
        if candles:
            store.upsert_candles("NSE", symbol, candles)


def _groww_prices_if_available(
    client: GrowwClient,
    symbols: list[str],
    benchmark_exchange: str,
    benchmark_symbol: str,
) -> dict[str, float]:
    keys = [f"NSE_{s}" for s in symbols]
    if benchmark_symbol not in symbols:
        keys.append(f"{benchmark_exchange}_{benchmark_symbol}")
    try:
        return client.get_ltp("CASH", keys)
    except Exception as exc:
        logger.warning("Groww LTP unavailable, using Yahoo: %s", exc)
        return {}


def run_analysis(settings: Settings, offline: bool = False) -> dict[str, Any]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    db_path = settings.data_dir / "portfolio.db"

    with DataStore(db_path) as store:
        previous = store.get_previous_snapshot()
        prev_ltps = store.get_cached_ltp("CASH")
        data_warnings: list[str] = []

        if offline:
            snapshot = store.get_latest_snapshot()
            imported = load_stocks_file(settings.stocks_path) if settings.stocks_path else []
            if imported:
                holdings = imported
                positions = []
                snapshot_id = store.save_snapshot(holdings, positions)
                captured_at = datetime.now(timezone.utc).isoformat()
                data_warnings.append("Stocks loaded from imported Groww file (stocks.json), not live API.")
            elif snapshot:
                holdings = snapshot["holdings"]
                positions = snapshot["positions"]
                snapshot_id = snapshot["id"]
                captured_at = snapshot["captured_at"]
            else:
                raise RuntimeError(
                    "No stock holdings. Import a Groww CSV/XLSX: grow-assistant import FILE --kind stocks"
                )
            symbols = [h["trading_symbol"] for h in holdings]
            ltp_map = dict(prev_ltps)
            stock_market_data = {}
            try:
                yahoo_prices, yahoo_warnings, yahoo = _fetch_prices_yahoo(
                    symbols, holdings, settings.benchmark_symbol
                )
                data_warnings.extend(yahoo_warnings)
                ltp_map.update(yahoo_prices)
                for sym in symbols:
                    sd = yahoo.get_full_data(sym)
                    if sd:
                        stock_market_data[sym] = sd
                bench = yahoo.get_full_data(settings.benchmark_symbol)
                if bench:
                    stock_market_data[settings.benchmark_symbol] = bench
                for sym, sd in stock_market_data.items():
                    if sym != settings.benchmark_symbol and sd.last_price == sd.last_price:
                        ltp_map[f"NSE_{sym}"] = sd.last_price
            except Exception as exc:
                logger.warning("Yahoo unavailable in offline mode: %s", exc)
                data_warnings.append(f"Live prices skipped ({exc}); using cached/avg buy prices.")
            store.cache_ltp("CASH", ltp_map)
        else:
            holdings = []
            positions = []
            yahoo = YahooFinanceProvider()
            try:
                with GrowwClient(settings) as client:
                    holdings = client.get_holdings()
                    positions = client.get_positions(segment="CASH")
                    snapshot_id = store.save_snapshot(holdings, positions)
                    captured_at = datetime.now(timezone.utc).isoformat()
                    symbols = [h["trading_symbol"] for h in holdings]

                    groww_prices = _groww_prices_if_available(
                        client, symbols, settings.benchmark_exchange, settings.benchmark_symbol
                    )
                    yahoo_prices, yahoo_warnings, yahoo = _fetch_prices_yahoo(
                        symbols, holdings, settings.benchmark_symbol
                    )
                    data_warnings.extend(yahoo_warnings)

                    ltp_map = dict(yahoo_prices)
                    if groww_prices:
                        for k, v in groww_prices.items():
                            ltp_map[k] = v
                        data_warnings.append(
                            f"Groww live prices used for {len(groww_prices)} symbols where available"
                        )
                    store.cache_ltp("CASH", ltp_map)
                    _sync_yahoo_candles(yahoo, store, symbols)
            except Exception as exc:
                logger.warning("Groww API unavailable (%s); trying imported/cached stocks", exc)
                data_warnings.append(f"Groww API failed ({exc}). Using imported file or last cache.")
                imported = load_stocks_file(settings.stocks_path) if settings.stocks_path else []
                snapshot = store.get_latest_snapshot()
                if imported:
                    holdings = imported
                    positions = []
                elif snapshot:
                    holdings = snapshot["holdings"]
                    positions = snapshot["positions"]
                else:
                    raise RuntimeError(
                        "Groww API failed and no imported stocks.json / cache. "
                        "Upload a Groww holdings CSV/XLSX: grow-assistant import FILE"
                    ) from exc
                snapshot_id = store.save_snapshot(holdings, positions)
                captured_at = datetime.now(timezone.utc).isoformat()
                symbols = [h["trading_symbol"] for h in holdings]
                yahoo_prices, yahoo_warnings, yahoo = _fetch_prices_yahoo(
                    symbols, holdings, settings.benchmark_symbol
                )
                data_warnings.extend(yahoo_warnings)
                ltp_map = dict(prev_ltps)
                ltp_map.update(yahoo_prices)
                store.cache_ltp("CASH", ltp_map)

            stock_market_data = {}
            for sym in symbols:
                sd = yahoo.get_full_data(sym)
                if sd:
                    stock_market_data[sym] = sd
            bench = yahoo.get_full_data(settings.benchmark_symbol)
            if bench:
                stock_market_data[settings.benchmark_symbol] = bench

            for sym, sd in stock_market_data.items():
                if sym != settings.benchmark_symbol and sd.last_price == sd.last_price:
                    ltp_map[f"NSE_{sym}"] = sd.last_price

        candles_by_symbol = {
            h["trading_symbol"]: store.get_candles("NSE", h["trading_symbol"])
            for h in holdings
        }

        position_metrics = build_position_metrics(holdings, ltp_map, candles_by_symbol)
        summary = summarize_portfolio(snapshot_id, captured_at, position_metrics)
        recommendations = rank_recommendations(summary, settings, store)

        # Mutual funds
        mf_config = load_mutual_fund_config(
            str(settings.mutual_funds_path) if settings.mutual_funds_path else None
        )
        mf_holdings = []
        if mf_config:
            with MFApiClient() as mf_client:
                mf_holdings = mf_client.analyze_holdings(mf_config)
        elif settings.mutual_funds_path and settings.mutual_funds_path.exists():
            data_warnings.append(
                "Mutual funds not configured. Groww API shows stocks only (DEMAT). "
                "Add MF holdings: grow-assistant mf add"
            )

        # News
        news = {}
        if settings.fetch_news and not offline:
            with GoogleNewsRSS() as news_client:
                news = news_client.fetch_for_symbols(symbols[:6], limit_per=2)

        deep = run_deep_analysis(
            summary, recommendations, stock_market_data, mf_holdings, news, settings.max_single_stock_weight
        )
        memo = build_investment_memo(
            summary,
            mf_holdings,
            deep.combined_value,
            deep.stocks_cost,
            deep.mf_cost,
            deep.mf_value,
        )

        changes = compare_snapshots(
            summary,
            previous["holdings"] if previous else None,
            prev_ltps if previous else None,
        )

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
                "Deep analysis then scores concentration (single name / sector), MF category overlap, 50/200-day trend, drawdown, and 1Y scheme return — then writes review-only Keep / Trim / Monitor notes.",
            ],
            "checklist": [
                "Did any single stock or sector exceed your limits?",
                "Are you overweight direct stocks vs mutual funds for your goals?",
                "Do MF categories overlap with your direct stock sectors?",
                "Are trim candidates driven by concentration, not short-term noise?",
                "Have you verified news headlines and 1Y returns independently?",
            ],
        }

        md = render_deep_markdown(report_payload, format_inr)
        paths = write_reports(settings.reports_dir, report_payload, md)
        report_payload["report_paths"] = {k: str(v) for k, v in paths.items()}
        return report_payload
