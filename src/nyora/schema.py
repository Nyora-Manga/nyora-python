"""Unified Nyora sync schema — table names and row builders.

The single source of truth for the cloud sync data contract. Row shapes match
the nyora-web sync client field-for-field, so favourites, history, and manga
metadata written by the Python TUI and the web app interoperate on the shared
sync server.

Conventions:

* Lists (``authors``, ``alt_titles``, ``tags``) are JSON-encoded strings.
* The source reference is JSON ``{"name": <source_id>}`` — what the web decoder
  reads back to resolve a source.
* Timestamps are ISO-8601 UTC.
* Deletes are soft: a ``deleted_at`` tombstone (last-write-wins).
* ``user_id`` is injected server-side from the auth token; clients never send it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

#: Cloud table names (shared with nyora-web).
TABLE_MANGA = "nyora_manga"
TABLE_FAVOURITE = "nyora_favourite"
TABLE_HISTORY = "nyora_history"


def now_iso() -> str:
    """Current time as an ISO-8601 UTC string."""
    return datetime.now(timezone.utc).isoformat()


def _first(obj: Any, *names: str, default: Any = "") -> Any:
    for name in names:
        value = getattr(obj, name, None)
        if value:
            return value
    return default


def manga_id_of(manga: Any) -> str:
    """The stable library/sync key for a manga: its URL (fall back to id)."""
    return str(_first(manga, "url", "id", default=""))


def source_name_of(source_ref: str) -> str:
    """Resolve the source name from a JSON ``source_ref`` (``name``, legacy ``source``)."""
    try:
        obj = json.loads(source_ref)
    except (ValueError, TypeError):
        return ""
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("name") or obj.get("source") or "")


def manga_row(source_id: str, manga: Any, *, now: str | None = None) -> dict[str, Any]:
    """Build a ``nyora_manga`` row from a manga model (web field order)."""
    now = now or now_iso()
    manga_id = manga_id_of(manga)
    return {
        # A manga's identity IS its URL: both `id` and `url` carry the same key so
        # favourite/history rows can join back on it. `public_url` is the human-
        # shareable link (may differ from the source-relative `url`).
        "id": manga_id,
        "title": str(_first(manga, "title", default=manga_id)),
        "alt_titles": json.dumps([str(t) for t in (getattr(manga, "alt_titles", []) or [])]),
        "url": manga_id,
        "public_url": str(_first(manga, "public_url", "url", default="")),
        "rating": float(getattr(manga, "rating", -1.0) or -1.0),  # -1 == unrated
        "is_nsfw": bool(getattr(manga, "is_nsfw", False)),
        # Coerce empty strings to NULL so nullable columns stay nullable, not "".
        "content_rating": getattr(manga, "content_rating", None) or None,
        "cover_url": str(_first(manga, "cover_url", "cover", default="")),
        "large_cover_url": str(_first(manga, "large_cover_url", default="")),
        "state": _first(manga, "state", default=None) or None,
        "authors": json.dumps([str(a) for a in (getattr(manga, "authors", []) or [])]),
        "source_ref": json.dumps({"name": source_id}),
        "description": str(_first(manga, "description", default="")),
        "tags": json.dumps(list(getattr(manga, "tags", []) or [])),
        "updated_at": now,
    }


def favourite_row(
    manga_id: str, *, now: str | None = None, deleted: bool = False
) -> dict[str, Any]:
    """Build a ``nyora_favourite`` row (a tombstone when ``deleted``)."""
    now = now or now_iso()
    return {
        "manga_id": manga_id,
        "sort_key": 0,
        "updated_at": now,
        "deleted_at": now if deleted else None,
    }


def history_row(
    source_id: str,
    manga_id: str,
    chapter: Any,
    *,
    page: int = 0,
    total: int = 0,
    percent: float = 0.0,
    now: str | None = None,
) -> dict[str, Any]:
    """Build a ``nyora_history`` row for a chapter's reading progress."""
    now = now or now_iso()
    return {
        "manga_id": manga_id,
        "source_id": source_id,
        "chapter_id": str(getattr(chapter, "id", "") or ""),
        "chapter_title": str(getattr(chapter, "title", "") or ""),
        "page": int(page),
        "scroll": 0,
        "percent": float(percent),
        "chapters_count": int(total),
        "updated_at": now,
        "deleted_at": None,
    }


def manga_row_from_view(view: dict[str, Any], *, now: str | None = None) -> dict[str, Any]:
    """Build a ``nyora_manga`` row from a local library view dict (minimal fields).

    Used to bulk-push a device's local library to the cloud (web ``pushAll``
    parity). The local store only keeps title/url/cover/source, so other fields
    default; the row still lets favourite/history joins resolve a title + cover.
    """
    now = now or now_iso()
    mid = str(view.get("manga_id") or view.get("url") or "")
    return {
        "id": mid,
        "title": str(view.get("title") or mid),
        "alt_titles": json.dumps([]),
        "url": mid,
        "public_url": str(view.get("url") or ""),
        "rating": -1.0,
        "is_nsfw": False,
        "content_rating": None,
        "cover_url": str(view.get("cover") or ""),
        "large_cover_url": "",
        "state": None,
        "authors": json.dumps([]),
        "source_ref": json.dumps({"name": str(view.get("source") or "")}),
        "description": "",
        "tags": json.dumps([]),
        "updated_at": str(view.get("added_at") or view.get("updated_at") or now),
    }


def history_row_from_view(view: dict[str, Any], *, now: str | None = None) -> dict[str, Any]:
    """Build a ``nyora_history`` row from a local history view dict."""
    now = now or now_iso()
    return {
        "manga_id": str(view.get("manga_id") or view.get("url") or ""),
        "source_id": str(view.get("source") or ""),
        "chapter_id": str(view.get("chapter_id") or ""),
        "chapter_title": str(view.get("chapter_title") or ""),
        "page": int(view.get("page", 0) or 0),
        "scroll": 0,
        "percent": float(view.get("percent", 0.0) or 0.0),
        "chapters_count": int(view.get("total", 0) or 0),
        "updated_at": str(view.get("updated_at") or now),
        "deleted_at": None,
    }


def manga_view(manga_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    """A friendly read-shape for a synced manga (joins a metadata row).

    Used by the high-level ``NyoraSync`` library/history readers to return
    something more useful than the raw ``nyora_manga`` row.
    """
    return {
        "manga_id": manga_id,
        "title": meta.get("title") or manga_id,
        "url": meta.get("url") or manga_id,
        "cover": meta.get("cover_url", ""),
        "source": source_name_of(meta.get("source_ref", "")),
    }
