# Server guide

`nyora.server.NyoraServer` turns the Python SDK into a **Nyora helper**. It
serves the same camelCase REST contract the JVM helper exposes, but backs it
with the embedded `nyora.runtime.ParserRuntime` instead of the JVM — no Node and
no Java. Any Nyora client, including `nyora.client.Nyora`, can attach to it as if
it were the real helper.

```{note}
This is the library API. The CLI tool exposes the same server via
`nyora-cli serve`; that command is documented in the CLI docs.
```

## What the server is for

- Let other Nyora apps (or a second process) reach the Python parsers over HTTP.
- Provide a stable, helper-compatible endpoint surface so existing Nyora clients
  work unchanged.
- Publish a discoverable port file so clients attach automatically.

It is built on `http.server.ThreadingHTTPServer`. Requests are serialized onto
the runtime via a lock, and every error is returned as clean JSON (never a
stack-trace 500).

## Start a server

```python
from nyora.server import NyoraServer

server = NyoraServer()           # 127.0.0.1, ephemeral port, writes port file
base_url = server.start()        # background daemon thread, returns immediately
print("serving at", base_url)    # e.g. http://127.0.0.1:53124
# ...
server.stop()
```

### Constructor

```python
NyoraServer(
    host="127.0.0.1",
    port=0,
    *,
    runtime=None,
    write_port_file=True,
    timeout=60.0,
)
```

- `host` — interface to bind (defaults to loopback).
- `port` — port to bind, or `0` to pick a free ephemeral port.
- `runtime` — an existing `ParserRuntime` to serve. When `None`, the server
  creates and owns one (and closes it on `stop()`).
- `write_port_file` — when `True`, the bound port is written to the standard
  helper port file so other apps and the SDK can discover this server.
- `timeout` — per-call runtime timeout in seconds for an owned runtime.

### Methods

- `start() -> str` — start serving in a background daemon thread and return the
  base URL. Idempotent: calling it again while running returns the existing URL.
- `serve_forever() -> None` — serve in the **calling** thread until interrupted
  (e.g. `KeyboardInterrupt`), then stop and clean up. Use this for a blocking
  foreground server.
- `stop() -> None` — shut down, close the socket, join the thread, and close an
  owned runtime. Safe to call when not running.
- `base_url` (property) — the `http://host:port` the server is bound to. Raises
  `nyora.NyoraError` if the server has not been started.

## Port-file discovery

When `write_port_file=True`, the server writes its bound port to the standard
helper port file. The path is platform-specific (resolved by
`nyora.config.default_port_file`):

| Platform | Default port-file path |
| --- | --- |
| macOS | `~/Library/Application Support/Nyora/helper.port` |
| Windows | `%APPDATA%\Nyora\helper.port` |
| Linux | `$XDG_CONFIG_HOME/nyora/helper.port` (via `user_config_dir`) |

Override the path with the `NYORA_HELPER_PORT_FILE` environment variable.

A helper client discovers the URL automatically, in this order:

1. An explicit `base_url` argument.
2. The `NYORA_BASE_URL` environment variable.
3. The helper port file above (read as `http://127.0.0.1:<port>`).

So a client started after the server, in another process, attaches with no
configuration.

## REST endpoints

All endpoints are `GET` and return `application/json`. Query parameters are
parsed from the URL. Error responses use `{"error": "<message>"}` with a status
of 400 (bad/missing parameter), 404 (unknown source or path), 502 (runtime
failure), or 500 (unexpected error).

| Method | Path | Query params | Success response shape |
| --- | --- | --- | --- |
| GET | `/health` | — | `{"ok": true, "engine": "python-quickjs"}` |
| GET | `/sources` | — | `{"sources": [<source>, ...]}` |
| GET | `/sources/popular` | `id` (required), `page` (int, default 1) | `{"entries": [<manga>, ...], "hasNextPage": bool}` |
| GET | `/sources/latest` | `id` (required), `page` (int, default 1) | `{"entries": [<manga>, ...], "hasNextPage": bool}` |
| GET | `/sources/search` | `id` (required), `q` (required), `page` (int, default 1) | `{"entries": [<manga>, ...], "hasNextPage": bool}` |
| GET | `/manga/details` | `id` (required), `url` (required), `title` (optional) | `{"manga": <manga>, "chapters": [<chapter>, ...]}` |
| GET | `/manga/pages` | `id` (required), `url` (required), `branch` (optional) | `{"pages": [<page>, ...]}` |

Any other path returns `404` with `{"error": "Not found: <path>"}`.

The `<source>`, `<manga>`, `<chapter>`, and `<page>` objects use the camelCase
helper shapes that `nyora.models.Source`, `Manga`, `MangaChapter`, and
`MangaPage` parse via their `from_json` methods. `hasNextPage` is a heuristic:
`true` when the page returned any entries.

```{note}
This embedded server implements the **read/browse** subset of the helper
contract (sources, browse, search, details, pages). The library, downloads,
history, backup, and sync endpoints of the full JVM helper are not served here;
for those, run the real Nyora helper and use `nyora.client.Nyora` against it.
```

## Worked example: serve in one process, attach in another

**Process A — serve the Python parsers:**

```python
# serve.py
from nyora.server import NyoraServer

server = NyoraServer()  # write_port_file=True by default
print("serving at", server.start())
try:
    # keep the process alive
    import threading
    threading.Event().wait()
except KeyboardInterrupt:
    server.stop()
```

Or, to block in the foreground without the manual `Event`:

```python
from nyora.server import NyoraServer

NyoraServer().serve_forever()  # Ctrl-C to stop
```

**Process B — attach with the helper client:**

```python
# attach.py
from nyora import NyoraHelper  # nyora.client.Nyora

# Auto-discovers the URL from the port file written by process A.
with NyoraHelper.attach() as client:
    print(client.health())  # {"ok": True, "engine": "python-quickjs"}

    source = client.sources.find("mangadex")
    page = client.manga.popular(source.id)
    entry = page.entries[0]

    details = client.manga.details(source.id, entry.url)
    chapter = details.chapters[0]
    pages = client.manga.pages(source.id, chapter.url)
    print(len(pages), "pages")
```

### Same-process example

You can also serve and attach in one process — handy for tests:

```python
from nyora.server import NyoraServer
from nyora import NyoraHelper

server = NyoraServer()
base_url = server.start()
try:
    with NyoraHelper.attach(base_url) as client:
        print(client.health())
        print(len(client.sources.list()), "sources")
finally:
    server.stop()
```

## Related

- [Library guide](library.md) — the `nyora.client.Nyora` helper client and its
  services in full.
- [API reference](../reference/api.md) — autodoc for `nyora.server`.
