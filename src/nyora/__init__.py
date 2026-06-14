"""Nyora Python SDK — the importable ``nyora`` library.

Nyora is a self-contained manga sources SDK. The default client
(:class:`nyora.direct.Nyora`, re-exported here as :class:`Nyora`) embeds the
JavaScript parser bundle inside a QuickJS context via
:class:`nyora.runtime.ParserRuntime`, so it needs **no** Node and **no** JVM
helper: HTTP is handled by ``httpx`` and HTML parsing by ``selectolax``. The
parser bundle and source catalog are kept current through
:class:`nyora.ota.OtaManager` (over-the-air updates).

This module is the public surface of the SDK. It re-exports the primary
client, the helper-backed REST clients, the over-the-air manager, the embedded
:class:`nyora.server.NyoraServer`, the typed :mod:`nyora.models` dataclasses,
and the SDK exception hierarchy.

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

from nyora.client import AsyncNyora
from nyora.client import Nyora as NyoraHelper
from nyora.direct import Nyora
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
from nyora.ota import OtaManager, OtaUpdateResult
from nyora.parser_bridge import NyoraPythonEngine
from nyora.server import NyoraServer

__all__ = [
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
    "Nyora",
    "NyoraError",
    "NyoraHTTPError",
    "NyoraHelper",
    "NyoraPythonEngine",
    "NyoraServer",
    "OtaManager",
    "OtaUpdateResult",
    "SearchPage",
    "Source",
    "SourceFilter",
    "Stats",
]
