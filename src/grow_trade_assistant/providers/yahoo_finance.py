from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from grow_trade_assistant.features.indicators import (
    annualized_volatility_pct,
    compute_technical_features,
)

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore


@dataclass
class StockMarketData:
    symbol: str
    last_price: float
    previous_close: float
    return_1y_pct: float | None
    return_3y_pct: float | None
    volatility_30d: float | None
    week_52_high: float | None
    week_52_low: float | None
    ma50: float | None
    ma200: float | None
    rsi14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    atr14: float | None = None
    source: str = "yahoo_finance"


def _nse_ticker(symbol: str) -> str:
    if symbol in ("NIFTY", "NIFTY50"):
        return "^NSEI"
    return f"{symbol}.NS"


class YahooFinanceProvider:
    """Free live & historical prices for NSE stocks via Yahoo Finance."""

    def __init__(self):
        if yf is None:
            raise RuntimeError("yfinance not installed. Run: pip install yfinance")

    def get_prices(self, symbols: list[str]) -> dict[str, float]:
        prices: dict[str, float] = {}
        for symbol in symbols:
            try:
                ticker = yf.Ticker(_nse_ticker(symbol))
                info = ticker.fast_info
                price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
                if price and not (isinstance(price, float) and __import__("math").isnan(price)):
                    prices[f"NSE_{symbol}"] = float(price)
            except Exception as exc:
                logger.warning("Yahoo price failed for %s: %s", symbol, exc)
        return prices

    def get_full_data(self, symbol: str) -> StockMarketData | None:
        try:
            ticker = yf.Ticker(_nse_ticker(symbol))
            hist = ticker.history(period="3y", interval="1d")
            if hist.empty:
                return None

            closes = hist["Close"].tolist()
            last = float(closes[-1])
            prev = float(closes[-2]) if len(closes) > 1 else last

            features = compute_technical_features(closes)
            ret_1y = features.return_1y_pct
            ret_3y = features.return_3y_pct
            vol = annualized_volatility_pct(closes, 30)

            hi_52 = float(hist["High"].tail(252).max()) if len(hist) >= 252 else float(hist["High"].max())
            lo_52 = float(hist["Low"].tail(252).min()) if len(hist) >= 252 else float(hist["Low"].min())

            return StockMarketData(
                symbol=symbol,
                last_price=last,
                previous_close=prev,
                return_1y_pct=ret_1y,
                return_3y_pct=ret_3y,
                volatility_30d=vol,
                week_52_high=hi_52,
                week_52_low=lo_52,
                ma50=features.ma50,
                ma200=features.ma200,
                rsi14=features.rsi14,
                macd=features.macd,
                macd_signal=features.macd_signal,
                atr14=features.atr14,
            )
        except Exception as exc:
            logger.warning("Yahoo full data failed for %s: %s", symbol, exc)
            return None

    def candles_for_store(self, symbol: str) -> list[list[Any]]:
        import math
        try:
            ticker = yf.Ticker(_nse_ticker(symbol))
            hist = ticker.history(period="2y", interval="1d")
            candles = []
            for ts, row in hist.iterrows():
                o, h, l, c, v = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]), float(row["Volume"])
                if any(math.isnan(x) for x in (o, h, l, c, v)):
                    continue
                epoch = int(ts.timestamp())
                candles.append([epoch, o, h, l, c, v])
            return candles
        except Exception as exc:
            logger.warning("Yahoo candles failed for %s: %s", symbol, exc)
            return []

