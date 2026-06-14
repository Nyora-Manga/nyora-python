"""Self-contained Nyora client that does not require the JVM helper.

This module provides the default Nyora SDK entry point. :class:`Nyora` drives an
embedded :class:`nyora.runtime.ParserRuntime` (the JavaScript parser bundle
running inside QuickJS) and exposes two service objects:

* :class:`DirectSourcesService` — list and look up bundled sources.
* :class:`DirectMangaService` — browse popular/latest, search, and fetch manga
  details and chapter pages.

Unlike :mod:`nyora.client` (which talks to an external helper over REST), this
path is fully in-process: no Node, no JVM. Over-the-air updates of the parser
bundle and source catalog are managed through the attached
:class:`nyora.ota.OtaManager` (``self.ota``).
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

from typing_extensions import Self

from nyora.client import Nyora as NyoraHelper
from nyora.models import MangaDetails, MangaPage, SearchPage, Source
from nyora.ota import OtaManager, OtaUpdateResult
from nyora.runtime import ParserRuntime


class Nyora:
    """Default no-helper Nyora SDK client.

    Drives an embedded :class:`nyora.runtime.ParserRuntime` (the JavaScript
    parser bundle inside QuickJS) entirely in-process, so it requires neither a
    Node runtime nor the JVM helper. The parser bundle and source catalog are
    kept current through the attached :class:`nyora.ota.OtaManager`
    (``self.ota``).

    Attributes:
        ota: Over-the-air manager for the parser bundle and source catalog.
        sources: :class:`DirectSourcesService` for listing and finding sources.
        manga: :class:`DirectMangaService` for browsing, search, and details.

    Example:
        >>> with Nyora() as client:
        ...     source = client.sources.find("mangadex")
        ...     page = client.manga.popular(source.id)
        ...     entry = page.entries[0]
        ...     details = client.manga.details(source.id, entry.url, title=entry.title)
    """

    def __init__(self, *, timeout: float = 60.0) -> None:
        """Initialize the client and its embedded parser runtime.

        Args:
            timeout: Per-call timeout in seconds for parser runtime operations.
        """
        self.ota = OtaManager()
        self._runtime = ParserRuntime(timeout=timeout, ota=self.ota)
        self.sources = DirectSourcesService(self._runtime)
        self.manga = DirectMangaService(self._runtime)

    def update(self, *, force: bool = False) -> OtaUpdateResult:
        """Fetch the latest OTA parser bundle and reload the runtime.

        Args:
            force: Re-download and reload even if the installed version is
                already current.

        Returns:
            The :class:`~nyora.ota.OtaUpdateResult` describing the applied
            update (``updated`` is ``False`` when already up to date).
        """
        result = self.ota.update(force=force)
        self._runtime.reload()
        return result

    def check_update(self) -> tuple[bool, int | None, int | None]:
        """Check whether a newer OTA parser bundle is available.

        Returns:
            A tuple ``(available, installed_version, latest_version)``. Versions
            are ``None`` when unknown (e.g. nothing installed yet, or the
            manifest could not be reached).
        """
        return self.ota.is_update_available()

    @classmethod
    def helper(cls, base_url: str | None = None, *, timeout: float = 60.0) -> NyoraHelper:
        """Attach to an already-running external Nyora helper over REST.

        Args:
            base_url: Helper base URL. When ``None`` it is discovered from the
                ``NYORA_BASE_URL`` environment variable or the helper port file.
            timeout: Per-request HTTP timeout in seconds.

        Returns:
            A connected :class:`nyora.client.Nyora` helper client.
        """
        return NyoraHelper.attach(base_url=base_url, timeout=timeout)

    @classmethod
    def managed_helper(
        cls,
        jar_path: str,
        *,
        timeout: float = 60.0,
        launch_timeout: float = 20.0,
    ) -> NyoraHelper:
        """Launch and attach to a helper process from a JVM jar.

        Args:
            jar_path: Filesystem path to the helper jar to launch.
            timeout: Per-request HTTP timeout in seconds for the client.
            launch_timeout: Seconds to wait for the helper to become healthy.

        Returns:
            A :class:`nyora.client.Nyora` client bound to the managed process.
        """
        return NyoraHelper.managed(
            jar_path=jar_path,
            timeout=timeout,
            launch_timeout=launch_timeout,
        )

    def close(self) -> None:
        """Close the embedded parser runtime and release its resources."""
        self._runtime.close()

    def __enter__(self) -> Self:
        """Enter the context manager and return this client."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the context manager, closing the runtime."""
        self.close()


class DirectSourcesService:
    """List and look up the sources bundled with the parser runtime."""

    def __init__(self, runtime: ParserRuntime) -> None:
        """Bind the service to a parser runtime.

        Args:
            runtime: The embedded runtime providing the bundled source catalog.
        """
        self._runtime = runtime

    def list(self) -> list[Source]:
        """List every source available in the bundled catalog.

        Returns:
            A list of :class:`~nyora.models.Source` records.
        """
        return [Source.from_json(_source_to_helper_shape(item)) for item in self._runtime.sources()]

    def find(self, query: str) -> Source:
        """Find a bundled source by a case-insensitive id or name substring.

        Args:
            query: Substring matched against each source's id and name.

        Returns:
            The first matching :class:`~nyora.models.Source`.

        Raises:
            LookupError: If no bundled source matches ``query``.
        """
        needle = query.casefold()
        for source in self.list():
            if needle in source.id.casefold() or needle in source.name.casefold():
                return source
        raise LookupError(f"No bundled source matched {query!r}")


class DirectMangaService:
    """Browse, search, and read manga directly through the parser runtime."""

    def __init__(self, runtime: ParserRuntime) -> None:
        """Bind the service to a parser runtime.

        Args:
            runtime: The embedded runtime used to invoke parser methods.
        """
        self._runtime = runtime

    def popular(self, source_id: str, page: int = 1) -> SearchPage:
        """Fetch a page of popular manga from a source.

        Args:
            source_id: Identifier of the source to query.
            page: One-based page number to fetch.

        Returns:
            A :class:`~nyora.models.SearchPage` of entries.
        """
        data = self._runtime.call(source_id, "popular", {"page": page})
        return SearchPage.from_json({"entries": data, "hasNextPage": bool(data)})

    def latest(self, source_id: str, page: int = 1) -> SearchPage:
        """Fetch a page of the latest updated manga from a source.

        Args:
            source_id: Identifier of the source to query.
            page: One-based page number to fetch.

        Returns:
            A :class:`~nyora.models.SearchPage` of entries.
        """
        data = self._runtime.call(source_id, "latest", {"page": page})
        return SearchPage.from_json({"entries": data, "hasNextPage": bool(data)})

    def search(self, source_id: str, query: str, page: int = 1) -> SearchPage:
        """Search a source for manga matching a query.

        Args:
            source_id: Identifier of the source to query.
            query: Free-text search query.
            page: One-based page number to fetch.

        Returns:
            A :class:`~nyora.models.SearchPage` of matching entries.
        """
        data = self._runtime.call(source_id, "search", {"query": query, "page": page})
        return SearchPage.from_json({"entries": data, "hasNextPage": bool(data)})

    def details(self, source_id: str, manga_url: str, *, title: str = "") -> MangaDetails:
        """Fetch full metadata and the chapter list for one manga.

        Args:
            source_id: Identifier of the source that owns the manga.
            manga_url: The manga's source-relative or absolute URL.
            title: Optional known title, passed through to the parser to help
                resolve the entry.

        Returns:
            A :class:`~nyora.models.MangaDetails` with the manga and its
            chapters.
        """
        manga = self._runtime.call(source_id, "details", {"url": manga_url, "title": title})
        return MangaDetails.from_json(
            {
                "manga": manga,
                "chapters": manga.get("chapters", []) if isinstance(manga, dict) else [],
            }
        )

    def pages(
        self,
        source_id: str,
        chapter_url: str,
        *,
        branch: str | None = None,
    ) -> list[MangaPage]:
        """Resolve the readable image pages of a single chapter.

        Args:
            source_id: Identifier of the source that owns the chapter.
            chapter_url: The chapter's source-relative or absolute URL.
            branch: Optional scanlation branch/translation to select.

        Returns:
            An ordered list of :class:`~nyora.models.MangaPage` objects.
        """
        data = self._runtime.call(source_id, "pages", {"url": chapter_url, "branch": branch})
        return [MangaPage.from_json(item) for item in data]


def _source_to_helper_shape(source: dict[str, Any]) -> dict[str, Any]:
    """Normalize a bundled source record into the helper REST source shape.

    Args:
        source: A raw source entry from the parser bundle's catalog.

    Returns:
        A camelCase dict matching the helper ``/sources`` contract, suitable
        for :meth:`nyora.models.Source.from_json`.
    """
    return {
        "id": source.get("id", ""),
        "name": source.get("title") or source.get("name") or source.get("id", ""),
        "lang": source.get("locale", ""),
        "baseUrl": f"https://{source.get('domain', '')}" if source.get("domain") else "",
        "engine": "JavaScript",
        "contentType": "Manga",
        "isInstalled": True,
        "isPinned": False,
        "isNsfw": bool(source.get("isNsfw", False)),
        "canUninstall": False,
    }
