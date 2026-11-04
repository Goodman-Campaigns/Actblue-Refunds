"""Client for ActBlue's CSV report API (https://secure.actblue.com/api/v1)."""

import time

import requests

API_BASE = "https://secure.actblue.com/api/v1"

# Identify this tool honestly. ActBlue's firewall rejects requests carrying
# the generic "python-requests" User-Agent with an HTML 403 before they reach
# the API, so set a descriptive one (and ask for JSON) on every request.
HEADERS = {
    "User-Agent": "actblue-refunds/1.0 (Goodman Campaigns refund reporting; CSV API)",
    "Accept": "application/json",
}


class ActBlueAPIError(Exception):
    """Raised when ActBlue reports that CSV generation failed."""


class ActBlueClient:
    """Requests and downloads CSV reports for a single ActBlue entity."""

    def __init__(self, client_uuid, client_secret, timeout=30):
        self.auth = (client_uuid, client_secret)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def request_csv(self, csv_type, date_range_start, date_range_end):
        response = self.session.post(
            f"{API_BASE}/csvs",
            auth=self.auth,
            json={
                "csv_type": csv_type,
                "date_range_start": date_range_start,
                "date_range_end": date_range_end,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["id"]

    def poll_csv(self, csv_id, poll_interval=2, max_retries=150):
        for _ in range(max_retries):
            response = self.session.get(f"{API_BASE}/csvs/{csv_id}", auth=self.auth, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if data.get("download_url"):
                return data["download_url"]
            if data.get("status") == "failed":
                raise ActBlueAPIError(f"CSV generation failed for id {csv_id}: {data}")
            time.sleep(poll_interval)
        raise TimeoutError(f"Timed out waiting for ActBlue CSV {csv_id} to generate")

    def download_csv(self, download_url):
        response = self.session.get(download_url, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def get_refunded_contributions(self, date_range_start, date_range_end, poll_interval=2, max_retries=150):
        """Fetch the 'refunded_contributions' report for this account and date range.

        date_range_start is inclusive, date_range_end is exclusive (both 'YYYY-MM-DD'),
        per ActBlue's CSV API.
        """
        csv_id = self.request_csv("refunded_contributions", date_range_start, date_range_end)
        download_url = self.poll_csv(csv_id, poll_interval=poll_interval, max_retries=max_retries)
        return self.download_csv(download_url)
