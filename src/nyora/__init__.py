"""Nyora Python SDK — the importable ``nyora`` library.

Nyora is a manga sources SDK. The default client (:class:`nyora.Nyora`) is a
thin client over a Nyora parser engine (the kotatsu-parsers stack, ~960
sources): it runs no parsers in-process, speaking the engine's REST contract
over ``httpx``. It is fully self-contained — with no server configured it
launches its own **bundled engine** locally (via ``nyora-extension-server``),
so no cloud is required. Point it at any server with ``nyora config set-url``.
:class:`nyora.sync.NyoraSync` optionally adds account and library sync against a
(self-hosted) Nyora sync server.

This module is the public surface of the SDK. It re-exports the primary client
(and the async :class:`nyora.AsyncNyora`), the sync client, the typed
:mod:`nyora.models` dataclasses, and the SDK exception hierarchy.

The importable ``nyora`` library and the separately shipped ``nyora-cli`` tool
(which launches the terminal UI) are distinct: this package documents the SDK.

Example:
    >>> import nyora
    >>> with nyora.Nyora() as client:
    ...     source = client.sources.find("mangadex")
    ...     page = client.manga.popular(source.id)
    ...     first = page.entries[0]
    ...     details = client.manga.details(source.id, first.url, title=first.title)
"""

from nyora import schema
from nyora._meta import __version__
from nyora.client import AsyncNyora, Nyora
from nyora.errors import (
    HelperLaunchError,
    HelperNotFoundError,
    NyoraConnectionError,
    NyoraError,
    NyoraHTTPError,
    NyoraTimeoutError,
    NyoraTransportError,
)
from nyora.models import (
    BackupImportResult,
    Category,
    Download,
    DownloadSettings,
    GlobalSearchGroup,
    HistoryEntry,
    Manga,
    MangaChapter,
    MangaDetails,
    MangaPage,
    MangaPrefs,
    SearchPage,
    Source,
    SourceFilter,
    Stats,
)
from nyora.ordering import (
    adjacent_chapter,
    chapter_reading_delta,
    next_chapter,
    previous_chapter,
    reading_order,
)
from nyora.pagers import AsyncMangaPager, MangaPager
from nyora.retry import RetryConfig
from nyora.sync import NotSignedInError, NyoraSync

#: Backwards-compatible alias: the helper client used to be exposed separately.
NyoraHelper = Nyora

__all__ = [
    "AsyncMangaPager",
    "AsyncNyora",
    "BackupImportResult",
    "Category",
    "Download",
    "DownloadSettings",
    "GlobalSearchGroup",
    "HelperLaunchError",
    "HelperNotFoundError",
    "HistoryEntry",
    "Manga",
    "MangaChapter",
    "MangaDetails",
    "MangaPage",
    "MangaPager",
    "MangaPrefs",
    "NotSignedInError",
    "Nyora",
    "NyoraConnectionError",
    "NyoraError",
    "NyoraHTTPError",
    "NyoraHelper",
    "NyoraSync",
    "NyoraTimeoutError",
    "NyoraTransportError",
    "RetryConfig",
    "SearchPage",
    "Source",
    "SourceFilter",
    "Stats",
    "__version__",
    "schema",
    "adjacent_chapter",
    "chapter_reading_delta",
    "next_chapter",
    "previous_chapter",
    "reading_order",
]
