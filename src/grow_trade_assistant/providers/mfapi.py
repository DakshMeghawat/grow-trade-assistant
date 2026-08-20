from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MFAPI_BASE = "https://api.mfapi.in/mf"


@dataclass
class MutualFundHolding:
    scheme_code: str
    name: str
    units: float
    avg_nav: float
    current_nav: float
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    return_1y_pct: float | None
    category: str


def load_mutual_fund_config(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    from grow_trade_assistant.mf_config import load_mutual_fund_file

    p = Path(path)
    if not p.exists():
        logger.warning("Mutual fund config not found: %s", path)
        return []
    return load_mutual_fund_file(p)


class MFApiClient:
    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(timeout=30.0)
        self._owns = client is None

    def close(self) -> None:
        if self._owns:
            self._client.close()

    def __enter__(self) -> MFApiClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_scheme_data(self, scheme_code: str) -> dict[str, Any] | None:
        try:
            r = self._client.get(f"{MFAPI_BASE}/{scheme_code}")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            logger.warning("MFApi fetch failed for %s: %s", scheme_code, exc)
            return None

    def analyze_holdings(self, config: list[dict[str, Any]]) -> list[MutualFundHolding]:
        results: list[MutualFundHolding] = []
        for item in config:
            code = str(item.get("scheme_code", "")).strip()
            if not code:
                continue
            units = float(item.get("units", 0))
            avg_nav = float(item.get("avg_nav", 0))
            name = item.get("name", f"Scheme {code}")

            data = self.get_scheme_data(code)
            current_nav = avg_nav
            return_1y = None
            category = item.get("category", "Unknown")

            if data and data.get("data"):
                latest = data["data"][0]
                current_nav = float(latest["nav"])
                meta = data.get("meta", {})
                name = meta.get("scheme_name", name)
                category = meta.get("scheme_category", category)
                return_1y = _nav_return_pct(data["data"], days=365)

            mv = units * current_nav
            cost = units * avg_nav
            pnl = mv - cost
            pnl_pct = (pnl / cost * 100) if cost else 0.0

            results.append(
                MutualFundHolding(
                    scheme_code=code,
                    name=name,
                    units=units,
                    avg_nav=avg_nav,
                    current_nav=current_nav,
                    market_value=mv,
                    cost_basis=cost,
                    unrealized_pnl=pnl,
                    unrealized_pnl_pct=pnl_pct,
                    return_1y_pct=return_1y,
                    category=category,
                )
            )
        return results


def _nav_return_pct(nav_history: list[dict[str, Any]], days: int = 365) -> float | None:
    if len(nav_history) < 2:
        return None
    try:
        latest_nav = float(nav_history[0]["nav"])
        idx = min(days, len(nav_history) - 1)
        old_nav = float(nav_history[idx]["nav"])
        if old_nav <= 0:
            return None
        return (latest_nav - old_nav) / old_nav * 100
    except (KeyError, ValueError, IndexError):
        return None
