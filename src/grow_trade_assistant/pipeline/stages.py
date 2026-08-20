from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from grow_trade_assistant.cache.store import DataStore
from grow_trade_assistant.config import Settings
from grow_trade_assistant.groww_client import GrowwClient
from grow_trade_assistant.groww_import import load_stocks_file
from grow_trade_assistant.ingestion.result import IngestionResult, IngestionStatus, SourceResult
from grow_trade_assistant.providers.mfapi import MFApiClient, load_mutual_fund_config
from grow_trade_assistant.providers.news import GoogleNewsRSS
from grow_trade_assistant.providers.yahoo_finance import StockMarketData, YahooFinanceProvider

logger = logging.getLogger(__name__)


@dataclass
class HoldingsStageResult:
    holdings: list[dict[str, Any]]
    positions: list[dict[str, Any]]
    snapshot_id: int
    captured_at: str
    symbols: list[str]
    ingestion: IngestionResult = field(default_factory=IngestionResult)


@dataclass
class PricesStageResult:
    ltp_map: dict[str, float]
    stock_market_data: dict[str, StockMarketData]
    yahoo: YahooFinanceProvider | None
    ingestion: IngestionResult = field(default_factory=IngestionResult)


@dataclass
class AncillaryStageResult:
    mf_holdings: list[Any]
    news: dict[str, list[Any]]
    ingestion: IngestionResult = field(default_factory=IngestionResult)


def fetch_prices_yahoo(
    symbols: list[str],
    holdings: list[dict[str, Any]],
    benchmark: str,
) -> tuple[dict[str, float], IngestionResult, YahooFinanceProvider]:
    ingestion = IngestionResult()
    yahoo = YahooFinanceProvider()
    all_symbols = list(dict.fromkeys(symbols + [benchmark]))
    prices = yahoo.get_prices(all_symbols)

    avg_by_symbol = {h["trading_symbol"]: float(h.get("average_price", 0)) for h in holdings}
    fallback_count = 0
    for sym in symbols:
        key = f"NSE_{sym}"
        if key not in prices:
            avg = avg_by_symbol.get(sym)
            if avg:
                prices[key] = avg
                fallback_count += 1
                ingestion.warnings.append(
                    f"Yahoo price unavailable for {sym}; using avg buy ₹{avg:,.2f}"
                )

    status = IngestionStatus.OK
    if fallback_count and fallback_count < len(symbols):
        status = IngestionStatus.PARTIAL
    elif fallback_count == len(symbols) and symbols:
        status = IngestionStatus.PARTIAL

    ingestion.add(
        SourceResult(
            source="yahoo_finance",
            status=status,
            records=len(prices),
            fetched_at=datetime.now(timezone.utc).isoformat(),
            warnings=(
                [f"Live prices sourced from Yahoo Finance ({len(prices)} symbols)"]
                if prices
                else ["No Yahoo prices returned"]
            ),
        )
    )
    return prices, ingestion, yahoo


def sync_yahoo_candles(yahoo: YahooFinanceProvider, store: DataStore, symbols: list[str]) -> int:
    synced = 0
    for symbol in symbols:
        if len(store.get_candles("NSE", symbol, limit=200)) >= 200:
            continue
        candles = yahoo.candles_for_store(symbol)
        if candles:
            store.upsert_candles("NSE", symbol, candles)
            synced += 1
    return synced


def groww_prices_if_available(
    client: GrowwClient,
    symbols: list[str],
    benchmark_exchange: str,
    benchmark_symbol: str,
) -> tuple[dict[str, float], SourceResult]:
    keys = [f"NSE_{s}" for s in symbols]
    if benchmark_symbol not in symbols:
        keys.append(f"{benchmark_exchange}_{benchmark_symbol}")
    try:
        prices = client.get_ltp("CASH", keys)
        return prices, SourceResult(
            source="groww_ltp",
            status=IngestionStatus.OK,
            records=len(prices),
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        logger.warning("Groww LTP unavailable, using Yahoo: %s", exc)
        return {}, SourceResult(
            source="groww_ltp",
            status=IngestionStatus.FAILED,
            error=str(exc),
            warnings=["Groww LTP unavailable; Yahoo prices used"],
        )


def ingest_holdings(
    settings: Settings,
    store: DataStore,
    offline: bool,
) -> HoldingsStageResult:
    ingestion = IngestionResult()

    if offline:
        snapshot = store.get_latest_snapshot()
        imported = load_stocks_file(settings.stocks_path) if settings.stocks_path else []
        if imported:
            holdings = imported
            positions: list[dict[str, Any]] = []
            snapshot_id = store.save_snapshot(holdings, positions)
            captured_at = datetime.now(timezone.utc).isoformat()
            ingestion.add(
                SourceResult(
                    source="groww_import",
                    status=IngestionStatus.OK,
                    records=len(holdings),
                    warnings=["Stocks loaded from imported Groww file (stocks.json), not live API."],
                )
            )
        elif snapshot:
            holdings = snapshot["holdings"]
            positions = snapshot["positions"]
            snapshot_id = snapshot["id"]
            captured_at = snapshot["captured_at"]
            ingestion.add(
                SourceResult(
                    source="sqlite_cache",
                    status=IngestionStatus.OK,
                    records=len(holdings),
                    warnings=["Using last cached snapshot (offline mode)."],
                )
            )
        else:
            raise RuntimeError(
                "No stock holdings. Import a Groww CSV/XLSX: grow-assistant import FILE --kind stocks"
            )
        return HoldingsStageResult(
            holdings=holdings,
            positions=positions,
            snapshot_id=snapshot_id,
            captured_at=captured_at,
            symbols=[h["trading_symbol"] for h in holdings],
            ingestion=ingestion,
        )

    try:
        with GrowwClient(settings) as client:
            holdings = client.get_holdings()
            positions = client.get_positions(segment="CASH")
            snapshot_id = store.save_snapshot(holdings, positions)
            captured_at = datetime.now(timezone.utc).isoformat()
            ingestion.add(
                SourceResult(
                    source="groww_api",
                    status=IngestionStatus.OK,
                    records=len(holdings),
                    fetched_at=captured_at,
                )
            )
            return HoldingsStageResult(
                holdings=holdings,
                positions=positions,
                snapshot_id=snapshot_id,
                captured_at=captured_at,
                symbols=[h["trading_symbol"] for h in holdings],
                ingestion=ingestion,
            )
    except Exception as exc:
        logger.warning("Groww API unavailable (%s); trying imported/cached stocks", exc)
        ingestion.add(
            SourceResult(
                source="groww_api",
                status=IngestionStatus.FAILED,
                error=str(exc),
                warnings=[f"Groww API failed ({exc}). Using imported file or last cache."],
            )
        )
        imported = load_stocks_file(settings.stocks_path) if settings.stocks_path else []
        snapshot = store.get_latest_snapshot()
        if imported:
            holdings = imported
            positions = []
            ingestion.add(
                SourceResult(
                    source="groww_import",
                    status=IngestionStatus.PARTIAL,
                    records=len(holdings),
                )
            )
        elif snapshot:
            holdings = snapshot["holdings"]
            positions = snapshot["positions"]
            ingestion.add(
                SourceResult(
                    source="sqlite_cache",
                    status=IngestionStatus.PARTIAL,
                    records=len(holdings),
                )
            )
        else:
            raise RuntimeError(
                "Groww API failed and no imported stocks.json / cache. "
                "Upload a Groww holdings CSV/XLSX: grow-assistant import FILE"
            ) from exc
        snapshot_id = store.save_snapshot(holdings, positions)
        captured_at = datetime.now(timezone.utc).isoformat()
        return HoldingsStageResult(
            holdings=holdings,
            positions=positions,
            snapshot_id=snapshot_id,
            captured_at=captured_at,
            symbols=[h["trading_symbol"] for h in holdings],
            ingestion=ingestion,
        )


def ingest_prices(
    settings: Settings,
    store: DataStore,
    holdings: HoldingsStageResult,
    prev_ltps: dict[str, float],
    offline: bool,
) -> PricesStageResult:
    ingestion = IngestionResult()
    symbols = holdings.symbols
    yahoo: YahooFinanceProvider | None = None
    stock_market_data: dict[str, StockMarketData] = {}

    groww_live = any(
        s.source == "groww_api" and s.status == IngestionStatus.OK
        for s in holdings.ingestion.sources
    )

    if offline:
        ltp_map = dict(prev_ltps)
        try:
            yahoo_prices, yahoo_ing, yahoo = fetch_prices_yahoo(
                symbols, holdings.holdings, settings.benchmark_symbol
            )
            ingestion.sources.extend(yahoo_ing.sources)
            ingestion.warnings.extend(yahoo_ing.warnings)
            ltp_map.update(yahoo_prices)
            stock_market_data = _load_stock_market_data(yahoo, symbols, settings.benchmark_symbol)
            _overlay_ltp_from_market_data(ltp_map, stock_market_data, settings.benchmark_symbol)
        except Exception as exc:
            logger.warning("Yahoo unavailable in offline mode: %s", exc)
            ingestion.warnings.append(f"Live prices skipped ({exc}); using cached/avg buy prices.")
            ingestion.add(
                SourceResult(source="yahoo_finance", status=IngestionStatus.FAILED, error=str(exc))
            )
        store.cache_ltp("CASH", ltp_map)
        return PricesStageResult(ltp_map, stock_market_data, yahoo, ingestion)

    groww_prices: dict[str, float] = {}
    if groww_live:
        try:
            with GrowwClient(settings) as client:
                groww_prices, groww_result = groww_prices_if_available(
                    client,
                    symbols,
                    settings.benchmark_exchange,
                    settings.benchmark_symbol,
                )
                ingestion.add(groww_result)
        except Exception as exc:
            logger.warning("Groww LTP fetch failed: %s", exc)
            ingestion.add(
                SourceResult(
                    source="groww_ltp",
                    status=IngestionStatus.FAILED,
                    error=str(exc),
                )
            )

    yahoo_prices, yahoo_ing, yahoo = fetch_prices_yahoo(
        symbols, holdings.holdings, settings.benchmark_symbol
    )
    ingestion.sources.extend(yahoo_ing.sources)
    ingestion.warnings.extend(yahoo_ing.warnings)

    if groww_live:
        ltp_map = dict(yahoo_prices)
        if groww_prices:
            ltp_map.update(groww_prices)
            ingestion.warnings.append(
                f"Groww live prices used for {len(groww_prices)} symbols where available"
            )
    else:
        ltp_map = dict(prev_ltps)
        ltp_map.update(yahoo_prices)

    store.cache_ltp("CASH", ltp_map)
    if yahoo and groww_live:
        sync_yahoo_candles(yahoo, store, symbols)

    stock_market_data = _load_stock_market_data(yahoo, symbols, settings.benchmark_symbol)
    _overlay_ltp_from_market_data(ltp_map, stock_market_data, settings.benchmark_symbol)
    return PricesStageResult(ltp_map, stock_market_data, yahoo, ingestion)


def _load_stock_market_data(
    yahoo: YahooFinanceProvider | None,
    symbols: list[str],
    benchmark_symbol: str,
) -> dict[str, StockMarketData]:
    if not yahoo:
        return {}
    data: dict[str, StockMarketData] = {}
    for sym in symbols:
        sd = yahoo.get_full_data(sym)
        if sd:
            data[sym] = sd
    bench = yahoo.get_full_data(benchmark_symbol)
    if bench:
        data[benchmark_symbol] = bench
    return data


def _overlay_ltp_from_market_data(
    ltp_map: dict[str, float],
    stock_market_data: dict[str, StockMarketData],
    benchmark_symbol: str,
) -> None:
    for sym, sd in stock_market_data.items():
        if sym != benchmark_symbol and sd.last_price == sd.last_price:
            ltp_map[f"NSE_{sym}"] = sd.last_price


def ingest_ancillary(
    settings: Settings,
    symbols: list[str],
    offline: bool,
) -> AncillaryStageResult:
    ingestion = IngestionResult()
    mf_config = load_mutual_fund_config(
        str(settings.mutual_funds_path) if settings.mutual_funds_path else None
    )
    mf_holdings: list[Any] = []
    if mf_config:
        with MFApiClient() as mf_client:
            mf_holdings = mf_client.analyze_holdings(mf_config)
        ingestion.add(
            SourceResult(
                source="mfapi",
                status=IngestionStatus.OK,
                records=len(mf_holdings),
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )
        )
    elif settings.mutual_funds_path and settings.mutual_funds_path.exists():
        msg = (
            "Mutual funds not configured. Groww API shows stocks only (DEMAT). "
            "Add MF holdings: grow-assistant mf add"
        )
        ingestion.warnings.append(msg)
        ingestion.add(SourceResult(source="mfapi", status=IngestionStatus.SKIPPED, warnings=[msg]))

    news: dict[str, list[Any]] = {}
    if settings.fetch_news and not offline:
        with GoogleNewsRSS() as news_client:
            news = news_client.fetch_for_symbols(symbols[:6], limit_per=2)
        ingestion.add(
            SourceResult(
                source="google_news_rss",
                status=IngestionStatus.OK if news else IngestionStatus.SKIPPED,
                records=sum(len(v) for v in news.values()),
            )
        )

    return AncillaryStageResult(mf_holdings=mf_holdings, news=news, ingestion=ingestion)
