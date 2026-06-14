"""Embedded JavaScript parser runtime for Nyora Python.

This module hosts :class:`ParserRuntime`, the no-helper execution engine that
runs Nyora's bundled JavaScript parsers (``parsers.bundle.js``) inside a
`QuickJS <https://github.com/PetterS/quickjs>`_ context. The JavaScript side
exposes a global ``NyoraParsers`` object whose parsers call back into Python for
the things QuickJS cannot do on its own:

* HTTP requests are served by :mod:`httpx` (``__py_http_get`` / ``__py_http_post``).
* HTML parsing and DOM traversal are served by :mod:`selectolax`
  (``__py_parse_html`` and the ``__py_query_*`` / ``__py_*`` node accessors).

The runtime is deliberately *tolerant*: HTTP errors return the response body (or
an empty string on transport failure) instead of raising, and every DOM callback
returns a safe default rather than raising into JavaScript. Combined with the
browser/Node polyfills installed by :func:`_runtime_prelude`, this keeps the
embedded parsers running for the widest possible range of real-world sources.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
import threading
from typing import Any

import httpx
import quickjs
from selectolax.parser import HTMLParser, Node

from nyora.errors import NyoraError
from nyora.ota import OtaManager

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
)


class ParserRuntimeError(NyoraError):
    """Raised when the embedded parser runtime fails."""


class ParserRuntime:
    """Run Nyora's bundled JavaScript parsers inside an embedded QuickJS engine.

    A single instance owns one :class:`httpx.Client`, one QuickJS context, and
    the Python-side DOM node registry that backs the JavaScript ``PyNode``
    wrapper. The context is built from the JavaScript prelude
    (:func:`_runtime_prelude`) followed by the OTA-managed parser bundle.

    Args:
        timeout: Per-request HTTP timeout, in seconds, for the shared client.
        ota: Optional :class:`~nyora.ota.OtaManager`. When omitted a default
            manager is created, which transparently uses the bundled assets and
            the user cache.
    """

    def __init__(self, *, timeout: float = 60.0, ota: OtaManager | None = None) -> None:
        self._http = httpx.Client(timeout=timeout, follow_redirects=True)
        self._ota = ota or OtaManager()
        self._documents: dict[int, HTMLParser] = {}
        self._nodes: dict[int, Node] = {}
        self._lock = threading.Lock()
        self._build_context()

    def _build_context(self) -> None:
        self._documents = {}
        self._nodes = {}
        self._node_id_seq = 1
        self._ctx = quickjs.Context()
        self._install_python_callbacks()
        self._ctx.eval(_runtime_prelude())
        self._ctx.eval(self._ota.read_bundle_text())

    def reload(self) -> None:
        """Rebuild the QuickJS context from the (possibly updated) bundle.

        Re-reads the parser bundle via the :class:`~nyora.ota.OtaManager` and
        recreates the JavaScript context and DOM registry from scratch. Call
        this after an OTA update so the new parsers take effect.
        """
        with self._lock:
            self._build_context()

    def close(self) -> None:
        """Release the shared HTTP client. Safe to call once per instance."""
        self._http.close()

    def sources(self) -> list[dict[str, Any]]:
        """Return the catalog of available sources as raw parser metadata dicts.

        Returns:
            A list of source descriptors exactly as emitted by
            ``NyoraParsers.getAllSources()`` (camelCase keys), or an empty list
            if the bundle returns something other than an array.
        """
        with self._lock:
            raw = self._ctx.eval("JSON.stringify(NyoraParsers.getAllSources())")
        data = json.loads(str(raw))
        return data if isinstance(data, list) else []

    def call(self, source_id: str, method: str, args: dict[str, Any]) -> Any:
        """Invoke one parser method and return its decoded JSON result.

        Args:
            source_id: The source identifier, with or without the ``parser:``
                prefix.
            method: One of ``popular``, ``latest``, ``search``, ``details``, or
                ``pages``.
            args: Method arguments (e.g. ``page``, ``query``, ``url``,
                ``manga``, ``branch``, ``filter``) passed through to the parser.

        Returns:
            The parser result, JSON-decoded into native Python objects.

        Raises:
            ParserRuntimeError: If the parser is missing, the method is unknown,
                the parser reports an error, or the embedded engine fails.
        """
        clean_source_id = source_id.removeprefix("parser:")
        invocation = json.dumps(
            {"sourceId": clean_source_id, "method": method, "args": args},
            separators=(",", ":"),
        )
        with self._lock:
            try:
                self._ctx.set("__nyoraInvocationJson", invocation)
                self._ctx.eval("__nyoraInvoke(__nyoraInvocationJson)")
                for _ in range(1000):
                    if not self._ctx.execute_pending_job():
                        break
                error = self._ctx.eval("__nyoraError")
                if error:
                    raise ParserRuntimeError(str(error))
                result = self._ctx.eval("__nyoraResult")
            except ParserRuntimeError:
                raise
            except Exception as exc:
                # quickjs surfaces unhandled JS/callback failures as a raw SystemError;
                # normalise every engine-level failure to a NyoraError for callers.
                raise ParserRuntimeError(f"{source_id} {method} failed: {exc}") from exc
        if result is None:
            raise ParserRuntimeError("Parser returned no result")
        return json.loads(str(result))

    def _install_python_callbacks(self) -> None:
        """Bridge every Python callback into the JavaScript global scope."""
        self._ctx.add_callable("__py_http_get", self._http_get)
        self._ctx.add_callable("__py_http_post", self._http_post)
        self._ctx.add_callable("__py_parse_html", self._parse_html)
        self._ctx.add_callable("__py_query_all", self._query_all)
        self._ctx.add_callable("__py_query_one", self._query_one)
        self._ctx.add_callable("__py_get_attr", self._get_attr)
        self._ctx.add_callable("__py_text", self._text)
        self._ctx.add_callable("__py_inner_html", self._inner_html)
        self._ctx.add_callable("__py_outer_html", self._outer_html)
        self._ctx.add_callable("__py_tag_name", self._tag_name)
        self._ctx.add_callable("__py_parent", self._parent)
        self._ctx.add_callable("__py_children", self._children)
        self._ctx.add_callable("__py_next", self._next)
        self._ctx.add_callable("__py_remove", self._remove)

    def _http_get(self, url: str, headers_json: str, domain: str) -> str:
        """Fetch ``url`` and return the body text for ANY status code.

        Many real-world parsers expect to inspect the raw body even on 4xx/5xx
        responses, so this deliberately does not call ``raise_for_status``. On a
        transport-level failure (timeout, DNS, connection error) it returns an
        empty string rather than raising into JavaScript.
        """
        try:
            response = self._http.get(url, headers=self._headers(headers_json, domain))
        except httpx.HTTPError:
            return ""
        return response.text

    def _http_post(self, url: str, body: str, headers_json: str, domain: str) -> str:
        """POST ``body`` to ``url`` and return the body text for ANY status code.

        Mirrors :meth:`_http_get`: no ``raise_for_status``, and a transport
        failure yields an empty string instead of raising.
        """
        try:
            response = self._http.post(
                url, content=body, headers=self._headers(headers_json, domain)
            )
        except httpx.HTTPError:
            return ""
        return response.text

    def _headers(self, headers_json: str, domain: str) -> dict[str, str]:
        """Build the outgoing header set for a request.

        Starts from a browser-like default set, derives ``Referer``/``Origin``
        from ``domain`` when present, then layers any parser-supplied headers
        (a JSON object string) on top.
        """
        try:
            extra = json.loads(headers_json) if headers_json else {}
        except json.JSONDecodeError:
            extra = {}
        origin = f"https://{domain}" if domain else ""
        headers = {
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        if origin:
            headers["Referer"] = f"{origin}/"
            headers["Origin"] = origin
        if isinstance(extra, dict):
            headers.update({str(key): str(value) for key, value in extra.items()})
        return headers

    def _parse_html(self, html: str) -> int:
        """Parse an HTML string and return a node id for its root element.

        Empty or malformed input never raises: :mod:`selectolax` synthesises a
        valid (possibly empty) ``<html>`` root, which is registered and
        returned. On the unexpected event of a missing root, returns ``0``.
        """
        document = HTMLParser(html or "")
        if document.root is None:
            return 0
        node_id = self._store_node(document.root)
        self._documents[node_id] = document
        return node_id

    def _query_all(self, node_id: int, selector: str) -> str:
        """Return a JSON array of node ids matching ``selector`` under a node.

        Returns ``"[]"`` on an unknown node id or any selector/engine failure.
        """
        node = self._nodes.get(node_id)
        if node is None:
            return "[]"
        try:
            ids = [self._store_node(item) for item in node.css(selector)]
        except Exception:
            ids = []
        return json.dumps(ids)

    def _query_one(self, node_id: int, selector: str) -> int:
        """Return the first node id matching ``selector``, or ``0`` if none.

        Returns ``0`` on an unknown node id or any selector/engine failure.
        """
        node = self._nodes.get(node_id)
        if node is None:
            return 0
        try:
            found = node.css_first(selector)
        except Exception:
            found = None
        return self._store_node(found) if found is not None else 0

    def _get_attr(self, node_id: int, name: str) -> str | None:
        """Return the named attribute value, or ``None`` if absent/unknown node."""
        node = self._nodes.get(node_id)
        if node is None:
            return None
        return node.attributes.get(name)

    def _text(self, node_id: int) -> str:
        """Return the concatenated text content, or ``""`` for an unknown node."""
        node = self._nodes.get(node_id)
        if node is None:
            return ""
        try:
            return node.text()
        except Exception:
            return ""

    def _inner_html(self, node_id: int) -> str:
        """Return the node's HTML serialisation, or ``""`` for an unknown node."""
        node = self._nodes.get(node_id)
        if node is None:
            return ""
        return node.html or ""

    def _outer_html(self, node_id: int) -> str:
        """Return the node's HTML serialisation, or ``""`` for an unknown node."""
        node = self._nodes.get(node_id)
        if node is None:
            return ""
        return node.html or ""

    def _tag_name(self, node_id: int) -> str:
        """Return the upper-cased tag name, or ``""`` for an unknown node."""
        node = self._nodes.get(node_id)
        if node is None or node.tag is None:
            return ""
        return node.tag.upper()

    def _parent(self, node_id: int) -> int:
        """Return the parent node id, or ``0`` if none / unknown node."""
        node = self._nodes.get(node_id)
        if node is None:
            return 0
        parent = node.parent
        return self._store_node(parent) if parent is not None else 0

    def _children(self, node_id: int) -> str:
        """Return a JSON array of element-child node ids (text nodes skipped).

        Returns ``"[]"`` for an unknown node.
        """
        node = self._nodes.get(node_id)
        if node is None:
            return "[]"
        children: list[int] = []
        child = node.child
        while child is not None:
            if child.tag != "-text":
                children.append(self._store_node(child))
            child = child.next
        return json.dumps(children)

    def _next(self, node_id: int) -> int:
        """Return the next element-sibling node id, or ``0`` if none/unknown."""
        node = self._nodes.get(node_id)
        if node is None:
            return 0
        sibling = node.next
        while sibling is not None and sibling.tag == "-text":
            sibling = sibling.next
        return self._store_node(sibling) if sibling is not None else 0

    def _remove(self, node_id: int) -> None:
        """Detach a node from its document. No-op for an unknown node."""
        node = self._nodes.get(node_id)
        if node is None:
            return
        try:
            node.decompose()
        except Exception:
            pass

    def _store_node(self, node: Node) -> int:
        """Register ``node`` in the registry and return its stable integer id."""
        self._node_id_seq += 1
        node_id = self._node_id_seq
        self._nodes[node_id] = node
        return node_id


def _read_asset_text(name: str) -> str:
    try:
        return resources.files("nyora.assets").joinpath(name).read_text(encoding="utf-8")
    except FileNotFoundError:
        root = Path(__file__).resolve().parents[2]
        return root.joinpath(name).read_text(encoding="utf-8")


def _runtime_prelude() -> str:
    """Return the JavaScript prelude evaluated before the parser bundle.

    The prelude has two parts. First it installs browser/Node polyfills on
    ``globalThis`` for the APIs QuickJS lacks (``console``, ``atob``/``btoa``,
    ``TextEncoder``/``TextDecoder``, a minimal ``Buffer``, ``URL``,
    ``URLSearchParams``, ``Headers``, ``DOMParser``, and ``setTimeout`` &
    friends). It deliberately does NOT re-polyfill ES2020 features QuickJS
    already provides (``JSON``, ``Promise``, ``Array.from``, ``String.matchAll``,
    ``String.padStart``, ``encodeURIComponent``, ``globalThis``).

    Second it defines the Nyora glue: the ``PyNode`` DOM wrapper, the
    ``__nyoraContext`` (``httpGet``/``httpPost``/``parseHTML``/``decodeContent``)
    that proxies to the Python callbacks, and ``__nyoraInvoke`` which dispatches
    a parser method and records the result in ``__nyoraResult`` or the error text
    in ``__nyoraError``.
    """
    return _POLYFILL_PRELUDE + _NYORA_PRELUDE


_POLYFILL_PRELUDE = r"""
(function () {
  var g = globalThis;

  // --- console: safe no-ops -------------------------------------------------
  if (!g.console) {
    var noop = function () {};
    g.console = { log: noop, warn: noop, error: noop, info: noop, debug: noop };
  }

  // --- atob / btoa: binary-safe base64 -------------------------------------
  var B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  if (!g.btoa) {
    g.btoa = function (input) {
      var str = String(input);
      var out = "";
      for (var i = 0; i < str.length; ) {
        var c1 = str.charCodeAt(i++) & 0xff;
        var c2 = str.charCodeAt(i++);
        var c3 = str.charCodeAt(i++);
        var e1 = c1 >> 2;
        var e2 = ((c1 & 3) << 4) | ((isNaN(c2) ? 0 : c2) >> 4);
        var e3 = isNaN(c2) ? 64 : (((c2 & 15) << 2) | ((isNaN(c3) ? 0 : c3) >> 6));
        var e4 = isNaN(c3) ? 64 : (c3 & 63);
        out += B64.charAt(e1) + B64.charAt(e2) +
               (e3 === 64 ? "=" : B64.charAt(e3)) +
               (e4 === 64 ? "=" : B64.charAt(e4));
      }
      return out;
    };
  }
  if (!g.atob) {
    g.atob = function (input) {
      // Strip padding and any non-alphabet characters; decode by length.
      var str = String(input).replace(/[^A-Za-z0-9+/]/g, "");
      var out = "";
      for (var i = 0; i < str.length; ) {
        var e1 = B64.indexOf(str.charAt(i++));
        var e2 = B64.indexOf(str.charAt(i++));
        var e3 = i <= str.length ? B64.indexOf(str.charAt(i++)) : -1;
        var e4 = i <= str.length ? B64.indexOf(str.charAt(i++)) : -1;
        var c1 = (e1 << 2) | (e2 >> 4);
        out += String.fromCharCode(c1 & 0xff);
        if (e3 >= 0) {
          var c2 = ((e2 & 15) << 4) | (e3 >> 2);
          out += String.fromCharCode(c2 & 0xff);
        }
        if (e4 >= 0) {
          var c3 = ((e3 & 3) << 6) | e4;
          out += String.fromCharCode(c3 & 0xff);
        }
      }
      return out;
    };
  }

  // --- UTF-8 codec helpers (shared by TextEncoder/Decoder/Buffer) ----------
  function utf8Encode(str) {
    str = String(str);
    var bytes = [];
    for (var i = 0; i < str.length; i++) {
      var code = str.charCodeAt(i);
      if (code >= 0xd800 && code <= 0xdbff && i + 1 < str.length) {
        var next = str.charCodeAt(i + 1);
        if (next >= 0xdc00 && next <= 0xdfff) {
          code = 0x10000 + ((code - 0xd800) << 10) + (next - 0xdc00);
          i++;
        }
      }
      if (code < 0x80) {
        bytes.push(code);
      } else if (code < 0x800) {
        bytes.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f));
      } else if (code < 0x10000) {
        bytes.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));
      } else {
        bytes.push(
          0xf0 | (code >> 18),
          0x80 | ((code >> 12) & 0x3f),
          0x80 | ((code >> 6) & 0x3f),
          0x80 | (code & 0x3f)
        );
      }
    }
    return bytes;
  }
  function utf8Decode(bytes) {
    var out = "";
    var i = 0;
    var len = bytes.length;
    while (i < len) {
      var b1 = bytes[i++] & 0xff;
      var code;
      if (b1 < 0x80) {
        code = b1;
      } else if (b1 < 0xe0) {
        code = ((b1 & 0x1f) << 6) | (bytes[i++] & 0x3f);
      } else if (b1 < 0xf0) {
        code = ((b1 & 0x0f) << 12) | ((bytes[i++] & 0x3f) << 6) | (bytes[i++] & 0x3f);
      } else {
        code =
          ((b1 & 0x07) << 18) |
          ((bytes[i++] & 0x3f) << 12) |
          ((bytes[i++] & 0x3f) << 6) |
          (bytes[i++] & 0x3f);
      }
      if (code > 0xffff) {
        code -= 0x10000;
        out += String.fromCharCode(0xd800 + (code >> 10), 0xdc00 + (code & 0x3ff));
      } else {
        out += String.fromCharCode(code);
      }
    }
    return out;
  }

  // --- TextEncoder / TextDecoder -------------------------------------------
  if (!g.TextEncoder) {
    g.TextEncoder = function TextEncoder() {
      this.encoding = "utf-8";
    };
    g.TextEncoder.prototype.encode = function (str) {
      return Uint8Array.from(utf8Encode(str));
    };
  }
  if (!g.TextDecoder) {
    g.TextDecoder = function TextDecoder(label) {
      this.encoding = label ? String(label).toLowerCase() : "utf-8";
    };
    g.TextDecoder.prototype.decode = function (input) {
      if (input == null) return "";
      var bytes = input.buffer ? new Uint8Array(input.buffer, input.byteOffset, input.byteLength)
                               : input;
      var arr = [];
      for (var i = 0; i < bytes.length; i++) arr.push(bytes[i]);
      return utf8Decode(arr);
    };
  }

  // --- Buffer (minimal Node shim) ------------------------------------------
  function bytesToBinary(bytes) {
    var s = "";
    for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i] & 0xff);
    return s;
  }
  function binaryToBytes(str) {
    var bytes = [];
    for (var i = 0; i < str.length; i++) bytes.push(str.charCodeAt(i) & 0xff);
    return bytes;
  }
  if (!g.Buffer) {
    var Buffer = function Buffer(bytes) {
      this._bytes = bytes || [];
      this.length = this._bytes.length;
    };
    Buffer.from = function (value, encoding) {
      if (value == null) return new Buffer([]);
      if (typeof value === "string") {
        var enc = encoding ? String(encoding).toLowerCase() : "utf8";
        if (enc === "base64") return new Buffer(binaryToBytes(g.atob(value)));
        if (enc === "hex") {
          var bytes = [];
          for (var i = 0; i + 1 < value.length; i += 2) {
            bytes.push(parseInt(value.substr(i, 2), 16) & 0xff);
          }
          return new Buffer(bytes);
        }
        if (enc === "latin1" || enc === "binary") return new Buffer(binaryToBytes(value));
        return new Buffer(utf8Encode(value));
      }
      // array-like / typed array
      var out = [];
      for (var j = 0; j < value.length; j++) out.push(value[j] & 0xff);
      return new Buffer(out);
    };
    Buffer.prototype.toString = function (encoding) {
      var enc = encoding ? String(encoding).toLowerCase() : "utf8";
      if (enc === "base64") return g.btoa(bytesToBinary(this._bytes));
      if (enc === "hex") {
        var s = "";
        for (var i = 0; i < this._bytes.length; i++) {
          var h = (this._bytes[i] & 0xff).toString(16);
          s += h.length === 1 ? "0" + h : h;
        }
        return s;
      }
      if (enc === "latin1" || enc === "binary") return bytesToBinary(this._bytes);
      return utf8Decode(this._bytes);
    };
    g.Buffer = Buffer;
  }

  // --- URLSearchParams ------------------------------------------------------
  if (!g.URLSearchParams) {
    var URLSearchParams = function URLSearchParams(init) {
      this._pairs = [];
      if (init == null) return;
      if (typeof init === "string") {
        var s = init.charAt(0) === "?" ? init.slice(1) : init;
        if (s.length) {
          var parts = s.split("&");
          for (var i = 0; i < parts.length; i++) {
            if (!parts[i]) continue;
            var idx = parts[i].indexOf("=");
            var k = idx < 0 ? parts[i] : parts[i].slice(0, idx);
            var v = idx < 0 ? "" : parts[i].slice(idx + 1);
            this._pairs.push([decodeURIComponent(k.replace(/\+/g, " ")),
                              decodeURIComponent(v.replace(/\+/g, " "))]);
          }
        }
      } else if (Array.isArray(init)) {
        for (var a = 0; a < init.length; a++) {
          this._pairs.push([String(init[a][0]), String(init[a][1])]);
        }
      } else if (typeof init === "object") {
        for (var key in init) {
          if (Object.prototype.hasOwnProperty.call(init, key)) {
            this._pairs.push([String(key), String(init[key])]);
          }
        }
      }
    };
    URLSearchParams.prototype.append = function (k, v) {
      this._pairs.push([String(k), String(v)]);
    };
    URLSearchParams.prototype.set = function (k, v) {
      k = String(k);
      var found = false;
      var next = [];
      for (var i = 0; i < this._pairs.length; i++) {
        if (this._pairs[i][0] === k) {
          if (!found) { next.push([k, String(v)]); found = true; }
        } else {
          next.push(this._pairs[i]);
        }
      }
      if (!found) next.push([k, String(v)]);
      this._pairs = next;
    };
    URLSearchParams.prototype.get = function (k) {
      k = String(k);
      for (var i = 0; i < this._pairs.length; i++) {
        if (this._pairs[i][0] === k) return this._pairs[i][1];
      }
      return null;
    };
    URLSearchParams.prototype.getAll = function (k) {
      k = String(k);
      var out = [];
      for (var i = 0; i < this._pairs.length; i++) {
        if (this._pairs[i][0] === k) out.push(this._pairs[i][1]);
      }
      return out;
    };
    URLSearchParams.prototype.has = function (k) {
      return this.get(String(k)) !== null;
    };
    URLSearchParams.prototype["delete"] = function (k) {
      k = String(k);
      this._pairs = this._pairs.filter(function (p) { return p[0] !== k; });
    };
    URLSearchParams.prototype.forEach = function (cb, thisArg) {
      for (var i = 0; i < this._pairs.length; i++) {
        cb.call(thisArg, this._pairs[i][1], this._pairs[i][0], this);
      }
    };
    URLSearchParams.prototype.entries = function () {
      return this._pairs.map(function (p) { return [p[0], p[1]]; });
    };
    URLSearchParams.prototype.keys = function () {
      return this._pairs.map(function (p) { return p[0]; });
    };
    URLSearchParams.prototype.values = function () {
      return this._pairs.map(function (p) { return p[1]; });
    };
    URLSearchParams.prototype.toString = function () {
      return this._pairs
        .map(function (p) {
          return encodeURIComponent(p[0]) + "=" + encodeURIComponent(p[1]);
        })
        .join("&");
    };
    g.URLSearchParams = URLSearchParams;
  }

  // --- URL ------------------------------------------------------------------
  if (!g.URL) {
    function resolveUrl(url, base) {
      url = String(url);
      // Already absolute.
      if (/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(url)) return url;
      if (!base) return url;
      base = String(base);
      var m = base.match(/^([a-zA-Z][a-zA-Z0-9+.-]*:\/\/[^/?#]*)([^?#]*)/);
      if (!m) return url;
      var root = m[1];
      var basePath = m[2] || "/";
      if (url.indexOf("//") === 0) {
        return root.split("://")[0] + ":" + url;
      }
      if (url.charAt(0) === "/") return root + url;
      if (url.charAt(0) === "?" || url.charAt(0) === "#") {
        return root + basePath + url;
      }
      var dir = basePath.replace(/[^/]*$/, "");
      var combined = dir + url;
      var segs = combined.split("/");
      var stack = [];
      for (var i = 0; i < segs.length; i++) {
        if (segs[i] === "." || segs[i] === "") {
          if (i === segs.length - 1) stack.push("");
          continue;
        }
        if (segs[i] === "..") { stack.pop(); continue; }
        stack.push(segs[i]);
      }
      return root + "/" + stack.join("/");
    }
    var URL = function URL(url, base) {
      var href = resolveUrl(url, base);
      this.href = href;
      var m = href.match(
        /^([a-zA-Z][a-zA-Z0-9+.-]*:)\/\/([^/?#]*)([^?#]*)(\?[^#]*)?(#.*)?$/
      );
      if (m) {
        this.protocol = m[1];
        var host = m[2] || "";
        this.host = host;
        var hostParts = host.split(":");
        this.hostname = hostParts[0];
        this.port = hostParts.length > 1 ? hostParts[1] : "";
        this.pathname = m[3] || "/";
        this.search = m[4] || "";
        this.hash = m[5] || "";
        this.origin = this.protocol + "//" + this.host;
      } else {
        this.protocol = "";
        this.host = "";
        this.hostname = "";
        this.port = "";
        this.pathname = href;
        this.search = "";
        this.hash = "";
        this.origin = "";
      }
      this.searchParams = new g.URLSearchParams(this.search);
    };
    URL.prototype.toString = function () { return this.href; };
    g.URL = URL;
  }

  // --- Headers --------------------------------------------------------------
  if (!g.Headers) {
    var Headers = function Headers(init) {
      this._map = {};
      if (!init) return;
      if (Array.isArray(init)) {
        for (var i = 0; i < init.length; i++) this.append(init[i][0], init[i][1]);
      } else if (typeof init.forEach === "function") {
        var self = this;
        init.forEach(function (v, k) { self.append(k, v); });
      } else if (typeof init === "object") {
        for (var key in init) {
          if (Object.prototype.hasOwnProperty.call(init, key)) this.append(key, init[key]);
        }
      }
    };
    Headers.prototype.set = function (k, v) {
      this._map[String(k).toLowerCase()] = { name: String(k), value: String(v) };
    };
    Headers.prototype.append = function (k, v) {
      var lk = String(k).toLowerCase();
      if (this._map[lk]) {
        this._map[lk].value += ", " + String(v);
      } else {
        this._map[lk] = { name: String(k), value: String(v) };
      }
    };
    Headers.prototype.get = function (k) {
      var e = this._map[String(k).toLowerCase()];
      return e ? e.value : null;
    };
    Headers.prototype.has = function (k) {
      return Object.prototype.hasOwnProperty.call(this._map, String(k).toLowerCase());
    };
    Headers.prototype["delete"] = function (k) {
      delete this._map[String(k).toLowerCase()];
    };
    Headers.prototype.forEach = function (cb, thisArg) {
      for (var lk in this._map) {
        if (Object.prototype.hasOwnProperty.call(this._map, lk)) {
          cb.call(thisArg, this._map[lk].value, lk, this);
        }
      }
    };
    g.Headers = Headers;
  }

  // --- DOMParser ------------------------------------------------------------
  if (!g.DOMParser) {
    var DOMParser = function DOMParser() {};
    DOMParser.prototype.parseFromString = function (str, type) {
      return __nyoraContext.parseHTML(String(str == null ? "" : str));
    };
    g.DOMParser = DOMParser;
  }

  // --- timers ---------------------------------------------------------------
  if (!g.setTimeout) {
    g.setTimeout = function (fn) {
      try {
        if (typeof fn === "function") Promise.resolve().then(function () { fn(); });
      } catch (e) {}
      return 0;
    };
  }
  if (!g.clearTimeout) g.clearTimeout = function () {};
  if (!g.setInterval) g.setInterval = function () { return 0; };
  if (!g.clearInterval) g.clearInterval = function () {};
})();
"""


_NYORA_PRELUDE = r"""
globalThis.self = globalThis;
globalThis.crypto = {
  getRandomValues: function(arr) {
    for (let i = 0; i < arr.length; i++) arr[i] = Math.floor(Math.random() * 256);
    return arr;
  }
};

function __wrapNode(id) {
  if (!id) return null;
  return new PyNode(id);
}

class PyNode {
  constructor(id) {
    this.__id = id;
    this.nodeType = 1;
    this.documentElement = this;
  }
  querySelectorAll(selector) {
    return JSON.parse(__py_query_all(this.__id, String(selector))).map(__wrapNode);
  }
  querySelector(selector) {
    return __wrapNode(__py_query_one(this.__id, String(selector)));
  }
  getElementById(id) {
    return this.querySelector("#" + String(id).replace(/"/g, '\\"'));
  }
  getAttribute(name) {
    const value = __py_get_attr(this.__id, String(name));
    return value == null ? null : String(value);
  }
  cloneNode() {
    return this;
  }
  remove() {
    __py_remove(this.__id);
  }
  get textContent() {
    return __py_text(this.__id);
  }
  get innerText() {
    return this.textContent;
  }
  get innerHTML() {
    return __py_inner_html(this.__id);
  }
  get outerHTML() {
    return __py_outer_html(this.__id);
  }
  get tagName() {
    return __py_tag_name(this.__id);
  }
  get parentElement() {
    return __wrapNode(__py_parent(this.__id));
  }
  get nextElementSibling() {
    return __wrapNode(__py_next(this.__id));
  }
  get children() {
    return JSON.parse(__py_children(this.__id)).map(__wrapNode);
  }
  get childNodes() {
    return this.children;
  }
  get classList() {
    const self = this;
    return {
      contains: function(name) {
        return (self.getAttribute("class") || "").split(/\s+/).includes(String(name));
      }
    };
  }
}

const __nyoraContext = {
  httpGet: function(url, headersOrParser, parserMaybe) {
    let headers = {};
    let parser = parserMaybe || null;
    if (headersOrParser && headersOrParser.domain && !parserMaybe) {
      parser = headersOrParser;
    } else if (headersOrParser) {
      headers = headersOrParser;
    }
    return __py_http_get(String(url), JSON.stringify(headers || {}), parser && parser.domain || "");
  },
  httpPost: function(url, body, headersOrParser, parserMaybe) {
    let headers = {};
    let parser = parserMaybe || null;
    if (headersOrParser && headersOrParser.domain && !parserMaybe) {
      parser = headersOrParser;
    } else if (headersOrParser) {
      headers = headersOrParser;
    }
    return __py_http_post(
      String(url),
      body == null ? "" : String(body),
      JSON.stringify(headers || {}),
      parser && parser.domain || ""
    );
  },
  parseHTML: function(html) {
    return __wrapNode(__py_parse_html(String(html || "")));
  },
  decodeContent: function(value) {
    return value;
  }
};

var __nyoraResult = null;
var __nyoraError = null;
var __nyoraInvocationJson = null;

function __nyoraErrorText(error) {
  return (error && (error.stack || error.message || error.name)) || String(error);
}

function __nyoraInvoke(payloadJson) {
  __nyoraResult = null;
  __nyoraError = null;
  let call;
  try {
    const payload = JSON.parse(payloadJson);
    const parser = NyoraParsers.getParser(payload.sourceId, __nyoraContext);
    if (!parser) {
      __nyoraError = "Parser not found: " + payload.sourceId;
      return;
    }
    const args = payload.args || {};
    if (payload.method === "popular") {
      call = parser.getListPage(args.page || 1, "POPULARITY", args.filter || {});
    } else if (payload.method === "latest") {
      call = parser.getListPage(args.page || 1, "UPDATED", args.filter || {});
    } else if (payload.method === "search") {
      call = parser.getListPage(args.page || 1, "RELEVANCE", { query: args.query || "" });
    } else if (payload.method === "details") {
      call = parser.getDetails(
        args.manga || { id: args.url, url: args.url, title: args.title || "" }
      );
    } else if (payload.method === "pages") {
      call = parser.getPages({
        id: args.url,
        url: args.url,
        branch: args.branch,
        source: { id: payload.sourceId }
      });
    } else {
      __nyoraError = "Unknown parser method: " + payload.method;
      return;
    }
  } catch (error) {
    __nyoraError = __nyoraErrorText(error);
    return;
  }
  Promise.resolve(call).then(
    function(result) { __nyoraResult = JSON.stringify(result); },
    function(error) { __nyoraError = __nyoraErrorText(error); }
  );
}
"""
