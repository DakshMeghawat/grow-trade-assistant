from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MarketDataProvider(ABC):
    """Interface for future fundamentals and foreign-market data providers."""

    @abstractmethod
    def get_fundamentals(self, symbol: str) -> dict[str, Any]:
        """Return fundamental data for a symbol (placeholder for licensed providers)."""

    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier for reports."""


class PlaceholderFundamentalsProvider(MarketDataProvider):
    """Stub provider until a licensed fundamentals source is configured."""

    def get_fundamentals(self, symbol: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "available": False,
            "note": "Fundamentals not configured. Add a licensed provider adapter.",
        }

    def provider_name(self) -> str:
        return "placeholder"
