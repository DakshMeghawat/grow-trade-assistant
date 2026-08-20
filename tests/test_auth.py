import hashlib
import time

import pytest

from grow_trade_assistant.auth import generate_checksum, redact_secrets


def test_checksum_is_sha256_of_secret_plus_timestamp():
    secret = "my_secret"
    ts = "1719830400"
    expected = hashlib.sha256(f"{secret}{ts}".encode()).hexdigest()
    assert generate_checksum(secret, ts) == expected


def test_checksum_changes_with_timestamp():
    secret = "my_secret"
    assert generate_checksum(secret, "100") != generate_checksum(secret, "200")


def test_redact_secrets_bearer_token():
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdef123456"
    redacted = redact_secrets(text)
    assert "eyJhbGci" not in redacted
    assert "Bearer" in redacted


def test_redact_secrets_env_vars():
    text = "GROWW_API_KEY=abc123secret456 GROWW_API_SECRET=supersecret789"
    redacted = redact_secrets(text)
    assert "abc123secret456" not in redacted
    assert "supersecret789" not in redacted
