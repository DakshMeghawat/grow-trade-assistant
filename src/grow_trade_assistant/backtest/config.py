from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class BacktestConfig:
    """Configuration for future backtests — documents required realism constraints."""

    commission_bps: float = 10.0  # 0.10% per side (typical Indian discount broker)
    spread_bps: float = 5.0
    slippage_bps: float = 10.0
    min_liquidity_adv_pct: float = 5.0  # max order as % of 20-day ADV
    include_corporate_actions: bool = True
    respect_market_holidays: bool = True
    benchmark_symbol: str = "NIFTY"
    compare_buy_and_hold: bool = True
    initial_capital: float = 1_000_000.0
    risk_free_rate_annual: float = 0.07

    def total_friction_bps(self) -> float:
        return self.commission_bps + self.spread_bps + self.slippage_bps

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WalkForwardConfig:
    """Walk-forward validation windows to prevent look-ahead bias."""

    train_days: int = 504  # ~2 years
    validation_days: int = 63  # ~1 quarter
    test_days: int = 63
    step_days: int = 63
    embargo_days: int = 5  # gap between train end and test start
    min_train_periods: int = 200

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BacktestValidationPlan:
    """Human- and machine-readable validation checklist (not an engine yet)."""

    config: BacktestConfig = field(default_factory=BacktestConfig)
    walk_forward: WalkForwardConfig = field(default_factory=WalkForwardConfig)
    required_metrics: list[str] = field(
        default_factory=lambda: [
            "cagr_pct",
            "annualized_volatility_pct",
            "sharpe_ratio",
            "sortino_ratio",
            "max_drawdown_pct",
            "calmar_ratio",
            "turnover_pct",
            "win_rate_pct",
            "profit_factor",
            "avg_exposure_pct",
        ]
    )
    bias_controls: list[str] = field(
        default_factory=lambda: [
            "Chronological train/validation/test splits only — no random shuffles.",
            "Point-in-time fundamentals: use filing_date <= signal_date.",
            "Survivorship: include delisted symbols in universe when historically held.",
            "Corporate actions: adjust prices for splits/bonus before signal generation.",
            "No peeking: indicators at date t use data through t-1 close only.",
        ]
    )
    sensitivity_axes: list[str] = field(
        default_factory=lambda: [
            "commission_bps ±50%",
            "slippage_bps ±100%",
            "rebalance frequency (monthly vs quarterly)",
            "max_single_stock_weight guardrail",
        ]
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "walk_forward": self.walk_forward.to_dict(),
            "required_metrics": self.required_metrics,
            "bias_controls": self.bias_controls,
            "sensitivity_axes": self.sensitivity_axes,
            "status": "planned",
            "engine": "not_implemented",
            "recommended_libraries": [
                "vectorbt (fast vectorized backtests)",
                "backtesting.py (simple strategy prototyping)",
                "backtrader (event-driven, corporate actions)",
            ],
        }
