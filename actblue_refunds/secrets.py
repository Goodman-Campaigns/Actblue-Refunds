"""Reads ActBlue credentials from Google Cloud Secret Manager.

Secrets follow the vault naming from scripts/add-secrets.sh: one secret per
client named actblue_<client> (e.g. actblue_brad-lander), whose value is
JSON {"client_uuid": ..., "client_secret": ...}.

Turned on by two environment variables:
  ACTBLUE_SECRETS_PROJECT       Google Cloud project ID holding the secrets
  GOOGLE_SERVICE_ACCOUNT_JSON   the full JSON key of a service account with
                                the Secret Manager Secret Accessor role
"""

import base64
import json
import os

import requests

API = "https://secretmanager.googleapis.com/v1"
SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class SecretLookupError(Exception):
    pass


def secret_name_for(key):
    return "actblue_" + key.replace("_", "-")


class SecretManager:
    def __init__(self, project, service_account_info, timeout=30):
        self.project = project
        self.service_account_info = service_account_info
        self.timeout = timeout
        self._token = None
        self._sign_in_error = None

    @classmethod
    def from_env(cls):
        project = os.environ.get("ACTBLUE_SECRETS_PROJECT")
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not project or not sa_json:
            return None
        try:
            info = json.loads(sa_json)
        except ValueError as e:
            raise SecretLookupError("GOOGLE_SERVICE_ACCOUNT_JSON isn't valid JSON") from e
        return cls(project, info)

    def _access_token(self):
        if self._sign_in_error:
            raise self._sign_in_error
        if self._token is None:
            from google.auth.transport.requests import Request
            from google.oauth2 import service_account

            creds = service_account.Credentials.from_service_account_info(self.service_account_info, scopes=[SCOPE])
            try:
                creds.refresh(Request())
            except Exception as e:  # google.auth.exceptions.RefreshError and transport errors
                self._sign_in_error = SecretLookupError(f"couldn't sign in to Google Cloud with the service account: {e}")
                raise self._sign_in_error from e
            self._token = creds.token
        return self._token

    def get_credentials(self, key):
        """Returns (client_uuid, client_secret), or None if the secret doesn't exist."""
        name = secret_name_for(key)
        url = f"{API}/projects/{self.project}/secrets/{name}/versions/latest:access"
        try:
            r = requests.get(url, headers={"Authorization": f"Bearer {self._access_token()}"}, timeout=self.timeout)
        except requests.RequestException as e:
            raise SecretLookupError(f"couldn't reach Secret Manager for {name}: {e}") from e
        if r.status_code == 404:
            return None
        if r.status_code in (401, 403):
            raise SecretLookupError(
                f"Secret Manager refused access to {name} (HTTP {r.status_code}); the service account "
                "needs the Secret Manager Secret Accessor role"
            )
        if not r.ok:
            raise SecretLookupError(f"Secret Manager error for {name}: HTTP {r.status_code}")
        try:
            value = json.loads(base64.b64decode(r.json()["payload"]["data"]))
            return value["client_uuid"], value["client_secret"]
        except (KeyError, ValueError, TypeError) as e:
            raise SecretLookupError(f"{name} isn't in the expected {{client_uuid, client_secret}} format") from e
