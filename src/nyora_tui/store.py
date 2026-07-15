"""Local, offline-first library and download store for the Nyora TUI.

Guest users (and everyone, before a cloud sync) get a real favourites list,
reading history and a managed downloads folder persisted on disk — no account
required. When the user is signed in the TUI additionally mirrors favourites and
history to the cloud (:class:`nyora_tui.sync.TuiSync`); this module is the local
source of truth either way.

* :class:`LocalLibrary` — favourites + history in ``<config>/library.json``.
* :class:`Downloads` — a manifest + image files under ``<data>/downloads``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir

# Local library/downloads share the sync keying, so local and cloud favourites
# collapse onto the same manga id.
from nyora.schema import manga_id_of

__all__ = ["Downloads", "LocalLibrary", "manga_entry", "manga_id_of"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(text: str, limit: int = 60) -> str:
    """Filesystem-safe slug for a title/source/chapter name."""
    text = re.sub(r"[^\w .()\-]+", "", (text or "").strip())
    text = re.sub(r"\s+", " ", text).strip()
    return (text or "untitled")[:limit]


def manga_entry(source_id: str, manga: Any) -> dict[str, Any]:
    """Extract a compact, serialisable manga record."""
    mid = manga_id_of(manga)
    cover = getattr(manga, "cover_url", "") or getattr(manga, "large_cover_url", "") or ""
    return {
        "manga_id": mid,
        "title": str(getattr(manga, "title", "") or mid),
        "url": str(getattr(manga, "url", "") or mid),
        "source": source_id,
        "cover": str(cover),
    }


class LocalLibrary:
    """Favourites + reading history persisted to a local JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (Path(user_config_dir("nyora", appauthor=False)) / "library.json")
        self._data: dict[str, Any] = {"favourites": {}, "history": {}}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._data["favourites"] = raw.get("favourites") or {}
                self._data["history"] = raw.get("history") or {}
        except (OSError, ValueError):
            pass

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except OSError:
            pass

    # -- favourites ----------------------------------------------------------
    def is_favourite(self, manga_id: str) -> bool:
        return manga_id in self._data["favourites"]

    def toggle_favourite(self, source_id: str, manga: Any) -> bool:
        """Add/remove a favourite. Returns the new favourited state."""
        entry = manga_entry(source_id, manga)
        mid = entry["manga_id"]
        if not mid:
            return False
        if mid in self._data["favourites"]:
            del self._data["favourites"][mid]
            self._save()
            return False
        entry["added_at"] = _now()
        self._data["favourites"][mid] = entry
        self._save()
        return True

    def remove_favourite(self, manga_id: str) -> None:
        if self._data["favourites"].pop(manga_id, None) is not None:
            self._save()

    def favourites(self) -> list[dict[str, Any]]:
        items = list(self._data["favourites"].values())
        items.sort(key=lambda e: str(e.get("added_at", "")), reverse=True)
        return items

    def merge_cloud_favourites(self, rows: list[dict[str, Any]]) -> None:
        """Merge cloud favourite rows (from TuiSync.library) into the local store."""
        changed = False
        for row in rows:
            mid = row.get("manga_id") or row.get("url")
            if mid and mid not in self._data["favourites"]:
                self._data["favourites"][mid] = {
                    "manga_id": mid,
                    "title": row.get("title") or mid,
                    "url": row.get("url") or mid,
                    "source": row.get("source", ""),
                    "cover": row.get("cover", ""),
                    "added_at": _now(),
                }
                changed = True
        if changed:
            self._save()

    # -- history -------------------------------------------------------------
    def record_history(
        self, source_id: str, manga: Any, chapter: Any, *, page: int, total: int, percent: float
    ) -> None:
        entry = manga_entry(source_id, manga)
        mid = entry["manga_id"]
        if not mid:
            return
        entry.update(
            {
                "chapter_id": str(getattr(chapter, "id", "") or ""),
                "chapter_title": str(getattr(chapter, "title", "") or ""),
                "page": int(page),
                "total": int(total),
                "percent": float(percent),
                "updated_at": _now(),
            }
        )
        self._data["history"][mid] = entry
        self._save()

    def history(self) -> list[dict[str, Any]]:
        items = list(self._data["history"].values())
        items.sort(key=lambda e: str(e.get("updated_at", "")), reverse=True)
        return items


class Downloads:
    """CBZ downloads under the OS Downloads folder, tracked by a manifest.

    Files land in ``<Downloads>/nyora-tui/<source>/<manga>/<chapter>.cbz`` (the
    real per-OS Downloads directory on macOS/Windows/Linux, via platformdirs).
    The manifest lives in the config dir so it does not clutter Downloads.
    """

    def __init__(self, root: Path | None = None, manifest: Path | None = None) -> None:
        from platformdirs import user_downloads_dir

        self.root = root or (Path(user_downloads_dir()) / "nyora-tui")
        self._manifest_path = manifest or (
            Path(user_config_dir("nyora", appauthor=False)) / "downloads.json"
        )
        self._entries: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._entries = raw
        except (OSError, ValueError):
            pass

    def _save(self) -> None:
        try:
            self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
            self._manifest_path.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _key(manga_id: str, chapter: Any) -> str:
        return f"{manga_id}|{getattr(chapter, 'id', '') or getattr(chapter, 'url', '')}"

    def cbz_path(self, source_name: str, manga: Any, chapter: Any) -> Path:
        """``<Downloads>/nyora-tui/<source>/<manga>/<chapter>.cbz``."""
        chapter_name = (
            getattr(chapter, "title", "") or getattr(chapter, "id", "") or "chapter"
        )
        return (
            self.root
            / _slug(source_name or "source", 60)
            / _slug(getattr(manga, "title", "") or manga_id_of(manga))
            / f"{_slug(chapter_name)}.cbz"
        )

    def is_downloaded(self, manga_id: str, chapter: Any) -> bool:
        key = self._key(manga_id, chapter)
        entry = self._entries.get(key)
        if not entry:
            return False
        # Treat a manifest entry whose file was deleted as not-downloaded.
        if not Path(entry.get("file", "")).exists():
            del self._entries[key]
            self._save()
            return False
        return True

    def record(
        self, source_id: str, source_name: str, manga: Any, chapter: Any, cbz_file: Path, pages: int
    ) -> None:
        mid = manga_id_of(manga)
        self._entries[self._key(mid, chapter)] = {
            "manga_id": mid,
            "manga_title": str(getattr(manga, "title", "") or mid),
            "source": source_id,
            "source_name": source_name,
            "chapter_id": str(getattr(chapter, "id", "") or ""),
            "chapter_title": str(getattr(chapter, "title", "") or getattr(chapter, "id", "")),
            "file": str(cbz_file),
            "pages": int(pages),
            "downloaded_at": _now(),
        }
        self._save()

    def entries(self) -> list[dict[str, Any]]:
        items = [e for e in self._entries.values() if Path(e.get("file", "")).exists()]
        items.sort(key=lambda e: str(e.get("downloaded_at", "")), reverse=True)
        return items

    @staticmethod
    def cbz_images(cbz_file: str | Path) -> list[bytes]:
        """Return the page images (bytes), page-ordered, from a ``.cbz`` archive."""
        import zipfile

        exts = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
        out: list[bytes] = []
        try:
            with zipfile.ZipFile(cbz_file) as archive:
                names = sorted(n for n in archive.namelist() if n.lower().endswith(exts))
                out = [archive.read(n) for n in names]
        except (OSError, zipfile.BadZipFile):
            pass
        return out
