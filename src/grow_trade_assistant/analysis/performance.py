from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class PerformanceMetrics:
    """Deterministic portfolio/strategy performance statistics."""

    cagr_pct: float | None
    annualized_volatility_pct: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    max_drawdown_pct: float | None
    calmar_ratio: float | None
    turnover_pct: float | None
    win_rate_pct: float | None
    profit_factor: float | None
    avg_exposure_pct: float | None
    total_return_pct: float | None
    periods: int


def _daily_returns(closes: list[float]) -> list[float]:
    returns: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev > 0:
            returns.append((closes[i] - prev) / prev)
    return returns


def cagr(closes: list[float], trading_days_per_year: int = 252) -> float | None:
    if len(closes) < 2 or closes[0] <= 0:
        return None
    years = (len(closes) - 1) / trading_days_per_year
    if years <= 0:
        return None
    return ((closes[-1] / closes[0]) ** (1 / years) - 1) * 100


def annualized_volatility(returns: list[float], trading_days: int = 252) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(var) * math.sqrt(trading_days) * 100


def sharpe_ratio(
    returns: list[float],
    risk_free_rate_annual: float = 0.07,
    trading_days: int = 252,
) -> float | None:
    if len(returns) < 2:
        return None
    mean_daily = sum(returns) / len(returns)
    rf_daily = risk_free_rate_annual / trading_days
    excess = [r - rf_daily for r in returns]
    mean_excess = sum(excess) / len(excess)
    var = sum((r - mean_excess) ** 2 for r in excess) / (len(excess) - 1)
    if var <= 0:
        return None
    std = math.sqrt(var)
    return (mean_excess / std) * math.sqrt(trading_days)


def sortino_ratio(
    returns: list[float],
    risk_free_rate_annual: float = 0.07,
    trading_days: int = 252,
) -> float | None:
    if len(returns) < 2:
        return None
    rf_daily = risk_free_rate_annual / trading_days
    excess = [r - rf_daily for r in returns]
    mean_excess = sum(excess) / len(excess)
    downside = [min(0.0, r) for r in excess]
    downside_var = sum(d ** 2 for d in downside) / len(downside)
    if downside_var <= 0:
        return None
    downside_std = math.sqrt(downside_var)
    return (mean_excess / downside_std) * math.sqrt(trading_days)


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


def calmar_ratio(cagr_pct: float | None, max_dd_pct: float | None) -> float | None:
    if cagr_pct is None or max_dd_pct is None or max_dd_pct <= 0:
        return None
    return cagr_pct / max_dd_pct


def win_rate(returns: list[float]) -> float | None:
    if not returns:
        return None
    wins = sum(1 for r in returns if r > 0)
    return wins / len(returns) * 100


def profit_factor(returns: list[float]) -> float | None:
    gains = sum(r for r in returns if r > 0)
    losses = abs(sum(r for r in returns if r < 0))
    if losses == 0:
        return None if gains == 0 else float("inf")
    return gains / losses


def turnover_from_weights(weight_changes: list[float]) -> float | None:
    """Sum of absolute weight changes between rebalances (as % of portfolio)."""
    if not weight_changes:
        return None
    return sum(abs(w) for w in weight_changes) * 100


def compute_performance_metrics(
    closes: list[float],
    *,
    risk_free_rate_annual: float = 0.07,
    weight_changes: list[float] | None = None,
    exposure: float = 1.0,
) -> PerformanceMetrics:
    """Compute standard metrics from a price series (e.g. benchmark or backtest equity curve)."""
    returns = _daily_returns(closes)
    cagr_val = cagr(closes)
    vol = annualized_volatility(returns)
    mdd = max_drawdown_pct(closes)
    total_ret = None
    if len(closes) >= 2 and closes[0] > 0:
        total_ret = (closes[-1] / closes[0] - 1) * 100

    return PerformanceMetrics(
        cagr_pct=cagr_val,
        annualized_volatility_pct=vol,
        sharpe_ratio=sharpe_ratio(returns, risk_free_rate_annual),
        sortino_ratio=sortino_ratio(returns, risk_free_rate_annual),
        max_drawdown_pct=mdd,
        calmar_ratio=calmar_ratio(cagr_val, mdd),
        turnover_pct=turnover_from_weights(weight_changes or []),
        win_rate_pct=win_rate(returns),
        profit_factor=profit_factor(returns),
        avg_exposure_pct=exposure * 100,
        total_return_pct=total_ret,
        periods=len(closes),
    )
