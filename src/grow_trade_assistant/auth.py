from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from grow_trade_assistant.config import Settings


class AuthError(Exception):
    """Raised when Groww authentication fails."""


@dataclass
class AccessToken:
    token: str
    expiry: str | None = None


def looks_like_access_token(value: str) -> bool:
    """Groww daily access tokens are JWTs and must not be used as API keys."""
    return value.startswith("eyJ") and value.count(".") >= 2


def generate_checksum(secret: str, timestamp: str) -> str:
    """SHA256(secret + timestamp) as required by Groww API."""
    payload = f"{secret}{timestamp}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _redact(value: str, visible: int = 4) -> str:
    if len(value) <= visible * 2:
        return "***"
    return f"{value[:visible]}...{value[-visible:]}"


class GrowwAuth:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self._settings = settings
        self._client = client or httpx.Client(timeout=30.0)
        self._owns_client = client is None
        self._cached: AccessToken | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> GrowwAuth:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_access_token(self, force_refresh: bool = False) -> AccessToken:
        if self._settings.groww_access_token and not force_refresh:
            return AccessToken(token=self._settings.groww_access_token)

        if self._cached and not force_refresh:
            return self._cached

        token = self._fetch_token()
        self._cached = token
        return token

    def _fetch_token(self) -> AccessToken:
        mode = self._settings.groww_auth_mode
        url = f"{self._settings.groww_api_base_url}/v1/token/api/access"
        headers = {
            "Authorization": f"Bearer {self._settings.groww_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if mode == "approval":
            timestamp = str(int(time.time()))
            checksum = generate_checksum(self._settings.groww_api_secret, timestamp)
            body: dict[str, Any] = {
                "key_type": "approval",
                "checksum": checksum,
                "timestamp": timestamp,
            }
        elif mode == "totp":
            if not self._settings.groww_totp:
                raise AuthError(
                    "GROWW_TOTP is required when GROWW_AUTH_MODE=totp. "
                    "Set it in .env or use approval mode."
                )
            body = {"key_type": "totp", "totp": self._settings.groww_totp}
        else:
            raise AuthError(f"Unknown GROWW_AUTH_MODE: {mode}")

        try:
            response = self._client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            raise AuthError(
                "Groww token request failed. If using approval mode, visit the "
                "Groww Cloud API Keys page and approve today's session, then retry. "
                f"HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise AuthError(f"Network error during authentication: {exc}") from exc

        token = data.get("token")
        if not token:
            raise AuthError(
                "Groww did not return an access token. "
                "Approve your API key on the Groww Cloud API Keys page and retry."
            )

        return AccessToken(token=token, expiry=data.get("expiry"))


SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)([A-Za-z0-9._\-+/=]{8,})", re.IGNORECASE),
    re.compile(r'("(?:api_?key|secret|token|checksum|totp)"\s*:\s*")([^"]+)(")', re.IGNORECASE),
    re.compile(r"(GROWW_API_KEY=)([^\s]+)", re.IGNORECASE),
    re.compile(r"(GROWW_API_SECRET=)([^\s]+)", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    result = text
    for pattern in SECRET_PATTERNS:
        if pattern.groups == 3:
            result = pattern.sub(r"\1***\3", result)
        elif pattern.groups == 2 and "Bearer" in pattern.pattern:
            result = pattern.sub(r"\1***", result)
        else:
            result = pattern.sub(r"\1***", result)
    return result
