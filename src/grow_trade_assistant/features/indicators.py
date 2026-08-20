from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TechnicalFeatures:
    """Deterministic technical indicators from OHLCV history."""

    ma50: float | None = None
    ma200: float | None = None
    volatility_30d_ann: float | None = None  # decimal, e.g. 0.25 = 25% annualized
    max_drawdown_1y_pct: float | None = None  # percentage, e.g. 33.3
    rsi14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    atr14: float | None = None
    return_1y_pct: float | None = None
    return_3y_pct: float | None = None


def moving_average(closes: list[float], window: int) -> float | None:
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def period_return(closes: list[float], days: int) -> float | None:
    if len(closes) <= days:
        return None
    old = closes[-days - 1]
    if old <= 0:
        return None
    return (closes[-1] - old) / old * 100


def annualized_volatility(closes: list[float], window: int = 30) -> float | None:
    """Annualized volatility as a decimal (not percentage)."""
    if len(closes) < window + 1:
        return None
    returns: list[float] = []
    segment = closes[-(window + 1) :]
    for i in range(1, len(segment)):
        prev = segment[i - 1]
        if prev == 0:
            continue
        returns.append((segment[i] - prev) / prev)
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(252)


def annualized_volatility_pct(closes: list[float], window: int = 30) -> float | None:
    vol = annualized_volatility(closes, window)
    return vol * 100 if vol is not None else None


def max_drawdown_pct(closes: list[float]) -> float | None:
    if len(closes) < 2:
        return None
    peak = closes[0]
    max_dd = 0.0
    for price in closes:
        if price > peak:
            peak = price
        if peak > 0:
            max_dd = max(max_dd, (peak - price) / peak)
    return max_dd * 100


def classify_trend(price: float, ma50: float | None, ma200: float | None) -> str:
    if ma50 is None or ma200 is None:
        return "insufficient_data"
    if price > ma50 > ma200:
        return "uptrend"
    if price < ma50 < ma200:
        return "downtrend"
    return "mixed"


def _ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (span + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def rsi(closes: list[float], window: int = 14) -> float | None:
    if len(closes) < window + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for i in range(-window, 0):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / window
    avg_loss = sum(losses) / window
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[float | None, float | None, float | None]:
    if len(closes) < slow + signal:
        return None, None, None
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _ema(macd_line, signal)
    if not macd_line or not signal_line:
        return None, None, None
    m = macd_line[-1]
    s = signal_line[-1]
    return m, s, m - s


def atr(candles: list[dict[str, float]], window: int = 14) -> float | None:
    if len(candles) < window + 1:
        return None
    trs: list[float] = []
    segment = candles[-(window + 1) :]
    for i in range(1, len(segment)):
        high = segment[i]["high"]
        low = segment[i]["low"]
        prev_close = segment[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if not trs:
        return None
    return sum(trs) / len(trs)


def _normalize_candles(
    closes: list[float],
    candles: list[dict[str, float]] | None,
) -> list[dict[str, float]]:
    if candles and len(candles) == len(closes):
        rows: list[dict[str, float]] = []
        for c in candles:
            close = float(c["close"])
            rows.append(
                {
                    "open": float(c.get("open", close)),
                    "high": float(c.get("high", close)),
                    "low": float(c.get("low", close)),
                    "close": close,
                }
            )
        return rows
    return [{"open": c, "high": c, "low": c, "close": c} for c in closes]


def compute_technical_features(
    closes: list[float],
    candles: list[dict[str, float]] | None = None,
) -> TechnicalFeatures:
    m, sig, hist = macd(closes)
    candle_rows = _normalize_candles(closes, candles)
    return TechnicalFeatures(
        ma50=moving_average(closes, 50),
        ma200=moving_average(closes, 200),
        volatility_30d_ann=annualized_volatility(closes, 30),
        max_drawdown_1y_pct=max_drawdown_pct(closes),
        rsi14=rsi(closes, 14),
        macd=m,
        macd_signal=sig,
        macd_hist=hist,
        atr14=atr(candle_rows, 14) if len(candle_rows) >= 15 else None,
        return_1y_pct=period_return(closes, 252),
        return_3y_pct=period_return(closes, min(756, len(closes) - 1)) if len(closes) > 1 else None,
    )


def try_pandas_ta_features(closes: list[float], candles: list[dict[str, float]] | None = None) -> TechnicalFeatures | None:
    """Optional pandas-ta validation path; returns None if library unavailable."""
    try:
        import pandas as pd
        import pandas_ta as ta
    except ImportError:
        return None

    df = pd.DataFrame({"close": closes})
    if candles and len(candles) == len(closes):
        df["high"] = [c["high"] for c in candles]
        df["low"] = [c["low"] for c in candles]
        df["open"] = [c.get("open", c["close"]) for c in candles]

    base = compute_technical_features(closes, candles)
    rsi_ta = ta.rsi(df["close"], length=14)
    if rsi_ta is not None and not rsi_ta.empty:
        last = float(rsi_ta.iloc[-1])
        if not math.isnan(last):
            return TechnicalFeatures(
                **{**base.__dict__, "rsi14": last},
            )
    return base
