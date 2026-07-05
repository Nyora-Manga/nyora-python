"""Backup, sync, local file, tracker, and system operations.

Defines several helper-backed services: :class:`BackupService` (export/import),
:class:`LocalService` (local file scanning), :class:`TrackerService` (AniList
tracking), and :class:`SystemService` (stats, settings, OTA) which composes the
local and tracker services. ``SystemService`` is attached to a client as
``client.system``; the rest are reachable as ``client.system.local`` etc.

Cloud sync is a separate client: :class:`nyora.sync.NyoraSync`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nyora.models import BackupImportResult, Stats

if TYPE_CHECKING:
    from nyora.client import Nyora


class BackupService:
    """Export and import the helper's library backup.

    Attached to a client as ``client.backup``.
    """

    def __init__(self, client: Nyora) -> None:
        """Bind the service to a helper client.

        Args:
            client: The owning :class:`nyora.client.Nyora` instance.
        """
        self._client = client

    def export(self) -> Any:
        """Export the full backup archive.

        Returns:
            The backup payload as returned by the helper.
        """
        return self._client.get("/backup/export")

    def import_(self, backup_json: str | bytes) -> BackupImportResult:
        """Import a previously exported backup.

        Args:
            backup_json: The backup payload as JSON text or bytes.

        Returns:
            A :class:`~nyora.models.BackupImportResult` summarizing the import.
        """
        data = self._client.post("/backup/import", content=backup_json)
        return BackupImportResult.from_json(data)


class LocalService:
    """Scan and read locally stored manga files.

    Reachable as ``client.system.local``.
    """

    def __init__(self, client: Nyora) -> None:
        """Bind the service to a helper client.

        Args:
            client: The owning :class:`nyora.client.Nyora` instance.
        """
        self._client = client

    def scan(self, folder: str) -> list[dict[str, Any]]:
        """Scan a folder for local manga archives.

        Args:
            folder: Filesystem path to scan.

        Returns:
            Raw entry dicts for the discovered items.
        """
        return self._client.get("/local/scan", params={"folder": folder}).get("entries", [])

    def chapter(self, cbz: str) -> dict[str, Any]:
        """Read metadata for a local chapter archive.

        Args:
            cbz: Path to the ``.cbz`` archive.

        Returns:
            The raw chapter payload.
        """
        return self._client.get("/local/chapter", params={"cbz": cbz})


class TrackerService:
    """Progress-tracking integrations (AniList).

    Reachable as ``client.system.tracker``.
    """

    def __init__(self, client: Nyora) -> None:
        """Bind the service to a helper client.

        Args:
            client: The owning :class:`nyora.client.Nyora` instance.
        """
        self._client = client

    def anilist_search(self, query: str) -> dict[str, Any]:
        """Search AniList for a media entry.

        Args:
            query: Free-text search query.

        Returns:
            The raw AniList search payload.
        """
        return self._client.get("/tracker/anilist/search", params={"q": query})

    def anilist_scrobble(self, *, token: str, media_id: int, progress: int) -> dict[str, Any]:
        """Update AniList reading progress for a media entry.

        Args:
            token: AniList access token.
            media_id: AniList media identifier.
            progress: New progress (chapters read).

        Returns:
            The raw AniList response.
        """
        return self._client.post(
            "/tracker/anilist/scrobble",
            params={"token": token, "mediaId": media_id, "progress": progress},
        )


class SystemService:
    """System-level operations: stats, settings, OTA, and sub-services.

    Attached to a client as ``client.system``. Composes
    :class:`LocalService` (``.local``) and :class:`TrackerService` (``.tracker``).

    Cloud sync now lives in the standalone :class:`nyora.sync.NyoraSync` client
    (OAuth2/JWT against the Nyora sync server), not on ``client.system``.

    Attributes:
        local: Local-file operations.
        tracker: Progress-tracking operations.
    """

    def __init__(self, client: Nyora) -> None:
        """Bind the service to a helper client and build sub-services.

        Args:
            client: The owning :class:`nyora.client.Nyora` instance.
        """
        self._client = client
        self.local = LocalService(client)
        self.tracker = TrackerService(client)

    def stats(self) -> Stats:
        """Return aggregate reading statistics.

        Returns:
            The :class:`~nyora.models.Stats`.
        """
        return Stats.from_json(self._client.get("/stats"))

    def network_settings(self) -> dict[str, Any]:
        """Return the current network settings.

        Returns:
            The settings dict.
        """
        return self._client.get("/settings/network").get("settings", {})

    def save_network_settings(self, **settings: Any) -> dict[str, Any]:
        """Update network settings.

        Args:
            **settings: Setting key/value pairs to apply.

        Returns:
            The updated settings dict.
        """
        return self._client.post("/settings/network", params=settings).get("settings", {})

    def ota_status(self) -> dict[str, Any]:
        """Return the helper's OTA parser-feed status.

        Returns:
            The raw OTA status payload.
        """
        return self._client.get("/ota/status")

    def ota_check(self) -> dict[str, Any]:
        """Trigger an OTA update check on the helper.

        Returns:
            The raw OTA check payload.
        """
        return self._client.post("/ota/check")
