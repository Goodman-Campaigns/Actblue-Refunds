import pytest

from actblue_refunds.accounts import MissingCredentialsError, load_accounts


def test_load_accounts_reads_config_and_env(tmp_path, monkeypatch):
    config = tmp_path / "accounts.yaml"
    config.write_text(
        "accounts:\n"
        "  - key: campaign_a\n"
        "    name: Campaign A\n"
    )
    monkeypatch.setenv("ACTBLUE_CAMPAIGN_A_CLIENT_UUID", "uuid-1")
    monkeypatch.setenv("ACTBLUE_CAMPAIGN_A_CLIENT_SECRET", "secret-1")

    accounts = load_accounts(str(config))

    assert accounts == [
        {"key": "campaign_a", "name": "Campaign A", "client_uuid": "uuid-1", "client_secret": "secret-1"}
    ]


def test_load_accounts_missing_credentials_raises(tmp_path, monkeypatch):
    config = tmp_path / "accounts.yaml"
    config.write_text(
        "accounts:\n"
        "  - key: campaign_a\n"
        "    name: Campaign A\n"
    )
    monkeypatch.delenv("ACTBLUE_CAMPAIGN_A_CLIENT_UUID", raising=False)
    monkeypatch.delenv("ACTBLUE_CAMPAIGN_A_CLIENT_SECRET", raising=False)

    with pytest.raises(MissingCredentialsError):
        load_accounts(str(config))


def test_load_accounts_defaults_name_to_key(tmp_path, monkeypatch):
    config = tmp_path / "accounts.yaml"
    config.write_text("accounts:\n  - key: campaign_a\n")
    monkeypatch.setenv("ACTBLUE_CAMPAIGN_A_CLIENT_UUID", "uuid-1")
    monkeypatch.setenv("ACTBLUE_CAMPAIGN_A_CLIENT_SECRET", "secret-1")

    accounts = load_accounts(str(config))

    assert accounts[0]["name"] == "campaign_a"


def test_load_accounts_skip_missing_returns_missing_separately(tmp_path, monkeypatch):
    config = tmp_path / "accounts.yaml"
    config.write_text(
        "accounts:\n"
        "  - key: campaign_a\n"
        "    name: Campaign A\n"
        "  - key: campaign_b\n"
        "    name: Campaign B\n"
    )
    monkeypatch.setenv("ACTBLUE_CAMPAIGN_A_CLIENT_UUID", "uuid-1")
    monkeypatch.setenv("ACTBLUE_CAMPAIGN_A_CLIENT_SECRET", "secret-1")
    monkeypatch.setenv("ACTBLUE_CAMPAIGN_B_CLIENT_UUID", "uuid-2")
    monkeypatch.delenv("ACTBLUE_CAMPAIGN_B_CLIENT_SECRET", raising=False)

    accounts, missing = load_accounts(str(config), skip_missing=True)

    assert [a["key"] for a in accounts] == ["campaign_a"]
    assert missing == [
        {"key": "campaign_b", "name": "Campaign B", "missing": ["ACTBLUE_CAMPAIGN_B_CLIENT_SECRET"]}
    ]


def test_checked_in_accounts_yaml_lists_all_45_clients_with_valid_keys():
    import re
    from pathlib import Path

    import yaml

    raw = yaml.safe_load((Path(__file__).parent.parent / "accounts.yaml").read_text())
    keys = [a["key"] for a in raw["accounts"]]
    assert len(keys) == 45
    assert len(set(keys)) == 45
    assert all(re.fullmatch(r"[a-z0-9_]+", k) for k in keys)
