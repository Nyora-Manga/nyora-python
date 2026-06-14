"""Round-trip and default-value tests for the camelCase dataclass models."""

from __future__ import annotations

from nyora.models import (
    Manga,
    MangaChapter,
    MangaDetails,
    MangaPage,
    SearchPage,
    Source,
)
from tests.conftest import (
    SAMPLE_CHAPTER_RAW,
    SAMPLE_MANGA_RAW,
    SAMPLE_PAGE_RAW,
)


def test_manga_from_json_full() -> None:
    manga = Manga.from_json(SAMPLE_MANGA_RAW)
    assert manga.id == "manga-1"
    assert manga.title == "Test Manga"
    assert manga.alt_titles == ["Alt One", "Alt Two"]
    assert manga.url == "/manga/manga-1"
    assert manga.public_url == "https://mangadex.org/manga/manga-1"
    assert manga.rating == 4.5
    assert manga.is_nsfw is False
    assert manga.cover_url == "https://img.example/cover.jpg"
    assert manga.authors == ["Author A"]
    assert manga.tags == [{"key": "action", "title": "Action"}]
    assert manga.description == "A test manga."


def test_manga_from_json_defaults() -> None:
    manga = Manga.from_json({"id": "x", "title": "Y"})
    assert manga.id == "x"
    assert manga.title == "Y"
    # documented defaults
    assert manga.alt_titles == []
    assert manga.url == ""
    assert manga.public_url == ""
    assert manga.rating == -1.0
    assert manga.is_nsfw is False
    assert manga.content_rating is None
    assert manga.cover_url == ""
    assert manga.large_cover_url is None
    assert manga.authors == []
    assert manga.tags == []
    assert manga.chapters == []


def test_manga_from_json_non_dict_is_safe() -> None:
    manga = Manga.from_json(None)
    assert manga.id == ""
    assert manga.title == ""
    assert manga.chapters == []


def test_manga_embedded_chapters() -> None:
    raw = dict(SAMPLE_MANGA_RAW)
    raw["chapters"] = [dict(SAMPLE_CHAPTER_RAW)]
    manga = Manga.from_json(raw)
    assert len(manga.chapters) == 1
    assert isinstance(manga.chapters[0], MangaChapter)
    assert manga.chapters[0].id == "ch-1"


def test_chapter_from_json_full() -> None:
    chapter = MangaChapter.from_json(SAMPLE_CHAPTER_RAW)
    assert chapter.id == "ch-1"
    assert chapter.title == "Chapter 1"
    assert chapter.number == 1.0
    assert chapter.volume == 1
    assert chapter.url == "/chapter/ch-1"
    assert chapter.upload_date == 1_700_000_000
    assert chapter.branch == "English"
    assert chapter.index == 0
    assert chapter.pages == []


def test_chapter_from_json_defaults() -> None:
    chapter = MangaChapter.from_json({})
    assert chapter.id == ""
    assert chapter.title == ""
    assert chapter.number == 0.0
    assert chapter.volume == 0
    assert chapter.scanlator is None
    assert chapter.branch is None
    assert chapter.pages == []


def test_chapter_bad_numbers_fall_back() -> None:
    chapter = MangaChapter.from_json({"number": "not-a-number", "volume": None})
    assert chapter.number == 0.0
    assert chapter.volume == 0


def test_page_from_json_dict() -> None:
    page = MangaPage.from_json(SAMPLE_PAGE_RAW)
    assert page.url == "https://img.example/page-1.jpg"
    assert page.headers == {"Referer": "https://mangadex.org/"}


def test_page_from_json_string() -> None:
    page = MangaPage.from_json("https://img.example/bare.jpg")
    assert page.url == "https://img.example/bare.jpg"
    assert page.headers == {}


def test_source_from_json_helper_shape() -> None:
    helper = {
        "id": "mangadex",
        "name": "MangaDex",
        "lang": "en",
        "baseUrl": "https://mangadex.org",
        "engine": "JavaScript",
        "contentType": "Manga",
        "isInstalled": True,
        "isPinned": False,
        "isNsfw": False,
        "canUninstall": False,
    }
    source = Source.from_json(helper)
    assert source.id == "mangadex"
    assert source.name == "MangaDex"
    assert source.lang == "en"
    assert source.base_url == "https://mangadex.org"
    assert source.engine == "JavaScript"
    assert source.is_installed is True
    assert source.can_uninstall is False


def test_source_from_json_fallback_keys() -> None:
    # title/locale/site are the fallback aliases for name/lang/base_url.
    source = Source.from_json({"id": "s1", "title": "Alt Name", "locale": "ja", "site": "x.test"})
    assert source.name == "Alt Name"
    assert source.lang == "ja"
    assert source.base_url == "x.test"
    # can_uninstall defaults to True when absent
    assert source.can_uninstall is True


def test_search_page_from_json() -> None:
    page = SearchPage.from_json(
        {"entries": [dict(SAMPLE_MANGA_RAW), dict(SAMPLE_MANGA_RAW)], "hasNextPage": True}
    )
    assert len(page.entries) == 2
    assert all(isinstance(entry, Manga) for entry in page.entries)
    assert page.has_next_page is True


def test_search_page_defaults() -> None:
    page = SearchPage.from_json({})
    assert page.entries == []
    assert page.has_next_page is False


def test_manga_details_from_json() -> None:
    details = MangaDetails.from_json(
        {"manga": dict(SAMPLE_MANGA_RAW), "chapters": [dict(SAMPLE_CHAPTER_RAW)]}
    )
    assert isinstance(details.manga, Manga)
    assert details.manga.id == "manga-1"
    assert len(details.chapters) == 1
    assert details.chapters[0].id == "ch-1"
