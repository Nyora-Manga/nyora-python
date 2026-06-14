"""Tests for the direct (no-helper) services against a FakeRuntime."""

from __future__ import annotations

import pytest

from nyora.direct import (
    DirectMangaService,
    DirectSourcesService,
    _source_to_helper_shape,
)
from nyora.models import Manga, MangaDetails, MangaPage, SearchPage, Source
from tests.conftest import SAMPLE_SOURCE_RAW, FakeRuntime


def test_source_to_helper_shape() -> None:
    shaped = _source_to_helper_shape(dict(SAMPLE_SOURCE_RAW))
    assert shaped["id"] == "mangadex"
    assert shaped["name"] == "MangaDex"
    assert shaped["lang"] == "en"
    assert shaped["baseUrl"] == "https://mangadex.org"
    assert shaped["engine"] == "JavaScript"
    assert shaped["isInstalled"] is True
    assert shaped["canUninstall"] is False
    assert shaped["isNsfw"] is False


def test_source_to_helper_shape_missing_domain() -> None:
    shaped = _source_to_helper_shape({"id": "x"})
    assert shaped["baseUrl"] == ""
    assert shaped["name"] == "x"


def test_sources_list() -> None:
    service = DirectSourcesService(FakeRuntime())
    sources = service.list()
    assert all(isinstance(s, Source) for s in sources)
    assert sources[0].id == "mangadex"
    assert sources[0].name == "MangaDex"
    assert sources[0].base_url == "https://mangadex.org"


def test_sources_find_by_id() -> None:
    service = DirectSourcesService(FakeRuntime())
    found = service.find("weebcentral")
    assert found.id == "weebcentral"


def test_sources_find_fuzzy_name() -> None:
    service = DirectSourcesService(FakeRuntime())
    found = service.find("dex")  # substring of "MangaDex"
    assert found.id == "mangadex"


def test_sources_find_missing_raises() -> None:
    service = DirectSourcesService(FakeRuntime())
    with pytest.raises(LookupError):
        service.find("no-such-source")


def test_manga_search_shape() -> None:
    runtime = FakeRuntime()
    service = DirectMangaService(runtime)
    page = service.search("mangadex", "naruto", page=3)
    assert isinstance(page, SearchPage)
    assert page.entries[0].id == "manga-1"
    src, method, args = runtime.calls[-1]
    assert (src, method) == ("mangadex", "search")
    assert args == {"query": "naruto", "page": 3}


def test_manga_popular_and_latest() -> None:
    runtime = FakeRuntime()
    service = DirectMangaService(runtime)
    assert isinstance(service.popular("mangadex"), SearchPage)
    assert isinstance(service.latest("mangadex"), SearchPage)
    methods = [c[1] for c in runtime.calls]
    assert methods == ["popular", "latest"]


def test_manga_details_shape() -> None:
    runtime = FakeRuntime()
    service = DirectMangaService(runtime)
    details = service.details("mangadex", "/manga/manga-1")
    assert isinstance(details, MangaDetails)
    assert isinstance(details.manga, Manga)
    assert details.manga.id == "manga-1"
    # chapters are lifted from the embedded manga payload
    assert len(details.chapters) == 1
    assert details.chapters[0].id == "ch-1"


def test_manga_pages_shape() -> None:
    runtime = FakeRuntime()
    service = DirectMangaService(runtime)
    pages = service.pages("mangadex", "/chapter/ch-1", branch="English")
    assert all(isinstance(p, MangaPage) for p in pages)
    assert pages[0].url == "https://img.example/page-1.jpg"
    _, method, args = runtime.calls[-1]
    assert method == "pages"
    assert args == {"url": "/chapter/ch-1", "branch": "English"}
