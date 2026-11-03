import pytest


@pytest.fixture(autouse=True)
def _no_real_secret_manager(monkeypatch):
    monkeypatch.delenv("ACTBLUE_SECRETS_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
