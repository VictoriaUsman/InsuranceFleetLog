import requests

from connectors.base import RestConnector


class FakeResponse:
    def __init__(self, status_code, json_data=None, headers=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.headers = headers or {}
        self.content = b"{}"

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


class FakeSession:
    """Replays a scripted sequence of responses/exceptions, one per call."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def request(self, method, url, **kwargs):
        self.calls += 1
        outcome = self.script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class DummyConnector(RestConnector):
    base_url = "https://api.example.com"

    def _headers(self):
        return {}


def _no_sleep(monkeypatch):
    monkeypatch.setattr("connectors.base.time.sleep", lambda seconds: None)


def test_retries_on_429_then_succeeds(monkeypatch):
    _no_sleep(monkeypatch)
    session = FakeSession([
        FakeResponse(429, headers={"Retry-After": "1"}),
        FakeResponse(200, {"ok": True}),
    ])
    conn = DummyConnector(session=session)
    result = conn.request("GET", "/thing")
    assert result == {"ok": True}
    assert session.calls == 2


def test_retries_on_transient_5xx(monkeypatch):
    _no_sleep(monkeypatch)
    session = FakeSession([FakeResponse(503), FakeResponse(200, {"ok": True})])
    conn = DummyConnector(session=session)
    assert conn.request("GET", "/thing") == {"ok": True}
    assert session.calls == 2


def test_does_not_retry_client_error(monkeypatch):
    _no_sleep(monkeypatch)
    session = FakeSession([FakeResponse(404)])
    conn = DummyConnector(session=session)
    try:
        conn.request("GET", "/missing")
        assert False, "expected HTTPError"
    except requests.HTTPError:
        pass
    assert session.calls == 1


def test_gives_up_after_max_retries(monkeypatch):
    _no_sleep(monkeypatch)
    session = FakeSession([FakeResponse(429)] * 3)
    conn = DummyConnector(session=session)
    conn.max_retries = 3
    try:
        conn.request("GET", "/thing")
        assert False, "expected HTTPError after exhausting retries"
    except requests.HTTPError:
        pass
    assert session.calls == 3


def test_retries_on_connection_error_then_succeeds(monkeypatch):
    _no_sleep(monkeypatch)
    session = FakeSession([requests.ConnectionError("boom"), FakeResponse(200, {"ok": True})])
    conn = DummyConnector(session=session)
    assert conn.request("GET", "/thing") == {"ok": True}
    assert session.calls == 2


def test_backoff_prefers_retry_after_header():
    conn = DummyConnector(session=FakeSession([]))
    assert conn._backoff_seconds(attempt=1, retry_after="5") == 5.0


def test_backoff_is_capped(monkeypatch):
    conn = DummyConnector(session=FakeSession([]))
    conn.backoff_max = 10.0
    monkeypatch.setattr("connectors.base.random.uniform", lambda lo, hi: hi)
    assert conn._backoff_seconds(attempt=10, retry_after=None) == 10.0


def test_throttle_waits_out_min_interval(monkeypatch):
    conn = DummyConnector(session=FakeSession([]))
    conn.min_request_interval = 2.0

    fake_now = {"t": 100.0}
    monkeypatch.setattr("connectors.base.time.monotonic", lambda: fake_now["t"])
    sleeps = []
    monkeypatch.setattr("connectors.base.time.sleep", lambda seconds: sleeps.append(seconds))

    conn._last_request_at = 99.0  # 1s ago; needs 1 more second to reach the 2s floor
    conn._throttle()
    assert sleeps == [1.0]


def test_paginate_follows_cursor_param():
    session = FakeSession([
        FakeResponse(200, {"results": [1, 2], "next": "abc"}),
        FakeResponse(200, {"results": [3], "next": None}),
    ])
    conn = DummyConnector(session=session)
    assert list(conn.paginate("/items")) == [1, 2, 3]
    assert session.calls == 2


def test_paginate_follows_full_next_url():
    session = FakeSession([
        FakeResponse(200, {"results": [1], "next": "https://api.example.com/items?cursor=xyz"}),
        FakeResponse(200, {"results": [2], "next": None}),
    ])
    conn = DummyConnector(session=session)
    assert list(conn.paginate("/items")) == [1, 2]
