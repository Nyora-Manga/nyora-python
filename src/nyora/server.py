"""Stdlib HTTP server exposing the helper-compatible REST contract.

This module lets the Python SDK act as a Nyora helper. :class:`NyoraServer`
serves the same camelCase REST endpoints the JVM helper exposes
(``/health``, ``/sources``, ``/sources/popular`` and friends,
``/manga/details``, ``/manga/pages``), but backs them with an embedded
:class:`nyora.runtime.ParserRuntime` instead of the JVM. On start it can write
the discovered port to the standard helper port file, so other Nyora apps and
:class:`nyora.client.Nyora` can attach to it automatically.

The server is built on :class:`http.server.ThreadingHTTPServer`; requests are
serialized onto the runtime via a lock, and all errors are returned as clean
JSON rather than stack-trace 500s.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from nyora.config import default_port_file
from nyora.direct import _source_to_helper_shape
from nyora.errors import NyoraError
from nyora.runtime import ParserRuntime


class NyoraServer:
    """Serve the camelCase helper REST contract over an embedded runtime.

    Exposes the Nyora helper REST API backed by a :class:`ParserRuntime`, so any
    Nyora client (including :class:`nyora.client.Nyora`) can talk to the Python
    SDK as if it were the JVM helper.

    Example:
        >>> server = NyoraServer()
        >>> base_url = server.start()  # background thread, returns immediately
        >>> # ... attach a client to base_url ...
        >>> server.stop()
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        *,
        runtime: ParserRuntime | None = None,
        write_port_file: bool = True,
        timeout: float = 60.0,
    ) -> None:
        """Initialize the server.

        Args:
            host: Interface to bind. Defaults to loopback.
            port: Port to bind, or ``0`` to pick a free ephemeral port.
            runtime: An existing :class:`ParserRuntime` to serve. When ``None``,
                a new one is created and owned (closed on :meth:`stop`).
            write_port_file: Whether to write the bound port to the standard
                helper port file so other apps can discover this server.
            timeout: Per-call timeout in seconds for an owned runtime.
        """
        self._host = host
        self._port = port
        self._owns_runtime = runtime is None
        self._runtime = runtime or ParserRuntime(timeout=timeout)
        self._write_port_file = write_port_file
        self._lock = threading.Lock()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        """The base URL the server is bound to.

        Returns:
            The ``http://host:port`` base URL.

        Raises:
            NyoraError: If the server has not been started yet.
        """
        if self._httpd is None:
            raise NyoraError("Server is not running; call start() first")
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}"

    def _ensure_httpd(self) -> ThreadingHTTPServer:
        """Create the underlying HTTP server if needed and bind the socket.

        Returns:
            The bound :class:`http.server.ThreadingHTTPServer`.
        """
        if self._httpd is not None:
            return self._httpd
        handler = _make_handler(self)
        self._httpd = ThreadingHTTPServer((self._host, self._port), handler)
        self._host, self._port = self._httpd.server_address[:2]
        if self._write_port_file:
            self._persist_port_file(self._port)
        return self._httpd

    def _persist_port_file(self, port: int) -> None:
        """Write the bound port to the standard helper port file.

        Args:
            port: The port number to record.
        """
        path = default_port_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(port), encoding="utf-8")

    def start(self) -> str:
        """Start serving in a background daemon thread.

        Idempotent: calling it again while running returns the existing URL.

        Returns:
            The base URL the server is bound to.
        """
        httpd = self._ensure_httpd()
        if self._thread is not None and self._thread.is_alive():
            return self.base_url
        self._thread = threading.Thread(
            target=httpd.serve_forever,
            name="nyora-server",
            daemon=True,
        )
        self._thread.start()
        return self.base_url

    def serve_forever(self) -> None:
        """Serve requests in the calling thread until interrupted.

        Blocks until the server is shut down (e.g. by ``KeyboardInterrupt``),
        then stops and cleans up.
        """
        httpd = self._ensure_httpd()
        try:
            httpd.serve_forever()
        finally:
            self.stop()

    def stop(self) -> None:
        """Shut down the server and release its resources.

        Closes the listening socket, joins the background thread, and closes an
        owned runtime. Safe to call when not running.
        """
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread = None
        if self._owns_runtime:
            self._runtime.close()

    # --- request dispatch (called under the handler thread) -------------------

    def _call(self, source_id: str, method: str, args: dict[str, Any]) -> Any:
        """Invoke a parser method under the runtime lock.

        Args:
            source_id: Source identifier.
            method: Parser method name (e.g. ``"popular"``, ``"details"``).
            args: Method arguments.

        Returns:
            The raw parser result.
        """
        with self._lock:
            return self._runtime.call(source_id, method, args)

    def _sources(self) -> list[dict[str, Any]]:
        """Return the source catalog in helper REST shape, under the lock.

        Returns:
            A list of camelCase source dicts.
        """
        with self._lock:
            return [_source_to_helper_shape(item) for item in self._runtime.sources()]

    def dispatch(self, path: str, query: dict[str, list[str]]) -> tuple[int, dict[str, Any]]:
        """Route one request to the appropriate handler.

        Args:
            path: The request path (no query string).
            query: Parsed query parameters (each value is a list).

        Returns:
            A ``(status_code, json_body)`` tuple.

        Raises:
            _BadRequest: If a required query parameter is missing or invalid.
            LookupError: If a referenced source does not exist.
            NyoraError: If the underlying runtime call fails.
        """
        if path == "/health":
            return 200, {"ok": True, "engine": "python-quickjs"}

        if path == "/sources":
            return 200, {"sources": self._sources()}

        if path in ("/sources/popular", "/sources/latest", "/sources/search"):
            source_id = _require(query, "id")
            page = _int_param(query, "page", 1)
            if path.endswith("/popular"):
                data = self._call(source_id, "popular", {"page": page})
            elif path.endswith("/latest"):
                data = self._call(source_id, "latest", {"page": page})
            else:
                data = self._call(
                    source_id,
                    "search",
                    {"query": _require(query, "q"), "page": page},
                )
            entries = data if isinstance(data, list) else []
            return 200, {"entries": entries, "hasNextPage": bool(entries)}

        if path == "/manga/details":
            source_id = _require(query, "id")
            url = _require(query, "url")
            title = _opt(query, "title") or ""
            manga = self._call(source_id, "details", {"url": url, "title": title})
            chapters = manga.get("chapters", []) if isinstance(manga, dict) else []
            return 200, {"manga": manga, "chapters": chapters}

        if path == "/manga/pages":
            source_id = _require(query, "id")
            url = _require(query, "url")
            branch = _opt(query, "branch")
            data = self._call(source_id, "pages", {"url": url, "branch": branch})
            pages = data if isinstance(data, list) else []
            return 200, {"pages": pages}

        return 404, {"error": f"Not found: {path}"}


def _require(query: dict[str, list[str]], name: str) -> str:
    """Return a required query parameter or raise.

    Args:
        query: Parsed query parameters.
        name: Parameter name to read.

    Returns:
        The parameter's first value.

    Raises:
        _BadRequest: If the parameter is missing or empty.
    """
    value = _opt(query, name)
    if not value:
        raise _BadRequest(f"Missing required query parameter: {name!r}")
    return value


def _opt(query: dict[str, list[str]], name: str) -> str | None:
    """Return an optional query parameter's first value.

    Args:
        query: Parsed query parameters.
        name: Parameter name to read.

    Returns:
        The first value, or ``None`` when absent.
    """
    values = query.get(name)
    if not values:
        return None
    return values[0]


def _int_param(query: dict[str, list[str]], name: str, default: int) -> int:
    """Read an integer query parameter with a default.

    Args:
        query: Parsed query parameters.
        name: Parameter name to read.
        default: Value returned when the parameter is absent.

    Returns:
        The parsed integer, or ``default``.

    Raises:
        _BadRequest: If the parameter is present but not an integer.
    """
    raw = _opt(query, name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise _BadRequest(f"Query parameter {name!r} must be an integer") from exc


class _BadRequest(Exception):
    """Internal signal for a 400 response."""


def _make_handler(server: NyoraServer) -> type[BaseHTTPRequestHandler]:
    """Build a request-handler class bound to a server instance.

    Args:
        server: The :class:`NyoraServer` whose ``dispatch`` handles requests.

    Returns:
        A :class:`http.server.BaseHTTPRequestHandler` subclass.
    """

    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "NyoraServer/1.0"

        def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
            parts = urlsplit(self.path)
            query = parse_qs(parts.query)
            try:
                status, body = server.dispatch(parts.path, query)
            except _BadRequest as exc:
                status, body = 400, {"error": str(exc)}
            except LookupError as exc:
                status, body = 404, {"error": str(exc)}
            except NyoraError as exc:
                status, body = 502, {"error": str(exc)}
            except Exception as exc:  # noqa: BLE001 (return clean JSON, never 500-traceback)
                status, body = 500, {"error": f"{type(exc).__name__}: {exc}"}
            self._send_json(status, body)

        def _send_json(self, status: int, body: dict[str, Any]) -> None:
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: Any) -> None:  # silence stderr access logs
            pass

    return _Handler
