"""Loads the list of ActBlue accounts to pull refunds from.

Account names/keys live in a checked-in YAML file (accounts.yaml); the
matching API credentials live only in environment variables / .env so
secrets never get committed.
"""

import os

import yaml


class MissingCredentialsError(Exception):
    pass


def _env_names(key):
    prefix = f"ACTBLUE_{key.upper()}"
    return f"{prefix}_CLIENT_UUID", f"{prefix}_CLIENT_SECRET"


def load_accounts(config_path="accounts.yaml", skip_missing=False):
    """Returns the configured accounts with their credentials.

    With skip_missing=True, accounts whose credentials aren't set are left
    out and returned separately instead of raising, so one missing key pair
    doesn't stop every other account: returns (accounts, missing), where
    missing is a list of {"key", "name", "missing": [env var names]}.
    """
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
        if not client_uuid or not client_secret:
            if skip_missing:
                missing.append(
                    {
                        "key": key,
                        "name": name,
                        "missing": [n for n, v in ((uuid_env, client_uuid), (secret_env, client_secret)) if not v],
                    }
                )
                continue
            raise MissingCredentialsError(
                f"Missing credentials for account '{key}'. Set {uuid_env} and "
                f"{secret_env} in your environment or .env file."
            )
        accounts.append({"key": key, "name": name, "client_uuid": client_uuid, "client_secret": client_secret})
    if skip_missing:
        return accounts, missing
    return accounts
