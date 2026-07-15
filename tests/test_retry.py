"""Tests for retry policy, transport retries, and User-Agent."""

from __future__ import annotations

import httpx
import pytest

from nyora import Nyora, NyoraTimeoutError, RetryConfig
from nyora._meta import USER_AGENT
from nyora.retry import retry_after_seconds


def _client(handler, *, retries=3):
    """A Nyora client wired to a mock transport (no engine launch)."""
    policy = RetryConfig(max_retries=retries, backoff_base=0.0)
    client = Nyora(base_url="http://testserver", retries=policy)
    client._http = httpx.Client(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    return client


def test_retry_config_coerce():
    assert RetryConfig.coerce(None).max_retries == 3
    assert RetryConfig.coerce(5).max_retries == 5
    assert RetryConfig.coerce(-1).max_retries == 0
    policy = RetryConfig(max_retries=2)
    assert RetryConfig.coerce(policy) is policy
    with pytest.raises(TypeError):
        RetryConfig.coerce(True)  # bool must be rejected


def test_backoff_caps_and_retry_after():
    policy = RetryConfig(backoff_base=1.0, backoff_max=8.0, jitter=0.0)
    assert policy.backoff(0) == 1.0
    assert policy.backoff(1) == 2.0
    assert policy.backoff(2) == 4.0
    assert policy.backoff(10) == 8.0  # capped
    assert policy.backoff(0, retry_after=3.0) == 3.0  # honoured
    assert policy.backoff(0, retry_after=100.0) == 8.0  # capped


def test_should_retry_status():
    policy = RetryConfig()
    assert policy.should_retry_status(503)
    assert policy.should_retry_status(429)
    assert not policy.should_retry_status(404)
    assert not policy.should_retry_status(200)


def test_retries_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json={"ok": True})

    client = _client(handler)
    assert client.get("/health") == {"ok": True}
    assert calls["n"] == 3  # two retries + success


def test_gives_up_after_max_retries():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "still busy"})

    client = _client(handler, retries=2)
    from nyora import NyoraHTTPError

    with pytest.raises(NyoraHTTPError) as exc:
        client.get("/health")
    assert exc.value.status_code == 503


def test_timeout_wrapped_as_typed_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    client = _client(handler, retries=1)
    with pytest.raises(NyoraTimeoutError):
        client.get("/health")


def test_user_agent_sent():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, json={})

    _client(handler).get("/health")
    assert seen["ua"].startswith("nyora-python/")


def test_retry_after_parsing():
    resp = httpx.Response(429, headers={"retry-after": "5"})
    assert retry_after_seconds(resp) == 5.0
    assert retry_after_seconds(httpx.Response(200)) is None
    assert retry_after_seconds(httpx.Response(429, headers={"retry-after": "nonsense"})) is None
