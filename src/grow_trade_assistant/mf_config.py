from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MFAPI_BASE = "https://api.mfapi.in/mf"


def search_schemes(query: str, limit: int = 10) -> list[dict[str, str]]:
    """Search mutual fund schemes by name via MFApi.in (free, no key)."""
    try:
        r = httpx.get(f"{MFAPI_BASE}/search", params={"q": query}, timeout=15.0)
        r.raise_for_status()
        results = r.json()
        if not isinstance(results, list):
            return []
        return [{"scheme_code": str(x["schemeCode"]), "name": x["schemeName"]} for x in results[:limit]]
    except httpx.HTTPError as exc:
        logger.warning("MF search failed: %s", exc)
        return []


def load_mutual_fund_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("holdings", [])
    return data if isinstance(data, list) else []


def save_mutual_fund_file(path: Path, holdings: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(holdings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def add_holding(path: Path, holding: dict[str, Any]) -> list[dict[str, Any]]:
    holdings = load_mutual_fund_file(path)
    code = str(holding.get("scheme_code", ""))
    holdings = [h for h in holdings if str(h.get("scheme_code", "")) != code]
    holdings.append(holding)
    save_mutual_fund_file(path, holdings)
    return holdings
