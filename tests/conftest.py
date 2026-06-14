"""Shared fakes and fixtures for the Nyora test suite.

Everything here is offline by design: a :class:`FakeRuntime` stands in for the
real :class:`nyora.runtime.ParserRuntime`, exposing the exact surface the rest
of the package depends on (``sources()`` / ``call()`` / ``close()`` /
``reload()``) without spinning up the embedded JavaScript engine or touching the
network.
"""

from __future__ import annotations

from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Canonical sample payloads (raw runtime shapes -- camelCase, as the real
# ParserRuntime emits them and as Manga.from_json consumes them).
# ---------------------------------------------------------------------------

#: A raw source dict as returned by ``ParserRuntime.sources()`` (NOT the
#: helper-shaped variant). Keys mirror the JS parser metadata.
SAMPLE_SOURCE_RAW: dict[str, Any] = {
    "id": "mangadex",
    "title": "MangaDex",
    "locale": "en",
    "domain": "mangadex.org",
    "isNsfw": False,
}

SAMPLE_SOURCE_RAW_2: dict[str, Any] = {
    "id": "weebcentral",
    "title": "Weeb Central",
    "locale": "en",
    "domain": "weebcentral.com",
    "isNsfw": True,
}

#: A raw manga entry as emitted by popular/latest/search parser methods.
SAMPLE_MANGA_RAW: dict[str, Any] = {
    "id": "manga-1",
    "title": "Test Manga",
    "altTitles": ["Alt One", "Alt Two"],
    "url": "/manga/manga-1",
    "publicUrl": "https://mangadex.org/manga/manga-1",
    "rating": 4.5,
    "isNsfw": False,
    "coverUrl": "https://img.example/cover.jpg",
    "authors": ["Author A"],
    "tags": [{"key": "action", "title": "Action"}],
    "description": "A test manga.",
}

#: A raw chapter, as embedded in a details payload.
SAMPLE_CHAPTER_RAW: dict[str, Any] = {
    "id": "ch-1",
    "title": "Chapter 1",
    "number": 1.0,
    "volume": 1,
    "url": "/chapter/ch-1",
    "uploadDate": 1_700_000_000,
    "branch": "English",
    "index": 0,
}

#: A raw page, as emitted by the pages parser method.
SAMPLE_PAGE_RAW: dict[str, Any] = {
    "url": "https://img.example/page-1.jpg",
    "headers": {"Referer": "https://mangadex.org/"},
}


class FakeRuntime:
    """In-memory stand-in for :class:`nyora.runtime.ParserRuntime`.

    Records every ``call`` for assertions and serves canned payloads keyed by
    parser method. Construct with overrides to exercise edge cases.
    """

    def __init__(
        self,
        *,
        sources: list[dict[str, Any]] | None = None,
        responses: dict[str, Any] | None = None,
    ) -> None:
        self._sources = (
            sources if sources is not None else [dict(SAMPLE_SOURCE_RAW), dict(SAMPLE_SOURCE_RAW_2)]
        )
        self._responses = responses or {}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.closed = False
        self.reloaded = 0

    # -- runtime surface ----------------------------------------------------
    def sources(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._sources]

    def call(self, source_id: str, method: str, args: dict[str, Any]) -> Any:
        self.calls.append((source_id, method, dict(args)))
        if method in self._responses:
            return self._responses[method]
        if method in ("popular", "latest", "search"):
            return [dict(SAMPLE_MANGA_RAW)]
        if method == "details":
            manga = dict(SAMPLE_MANGA_RAW)
            manga["chapters"] = [dict(SAMPLE_CHAPTER_RAW)]
            return manga
        if method == "pages":
            return [dict(SAMPLE_PAGE_RAW)]
        raise AssertionError(f"unexpected method {method!r}")

    def close(self) -> None:
        self.closed = True

    def reload(self) -> None:
        self.reloaded += 1


@pytest.fixture
def fake_runtime() -> FakeRuntime:
    return FakeRuntime()


@pytest.fixture
def sample_source_raw() -> dict[str, Any]:
    return dict(SAMPLE_SOURCE_RAW)


@pytest.fixture
def sample_manga_raw() -> dict[str, Any]:
    return dict(SAMPLE_MANGA_RAW)
