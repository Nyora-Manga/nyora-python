"""Cloud sync helpers for the Nyora TUI.

Wraps :class:`nyora.sync.NyoraSync` with TUI-friendly operations: sign in/out,
favourite a manga (pushed to the cloud), and pull the synced library. Tokens
persist via ``NyoraSync`` so the TUI stays signed in across runs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from nyora.sync import NyoraSync

#: User-Agent for direct image downloads (cover/page CDNs expect a browser UA).
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _attr(obj: Any, *names: str, default: Any = "") -> Any:
    for name in names:
        val = getattr(obj, name, None)
        if val:
            return val
    return default


class TuiSync:
    """Thin, TUI-oriented facade over :class:`nyora.sync.NyoraSync`."""

    def __init__(self) -> None:
        self._sync = NyoraSync()

    # -- account ---------------------------------------------------------------

    @property
    def is_signed_in(self) -> bool:
        return self._sync.is_signed_in

    @property
    def email(self) -> str | None:
        return self._sync.email

    def sign_in(self, email: str, password: str) -> None:
        self._sync.sign_in(email, password)

    def register(self, email: str, password: str) -> None:
        self._sync.register(email, password)

    def sign_out(self) -> None:
        self._sync.sign_out()

    # -- library ---------------------------------------------------------------

    def favourite(self, source_id: str, manga: Any) -> None:
        """Push ``manga`` to the cloud library and favourite it."""
        now = _iso_now()
        manga_id = str(_attr(manga, "url", "key", "id", default=""))
        self._sync.upsert(
            "nyora_manga",
            [
                {
                    "id": manga_id,
                    "title": str(_attr(manga, "title", default=manga_id)),
                    "url": manga_id,
                    "public_url": str(_attr(manga, "url", default="")),
                    "cover_url": str(_attr(manga, "cover", "cover_url", default="")),
                    "authors": json.dumps(list(getattr(manga, "authors", []) or [])),
                    "description": str(_attr(manga, "description", default="")),
                    "source_ref": json.dumps({"source": source_id}),
                    "updated_at": now,
                }
            ],
        )
        self._sync.upsert(
            "nyora_favourite",
            [{"manga_id": manga_id, "added_at": now, "sort_key": 0, "updated_at": now}],
        )

    def unfavourite(self, manga_id: str) -> None:
        """Tombstone a favourite in the cloud (last-write-wins delete)."""
        now = _iso_now()
        self._sync.upsert(
            "nyora_favourite",
            [{"manga_id": manga_id, "deleted_at": now, "updated_at": now}],
        )

    def library(self) -> list[dict[str, Any]]:
        """Pull the synced favourites joined with their manga metadata."""
        favourites = [f for f in self._sync.select("nyora_favourite") if not f.get("deleted_at")]
        manga = {m.get("id"): m for m in self._sync.select("nyora_manga")}
        items: list[dict[str, Any]] = []
        for fav in favourites:
            mid = fav.get("manga_id", "")
            meta = manga.get(mid, {})
            items.append(
                {
                    "manga_id": mid,
                    "title": meta.get("title") or mid,
                    "url": meta.get("url") or mid,
                    "cover": meta.get("cover_url", ""),
                    "source": _source_of(meta.get("source_ref", "")),
                }
            )
        return items


def _source_of(source_ref: str) -> str:
    try:
        return str(json.loads(source_ref).get("source", ""))
    except (ValueError, AttributeError):
        return ""
