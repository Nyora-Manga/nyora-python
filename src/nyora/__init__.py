"""Nyora Python SDK — the importable ``nyora`` library.

Nyora is a manga sources SDK. The default client (:class:`nyora.Nyora`) is a
thin client over the Nyora cloud helper (``https://api.hasanraza.tech`` — the
kotatsu-parsers engine, ~960 sources): it runs no parsers in-process, speaking
the helper's REST contract over ``httpx``. :class:`nyora.sync.NyoraSync` adds
account and library sync against the Nyora cloud
(``https://stream.hasanraza.tech``).

This module is the public surface of the SDK. It re-exports the primary client
(and the async :class:`nyora.AsyncNyora`), the cloud sync client, the typed
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

from nyora.client import CLOUD_BASE_URL, AsyncNyora, Nyora
from nyora.errors import HelperNotFoundError, NyoraError, NyoraHTTPError
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
from nyora.sync import NotSignedInError, NyoraSync

#: Backwards-compatible alias: the cloud client used to be exposed separately.
NyoraHelper = Nyora

__all__ = [
    "CLOUD_BASE_URL",
    "AsyncNyora",
    "BackupImportResult",
    "Category",
    "Download",
    "DownloadSettings",
    "GlobalSearchGroup",
    "HelperNotFoundError",
    "HistoryEntry",
    "Manga",
    "MangaChapter",
    "MangaDetails",
    "MangaPage",
    "MangaPrefs",
    "NotSignedInError",
    "Nyora",
    "NyoraError",
    "NyoraHTTPError",
    "NyoraHelper",
    "NyoraSync",
    "SearchPage",
    "Source",
    "SourceFilter",
    "Stats",
]
