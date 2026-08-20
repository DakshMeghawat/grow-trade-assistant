from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from grow_trade_assistant.auth import AuthError, GrowwAuth, redact_secrets
from grow_trade_assistant.config import Settings

logger = logging.getLogger(__name__)


class GrowwAPIError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


class GrowwClient:
    """Read-only Groww API client with retry and secret redaction."""

    MAX_RETRIES = 3
    RETRY_STATUS = {429, 500, 502, 503, 504}

    def __init__(self, settings: Settings, auth: GrowwAuth | None = None):
        self._settings = settings
        self._auth = auth or GrowwAuth(settings)
        self._client = httpx.Client(timeout=30.0)

    def close(self) -> None:
        self._client.close()
        self._auth.close()

    def __enter__(self) -> GrowwClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        token = self._auth.get_access_token()
        return {
            "Authorization": f"Bearer {token.token}",
            "Accept": "application/json",
            "X-API-VERSION": self._settings.groww_api_version,
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        optional: bool = False,
    ) -> dict[str, Any] | None:
        url = f"{self._settings.groww_api_base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self._client.request(
                    method,
                    url,
                    headers=self._headers(),
                    params=params,
                    json=json_body,
                )
                if response.status_code == 401 and attempt == 0:
                    self._auth.get_access_token(force_refresh=True)
                    continue
                if response.status_code in self.RETRY_STATUS:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                response.raise_for_status()
                data = response.json()
                if data.get("status") == "FAILURE":
                    err = data.get("error", {})
                    msg = err.get("message", "Unknown Groww API error")
                    raise GrowwAPIError(msg, err.get("code"))
                return data
            except AuthError:
                raise
            except GrowwAPIError:
                raise
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if optional and exc.response.status_code in (403, 404):
                    logger.warning(
                        "Optional request forbidden/not found: %s %s",
                        path,
                        exc.response.status_code,
                    )
                    return None
                if exc.response.status_code in self.RETRY_STATUS:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                body = redact_secrets(exc.response.text[:500])
                raise GrowwAPIError(
                    f"HTTP {exc.response.status_code}: {body}"
                ) from exc
            except httpx.RequestError as exc:
                last_error = exc
                time.sleep(0.5 * (attempt + 1))

        raise GrowwAPIError(f"Request failed after retries: {last_error}")

    def get_holdings(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/v1/holdings/user")
        if not data:
            return []
        return data.get("payload", {}).get("holdings", [])

    def get_positions(self, segment: str | None = None) -> list[dict[str, Any]]:
        params = {"segment": segment} if segment else None
        data = self._request("GET", "/v1/positions/user", params=params)
        if not data:
            return []
        return data.get("payload", {}).get("positions", [])

    def get_ltp(
        self, segment: str, exchange_symbols: list[str]
    ) -> dict[str, float]:
        """Fetch LTP with per-symbol fallback if batch live-data is forbidden."""
        if not exchange_symbols:
            return {}

        results: dict[str, float] = {}
        batch_size = 50

        for i in range(0, len(exchange_symbols), batch_size):
            batch = exchange_symbols[i : i + batch_size]
            data = self._request(
                "GET",
                "/v1/live-data/ltp",
                params={"segment": segment, "exchange_symbols": ",".join(batch)},
                optional=True,
            )
            if data:
                payload = data.get("payload", {})
                for key, value in payload.items():
                    results[key] = float(value)
                continue

            # Batch failed (often 403) — try symbols one at a time
            for symbol_key in batch:
                single = self._request(
                    "GET",
                    "/v1/live-data/ltp",
                    params={"segment": segment, "exchange_symbols": symbol_key},
                    optional=True,
                )
                if single:
                    for key, value in single.get("payload", {}).items():
                        results[key] = float(value)
                    continue

                # Last resort: quote endpoint for individual stock
                if "_" in symbol_key:
                    exchange, trading_symbol = symbol_key.split("_", 1)
                    quote = self._request(
                        "GET",
                        "/v1/live-data/quote",
                        params={
                            "exchange": exchange,
                            "segment": segment,
                            "trading_symbol": trading_symbol,
                        },
                        optional=True,
                    )
                    if quote:
                        payload = quote.get("payload", {})
                        last = payload.get("last_price")
                        if last is not None:
                            results[symbol_key] = float(last)

        return results

    def get_quote(
        self, exchange: str, segment: str, trading_symbol: str
    ) -> dict[str, Any]:
        data = self._request(
            "GET",
            "/v1/live-data/quote",
            params={
                "exchange": exchange,
                "segment": segment,
                "trading_symbol": trading_symbol,
            },
        )
        return data.get("payload", {})

    def get_historical_candles(
        self,
        exchange: str,
        segment: str,
        trading_symbol: str,
        start_time: str,
        end_time: str,
        interval_in_minutes: int = 1440,
    ) -> list[list[Any]]:
        data = self._request(
            "GET",
            "/v1/historical/candle/range",
            params={
                "exchange": exchange,
                "segment": segment,
                "trading_symbol": trading_symbol,
                "start_time": start_time,
                "end_time": end_time,
                "interval_in_minutes": str(interval_in_minutes),
            },
            optional=True,
        )
        if not data:
            return []
        return data.get("payload", {}).get("candles", [])

    def log_response_debug(self, label: str, data: dict[str, Any]) -> None:
        logger.debug("%s: %s", label, redact_secrets(json.dumps(data)[:1000]))
