"""Loads the list of ActBlue accounts to pull refunds from.

Account names/keys live in a checked-in YAML file (accounts.yaml); the
matching API credentials live only in environment variables / .env so
secrets never get committed.
"""

import os

import yaml

from actblue_refunds.secrets import SecretLookupError, SecretManager, secret_name_for


class MissingCredentialsError(Exception):
    pass


def _env_names(key):
    prefix = f"ACTBLUE_{key.upper()}"
    return f"{prefix}_CLIENT_UUID", f"{prefix}_CLIENT_SECRET"


def load_accounts(config_path="accounts.yaml", skip_missing=False, secret_manager="env"):
    """Returns the configured accounts with their credentials.

    With skip_missing=True, accounts whose credentials aren't set are left
    out and returned separately instead of raising, so one missing key pair
    doesn't stop every other account: returns (accounts, missing), where
    missing is a list of {"key", "name", "missing": [what's missing]}.

    Credentials come from ACTBLUE_<KEY>_CLIENT_UUID / _CLIENT_SECRET when
    set; otherwise from Google Secret Manager (secret actblue_<client>) when
    that's configured (see actblue_refunds/secrets.py).
    """
    vault_error = None
    if secret_manager == "env":
        try:
            secret_manager = SecretManager.from_env()
        except SecretLookupError as e:
            secret_manager, vault_error = None, str(e)
    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    accounts = []
    missing = []
    for entry in raw.get("accounts", []):
        key = entry["key"]
        name = entry.get("name", key)
        uuid_env, secret_env = _env_names(key)
        client_uuid = os.environ.get(uuid_env)
        client_secret = os.environ.get(secret_env)
        missing_what = [n for n, v in ((uuid_env, client_uuid), (secret_env, client_secret)) if not v]
        if missing_what and vault_error:
            missing_what = [vault_error]
        if missing_what and secret_manager is not None:
            try:
                found = secret_manager.get_credentials(key)
            except SecretLookupError as e:
                found = None
                missing_what = [str(e)]
            else:
                if found:
                    client_uuid, client_secret = found
                    missing_what = []
                else:
                    missing_what = [f"Secret Manager secret {secret_name_for(key)} (not found)"]
        if not client_uuid or not client_secret or missing_what:
            if skip_missing:
                missing.append(
                    {
                        "key": key,
                        "name": name,
                        "missing": missing_what,
                    }
                )
                continue
            raise MissingCredentialsError(
                f"Missing credentials for account '{key}'. Set {uuid_env} and "
                f"{secret_env}, or add Secret Manager secret {secret_name_for(key)}."
            )
        accounts.append({"key": key, "name": name, "client_uuid": client_uuid, "client_secret": client_secret})
    if skip_missing:
        return accounts, missing
    return accounts
