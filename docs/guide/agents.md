# Using Nyora from an AI agent or programmatically

This page is written for **LLM-driven agents** and automation that need to drive
Nyora directly. Every example is copy-pasteable and matches the real API. If you
are an agent reading this: prefer the **library** ({py:class}`nyora.direct.Nyora`)
for in-process work, and the **`nyora-cli --json`** path when you can only shell
out. Both are covered below.

## Minimal import surface

Almost everything you need is one import:

```python
from nyora import Nyora
```

`Nyora` is {py:class}`nyora.direct.Nyora` — a self-contained client backed by an
embedded JavaScript parser runtime. It needs **no** external helper, **no** Node,
and **no** JVM. HTTP and HTML parsing are handled in-process.

Other useful re-exports from the top-level `nyora` package:

| Import | What it is |
| ------ | ---------- |
| `from nyora import Nyora` | The default in-process client. |
| `from nyora import NyoraServer` | REST server exposing the helper-compatible API. |
| `from nyora import NyoraError` | Base SDK exception. |
| `from nyora.models import Manga, MangaChapter, MangaPage, Source, SearchPage, MangaDetails` | Typed result dataclasses (all have `from_json`). |
| `from nyora.runtime import BROWSER_UA` | A browser `User-Agent` string for downloading page images. |
| `from nyora.ota import OtaManager, OtaUpdateResult` | Over-the-air parser updates. |

The client is a context manager — always close it (use `with`) so the runtime is
released.

## End-to-end: search → details → pages → download bytes

A complete, typed flow that finds a source, searches it, opens the first result,
resolves the first chapter's pages, and downloads the page images with the
**correct per-page headers**. This is the canonical agent recipe.

```python
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import httpx

from nyora import Nyora
from nyora.models import MangaPage
from nyora.runtime import BROWSER_UA


def page_headers(page: MangaPage) -> dict[str, str]:
    """Build request headers for a page image.

    Sources may require a ``Referer`` and other headers; they are carried on
    ``page.headers``. We start from a browser UA, merge the source's headers,
    and synthesize a ``Referer`` from the image origin when none is given.
    """
    headers: dict[str, str] = {"User-Agent": BROWSER_UA}
    headers.update({str(k): str(v) for k, v in page.headers.items()})
    if "Referer" not in headers:
        parsed = urlparse(page.url)
        if parsed.scheme and parsed.netloc:
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
    return headers


with Nyora() as client:
    # 1. Resolve a source (fuzzy: matches id or name, case-insensitive).
    source = client.sources.find("mangadex")          # -> Source

    # 2. Search (page is 1-based). Use .popular()/.latest() for browsing.
    results = client.manga.search(source.id, "berserk", page=1)   # -> SearchPage
    first = results.entries[0]                         # -> Manga

    # 3. Full metadata + chapter list. Pass the known title to help the parser.
    details = client.manga.details(source.id, first.url, title=first.title)
    chapter = details.chapters[0]                      # -> MangaChapter

    # 4. Resolve the chapter's image pages (no download yet).
    pages = client.manga.pages(source.id, chapter.url, branch=chapter.branch)

    # 5. Download the image bytes with the right headers.
    out = Path("download")
    out.mkdir(exist_ok=True)
    width = len(str(len(pages)))
    with httpx.Client(follow_redirects=True, timeout=60.0) as http:
        for i, page in enumerate(pages, start=1):
            resp = http.get(page.url, headers=page_headers(page))
            resp.raise_for_status()
            (out / f"{i:0{width}d}.jpg").write_bytes(resp.content)
    print(f"Saved {len(pages)} pages to {out}")
```

Key facts an agent should rely on:

- `page` arguments are **1-based**.
- `SearchPage` has `.entries: list[Manga]` and `.has_next_page: bool`.
- `MangaDetails` has `.manga: Manga` and `.chapters: list[MangaChapter]`.
- Listing/details URLs may be **source-relative** (e.g. `/title/...`); pass them
  straight back into `details()` / `pages()` — the runtime resolves them.
- Each `MangaPage` carries `.url` and `.headers`; **use those headers** when
  downloading, or you may get 403s.
- `chapter.branch` selects a scanlation/translation; pass it through to
  `pages()` (it may be `None`).

## Driving `nyora-cli --json` and parsing it

When you can only shell out, every read command supports `--json` (global flag,
**before** the subcommand). Output goes to stdout; errors go to stderr with a
non-zero exit code.

```python
import json
import subprocess


def cli_json(*args: str):
    """Run `nyora-cli --json <args>` and return the parsed JSON."""
    proc = subprocess.run(
        ["nyora-cli", "--json", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


sources = cli_json("sources")                              # list[dict]
popular = cli_json("popular", "-s", "mangadex")            # {"entries": [...], "has_next_page": ...}
first_url = popular["entries"][0]["url"]
details = cli_json("details", "-s", "mangadex", first_url) # {"manga": {...}, "chapters": [...]}
chapter_url = details["chapters"][0]["url"]
pages = cli_json("pages", "-s", "mangadex", chapter_url)   # [{"url": ..., "headers": {...}}, ...]

# Download the chapter to a .cbz and read back where it went.
saved = cli_json("download", "-s", "mangadex", chapter_url) # {"file": ..., "pages": int, "total": int}
print(saved["file"], f"({saved['pages']}/{saved['total']} pages)")
```

JSON shapes by command:

| Command | JSON shape |
| ------- | ---------- |
| `sources` | array of `Source` objects (snake_case fields). |
| `search` / `popular` / `latest` | `SearchPage`: `{"entries": [Manga...], "has_next_page": bool}`. |
| `details` | `MangaDetails`: `{"manga": Manga, "chapters": [MangaChapter...]}`. |
| `pages` | array of `MangaPage`: `[{"url": str, "headers": {...}}]`. |
| `download` | `{"file": str, "pages": int, "total": int}` — the saved `.cbz` path plus the fetched/total page counts. |
| `update` | `{"updated": bool, "version": int, "bundlePath": str, "sourcesPath": str}`. |
| `version` | `{"package": str, "ota": int | null}`. |
| `serve` | `{"baseUrl": str}` (then keeps serving). |

```{tip}
For shell scripting, pipe into `jq`. Note `--json` must precede the subcommand:
`nyora-cli --json sources | jq -r '.[].id'`.
```

## Starting `NyoraServer` and calling the REST API

For multi-process setups (or to let another tool attach), run the embedded REST
server. It speaks the helper-compatible contract and writes its port to the
standard helper port file on start.

```python
import httpx

from nyora import NyoraServer

server = NyoraServer(host="127.0.0.1", port=0)  # port 0 -> ephemeral free port
base_url = server.start()                       # non-blocking; returns the URL
try:
    with httpx.Client(base_url=base_url) as http:
        assert http.get("/health").json() == {"ok": True, "engine": "python-quickjs"}

        sources = http.get("/sources").json()["sources"]
        sid = sources[0]["id"]

        popular = http.get("/sources/popular", params={"id": sid, "page": 1}).json()
        manga_url = popular["entries"][0]["url"]

        details = http.get(
            "/manga/details", params={"id": sid, "url": manga_url}
        ).json()
        chapter_url = details["chapters"][0]["url"]

        pages = http.get(
            "/manga/pages", params={"id": sid, "url": chapter_url}
        ).json()["pages"]
finally:
    server.stop()
```

REST endpoints (all `GET`, all JSON):

| Endpoint | Query params | Response |
| -------- | ------------ | -------- |
| `/health` | — | `{"ok": true, "engine": "python-quickjs"}` |
| `/sources` | — | `{"sources": [Source...]}` (camelCase source shape) |
| `/sources/popular` | `id`, `page` (default 1) | `{"entries": [...], "hasNextPage": bool}` |
| `/sources/latest` | `id`, `page` | `{"entries": [...], "hasNextPage": bool}` |
| `/sources/search` | `id`, `q`, `page` | `{"entries": [...], "hasNextPage": bool}` |
| `/manga/details` | `id`, `url`, `title` (optional) | `{"manga": {...}, "chapters": [...]}` |
| `/manga/pages` | `id`, `url`, `branch` (optional) | `{"pages": [...]}` |

Status codes: `400` missing/invalid query param, `404` unknown source or path,
`502` runtime/parser error, `500` unexpected error. Errors are always returned
as clean JSON: `{"error": "..."}`. You can also start the server from the shell
with `nyora-cli serve --port 8765`.

## Error handling

All SDK failures derive from {py:class}`nyora.errors.NyoraError`. The most
common cases:

```python
from nyora import Nyora, NyoraError

with Nyora() as client:
    try:
        source = client.sources.find("does-not-exist")
    except LookupError as exc:
        # .sources.find raises LookupError when nothing matches the query.
        print("no such source:", exc)

    try:
        page = client.manga.popular("mangadex")
    except NyoraError as exc:
        # Parser/runtime failures surface as NyoraError (subclass
        # ParserRuntimeError). Network hiccups in the runtime are tolerant and
        # usually yield empty results rather than raising.
        print("runtime error:", exc)
```

Guidance for agents:

- `client.sources.find(query)` raises **`LookupError`** if no source matches —
  catch it and fall back (e.g. call `client.sources.list()` and pick).
- Parser/runtime errors raise **`NyoraError`** (specifically
  `nyora.runtime.ParserRuntimeError`). The runtime is *tolerant*: transient
  network errors typically produce empty `entries`/`pages` rather than
  exceptions, so check for empty results too.
- The CLI maps `NyoraError`/`LookupError` to exit code `1` (message on stderr),
  argparse usage errors to `2`, and `Ctrl+C` to `130`.
- The REST server never returns a stack-trace `500`; it returns
  `{"error": "..."}` with an appropriate status.

## OTA updates

Keep the parser bundle and source catalog current (SHA-256 verified, cached
per-user, with an offline bundled fallback) without upgrading the package.

```python
from nyora import Nyora

with Nyora() as client:
    available, installed, latest = client.check_update()  # (bool, int|None, int|None)
    if available:
        result = client.update()        # downloads + reloads the runtime
        print("updated:", result.updated, "version:", result.version)
        print("bundle:", result.bundle_path)
        print("sources:", result.sources_path)
```

- `client.check_update()` is safe to call opportunistically — network/manifest
  errors are reported as "no update available", never raised.
- `client.update(force=True)` re-downloads and reloads even when already current.
- {py:class}`~nyora.ota.OtaUpdateResult` fields: `updated`, `version`,
  `bundle_path`, `sources_path`.
- Equivalent CLI: `nyora-cli update [--force]` (machine output via
  `nyora-cli --json update`).

## Cheat sheet — intent → SDK call → CLI command

Assume `client = Nyora()` (use it as a context manager). All `page` args are
1-based.

| Intent | SDK call | CLI command |
| ------ | -------- | ----------- |
| List all sources | `client.sources.list()` | `nyora-cli --json sources` |
| Find a source (fuzzy) | `client.sources.find("dex")` | `nyora-cli sources --search dex` |
| Popular manga | `client.manga.popular(sid, page=1)` | `nyora-cli --json popular -s SRC -p 1` |
| Latest manga | `client.manga.latest(sid, page=1)` | `nyora-cli --json latest -s SRC -p 1` |
| Search | `client.manga.search(sid, "q", page=1)` | `nyora-cli --json search -s SRC "q"` |
| Manga details + chapters | `client.manga.details(sid, url, title="...")` | `nyora-cli --json details -s SRC URL` |
| Chapter page URLs | `client.manga.pages(sid, url, branch=None)` | `nyora-cli --json pages -s SRC CHAPTER_URL` |
| Download a chapter as a `.cbz` | (loop over `pages`, fetch with `page.headers`, zip them) | `nyora-cli download -s SRC -o OUT CHAPTER_URL` |
| Download every chapter as `.cbz` | (loop over `details.chapters` + `pages`) | `nyora-cli batch -s SRC -o DIR MANGA_URL` |
| Check for OTA update | `client.check_update()` | — |
| Apply OTA update | `client.update(force=False)` | `nyora-cli --json update [--force]` |
| Run the REST server | `NyoraServer().start()` | `nyora-cli serve --host H --port P` |
| Package + OTA version | `OtaManager().installed_version()` | `nyora-cli --json version` |

Where `sid` is a resolved source id (e.g. `client.sources.find("dex").id`) and
`SRC` is any fuzzy id/name the CLI resolves the same way.
