from unittest.mock import MagicMock, patch

import pytest

from grow_trade_assistant.secrets import (
    SECRET_FIELDS,
    delete_secret,
    get_secret,
    list_stored_secrets,
    load_secrets_into_env,
    mask_value,
    store_secret,
)


@pytest.fixture
def mock_keyring():
    storage: dict[str, str] = {}

    def set_password(service, account, password):
        storage[f"{service}:{account}"] = password

    def get_password(service, account):
        return storage.get(f"{service}:{account}")

    def delete_password(service, account):
        key = f"{service}:{account}"
        if key not in storage:
            raise Exception("not found")
        del storage[key]

    mock = MagicMock()
    mock.set_password = set_password
    mock.get_password = get_password
    mock.delete_password = delete_password
    mock.errors.PasswordDeleteError = Exception

    with patch("grow_trade_assistant.secrets._keyring", return_value=mock):
        yield storage


def test_store_and_get_secret(mock_keyring):
    store_secret("GROWW_API_KEY", "test-key-12345")
    assert get_secret("GROWW_API_KEY") == "test-key-12345"


def test_delete_secret(mock_keyring):
    store_secret("GROWW_API_KEY", "abc")
    assert delete_secret("GROWW_API_KEY") is True
    assert get_secret("GROWW_API_KEY") is None


def test_list_stored_secrets(mock_keyring):
    store_secret("GROWW_API_KEY", "abc")
    status = list_stored_secrets()
    assert status["GROWW_API_KEY"] is True
    assert status["GROWW_API_SECRET"] is False


def test_mask_value():
    assert mask_value("abcdefghij") == "abcd...ghij"
    assert mask_value("ab") == "****"


def test_load_secrets_into_env_prefers_keychain(mock_keyring, monkeypatch):
    import os

    monkeypatch.setenv("GROWW_API_KEY", "from-env-plaintext")
    store_secret("GROWW_API_KEY", "from-keychain-secure")

    warnings = load_secrets_into_env()
    assert os.environ["GROWW_API_KEY"] == "from-keychain-secure"
    assert any("Keychain" in w for w in warnings)


def test_load_secrets_warns_on_plain_env(mock_keyring, monkeypatch):
    import os

    monkeypatch.delenv("GROWW_API_KEY", raising=False)
    monkeypatch.setenv("GROWW_API_KEY", "plain-text-key")

    warnings = load_secrets_into_env()
    assert any("plain-text .env" in w for w in warnings)
