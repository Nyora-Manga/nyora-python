"""Offline white-box tests for :class:`nyora.runtime.ParserRuntime`.

These tests never touch the network. They build a real :class:`ParserRuntime`
(which loads the bundled parser bundle), then drive its embedded QuickJS context
directly to prove that the browser/Node polyfills installed by the prelude work,
that the DOM callbacks tolerate empty / unknown input, and that an HTTP
transport failure degrades to an empty string instead of raising.
"""

from __future__ import annotations

import httpx
import pytest

from nyora.runtime import ParserRuntime


@pytest.fixture
def runtime() -> ParserRuntime:
    """Yield a live runtime and guarantee its HTTP client is closed."""
    rt = ParserRuntime()
    try:
        yield rt
    finally:
        rt.close()


# ---------------------------------------------------------------------------
# JavaScript polyfills
# ---------------------------------------------------------------------------
def test_btoa_atob_roundtrip(runtime: ParserRuntime) -> None:
    assert runtime._ctx.eval('btoa("hi")') == "aGk="
    assert runtime._ctx.eval('atob("aGk=")') == "hi"
    assert runtime._ctx.eval('atob(btoa("Hello, world!"))') == "Hello, world!"


def test_text_encoder_decoder_roundtrip(runtime: ParserRuntime) -> None:
    script = (
        "(function () {"
        '  var bytes = new TextEncoder().encode("héllo");'
        "  return new TextDecoder().decode(bytes);"
        "})()"
    )
    assert runtime._ctx.eval(script) == "héllo"


def test_buffer_base64_and_hex(runtime: ParserRuntime) -> None:
    assert runtime._ctx.eval('Buffer.from("hi").toString("base64")') == "aGk="
    assert runtime._ctx.eval('Buffer.from("hi").toString("hex")') == "6869"
    assert runtime._ctx.eval('Buffer.from("aGk=", "base64").toString("utf8")') == "hi"
    assert runtime._ctx.eval('Buffer.from("68656c6c6f", "hex").toString("utf8")') == "hello"


def test_url_parsing(runtime: ParserRuntime) -> None:
    assert runtime._ctx.eval('new URL("https://a.b/c?d=1").hostname') == "a.b"
    assert runtime._ctx.eval('new URL("https://a.b/x/y/z").pathname') == "/x/y/z"
    assert runtime._ctx.eval('new URL("https://a.b:8080/c").origin') == "https://a.b:8080"
    # Relative resolution against a base.
    assert runtime._ctx.eval('new URL("/c/d", "https://a.b/x/y").pathname') == "/c/d"


def test_url_search_params(runtime: ParserRuntime) -> None:
    assert runtime._ctx.eval('new URLSearchParams("a=1&b=2").get("b")') == "2"
    assert runtime._ctx.eval('new URLSearchParams({a: "1", b: "2"}).toString()') == "a=1&b=2"


def test_headers_case_insensitive(runtime: ParserRuntime) -> None:
    script = 'new Headers({"Content-Type": "text/html"}).get("content-type")'
    assert runtime._ctx.eval(script) == "text/html"


# ---------------------------------------------------------------------------
# DOM-callback tolerance
# ---------------------------------------------------------------------------
def test_parse_html_empty_does_not_raise(runtime: ParserRuntime) -> None:
    node_id = runtime._parse_html("")
    assert node_id != 0
    assert runtime._parse_html("<<<not valid") != 0


def test_dom_callbacks_safe_defaults_on_unknown_node(runtime: ParserRuntime) -> None:
    missing = 999_999_999
    assert runtime._query_all(missing, "div") == "[]"
    assert runtime._query_one(missing, "div") == 0
    assert runtime._get_attr(missing, "href") is None
    assert runtime._text(missing) == ""
    assert runtime._inner_html(missing) == ""
    assert runtime._outer_html(missing) == ""
    assert runtime._tag_name(missing) == ""
    assert runtime._parent(missing) == 0
    assert runtime._children(missing) == "[]"
    assert runtime._next(missing) == 0
    # Must not raise.
    runtime._remove(missing)


def test_dom_callbacks_on_empty_document(runtime: ParserRuntime) -> None:
    node_id = runtime._parse_html("")
    assert runtime._query_all(node_id, "div") == "[]"
    assert runtime._query_one(node_id, "div") == 0


# ---------------------------------------------------------------------------
# HTTP tolerance
# ---------------------------------------------------------------------------
def test_http_get_returns_empty_on_transport_failure(
    runtime: ParserRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(*_args: object, **_kwargs: object) -> None:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(runtime._http, "get", _raise)
    assert runtime._http_get("https://example.invalid/", "{}", "example.invalid") == ""


def test_http_post_returns_empty_on_transport_failure(
    runtime: ParserRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(*_args: object, **_kwargs: object) -> None:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(runtime._http, "post", _raise)
    assert runtime._http_post("https://example.invalid/", "", "{}", "example.invalid") == ""
