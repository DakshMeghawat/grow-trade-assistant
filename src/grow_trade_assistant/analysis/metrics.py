from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from grow_trade_assistant.features.indicators import (
    classify_trend,
    compute_technical_features,
    max_drawdown_pct,
    moving_average,
    annualized_volatility,
)

__all__ = [
    "PositionMetrics",
    "PortfolioSummary",
    "build_position_metrics",
    "classify_trend",
    "compare_snapshots",
    "format_inr",
    "max_drawdown",
    "moving_average",
    "summarize_portfolio",
    "volatility",
]


@dataclass
class PositionMetrics:
    trading_symbol: str
    exchange: str
    quantity: float
    average_price: float
    last_price: float
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    weight_pct: float
    ma50: float | None = None
    ma200: float | None = None
    trend: str | None = None
    volatility_30d: float | None = None
    max_drawdown_1y: float | None = None
    week_52_high: float | None = None
    week_52_low: float | None = None
    rsi14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    atr14: float | None = None


@dataclass
class PortfolioSummary:
    snapshot_id: int
    captured_at: str
    total_value: float
    total_cost: float
    total_unrealized_pnl: float
    total_unrealized_pnl_pct: float
    positions: list[PositionMetrics] = field(default_factory=list)
    benchmark_return_pct: float | None = None
    concentration_warnings: list[str] = field(default_factory=list)


def volatility(closes: list[float], window: int = 30) -> float | None:
    """Backward-compatible alias — annualized vol as decimal."""
    return annualized_volatility(closes, window)


def max_drawdown(closes: list[float]) -> float | None:
    """Backward-compatible alias."""
    return max_drawdown_pct(closes)


def build_position_metrics(
    holdings: list[dict[str, Any]],
    ltp_map: dict[str, float],
    candles_by_symbol: dict[str, list[dict[str, float]]],
    exchange: str = "NSE",
) -> list[PositionMetrics]:
    positions: list[PositionMetrics] = []
    for h in holdings:
        symbol = h.get("trading_symbol", "")
        qty = float(h.get("quantity", 0))
        avg = float(h.get("average_price", 0))
        key = f"{exchange}_{symbol}"
        last = ltp_map.get(key, avg)
        if last != last:  # NaN check
            last = avg
        mv = qty * last
        cost = qty * avg
        pnl = mv - cost
        pnl_pct = (pnl / cost * 100) if cost else 0.0

        candles = candles_by_symbol.get(symbol, [])
        closes = [c["close"] for c in candles]
        features = compute_technical_features(closes, candles if candles else None)
        trend = classify_trend(last, features.ma50, features.ma200)

        positions.append(
            PositionMetrics(
                trading_symbol=symbol,
                exchange=exchange,
                quantity=qty,
                average_price=avg,
                last_price=last,
                market_value=mv,
                cost_basis=cost,
                unrealized_pnl=pnl,
                unrealized_pnl_pct=pnl_pct,
                weight_pct=0.0,
                ma50=features.ma50,
                ma200=features.ma200,
                trend=trend,
                volatility_30d=features.volatility_30d_ann,
                max_drawdown_1y=features.max_drawdown_1y_pct,
                rsi14=features.rsi14,
                macd=features.macd,
                macd_signal=features.macd_signal,
                atr14=features.atr14,
            )
        )
    return positions


def summarize_portfolio(
    snapshot_id: int,
    captured_at: str,
    positions: list[PositionMetrics],
    benchmark_return_pct: float | None = None,
) -> PortfolioSummary:
    total_value = sum(p.market_value for p in positions)
    total_cost = sum(p.cost_basis for p in positions)
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0.0

    for p in positions:
        p.weight_pct = (p.market_value / total_value * 100) if total_value else 0.0

    return PortfolioSummary(
        snapshot_id=snapshot_id,
        captured_at=captured_at,
        total_value=total_value,
        total_cost=total_cost,
        total_unrealized_pnl=total_pnl,
        total_unrealized_pnl_pct=total_pnl_pct,
        positions=positions,
        benchmark_return_pct=benchmark_return_pct,
    )


def compare_snapshots(
    current: PortfolioSummary,
    previous_holdings: list[dict[str, Any]] | None,
    previous_ltps: dict[str, float] | None,
) -> list[str]:
    if not previous_holdings:
        return ["First report — no prior snapshot to compare."]

    prev_symbols = {h["trading_symbol"] for h in previous_holdings}
    curr_symbols = {p.trading_symbol for p in current.positions}
    changes: list[str] = []

    added = curr_symbols - prev_symbols
    removed = prev_symbols - curr_symbols
    if added:
        changes.append(f"New holdings: {', '.join(sorted(added))}")
    if removed:
        changes.append(f"Removed holdings: {', '.join(sorted(removed))}")

    prev_qty = {h["trading_symbol"]: float(h.get("quantity", 0)) for h in previous_holdings}
    for p in current.positions:
        old_qty = prev_qty.get(p.trading_symbol)
        if old_qty is not None and old_qty != p.quantity:
            changes.append(
                f"{p.trading_symbol}: quantity {old_qty:g} → {p.quantity:g}"
            )

    if previous_ltps:
        for p in current.positions:
            key = f"NSE_{p.trading_symbol}"
            old_ltp = previous_ltps.get(key)
            if old_ltp and old_ltp > 0:
                chg = (p.last_price - old_ltp) / old_ltp * 100
                if abs(chg) >= 2:
                    changes.append(
                        f"{p.trading_symbol}: price moved {chg:+.1f}% since last report"
                    )

    return changes or ["No significant portfolio changes since last report."]


def format_inr(amount: float) -> str:
    return f"₹{amount:,.2f}"
