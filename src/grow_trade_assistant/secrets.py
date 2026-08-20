from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

SERVICE_NAME = "grow-trade-assistant"

# Maps env var names to Keychain account labels
SECRET_FIELDS = {
    "GROWW_API_KEY": "groww_api_key",
    "GROWW_API_SECRET": "groww_api_secret",
    "GROWW_ACCESS_TOKEN": "groww_access_token",
    "GROWW_TOTP": "groww_totp",
}


def _keyring():
    try:
        import keyring
    except ImportError as exc:
        raise RuntimeError(
            "keyring is required for secure credential storage. "
            "Run: pip install keyring"
        ) from exc
    return keyring


def store_secret(env_name: str, value: str) -> None:
    if env_name not in SECRET_FIELDS:
        raise ValueError(f"Unknown secret field: {env_name}")
    keyring = _keyring()
    keyring.set_password(SERVICE_NAME, SECRET_FIELDS[env_name], value)


def get_secret(env_name: str) -> str | None:
    if env_name not in SECRET_FIELDS:
        return None
    keyring = _keyring()
    return keyring.get_password(SERVICE_NAME, SECRET_FIELDS[env_name])


def delete_secret(env_name: str) -> bool:
    if env_name not in SECRET_FIELDS:
        return False
    keyring = _keyring()
    try:
        keyring.delete_password(SERVICE_NAME, SECRET_FIELDS[env_name])
        return True
    except keyring.errors.PasswordDeleteError:
        return False


def delete_all_secrets() -> int:
    removed = 0
    for env_name in SECRET_FIELDS:
        if delete_secret(env_name):
            removed += 1
    return removed


def list_stored_secrets() -> dict[str, bool]:
    return {env_name: get_secret(env_name) is not None for env_name in SECRET_FIELDS}


def mask_value(value: str, visible: int = 4) -> str:
    if len(value) <= visible * 2:
        return "****"
    return f"{value[:visible]}...{value[-visible:]}"


def keychain_available() -> bool:
    try:
        _keyring()
        return True
    except RuntimeError:
        return False


def backend_name() -> str:
    try:
        keyring = _keyring()
        return keyring.get_keyring().__class__.__name__
    except RuntimeError:
        return "unavailable"


def load_secrets_into_env(force_keychain: bool = True) -> list[str]:
    """
    Load secrets from macOS Keychain into os.environ when not already set.
    Returns warnings about insecure .env usage.
    """
    import os

    warnings: list[str] = []
    if not keychain_available():
        return warnings

    for env_name in SECRET_FIELDS:
        env_val = os.getenv(env_name, "").strip()
        chain_val = get_secret(env_name)

        if chain_val and env_val and chain_val != env_val:
            warnings.append(
                f"{env_name} exists in both Keychain and .env — using Keychain (more secure)."
            )
            os.environ[env_name] = chain_val
        elif chain_val:
            os.environ[env_name] = chain_val
        elif env_val and force_keychain:
            warnings.append(
                f"{env_name} is stored in plain-text .env. "
                f"Run: grow-assistant secrets migrate"
            )

    return warnings


def emit_security_warnings(warnings: list[str]) -> None:
    for msg in warnings:
        logger.warning(msg)
