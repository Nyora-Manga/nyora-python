"""The unified sync schema stays field-compatible with nyora-web."""

from __future__ import annotations

import json
from typing import Any

from nyora import schema
from nyora.models import Manga, MangaChapter
from nyora_tui import store as store_mod

# Exact field sets the nyora-web sync client sends (minus server-injected user_id).
WEB_MANGA_FIELDS = {
    "id", "title", "alt_titles", "url", "public_url", "rating", "is_nsfw",
    "content_rating", "cover_url", "large_cover_url", "state", "authors",
    "source_ref", "description", "tags", "updated_at",
}
WEB_FAVOURITE_FIELDS = {"manga_id", "sort_key", "updated_at", "deleted_at"}
WEB_HISTORY_FIELDS = {
    "manga_id", "source_id", "chapter_id", "chapter_title", "page", "scroll",
    "percent", "chapters_count", "updated_at", "deleted_at",
}


def _manga() -> Manga:
    return Manga.from_json(
        {"id": "1", "title": "T", "url": "/m/1", "altTitles": ["A"], "rating": 0.8,
         "isNsfw": True, "coverUrl": "c", "authors": ["x"], "tags": [{"title": "Action"}],
         "description": "d", "state": "ongoing"}
    )


def test_manga_row_matches_web_fields() -> None:
    assert set(schema.manga_row("parser:MDX", _manga())) == WEB_MANGA_FIELDS


def test_favourite_and_history_row_fields() -> None:
    assert set(schema.favourite_row("/m/1")) == WEB_FAVOURITE_FIELDS
    chapter = MangaChapter.from_json({"id": "c1", "title": "Ch 1"})
    row = schema.history_row("parser:MDX", "/m/1", chapter, page=2, total=10, percent=0.2)
    assert set(row) == WEB_HISTORY_FIELDS
    assert row["page"] == 2 and row["chapters_count"] == 10 and row["scroll"] == 0


def test_source_ref_is_name_keyed_and_roundtrips() -> None:
    row = schema.manga_row("parser:MDX", _manga())
    assert json.loads(row["source_ref"]) == {"name": "parser:MDX"}
    assert schema.source_name_of(row["source_ref"]) == "parser:MDX"
    assert schema.source_name_of(json.dumps({"source": "legacy"})) == "legacy"  # legacy key
    assert schema.source_name_of("not json") == ""


def test_lists_are_json_encoded() -> None:
    row = schema.manga_row("s", _manga())
    assert json.loads(row["alt_titles"]) == ["A"]
    assert json.loads(row["authors"]) == ["x"]
    assert json.loads(row["tags"]) == [{"title": "Action"}]


def test_manga_id_unified_across_store_and_schema() -> None:
    # The local store and the sync schema must key manga identically.
    assert store_mod.manga_id_of is schema.manga_id_of
    assert schema.manga_id_of(_manga()) == "/m/1"


def test_nyorasync_builds_rows_through_schema() -> None:
    """The SDK sync client builds cloud rows via the unified schema."""
    from nyora.sync import NyoraSync

    sync = NyoraSync(token_path="")  # no token persistence, no network
    calls: list[tuple[str, list[dict[str, Any]]]] = []
    sync.upsert = lambda table, rows: (calls.append((table, rows)), len(rows))[1]  # type: ignore[method-assign]

    sync.favourite("parser:MDX", _manga())
    assert [t for t, _ in calls] == [schema.TABLE_MANGA, schema.TABLE_FAVOURITE]
    assert set(calls[0][1][0]) == WEB_MANGA_FIELDS
    assert set(calls[1][1][0]) == WEB_FAVOURITE_FIELDS


def test_tuisync_delegates_to_sdk() -> None:
    """TuiSync is a thin facade — favourite() just calls the SDK method."""
    from nyora_tui.sync import TuiSync

    seen: list[tuple[str, Any]] = []

    class _FakeSDK:
        def favourite(self, source_id: str, manga: Any) -> str:
            seen.append((source_id, manga))
            return "id"

    tui = TuiSync()
    tui._sync = _FakeSDK()  # type: ignore[assignment]
    tui.favourite("parser:MDX", _manga())
    assert seen and seen[0][0] == "parser:MDX"


def test_history_syncs_bidirectionally_like_favourites(tmp_path: Any) -> None:
    """History pulls + merges cloud rows (last-write-wins), matching nyora-web."""
    from nyora_tui.store import LocalLibrary

    lib = LocalLibrary(path=tmp_path / "library.json")
    lib._data["history"]["/m/1"] = {
        "manga_id": "/m/1", "title": "A", "updated_at": "2026-01-01T00:00:00", "percent": 0.1,
    }
    lib.merge_cloud_history([
        {"manga_id": "/m/1", "title": "A", "updated_at": "2026-02-01T00:00:00", "percent": 0.8},
        {"manga_id": "/m/2", "title": "B", "updated_at": "2026-01-15T00:00:00", "percent": 0.5},
    ])
    by_id = {e["manga_id"]: e for e in lib.history()}
    assert by_id["/m/1"]["percent"] == 0.8   # newer cloud wins
    assert "/m/2" in by_id                    # new cloud manga pulled in
    # an older cloud row must NOT clobber the newer local entry
    lib.merge_cloud_history([{"manga_id": "/m/1", "updated_at": "2025-01-01", "percent": 0.01}])
    assert {e["manga_id"]: e for e in lib.history()}["/m/1"]["percent"] == 0.8


def test_tuisync_exposes_history_pull() -> None:
    """TuiSync forwards a cloud-history pull (the History screen calls this)."""
    from nyora_tui.sync import TuiSync

    class _FakeSDK:
        def favourites(self):  # noqa: D401
            return []

        def history(self):
            return [{"manga_id": "/m/1", "title": "A", "updated_at": "2026", "percent": 0.5}]

    tui = TuiSync()
    tui._sync = _FakeSDK()  # type: ignore[assignment]
    assert tui.history()[0]["manga_id"] == "/m/1"


def test_sync_now_pushes_local_then_pulls_cloud() -> None:
    """web parity: sync_now upserts local favourites+history, then selects them back."""
    from nyora.sync import NyoraSync

    s = NyoraSync(token_path="")
    upserts: list[tuple[str, int]] = []
    s.upsert = lambda table, rows: (upserts.append((table, len(rows))), len(rows))[1]  # type: ignore[method-assign]
    s.select = lambda table, since=None: []  # type: ignore[method-assign]

    favs = [{"manga_id": "/m/1", "title": "A", "url": "/m/1", "source": "parser:MDX",
             "cover": "c", "added_at": "2026-01-01"}]
    hist = [{"manga_id": "/m/2", "title": "B", "url": "/m/2", "source": "parser:WC",
             "chapter_title": "Ch 3", "percent": 0.4, "updated_at": "2026-02-01"}]
    cloud_favs, cloud_hist = s.sync_now(favs, hist)

    tables = [t for t, _ in upserts]
    assert tables == [schema.TABLE_MANGA, schema.TABLE_FAVOURITE, schema.TABLE_HISTORY]
    assert dict(upserts)[schema.TABLE_MANGA] == 2       # one manga row per referenced title
    assert cloud_favs == [] and cloud_hist == []         # pull ran (empty cloud)


def test_manga_row_from_view_matches_web_fields() -> None:
    row = schema.manga_row_from_view(
        {"manga_id": "/m/1", "title": "A", "url": "/m/1", "source": "s", "cover": "c"}
    )
    assert set(row) == WEB_MANGA_FIELDS
    assert json.loads(row["source_ref"]) == {"name": "s"}
