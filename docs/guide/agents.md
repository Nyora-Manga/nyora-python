# Using Nyora from an AI agent or programmatically

This page is written for **LLM-driven agents** and automation that need to drive
Nyora directly. Every example is copy-pasteable and matches the real API. If you
are an agent reading this: prefer the **library** ({py:class}`nyora.Nyora`) for
direct calls from your own process, and the **`nyora-cli --json`** path when you
can only shell out. Both are covered below.

## Minimal import surface

Almost everything you need is one import:

```python
from nyora import Nyora
```

`Nyora` is a thin, typed HTTP client over the **Nyora cloud**
(`https://api.hasanraza.tech`). It needs **no** local server and **no** Node
process — a bare `Nyora()` connects to the cloud. Override the target with
`Nyora(base_url=...)` or the `NYORA_BASE_URL` environment variable.

Other useful re-exports from the top-level `nyora` package:

| Import | What it is |
| ------ | ---------- |
| `from nyora import Nyora` | The default cloud client. |
| `from nyora import AsyncNyora` | The async read client. |
| `from nyora import NyoraSync` | Cloud account + library sync (OAuth2/JWT). |
| `from nyora import NyoraError` | Base SDK exception. |
| `from nyora import CLOUD_BASE_URL` | The default cloud base URL string. |
| `from nyora.models import Manga, MangaChapter, MangaPage, Source, SearchPage, MangaDetails` | Typed result dataclasses (all have `from_json`). |

The client is a context manager — always close it (use `with`) so the HTTP
connection is released.

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

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


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

    # 3. Full metadata + chapter list.
    details = client.manga.details(source.id, first.url)
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
  straight back into `details()` / `pages()` — the cloud resolves them.
- `details()` takes `(source_id, manga_url, *, manga_id=None)`; the URL alone is
  usually enough.
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
| `batch` | prints human-readable progress (no JSON payload). |
| `version` | `{"package": str}`. |

```{tip}
For shell scripting, pipe into `jq`. Note `--json` must precede the subcommand:
`nyora-cli --json sources | jq -r '.[].id'`.
```

## Syncing a user's library

To read or write a signed-in user's library, use {py:class}`nyora.sync.NyoraSync`
(OAuth2 password grant + JWT against `https://stream.hasanraza.tech`). Tokens
persist to `~/.config/nyora/sync.json`, so a process stays signed in across runs.

```python
from nyora.sync import NyoraSync

sync = NyoraSync()
if not sync.is_signed_in:
    sync.sign_in("me@example.com", "hunter2")

# Push last-write-wins rows and pull them back.
sync.upsert("nyora_favourite", [{"manga_id": "abc", "sort_key": 0}])
favourites = sync.select("nyora_favourite")               # list[dict]
history = sync.select("nyora_history", since="2026-01-01T00:00:00Z")
```

The tables are `nyora_manga`, `nyora_favourite`, `nyora_history`, and
`nyora_bookmark`. See the [sync guide](sync.md) for the full API and row shapes.

## Error handling

All SDK failures derive from {py:class}`nyora.errors.NyoraError`. The most
common cases:

```python
from nyora import Nyora, NyoraError, NyoraHTTPError

with Nyora() as client:
    try:
        source = client.sources.find("does-not-exist")
    except LookupError as exc:
        # .sources.find raises LookupError when nothing matches the query.
        print("no such source:", exc)

    try:
        page = client.manga.popular("mangadex")
    except NyoraHTTPError as exc:
        # The cloud returned a 4xx/5xx.
        print("HTTP", exc.status_code, exc.body)
    except NyoraError as exc:
        print("Nyora error:", exc)
```

Guidance for agents:

- `client.sources.find(query)` raises **`LookupError`** if no source matches —
  catch it and fall back (e.g. call `client.sources.list()` and pick).
- Cloud failures raise **`NyoraHTTPError`** (a `NyoraError`) with `.status_code`
  and `.body`.
- {py:class}`nyora.sync.NotSignedInError` is raised if you call `upsert`/`select`
  before signing in.
- The CLI maps `NyoraError`/`LookupError` to exit code `1` (message on stderr),
  argparse usage errors to `2`, and `Ctrl+C` to `130`.

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
| Manga details + chapters | `client.manga.details(sid, url)` | `nyora-cli --json details -s SRC URL` |
| Chapter page URLs | `client.manga.pages(sid, url, branch=None)` | `nyora-cli --json pages -s SRC CHAPTER_URL` |
| Download a chapter as a `.cbz` | (loop over `pages`, fetch with `page.headers`, zip them) | `nyora-cli download -s SRC -o OUT CHAPTER_URL` |
| Download every chapter as `.cbz` | (loop over `details.chapters` + `pages`) | `nyora-cli batch -s SRC -o DIR MANGA_URL` |
| Sign in to sync | `NyoraSync().sign_in(email, pw)` | — |
| Push/pull library rows | `sync.upsert(table, rows)` / `sync.select(table)` | — |
| Package version | `importlib.metadata.version("nyora")` | `nyora-cli --json version` |

Where `sid` is a resolved source id (e.g. `client.sources.find("dex").id`) and
`SRC` is any fuzzy id/name the CLI resolves the same way.
