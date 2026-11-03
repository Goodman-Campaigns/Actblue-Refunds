import base64
import json

import pytest

from actblue_refunds.accounts import load_accounts
from actblue_refunds.secrets import SecretLookupError, SecretManager, secret_name_for


class FakeVault:
    def __init__(self, secrets, error=None):
        self.secrets = secrets
        self.error = error
        self.asked = []

    def get_credentials(self, key):
        self.asked.append(key)
        if self.error:
            raise SecretLookupError(self.error)
        return self.secrets.get(key)


def _config(tmp_path):
    config = tmp_path / "accounts.yaml"
    config.write_text(
        "accounts:\n"
        "  - key: brad_lander\n    name: Brad Lander\n"
        "  - key: jose_garza\n    name: Jose Garza\n"
        "  - key: outvote\n    name: Outvote\n"
    )
    return str(config)


def test_secret_name_matches_vault_naming():
    assert secret_name_for("brad_lander") == "actblue_brad-lander"
    assert secret_name_for("house_democratic_campaign_committee_of_louisiana") == (
        "actblue_house-democratic-campaign-committee-of-louisiana"
    )


def test_vault_fills_in_credentials_env_vars_take_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("ACTBLUE_OUTVOTE_CLIENT_UUID", "env-uuid")
    monkeypatch.setenv("ACTBLUE_OUTVOTE_CLIENT_SECRET", "env-secret")
    vault = FakeVault({"brad_lander": ("u1", "s1"), "outvote": ("vault-u", "vault-s")})

    accounts, missing = load_accounts(_config(tmp_path), skip_missing=True, secret_manager=vault)

    by_key = {a["key"]: a for a in accounts}
    assert (by_key["brad_lander"]["client_uuid"], by_key["brad_lander"]["client_secret"]) == ("u1", "s1")
    assert by_key["outvote"]["client_uuid"] == "env-uuid"
    assert "outvote" not in vault.asked
    assert [m["key"] for m in missing] == ["jose_garza"]
    assert "actblue_jose-garza" in missing[0]["missing"][0]


def test_vault_errors_are_reported_per_account_not_raised(tmp_path):
    vault = FakeVault({}, error="Secret Manager refused access")
    accounts, missing = load_accounts(_config(tmp_path), skip_missing=True, secret_manager=vault)
    assert accounts == []
    assert len(missing) == 3
    assert missing[0]["missing"] == ["Secret Manager refused access"]


class _Resp:
    def __init__(self, status, body=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._body = body

    def json(self):
        return self._body


def _manager(monkeypatch, response):
    sm = SecretManager("my-project", {})
    monkeypatch.setattr(sm, "_access_token", lambda: "tok")
    calls = []

    def fake_get(url, headers, timeout):
        calls.append((url, headers))
        return response

    monkeypatch.setattr("actblue_refunds.secrets.requests.get", fake_get)
    return sm, calls


def test_secret_manager_reads_latest_version_json(monkeypatch):
    data = base64.b64encode(json.dumps({"client_uuid": "u", "client_secret": "s"}).encode()).decode()
    sm, calls = _manager(monkeypatch, _Resp(200, {"payload": {"data": data}}))
    assert sm.get_credentials("brad_lander") == ("u", "s")
    assert calls[0][0].endswith("/projects/my-project/secrets/actblue_brad-lander/versions/latest:access")
    assert calls[0][1]["Authorization"] == "Bearer tok"


def test_secret_manager_missing_secret_is_none(monkeypatch):
    sm, _ = _manager(monkeypatch, _Resp(404))
    assert sm.get_credentials("brad_lander") is None


def test_secret_manager_permission_denied_explains_role(monkeypatch):
    sm, _ = _manager(monkeypatch, _Resp(403))
    with pytest.raises(SecretLookupError, match="Secret Accessor"):
        sm.get_credentials("brad_lander")


def test_secret_manager_bad_format(monkeypatch):
    data = base64.b64encode(b"just-a-string").decode()
    sm, _ = _manager(monkeypatch, _Resp(200, {"payload": {"data": data}}))
    with pytest.raises(SecretLookupError, match="expected"):
        sm.get_credentials("brad_lander")


def test_from_env_needs_both_variables(monkeypatch):
    assert SecretManager.from_env() is None
    monkeypatch.setenv("ACTBLUE_SECRETS_PROJECT", "p")
    assert SecretManager.from_env() is None
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "not json")
    with pytest.raises(SecretLookupError):
        SecretManager.from_env()


def test_bad_service_account_json_reported_per_account(tmp_path, monkeypatch):
    monkeypatch.setenv("ACTBLUE_SECRETS_PROJECT", "p")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "not json")
    accounts, missing = load_accounts(_config(tmp_path), skip_missing=True)
    assert accounts == []
    assert missing[0]["missing"] == ["GOOGLE_SERVICE_ACCOUNT_JSON isn't valid JSON"]
