# Quickstart

This page gets you from `pip install` to reading manga pages with the **Nyora
library** in a few minutes. Everything here uses the importable `nyora` package
(`import nyora`).

```{note}
The library (`pip install nyora`, `import nyora`) and the `nyora-cli` terminal
tool are **separate**. This page documents the library. For the command-line
tool and its terminal UI, see the CLI docs.
```

## Install

Nyora requires **Python 3.10 or newer**.

```bash
pip install nyora
```

That is all you need. The default client **bundles the Nyora parser engine and
launches it locally**, so there is **nothing else to run** — no server and no
Node process (a JRE is auto-downloaded if you have no Java). HTTP is handled by
`httpx`, which is pulled in automatically.

## The default client: `nyora.Nyora`

`nyora.Nyora` is the default client. A bare `Nyora()` auto-launches a bundled
local engine, so it just works. Use it as a context manager so the HTTP
connection (and the managed engine) are released cleanly:

```python
from nyora import Nyora

with Nyora() as client:
    ...
```

`client` exposes several service objects; the two you need to browse and read
are:

- `client.sources` — list and find sources.
- `client.manga` — browse popular/latest, search, fetch details and pages.

```{tip}
`Nyora()` resolves its base URL in order: an explicit `base_url` argument, the
`NYORA_BASE_URL` environment variable, the saved `nyora config set-url`, a
running local helper's port file, and finally a **bundled engine it launches
itself**. Pass `Nyora(base_url=...)` to point at a server.
```

## List sources

```python
from nyora import Nyora

with Nyora() as client:
    for source in client.sources.list():
        print(source.id, "|", source.name, "|", source.lang)
```

Each item is a [`nyora.models.Source`](reference/api.md) dataclass. Find a
single source by a case-insensitive id or name substring:

```python
with Nyora() as client:
    source = client.sources.find("mangadex")
    print(source.id, source.name, source.base_url)
```

`find` raises `LookupError` if nothing matches.

## Browse and search

`popular`, `latest`, and `search` all return a
[`nyora.models.SearchPage`](reference/api.md) whose `.entries` is a list of
`nyora.models.Manga`.

```python
with Nyora() as client:
    source = client.sources.find("mangadex")

    popular = client.manga.popular(source.id, page=1)
    for manga in popular.entries:
        print(manga.title, "->", manga.url)

    results = client.manga.search(source.id, "berserk")
    print("matches:", len(results.entries))
    print("more pages?", results.has_next_page)
```

## Fetch details and chapters

`details` returns a [`nyora.models.MangaDetails`](reference/api.md) with the
`.manga` metadata and its `.chapters`:

```python
with Nyora() as client:
    source = client.sources.find("mangadex")
    entry = client.manga.popular(source.id).entries[0]

    details = client.manga.details(source.id, entry.url)
    print(details.manga.title)
    print("chapters:", len(details.chapters))

    first_chapter = details.chapters[0]
    print(first_chapter.number, first_chapter.title, first_chapter.url)
```

`details` also accepts an optional `manga_id=` keyword to disambiguate an entry
when the source needs it.

## Resolve the pages of a chapter

`pages` returns a list of [`nyora.models.MangaPage`](reference/api.md). Each
page has a `.url` and the `.headers` you must send when fetching the image
(some sources require a `Referer`):

```python
import httpx
from nyora import Nyora

with Nyora() as client:
    source = client.sources.find("mangadex")
    entry = client.manga.popular(source.id).entries[0]
    details = client.manga.details(source.id, entry.url)
    chapter = details.chapters[0]

    pages = client.manga.pages(source.id, chapter.url)
    for page in pages:
        print(page.url, page.headers)

    # Download the first page using its required headers.
    first = pages[0]
    image = httpx.get(first.url, headers=first.headers).content
    print("first page bytes:", len(image))
```

## Sync your library (optional)

Signed-in users can push and pull their library — favourites, history, and
bookmarks — across devices with {py:class}`nyora.sync.NyoraSync`:

```python
from nyora.sync import NyoraSync

sync = NyoraSync()
sync.sign_in("me@example.com", "hunter2")   # tokens persist to ~/.config/nyora/sync.json
sync.upsert("nyora_favourite", [{"manga_id": "...", "sort_key": 0}])
favourites = sync.select("nyora_favourite")
```

See the [sync guide](guide/sync.md) for tables, token persistence, and the full
API.

## Error handling

Every SDK-specific failure derives from `nyora.NyoraError`:

```python
from nyora import Nyora, NyoraError

try:
    with Nyora() as client:
        page = client.manga.popular("does-not-exist")
except NyoraError as exc:
    print("Nyora failed:", exc)
```

`client.sources.find(...)` raises the standard library `LookupError` when no
source matches.

## Next steps

- [Library guide](guide/library.md) — every method, return types, and the model
  dataclasses.
- [Sync guide](guide/sync.md) — cloud account and library sync in depth.
- [CLI guide](guide/cli.md) — the `nyora-cli` command-line tool.
- [API reference](reference/api.md) — full autodoc of every public symbol.
