"""Tests for :class:`nyora.sync.NyoraSync`, fully offline via httpx MockTransport."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from nyora.sync import NotSignedInError, NyoraSync


def _make(handler: Callable[[httpx.Request], httpx.Response], tmp_path) -> NyoraSync:
    sync = NyoraSync(token_path=str(tmp_path / "sync.json"))
    sync._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://sync.test")
    return sync


def test_sign_in_stores_tokens(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/token"
        assert b"grant_type=password" in request.content
        return httpx.Response(200, json={"access_token": "a", "refresh_token": "r"})

    sync = _make(handler, tmp_path)
    sync.sign_in("Me@X.com", "pw")
    assert sync.is_signed_in
    assert sync.email == "me@x.com"


def test_upsert_uses_bearer_and_returns_count(tmp_path) -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/token":
            return httpx.Response(200, json={"access_token": "a", "refresh_token": "r"})
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"ok": True, "count": 3})

    sync = _make(handler, tmp_path)
    sync.sign_in("me@x.com", "pw")
    assert sync.upsert("nyora_manga", [{"id": "1"}]) == 3
    assert seen["auth"] == "Bearer a"


def test_refreshes_once_on_401(tmp_path) -> None:
    state = {"tokens": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/token":
            state["tokens"] += 1
            token = "a2" if state["tokens"] == 2 else "a1"
            return httpx.Response(200, json={"access_token": token, "refresh_token": "r"})
        if request.headers.get("authorization") == "Bearer a1":
            return httpx.Response(401, json={})
        return httpx.Response(200, json={"data": [{"manga_id": "x"}]})

    sync = _make(handler, tmp_path)
    sync.sign_in("me@x.com", "pw")
    assert sync.select("nyora_favourite") == [{"manga_id": "x"}]
    assert state["tokens"] == 2  # signed in once, refreshed once


def test_requires_sign_in(tmp_path) -> None:
    sync = NyoraSync(token_path=str(tmp_path / "sync.json"))
    with pytest.raises(NotSignedInError):
        sync.upsert("nyora_manga", [{"id": "1"}])
