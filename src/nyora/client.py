"""Nyora helper HTTP clients.

This module provides the helper-backed REST clients used when an external Nyora
helper process (the JVM helper, or an embedded :class:`nyora.server.NyoraServer`)
is available. Unlike :class:`nyora.direct.Nyora`, these clients do not embed a
parser runtime; they speak the camelCase helper REST contract over HTTP via
``httpx``.

It exposes:

* :class:`Nyora` — synchronous client with the full set of service objects
  (sources, manga, library, downloads, backup, system).
* :class:`AsyncNyora` — lightweight async client for read-style requests.

The helper base URL is discovered from an explicit argument, the
``NYORA_BASE_URL`` environment variable, or the helper port file written by a
running Nyora app. A helper jar can also be launched and managed via
:meth:`Nyora.managed`.
"""

from __future__ import annotations

import os
from types import TracebackType
from typing import Any

import httpx
from typing_extensions import Self

from nyora.config import BASE_URL_ENV, read_base_url_from_port_file
from nyora.errors import HelperNotFoundError, NyoraHTTPError
from nyora.helper import HelperProcess
from nyora.services.backup import BackupService
from nyora.services.downloads import DownloadsService
from nyora.services.library import LibraryService
from nyora.services.manga import MangaService
from nyora.services.sources import SourcesService
from nyora.services.system import SystemService

Json = dict[str, Any] | list[Any]


def _resolve_base_url(base_url: str | None) -> str:
    """Resolve the helper base URL from an argument, env var, or port file.

    Args:
        base_url: Explicit base URL, or ``None`` to auto-discover.

    Returns:
        The resolved base URL with any trailing slash removed.

    Raises:
        HelperNotFoundError: If no helper can be discovered.
    """
    resolved = base_url or os.getenv(BASE_URL_ENV) or read_base_url_from_port_file()
    if not resolved:
        raise HelperNotFoundError(
            "No Nyora helper found. Start Nyora, set NYORA_BASE_URL, or use Nyora.managed()."
        )
    return resolved.rstrip("/")


class Nyora:
    """Synchronous Nyora SDK client backed by a helper REST API.

    Wraps an ``httpx.Client`` against a discovered or managed helper and exposes
    the full set of service objects. Use as a context manager to release the
    HTTP connection (and stop a managed helper) on exit.

    Attributes:
        base_url: The resolved helper base URL.
        sources: :class:`~nyora.services.sources.SourcesService`.
        manga: :class:`~nyora.services.manga.MangaService`.
        library: :class:`~nyora.services.library.LibraryService`.
        downloads: :class:`~nyora.services.downloads.DownloadsService`.
        backup: :class:`~nyora.services.backup.BackupService`.
        system: :class:`~nyora.services.backup.SystemService`.

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
        helper: HelperProcess | None = None,
    ) -> None:
        """Connect to a helper and construct the service objects.

        Args:
            base_url: Explicit helper base URL, or ``None`` to auto-discover.
            timeout: Per-request HTTP timeout in seconds.
            helper: An owned :class:`~nyora.helper.HelperProcess` to stop on
                :meth:`close`, when the client launched the helper itself.

        Raises:
            HelperNotFoundError: If no helper can be discovered.
        """
        self.base_url = _resolve_base_url(base_url or helper.base_url if helper else base_url)
        self._helper = helper
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

        self.sources = SourcesService(self)
        self.manga = MangaService(self)
        self.library = LibraryService(self)
        self.downloads = DownloadsService(self)
        self.backup = BackupService(self)
        self.system = SystemService(self)

    @classmethod
    def attach(cls, base_url: str | None = None, *, timeout: float = 60.0) -> Self:
        """Attach to an already-running helper.

        Args:
            base_url: Explicit helper base URL, or ``None`` to auto-discover.
            timeout: Per-request HTTP timeout in seconds.

        Returns:
            A connected client.
        """
        return cls(base_url=base_url, timeout=timeout)

    @classmethod
    def managed(
        cls,
        jar_path: str | os.PathLike[str] | None = None,
        *,
        java: str = "java",
        timeout: float = 60.0,
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
            launch_timeout: Seconds to wait for the helper to report healthy.

        Returns:
            A client connected to the managed helper.

        Raises:
            HelperNotFoundError: If the jar path is missing or does not exist.
            HelperLaunchError: If the helper fails to start within the timeout.
        """
        helper = HelperProcess(jar_path, java=java, timeout=launch_timeout)
        base_url = helper.start()
        return cls(base_url=base_url, timeout=timeout, helper=helper)

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
        """Send an HTTP request and decode the helper response.

        Args:
            method: HTTP method name.
            path: Request path relative to the base URL.
            params: Optional query parameters.
            json: Optional JSON-serializable request body.
            content: Optional raw request body.

        Returns:
            Parsed JSON for JSON responses, an empty dict for empty bodies, or
            the raw response text otherwise.

        Raises:
            NyoraHTTPError: If the response status is 400 or greater.
        """
        response = self._http.request(method, path, params=params, json=json, content=content)
        if response.status_code >= 400:
            raise NyoraHTTPError(response.status_code, _error_message(response), body=response.text)
        if not response.content:
            return {}
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text


class AsyncNyora:
    """Asynchronous Nyora helper client for read-style requests.

    A lightweight ``httpx.AsyncClient`` wrapper exposing :meth:`get` against a
    discovered or explicit helper base URL. Use as an async context manager to
    release the connection on exit.

    Attributes:
        base_url: The resolved helper base URL.

    Example:
        >>> async with AsyncNyora.attach() as client:
        ...     payload = await client.get("/sources")
    """

    def __init__(self, base_url: str | None = None, *, timeout: float = 60.0) -> None:
        """Connect to a helper.

        Args:
            base_url: Explicit helper base URL, or ``None`` to auto-discover.
            timeout: Per-request HTTP timeout in seconds.

        Raises:
            HelperNotFoundError: If no helper can be discovered.
        """
        self.base_url = _resolve_base_url(base_url)
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    @classmethod
    def attach(cls, base_url: str | None = None, *, timeout: float = 60.0) -> AsyncNyora:
        """Attach to an already-running helper.

        Args:
            base_url: Explicit helper base URL, or ``None`` to auto-discover.
            timeout: Per-request HTTP timeout in seconds.

        Returns:
            A connected async client.
        """
        return cls(base_url=base_url, timeout=timeout)

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

    async def health(self) -> dict[str, Any]:
        """Return the helper's ``/health`` payload.

        Returns:
            The health dict, or an empty dict if the response was not an object.
        """
        data = await self.get("/health")
        return data if isinstance(data, dict) else {}

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """Issue a ``GET`` request against the helper.

        Args:
            path: Request path relative to the base URL.
            params: Optional query parameters.

        Returns:
            Parsed JSON, or an empty dict for empty bodies.

        Raises:
            NyoraHTTPError: If the helper returns a 4xx/5xx response.
        """
        response = await self._http.get(path, params=params)
        if response.status_code >= 400:
            raise NyoraHTTPError(response.status_code, _error_message(response), body=response.text)
        return response.json() if response.content else {}


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
