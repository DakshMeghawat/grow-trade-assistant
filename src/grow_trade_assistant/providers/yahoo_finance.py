from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

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

            ret_1y = _period_return(closes, 252)
            ret_3y = _period_return(closes, min(756, len(closes) - 1))
            vol = _volatility(closes, 30)
            ma50 = _ma(closes, 50)
            ma200 = _ma(closes, 200)

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
                ma50=ma50,
                ma200=ma200,
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


def _ma(closes: list[float], window: int) -> float | None:
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def _period_return(closes: list[float], days: int) -> float | None:
    if len(closes) <= days:
        return None
    old = closes[-days - 1]
    if old <= 0:
        return None
    return (closes[-1] - old) / old * 100


def _volatility(closes: list[float], window: int = 30) -> float | None:
    if len(closes) < window + 2:
        return None
    import math
    returns = []
    segment = closes[-(window + 1):]
    for i in range(1, len(segment)):
        if segment[i - 1] > 0:
            returns.append((segment[i] - segment[i - 1]) / segment[i - 1])
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(var) * math.sqrt(252) * 100
