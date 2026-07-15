"""Download operations."""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any, cast

from nyora.models import Download, DownloadSettings
from nyora.services._base import _Service

if TYPE_CHECKING:
    pass


class DownloadsService(_Service):
    """Start, enqueue, monitor, and configure chapter downloads.

    Attached to a client as ``client.downloads``.
    """


    def list(self) -> builtins.list[Download]:
        """List current download tasks.

        Returns:
            The :class:`~nyora.models.Download` tasks.
        """
        data = cast(dict[str, Any], self._client.get("/downloads"))
        return [Download.from_json(item) for item in data.get("entries", [])]

    def start(
        self,
        *,
        source_id: str,
        manga_url: str,
        chapter_url: str,
        manga_title: str = "",
        chapter_title: str = "",
    ) -> Download:
        """Start downloading a single chapter.

        Args:
            source_id: Identifier of the owning source.
            manga_url: URL of the manga.
            chapter_url: URL of the chapter to download.
            manga_title: Optional manga title for display.
            chapter_title: Optional chapter title for display.

        Returns:
            The created :class:`~nyora.models.Download` task.
        """
        data = cast(dict[str, Any], self._client.post(
            "/downloads/start",
            params={
                "sourceId": source_id,
                "mangaUrl": manga_url,
                "chapterUrl": chapter_url,
                "mangaTitle": manga_title,
                "chapterTitle": chapter_title,
            },
        ))
        return Download.from_json(data.get("entry", data))

    def enqueue(
        self,
        *,
        source_id: str,
        manga_url: str,
        chapters: builtins.list[dict[str, Any]],
        manga_title: str = "",
    ) -> builtins.list[Download]:
        """Enqueue multiple chapters for download.

        Args:
            source_id: Identifier of the owning source.
            manga_url: URL of the manga.
            chapters: Chapter descriptor dicts to enqueue.
            manga_title: Optional manga title for display.

        Returns:
            The created :class:`~nyora.models.Download` tasks.
        """
        data = cast(dict[str, Any], self._client.post(
            "/downloads/enqueue",
            params={"sourceId": source_id, "mangaUrl": manga_url, "mangaTitle": manga_title},
            json=chapters,
        ))
        return [Download.from_json(item) for item in data.get("entries", [])]

    def cancel(self, download_id: str) -> dict[str, Any]:
        """Cancel a download task.

        Args:
            download_id: Identifier of the download to cancel.

        Returns:
            The raw helper response.
        """
        return cast(
            dict[str, Any],
            self._client.post("/downloads/cancel", params={"id": download_id}),
        )

    def settings(self) -> DownloadSettings:
        """Return the current download settings.

        Returns:
            The :class:`~nyora.models.DownloadSettings`.
        """
        return DownloadSettings.from_json(self._client.get("/downloads/settings"))

    def save_settings(
        self,
        *,
        max_concurrent: int | None = None,
        format: str | None = None,
    ) -> DownloadSettings:
        """Update download settings.

        Args:
            max_concurrent: New maximum simultaneous downloads, if changing.
            format: New output format, if changing.

        Returns:
            The updated :class:`~nyora.models.DownloadSettings`.
        """
        params: dict[str, Any] = {}
        if max_concurrent is not None:
            params["maxConcurrent"] = max_concurrent
        if format is not None:
            params["format"] = format
        return DownloadSettings.from_json(self._client.post("/downloads/settings", params=params))
