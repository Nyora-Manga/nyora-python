"""Tests for :class:`nyora.server.NyoraServer` with a FakeRuntime injected.

The server is started on port 0 (ephemeral) and driven with a real httpx
client against ``127.0.0.1`` only; no external network is touched.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from nyora.server import NyoraServer
from tests.conftest import FakeRuntime


@pytest.fixture
def server() -> Iterator[tuple[NyoraServer, FakeRuntime]]:
    runtime = FakeRuntime()
    srv = NyoraServer(port=0, runtime=runtime, write_port_file=False)
    srv.start()
    try:
        yield srv, runtime
    finally:
        srv.stop()


def test_base_url_is_loopback(server: tuple[NyoraServer, FakeRuntime]) -> None:
    srv, _ = server
    assert srv.base_url.startswith("http://127.0.0.1:")


def test_health(server: tuple[NyoraServer, FakeRuntime]) -> None:
    srv, _ = server
    resp = httpx.get(f"{srv.base_url}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") is True


def test_sources_helper_shape(server: tuple[NyoraServer, FakeRuntime]) -> None:
    srv, _ = server
    resp = httpx.get(f"{srv.base_url}/sources")
    assert resp.status_code == 200
    body = resp.json()
    sources = body["sources"]
    assert isinstance(sources, list)
    first = sources[0]
    # helper-compatible keys produced by _source_to_helper_shape
    assert first["id"] == "mangadex"
    assert first["name"] == "MangaDex"
    assert first["lang"] == "en"
    assert first["baseUrl"] == "https://mangadex.org"
    assert first["engine"] == "JavaScript"
    assert first["isInstalled"] is True
    assert first["canUninstall"] is False


def test_search_contract(server: tuple[NyoraServer, FakeRuntime]) -> None:
    srv, runtime = server
    resp = httpx.get(
        f"{srv.base_url}/sources/search", params={"id": "mangadex", "q": "naruto", "page": 1}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "entries" in body
    assert "hasNextPage" in body
    assert body["entries"][0]["id"] == "manga-1"
    # runtime received the search call with the query forwarded
    src, method, args = runtime.calls[-1]
    assert src == "mangadex"
    assert method == "search"
    assert args["query"] == "naruto"


def test_popular_and_latest(server: tuple[NyoraServer, FakeRuntime]) -> None:
    srv, _ = server
    for path in ("popular", "latest"):
        resp = httpx.get(f"{srv.base_url}/sources/{path}", params={"id": "mangadex", "page": 2})
        assert resp.status_code == 200
        assert resp.json()["entries"][0]["title"] == "Test Manga"


def test_details_contract(server: tuple[NyoraServer, FakeRuntime]) -> None:
    srv, _ = server
    resp = httpx.get(
        f"{srv.base_url}/manga/details", params={"id": "mangadex", "url": "/manga/manga-1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["manga"]["id"] == "manga-1"
    assert "chapters" in body


def test_pages_contract(server: tuple[NyoraServer, FakeRuntime]) -> None:
    srv, _ = server
    resp = httpx.get(
        f"{srv.base_url}/manga/pages", params={"id": "mangadex", "url": "/chapter/ch-1"}
    )
    assert resp.status_code == 200
    pages = resp.json()["pages"]
    assert pages[0]["url"] == "https://img.example/page-1.jpg"


def test_unknown_path_404(server: tuple[NyoraServer, FakeRuntime]) -> None:
    srv, _ = server
    resp = httpx.get(f"{srv.base_url}/does/not/exist")
    assert resp.status_code == 404


def test_error_body_on_runtime_failure(tmp_path: object) -> None:
    class BoomRuntime(FakeRuntime):
        def call(self, source_id: str, method: str, args: dict) -> object:  # type: ignore[override]
            raise RuntimeError("boom")

    runtime = BoomRuntime()
    srv = NyoraServer(port=0, runtime=runtime, write_port_file=False)
    srv.start()
    try:
        resp = httpx.get(
            f"{srv.base_url}/sources/popular", params={"id": "mangadex", "page": 1}
        )
        assert resp.status_code >= 400
        assert "error" in resp.json()
    finally:
        srv.stop()
