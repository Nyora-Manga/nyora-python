"""Nyora helper HTTP clients.

This module provides the SDK's REST clients. They run no parsers themselves;
they speak the camelCase helper REST contract over HTTP via ``httpx`` against a
Nyora parser engine.

It exposes:

* :class:`Nyora` — synchronous client with the full set of service objects
  (sources, manga, library, downloads, backup, system).
* :class:`AsyncNyora` — asynchronous client with the read/browse surface
  (``sources``/``manga``) plus raw ``get``/``post``/``delete``.

Both clients automatically **retry** transient failures (connect/read timeouts,
connection errors, ``429``/``5xx``) with exponential backoff + jitter, send a
descriptive **User-Agent**, and emit structured logs on the ``"nyora"`` logger.

The SDK is fully self-contained: when no server is configured, :class:`Nyora`
launches its own **bundled parser engine** locally (shipped with
``nyora-extension-server``) and owns its lifecycle — no cloud required. A base
URL can be supplied explicitly, via the ``NYORA_BASE_URL`` environment variable,
via persisted config (``nyora config set-url``), or discovered from a running
helper's port file. A self-hosted helper jar can also be launched and managed
via :meth:`Nyora.managed`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from types import TracebackType
from typing import Any

import httpx
from typing_extensions import Self

from nyora._meta import USER_AGENT
from nyora.config import BASE_URL_ENV, read_base_url_from_config, read_base_url_from_port_file
from nyora.errors import (
    HelperNotFoundError,
    NyoraConnectionError,
    NyoraHTTPError,
    NyoraTimeoutError,
)
from nyora.helper import HelperProcess
from nyora.models import MangaDetails, MangaPage, SearchPage, Source
from nyora.pagers import AsyncMangaPager
from nyora.retry import TRANSIENT_EXCEPTIONS, RetryConfig, retry_after_seconds
from nyora.services.backup import BackupService
from nyora.services.downloads import DownloadsService
from nyora.services.library import LibraryService
from nyora.services.manga import MangaService
from nyora.services.sources import SourcesService
from nyora.services.system import SystemService

logger = logging.getLogger("nyora")

_DEFAULT_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}


def _resolve_base_url(base_url: str | None) -> str | None:
    """Resolve a configured helper base URL, or ``None`` if none is set.

    Order: explicit argument → ``NYORA_BASE_URL`` env → persisted config
    (``nyora config set-url``) → a running local helper's port file. There is **no
    cloud fallback** — the SDK is fully self-contained: when nothing is configured,
    :class:`Nyora` launches its own bundled parser engine locally.

    Args:
        base_url: Explicit base URL, or ``None`` to auto-discover.

    Returns:
        The resolved base URL (trailing slash removed), or ``None``.
    """
    resolved = (
        base_url
        or os.getenv(BASE_URL_ENV)
        or read_base_url_from_config()
        or read_base_url_from_port_file()
    )
    return resolved.rstrip("/") if resolved else None


def _decode(response: httpx.Response) -> Any:
    """Decode a successful response: JSON, empty dict for no body, else text."""
    if not response.content:
        return {}
    if "application/json" in response.headers.get("content-type", ""):
        return response.json()
    return response.text


def _wrap_transport(exc: Exception) -> NyoraConnectionError | NyoraTimeoutError:
    """Wrap an exhausted httpx transport error in the SDK's typed exception."""
    if isinstance(exc, httpx.TimeoutException):
        return NyoraTimeoutError(f"Request to the Nyora engine timed out: {exc}")
    return NyoraConnectionError(f"Could not reach the Nyora engine: {exc}")


class Nyora:
    """Synchronous Nyora SDK client backed by a helper REST API.

    Wraps an ``httpx.Client`` against a discovered or managed helper and exposes
    the full set of service objects. Transient failures are retried with
    exponential backoff. Use as a context manager to release the HTTP connection
    (and stop a managed helper) on exit.

    Attributes:
        base_url: The resolved helper base URL.
        sources: :class:`~nyora.services.sources.SourcesService`.
        manga: :class:`~nyora.services.manga.MangaService`.
        library: :class:`~nyora.services.library.LibraryService`.
        downloads: :class:`~nyora.services.downloads.DownloadsService`.
        backup: :class:`~nyora.services.backup.BackupService`.
        system: :class:`~nyora.services.system.SystemService`.

    Example:
        >>> with Nyora.attach() as client:
        ...     for source in client.sources.list():
        ...         print(source.id, source.name)
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 60.0,
        retries: RetryConfig | int | None = None,
        helper: HelperProcess | None = None,
    ) -> None:
        """Connect to a helper and construct the service objects.

        Args:
            base_url: Explicit helper base URL, or ``None`` to auto-discover.
            timeout: Per-request HTTP timeout in seconds.
            retries: Retry policy — an int (max attempts) or a
                :class:`~nyora.retry.RetryConfig`. ``0`` disables retrying.
            helper: An owned :class:`~nyora.helper.HelperProcess` to stop on
                :meth:`close`, when the client launched the helper itself.

        Raises:
            HelperNotFoundError: If no server is configured and no bundled engine
                can be launched (e.g. no Java runtime / no engine jar).
        """
        explicit = base_url or (helper.base_url if helper else None)
        resolved = _resolve_base_url(explicit)
        if resolved is None:
            # Fully self-contained: no server configured or running → launch the
            # bundled parser engine locally and own its lifecycle. No cloud.
            if helper is None:
                helper = HelperProcess()
            resolved = helper.start()
        self.base_url: str = resolved
        self._helper = helper
        self._retry = RetryConfig.coerce(retries)
        self._http = httpx.Client(
            base_url=self.base_url, timeout=timeout, headers=_DEFAULT_HEADERS
        )

        self.sources = SourcesService(self)
        self.manga = MangaService(self)
        self.library = LibraryService(self)
        self.downloads = DownloadsService(self)
        self.backup = BackupService(self)
        self.system = SystemService(self)

    @classmethod
    def attach(
        cls,
        base_url: str | None = None,
        *,
        timeout: float = 60.0,
        retries: RetryConfig | int | None = None,
    ) -> Self:
        """Attach to an already-running helper.

        Args:
            base_url: Explicit helper base URL, or ``None`` to auto-discover.
            timeout: Per-request HTTP timeout in seconds.
            retries: Retry policy (int or :class:`~nyora.retry.RetryConfig`).

        Returns:
            A connected client.
        """
        return cls(base_url=base_url, timeout=timeout, retries=retries)

    @classmethod
    def managed(
        cls,
        jar_path: str | os.PathLike[str] | None = None,
        *,
        java: str = "java",
        timeout: float = 60.0,
        retries: RetryConfig | int | None = None,
        launch_timeout: float = 20.0,
    ) -> Self:
        """Launch a helper jar and return a client bound to it.

        The launched process is owned by the returned client and is stopped on
        :meth:`close`.

        Args:
            jar_path: Path to the helper jar. When ``None`` it is read from the
                ``NYORA_HELPER_JAR`` environment variable.
            java: The ``java`` executable to invoke.
            timeout: Per-request HTTP timeout in seconds for the client.
            retries: Retry policy (int or :class:`~nyora.retry.RetryConfig`).
            launch_timeout: Seconds to wait for the helper to report healthy.

        Returns:
            A client connected to the managed helper.

        Raises:
            HelperNotFoundError: If the jar path is missing or does not exist.
            HelperLaunchError: If the helper fails to start within the timeout.
        """
        helper = HelperProcess(jar_path, java=java, timeout=launch_timeout)
        base_url = helper.start()
        return cls(base_url=base_url, timeout=timeout, retries=retries, helper=helper)

    def close(self) -> None:
        """Close the HTTP connection and stop any managed helper process."""
        self._http.close()
        if self._helper is not None:
            self._helper.stop()
            self._helper = None

    def __enter__(self) -> Self:
        """Enter the context manager and return this client."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the context manager, closing the client."""
        self.close()

    def __repr__(self) -> str:
        return f"Nyora(base_url={self.base_url!r})"

    def health(self) -> dict[str, Any]:
        """Return the helper's ``/health`` payload.

        Returns:
            The health dict, or an empty dict if the response was not an object.
        """
        data = self.get("/health")
        return data if isinstance(data, dict) else {}

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """Issue a ``GET`` request against the helper.

        Args:
            path: Request path relative to the base URL.
            params: Optional query parameters.

        Returns:
            Parsed JSON, or the response text for non-JSON bodies.

        Raises:
            NyoraHTTPError: If the helper returns a 4xx/5xx response.
            NyoraTransportError: If the engine is unreachable after retries.
        """
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        content: str | bytes | None = None,
    ) -> Any:
        """Issue a ``POST`` request against the helper.

        Args:
            path: Request path relative to the base URL.
            params: Optional query parameters.
            json: Optional JSON-serializable request body.
            content: Optional raw request body (mutually exclusive with ``json``).

        Returns:
            Parsed JSON, or the response text for non-JSON bodies.

        Raises:
            NyoraHTTPError: If the helper returns a 4xx/5xx response.
            NyoraTransportError: If the engine is unreachable after retries.
        """
        return self._request("POST", path, params=params, json=json, content=content)

    def delete(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """Issue a ``DELETE`` request against the helper.

        Args:
            path: Request path relative to the base URL.
            params: Optional query parameters.

        Returns:
            Parsed JSON, or the response text for non-JSON bodies.

        Raises:
            NyoraHTTPError: If the helper returns a 4xx/5xx response.
            NyoraTransportError: If the engine is unreachable after retries.
        """
        return self._request("DELETE", path, params=params)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        content: str | bytes | None = None,
    ) -> Any:
        """Send a request with retries and decode the helper response.

        Retries transient transport errors and retryable status codes with
        exponential backoff (honouring ``Retry-After``) up to the configured
        limit, then raises.

        Raises:
            NyoraHTTPError: On a non-retryable (or final) 4xx/5xx response.
            NyoraTransportError: If the engine stays unreachable after retries.
        """
        retry = self._retry
        attempt = 0
        while True:
            try:
                response = self._http.request(
                    method, path, params=params, json=json, content=content
                )
            except TRANSIENT_EXCEPTIONS as exc:
                if attempt < retry.max_retries:
                    delay = retry.backoff(attempt)
                    logger.debug(
                        "%s %s transport error %s; retry %d/%d in %.2fs",
                        method, path, type(exc).__name__, attempt + 1, retry.max_retries, delay,
                    )
                    time.sleep(delay)
                    attempt += 1
                    continue
                raise _wrap_transport(exc) from exc
            if retry.should_retry_status(response.status_code) and attempt < retry.max_retries:
                delay = retry.backoff(attempt, retry_after=retry_after_seconds(response))
                logger.debug(
                    "%s %s -> HTTP %d; retry %d/%d in %.2fs",
                    method, path, response.status_code, attempt + 1, retry.max_retries, delay,
                )
                time.sleep(delay)
                attempt += 1
                continue
            if response.status_code >= 400:
                raise NyoraHTTPError(
                    response.status_code, _error_message(response), body=response.text
                )
            return _decode(response)


class AsyncNyora:
    """Asynchronous Nyora client for the read/browse surface.

    Wraps an ``httpx.AsyncClient`` and exposes async ``sources`` and ``manga``
    services (browse, search, details, pages) plus raw ``get``/``post``/``delete``
    — with the same automatic retries and User-Agent as :class:`Nyora`. Use as an
    async context manager to release the connection on exit.

    Unlike :class:`Nyora`, this client does not launch a bundled engine; point it
    at a running/configured server.

    Attributes:
        base_url: The resolved helper base URL.
        sources: async source listing / lookup.
        manga: async browse, search, details, pages (with ``iter_*`` pagers).

    Example:
        >>> async with AsyncNyora.attach() as client:
        ...     src = await client.sources.find("mangadex")
        ...     async for manga in client.manga.iter_popular(src.id, limit=30):
        ...         print(manga.title)
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 60.0,
        retries: RetryConfig | int | None = None,
    ) -> None:
        """Connect to a helper.

        Args:
            base_url: Explicit helper base URL, or ``None`` to auto-discover.
            timeout: Per-request HTTP timeout in seconds.
            retries: Retry policy (int or :class:`~nyora.retry.RetryConfig`).

        Raises:
            HelperNotFoundError: If no helper can be discovered.
        """
        resolved = _resolve_base_url(base_url)
        if resolved is None:
            raise HelperNotFoundError(
                "AsyncNyora needs a running or configured server — it does not launch a "
                "bundled engine. Set base_url, NYORA_BASE_URL, or `nyora config set-url`, "
                "or use the sync Nyora(), which can launch a bundled engine itself."
            )
        self.base_url: str = resolved
        self._retry = RetryConfig.coerce(retries)
        self._http = httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout, headers=_DEFAULT_HEADERS
        )
        self.sources = _AsyncSourcesService(self)
        self.manga = _AsyncMangaService(self)

    @classmethod
    def attach(
        cls,
        base_url: str | None = None,
        *,
        timeout: float = 60.0,
        retries: RetryConfig | int | None = None,
    ) -> AsyncNyora:
        """Attach to an already-running helper.

        Args:
            base_url: Explicit helper base URL, or ``None`` to auto-discover.
            timeout: Per-request HTTP timeout in seconds.
            retries: Retry policy (int or :class:`~nyora.retry.RetryConfig`).

        Returns:
            A connected async client.
        """
        return cls(base_url=base_url, timeout=timeout, retries=retries)

    async def close(self) -> None:
        """Close the underlying async HTTP connection."""
        await self._http.aclose()

    async def __aenter__(self) -> AsyncNyora:
        """Enter the async context manager and return this client."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the async context manager, closing the client."""
        await self.close()

    def __repr__(self) -> str:
        return f"AsyncNyora(base_url={self.base_url!r})"

    async def health(self) -> dict[str, Any]:
        """Return the helper's ``/health`` payload."""
        data = await self.get("/health")
        return data if isinstance(data, dict) else {}

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """Issue a ``GET`` request against the helper (with retries)."""
        return await self._request("GET", path, params=params)

    async def post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        content: str | bytes | None = None,
    ) -> Any:
        """Issue a ``POST`` request against the helper (with retries)."""
        return await self._request("POST", path, params=params, json=json, content=content)

    async def delete(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """Issue a ``DELETE`` request against the helper (with retries)."""
        return await self._request("DELETE", path, params=params)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        content: str | bytes | None = None,
    ) -> Any:
        """Async request with retries and response decoding (mirrors ``Nyora``)."""
        retry = self._retry
        attempt = 0
        while True:
            try:
                response = await self._http.request(
                    method, path, params=params, json=json, content=content
                )
            except TRANSIENT_EXCEPTIONS as exc:
                if attempt < retry.max_retries:
                    delay = retry.backoff(attempt)
                    logger.debug(
                        "%s %s transport error %s; retry %d/%d in %.2fs",
                        method, path, type(exc).__name__, attempt + 1, retry.max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue
                raise _wrap_transport(exc) from exc
            if retry.should_retry_status(response.status_code) and attempt < retry.max_retries:
                delay = retry.backoff(attempt, retry_after=retry_after_seconds(response))
                logger.debug(
                    "%s %s -> HTTP %d; retry %d/%d in %.2fs",
                    method, path, response.status_code, attempt + 1, retry.max_retries, delay,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue
            if response.status_code >= 400:
                raise NyoraHTTPError(
                    response.status_code, _error_message(response), body=response.text
                )
            return _decode(response)


class _AsyncSourcesService:
    """Async source listing / lookup (``AsyncNyora.sources``)."""

    def __init__(self, client: AsyncNyora) -> None:
        self._client = client

    async def list(self) -> list[Source]:
        """List installed sources."""
        data = await self._client.get("/sources")
        entries: list = []
        if isinstance(data, dict):
            got = data.get("sources", data.get("entries", []))
            entries = got if isinstance(got, list) else []
        return [Source.from_json(item) for item in entries]

    async def find(self, query: str) -> Source:
        """Find an installed source by case-insensitive id or name substring."""
        needle = query.casefold()
        for source in await self.list():
            if needle in source.id.casefold() or needle in source.name.casefold():
                return source
        raise LookupError(f"No installed source matched {query!r}")


class _AsyncMangaService:
    """Async browse / search / read surface (``AsyncNyora.manga``)."""

    def __init__(self, client: AsyncNyora) -> None:
        self._client = client

    async def popular(self, source_id: str, page: int = 1) -> SearchPage:
        """Fetch a page of popular manga from a source."""
        return SearchPage.from_json(
            await self._client.get("/sources/popular", params={"id": source_id, "page": page})
        )

    async def latest(self, source_id: str, page: int = 1) -> SearchPage:
        """Fetch a page of the latest-updated manga from a source."""
        return SearchPage.from_json(
            await self._client.get("/sources/latest", params={"id": source_id, "page": page})
        )

    async def search(
        self,
        source_id: str,
        query: str,
        page: int = 1,
        *,
        filters: list[dict[str, Any]] | None = None,
    ) -> SearchPage:
        """Search a source for manga matching a query."""
        params: dict[str, Any] = {"id": source_id, "q": query, "page": page}
        if filters:
            params["filters"] = filters
        return SearchPage.from_json(await self._client.get("/sources/search", params=params))

    async def details(
        self, source_id: str, manga_url: str, *, manga_id: str | None = None
    ) -> MangaDetails:
        """Fetch full metadata and chapters for one manga."""
        params = {"id": source_id, "url": manga_url}
        if manga_id:
            params["mangaId"] = manga_id
        return MangaDetails.from_json(await self._client.get("/manga/details", params=params))

    async def pages(
        self, source_id: str, chapter_url: str, *, branch: str | None = None
    ) -> list[MangaPage]:
        """Resolve the readable image pages of a chapter."""
        params = {"id": source_id, "url": chapter_url}
        if branch:
            params["branch"] = branch
        data = await self._client.get("/manga/pages", params=params)
        if isinstance(data, list):
            entries: list = data
        elif isinstance(data, dict) and isinstance(data.get("pages"), list):
            entries = data["pages"]
        else:
            entries = []
        return [MangaPage.from_json(item) for item in entries]

    def iter_popular(
        self, source_id: str, *, start_page: int = 1, max_pages: int | None = None,
        limit: int | None = None,
    ) -> AsyncMangaPager:
        """Auto-paging async iterator over popular manga."""
        return AsyncMangaPager(
            lambda p: self.popular(source_id, p),
            start_page=start_page, max_pages=max_pages, limit=limit,
        )

    def iter_latest(
        self, source_id: str, *, start_page: int = 1, max_pages: int | None = None,
        limit: int | None = None,
    ) -> AsyncMangaPager:
        """Auto-paging async iterator over the latest manga."""
        return AsyncMangaPager(
            lambda p: self.latest(source_id, p),
            start_page=start_page, max_pages=max_pages, limit=limit,
        )

    def iter_search(
        self, source_id: str, query: str, *, start_page: int = 1, max_pages: int | None = None,
        limit: int | None = None, filters: list[dict[str, Any]] | None = None,
    ) -> AsyncMangaPager:
        """Auto-paging async iterator over search results."""
        return AsyncMangaPager(
            lambda p: self.search(source_id, query, p, filters=filters),
            start_page=start_page, max_pages=max_pages, limit=limit,
        )


def _error_message(response: httpx.Response) -> str:
    """Extract a human-readable error message from a helper response.

    Args:
        response: The failed HTTP response.

    Returns:
        The ``error``/``message`` field of a JSON body, the trimmed text body,
        or the HTTP reason phrase as a fallback.
    """
    try:
        data = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    if isinstance(data, dict):
        return str(data.get("error") or data.get("message") or data)
    return str(data)


__all__ = ["Nyora", "AsyncNyora"]
