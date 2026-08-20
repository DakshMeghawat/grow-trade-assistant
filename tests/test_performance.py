import math

import pytest

from grow_trade_assistant.analysis.performance import (
    annualized_volatility,
    cagr,
    calmar_ratio,
    compute_performance_metrics,
    max_drawdown_pct,
    profit_factor,
    sharpe_ratio,
    sortino_ratio,
    win_rate,
)


def test_cagr_positive_trend():
    # ~10% annual over 252 days simplified
    closes = [100.0 * (1.001 ** i) for i in range(253)]
    result = cagr(closes)
    assert result is not None
    assert 20 < result < 40  # compounded daily 0.1%


def test_max_drawdown_known_series():
    closes = [100, 120, 80, 90]
    assert max_drawdown_pct(closes) == pytest.approx(33.333, rel=0.01)


def test_sharpe_sortino_finite():
    closes = [100 + i * 0.5 + (i % 3) for i in range(100)]
    returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
    assert sharpe_ratio(returns) is not None
    assert sortino_ratio(returns) is not None


def test_calmar_ratio():
    assert calmar_ratio(12.0, 20.0) == pytest.approx(0.6)


def test_win_rate_and_profit_factor():
    returns = [0.01, -0.005, 0.02, -0.01, 0.015]
    assert win_rate(returns) == pytest.approx(60.0)
    assert profit_factor(returns) == pytest.approx(3.0, rel=0.01)


def test_compute_performance_metrics_complete():
    closes = [100.0 * (1 + 0.0005 * i) for i in range(300)]
    m = compute_performance_metrics(closes)
    assert m.periods == 300
    assert m.cagr_pct is not None
    assert m.max_drawdown_pct is not None
    assert m.annualized_volatility_pct is not None


def test_empty_series_returns_none():
    assert cagr([]) is None
    assert max_drawdown_pct([100]) is None
    assert annualized_volatility([]) is None


def test_profit_factor_no_losses():
    returns = [0.01, 0.02, 0.03]
    assert profit_factor(returns) == math.inf
