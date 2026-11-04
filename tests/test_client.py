from actblue_refunds.client import HEADERS, ActBlueClient


def test_client_sends_descriptive_user_agent_not_python_default():
    client = ActBlueClient("u", "s")
    ua = client.session.headers["User-Agent"]
    assert ua == HEADERS["User-Agent"]
    assert "python-requests" not in ua
    assert client.session.headers["Accept"] == "application/json"


def test_all_requests_go_through_the_session(monkeypatch):
    calls = []

    class Resp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

        text = "a,b\n1,2\n"

    client = ActBlueClient("u", "s")
    monkeypatch.setattr(client.session, "post", lambda url, **kw: calls.append(("post", url)) or Resp({"id": "1"}))
    monkeypatch.setattr(
        client.session,
        "get",
        lambda url, **kw: calls.append(("get", url)) or Resp({"download_url": "https://dl"}),
    )
    assert client.get_refunded_contributions("2026-01-01", "2026-02-01", poll_interval=0) == "a,b\n1,2\n"
    assert [c[0] for c in calls] == ["post", "get", "get"]
