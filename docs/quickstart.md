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

That is all you need. The default client embeds the JavaScript parser bundle
inside an in-process QuickJS runtime, so there is **no Node and no JVM helper**
to install. HTTP is handled by `httpx` and HTML parsing by `selectolax`, both
pulled in automatically.

## The default client: `nyora.Nyora`

`nyora.Nyora` (which is `nyora.direct.Nyora`) is the default, self-contained
client. Use it as a context manager so the embedded runtime is closed cleanly:

```python
from nyora import Nyora

with Nyora() as client:
    ...
```

`client` exposes two service objects:

- `client.sources` — list and find the bundled sources.
- `client.manga` — browse popular/latest, search, fetch details and pages.

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

    details = client.manga.details(source.id, entry.url, title=entry.title)
    print(details.manga.title)
    print("chapters:", len(details.chapters))

    first_chapter = details.chapters[0]
    print(first_chapter.number, first_chapter.title, first_chapter.url)
```

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
    details = client.manga.details(source.id, entry.url, title=entry.title)
    chapter = details.chapters[0]

    pages = client.manga.pages(source.id, chapter.url)
    for page in pages:
        print(page.url, page.headers)

    # Download the first page using its required headers.
    first = pages[0]
    image = httpx.get(first.url, headers=first.headers).content
    print("first page bytes:", len(image))
```

## Keep parsers current (OTA)

Parsers and the source catalog are delivered **over the air** so you get new and
fixed sources without a package upgrade. On first run the SDK uses the parser
bundle shipped inside the package, then you can pull the latest:

```python
from nyora import Nyora

with Nyora() as client:
    available, installed, latest = client.check_update()
    if available:
        result = client.update()
        print("updated:", result.updated, "version:", result.version)
```

`client.update()` downloads and verifies the latest bundle, then reloads the
embedded runtime so the new parsers are live in the same process. See the
[OTA guide](guide/ota.md) for cache locations and the offline fallback.

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

- [Library guide](guide/library.md) — every method, return types, the helper
  client, and the model dataclasses.
- [Server guide](guide/server.md) — run the helper-compatible REST server.
- [OTA guide](guide/ota.md) — over-the-air parser updates in depth.
- [API reference](reference/api.md) — full autodoc of every public symbol.
