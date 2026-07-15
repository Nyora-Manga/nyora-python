<div align="center">

<a href="https://nyora.xyz"><img src="https://nyora.xyz/icon.png" width="128" height="128" alt="Nyora logo" /></a>

# Nyora — the manga reader SDK for Python

### Build your own manga, manhwa & manhua reader in ~10 lines.

**`nyora`** is the official Python SDK for [Nyora](https://nyora.xyz) — a
self-contained client that gives you **390 live, health-checked sources across 40 languages**
through one typed API: search, browse, read chapters, download `.cbz`, and sync a
library across devices. `pip install nyora` bundles the parser engine and launches it
locally on demand (auto-downloads a JRE if you don't have Java) — no server, no scraper
to maintain. You're reading in 60 seconds.

<p>
  <a href="https://pypi.org/project/nyora/"><img alt="PyPI version" src="https://img.shields.io/pypi/v/nyora?style=for-the-badge&logo=pypi&logoColor=white" /></a>
  <a href="https://pypi.org/project/nyora/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/nyora?style=for-the-badge&logo=python&logoColor=white" /></a>
  <a href="https://www.apache.org/licenses/LICENSE-2.0"><img alt="License: Apache 2.0" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=for-the-badge" /></a>
</p>

</div>

> **In one line:** Nyora is the programmatic, cross-platform **Tachiyomi / Mihon /
> Kotatsu alternative** — a manga API and reader SDK you can `import`. If you're
> building a manga reader, a scanlation bot, a downloader, or a library manager in
> Python, this is the fastest way to get **hundreds of working sources** without
> writing or maintaining a single scraper.

---

## Table of contents

- [Why Nyora](#why-nyora)
- [Install](#install)
- [Quickstart — a working reader in 10 lines](#quickstart)
- [Core concepts](#core-concepts)
- [API reference](#api-reference)
- [Recipes](#recipes)
- [Chapter ordering (ascending vs descending sources)](#chapter-ordering)
- [Cloud sync — a library across devices](#cloud-sync)
- [Command line (`nyora-cli`)](#command-line)
- [Interactive terminal reader (TUI)](#terminal-reader)
- [How it works](#how-it-works)
- [FAQ](#faq)
- [Ecosystem](#ecosystem)

---

## Why Nyora

| | |
|---|---|
| 📚 **390 working sources** | Every source is live health-checked; 570 dead or Cloudflare-walled ones are auto-hidden, so `list()`/`catalog()` return only sources that actually work — **390 across 40 languages** (289 all-ages, 101 mature). |
| 🌐 **One typed API** | `Source`, `Manga`, `MangaChapter`, `MangaPage`, `MangaDetails` dataclasses. Full type hints, `py.typed`, mypy-clean. |
| 📦 **Self-contained** | Bundles the [kotatsu-parsers](https://github.com/KotatsuApp/kotatsu-parsers) engine and runs it locally (auto-downloads a JRE if you have no Java). Parsed results, not scraping headaches — nothing to compile, no Node, no server. |
| 🔀 **Correct chapter order** | Built-in `next_chapter()` / `previous_chapter()` work on both ascending (MangaDex `0→N`) and descending (scanlation `N→0`) sources — no off-by-one "next goes backwards" bug. |
| 🧰 **Batteries included** | A CLI, an interactive terminal reader (TUI), a `.cbz` downloader, and cross-device cloud sync — all in one `pip install`. |
| ⚡ **Sync & async** | Use `Nyora` or `AsyncNyora` with identical APIs. |

<a name="install"></a>
## Install

```bash
pip install nyora           # everything: the library, the CLI, and the terminal reader (TUI)
```

Requires Python 3.10+. Nothing else to run — the parser engine is **bundled** and
launches locally on demand (a JRE is auto-downloaded if you have no Java). One
install ships all three front-ends: `import nyora` (library), `nyora-cli`
(CLI), and bare `nyora` (TUI).

<a name="quickstart"></a>
## Quickstart — a working reader in 10 lines

```python
import nyora

with nyora.Nyora() as client:
    source = client.sources.find("mangadex")           # pick any of 390 sources
    hits = client.manga.search(source.id, "frieren")   # search it
    manga = hits.entries[0]

    details = client.manga.details(source.id, manga.url, title=manga.title)
    first = details.reading_order()[0]                 # earliest chapter, order-safe

    for page in client.manga.pages(source.id, first.url, branch=first.branch):
        print(page.url)                                # image URLs, ready to render
```

That's a complete read path: **source → search → details → chapter → page images.**
Point an image widget (Pillow, a GUI, a web frontend) at those URLs and you have a reader.

<a name="core-concepts"></a>
## Core concepts

A source exposes manga; a manga has chapters; a chapter has pages. Every step is one call.

```
Nyora ─┬─ sources   → Source        (a content site: MangaDex, Bato, …)
       ├─ manga     → Manga          (a series: title, cover, authors, tags)
       │             → MangaDetails  (Manga + its MangaChapter list)
       │             → MangaChapter  (id, title, number, url, branch, uploadDate)
       │             → MangaPage      (a single image url)
       ├─ library   → favourites, history, bookmarks (local or synced)
       └─ downloads → offline chapter management
```

Everything is a plain dataclass — `dataclasses.asdict()` to serialise, full type hints throughout.

<a name="api-reference"></a>
## API reference

### Client

```python
nyora.Nyora(base_url=None, *, timeout=60.0)      # sync client (context manager)
nyora.AsyncNyora(base_url=None, *, timeout=60.0) # async client, identical API with await
```

`base_url` defaults to a bundled engine launched locally; pass a URL (or run `nyora config set-url`) to use a server instead. Attributes:
`client.sources`, `client.manga`, `client.library`, `client.downloads`. Also `client.health()`.

### `client.sources`

| Method | Returns | Description |
|---|---|---|
| `list()` | `list[Source]` | Installed/loaded sources (dead ones hidden). |
| `catalog()` | `list[Source]` | Every available source (dead ones hidden). |
| `find(query)` | `Source` | First source whose id or name matches (case-insensitive). |
| `filters(source_id)` | `list[SourceFilter]` | A source's supported search filters. |
| `refresh()` / `install(id)` / `uninstall(id)` / `pin(id)` | — | Manage the loaded set. |

### `client.manga`

| Method | Returns | Description |
|---|---|---|
| `popular(source_id, page=1)` | `SearchPage` | Popular titles from a source. |
| `latest(source_id, page=1)` | `SearchPage` | Recently updated titles. |
| `search(source_id, query, page=1)` | `SearchPage` | Search one source. |
| `global_search(query, *, limit_per_source=8)` | `list[GlobalSearchGroup]` | Search many sources at once. |
| `details(source_id, url, *, title=None)` | `MangaDetails` | Full metadata **+ chapter list**. |
| `pages(source_id, chapter_url, *, branch=None)` | `list[MangaPage]` | A chapter's image pages. |
| `suggestions()` / `alternatives(title)` | `list[Manga]` / `list[dict]` | Recommendations / cross-source matches. |

`SearchPage` has `.entries: list[Manga]` and `.has_next_page: bool` for pagination.

### Chapter ordering helpers

```python
nyora.next_chapter(chapters, current)       # -> MangaChapter | None
nyora.previous_chapter(chapters, current)   # -> MangaChapter | None
nyora.reading_order(chapters)               # -> list, earliest-first
nyora.chapter_reading_delta(chapters)       # -> +1 (ascending) or -1 (descending)
# convenience methods on MangaDetails:
details.next_chapter(chapter)  /  details.previous_chapter(chapter)  /  details.reading_order()
```

### `client.library` (local, syncable)

`history()`, `record_history(...)`, `favourites()`, `toggle_favourite(id)`, `is_favourite(id)`,
`bookmarks()`, `add_bookmark(...)`, `remove_bookmark(...)`.

<a name="recipes"></a>
## Recipes

**Browse popular with pagination**

```python
page = client.manga.popular(source.id, page=1)
while True:
    for m in page.entries:
        print(m.title)
    if not page.has_next_page:
        break
    page = client.manga.popular(source.id, page=page.number + 1)
```

**Search every source at once**

```python
for group in client.manga.global_search("solo leveling"):
    print(group.source.name, "→", [m.title for m in group.entries])
```

**Download a chapter as a `.cbz`**

```python
from nyora.cli import _download_pages
from pathlib import Path

pages = client.manga.pages(source.id, chapter.url, branch=chapter.branch)
_download_pages(pages, Path("solo-leveling-ch1"))
```

**Async**

```python
import asyncio, nyora

async def main():
    async with nyora.AsyncNyora() as client:
        src = await client.sources.find("mangadex")
        page = await client.manga.popular(src.id)
        print([m.title for m in page.entries])

asyncio.run(main())
```

<a name="chapter-ordering"></a>
## Chapter ordering (ascending vs descending sources)

Different sources return chapters in different orders — MangaDex lists oldest-first
(`0 → N`), many scanlation sites list newest-first (`N → 0`). A naive `chapters[i+1]`
"next chapter" therefore goes **backwards** on half of all sources. Nyora detects the
direction from the chapter numbers so navigation is always correct:

```python
current = details.chapters[3]
nxt = details.next_chapter(current)      # always the LATER chapter, any source order
prv = details.previous_chapter(current)  # always the EARLIER chapter
```

<a name="cloud-sync"></a>
## Cloud sync — a library across devices

```python
from nyora.sync import NyoraSync

sync = NyoraSync()
sync.sign_in("you@example.com", "password")   # or register(...)
sync.upsert("nyora_favourite", [{ "manga_id": manga.url, "sort_key": 0 }])
favs = sync.select("nyora_favourite")          # syncs across every Nyora app
```

Same account and library as the Nyora apps on Android, iOS, macOS, Windows, Linux and web.

<a name="command-line"></a>
## Command line (`nyora-cli`)

```bash
nyora-cli sources --search mangadex        # list/filter sources
nyora-cli popular  -s MANGADEX             # popular titles
nyora-cli search   -s MANGADEX "frieren"   # search
nyora-cli details  -s MANGADEX <manga-url> # metadata + chapters
nyora-cli pages    -s MANGADEX <chap-url>  # page image URLs
nyora-cli download -s MANGADEX <chap-url>  # save a .cbz
nyora-cli --json popular -s MANGADEX       # machine-readable output
```

Both `nyora` and `nyora-cli` are installed. Add `--json` to any command for scripting.

<a name="terminal-reader"></a>
## Interactive terminal reader (TUI)

```bash
pip install "nyora[tui]"
nyora            # launch the full-screen reader — browse, search, read, download
```

Pick a source → search or browse → open a chapter → page through it, with
order-independent **next / previous chapter** navigation and inline downloads.

<a name="how-it-works"></a>
## How it works

`nyora` is **self-contained**. `pip install nyora` bundles the kotatsu-parsers JVM
engine (and auto-downloads a JRE if you don't have Java); `Nyora()` launches it locally
on demand — no server, no Node.js, nothing to compile. Dead and Cloudflare-blocked
sources are hidden (a sensible static list by default; run `nyora blocklist refresh` to
health-probe *your* engine and tailor it), so `list()`/`catalog()` return only the
**~390 sources that actually work**. Prefer a server? Point `base_url` (or
`nyora config set-url`) at any Nyora helper.

<a name="faq"></a>
## FAQ

**How do I build a manga reader in Python?**
`pip install nyora`, then `search → details → pages` (see [Quickstart](#quickstart)).
`client.manga.pages(...)` returns image URLs you can render in any UI.

**What's the best manga API / SDK?**
Nyora gives you 390 working, health-checked sources across 40 languages behind one typed
Python API — no scraper maintenance, plus a CLI, TUI, downloader and cloud sync.

**Is this a Tachiyomi / Mihon / Kotatsu alternative?**
Yes — it's the *programmatic* one. Those are Android apps; Nyora is an importable SDK
(and cross-platform apps) built on the same open-source Kotatsu parser engine.

**Do I need to run a server or a JVM?**
No. The engine is hosted. `pip install` and go. You *can* self-host and set `base_url`.

**Manga, manhwa or manhua?** All three — the sources cover Japanese, Korean and Chinese
comics across 40 languages.

**JavaScript / TypeScript?** Use the sibling SDK: [`nyora-sdk`](https://www.npmjs.com/package/nyora-sdk).

<a name="ecosystem"></a>
## Ecosystem

- **JS/TS SDK** — [`nyora-sdk`](https://www.npmjs.com/package/nyora-sdk) (`npm i nyora-sdk`)
- **Apps** — Android, iOS/iPadOS, macOS, Windows, Linux and a web app: <https://nyora.xyz>
- **Docs** — <https://nyora.xyz/docs/python/>
- **Source** — <https://github.com/Nyora-Manga/nyora-python>

## License

Apache-2.0. Nyora is built on the open-source Kotatsu parser engine and is not affiliated
with Tachiyomi, Mihon or Kotatsu.
