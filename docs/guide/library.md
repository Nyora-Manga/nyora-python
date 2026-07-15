# Library / SDK guide

This is the complete guide to the **Nyora library** (`pip install nyora`,
`import nyora`). It covers the client, its async counterpart, every service
method with its signature and return type, context-manager usage, error
handling, and the model dataclasses. Cloud account and library sync live in a
separate client, {py:class}`nyora.sync.NyoraSync`, documented in the
[sync guide](sync.md).

```{note}
The library and the `nyora-cli` terminal tool are **separate**. This guide is
about the importable `nyora` package only.
```

## Clients at a glance

| Client | Import | Backend | Use when |
| --- | --- | --- | --- |
| `nyora.Nyora` | `from nyora import Nyora` | bundled local engine, or REST to any server (default) | **Default.** Browse, search, read, and — against a full helper deployment — manage library, downloads, history, and backup. |
| `nyora.AsyncNyora` | `from nyora import AsyncNyora` | Async REST to the same endpoint | You need `async`/`await` read access. |
| `nyora.NyoraSync` | `from nyora import NyoraSync` | OAuth2/JWT to the Nyora **sync** server | You want to sync a user's favourites, history, and bookmarks. See the [sync guide](sync.md). |

`nyora.NyoraHelper` is a backwards-compatible alias of `nyora.Nyora`; new code
should use `Nyora`.

---

## The client: `nyora.Nyora`

```python
from nyora import Nyora

with Nyora() as client:
    for source in client.sources.list():
        print(source.id, source.name)
```

`Nyora` is a self-contained, typed client. By default a bare `Nyora()` launches a
bundled local engine (via `nyora-extension-server`), so it just works with nothing
else running. Point it at a server with `base_url=...` or `nyora config set-url`.

### Construction and discovery

- `Nyora(base_url=None, *, timeout=60.0, helper=None)` — connect. When
  `base_url` is `None`, the URL is resolved in order: the `NYORA_BASE_URL`
  environment variable, a running local helper's port file, then the public
  cloud. `timeout` is the per-request HTTP timeout in seconds.
- `Nyora.attach(base_url=None, *, timeout=60.0)` — classmethod alias for
  attaching to an already-running endpoint (explicit or auto-discovered).
- `Nyora.managed(jar_path=None, *, java="java", timeout=60.0, launch_timeout=20.0)`
  — classmethod that launches a local helper process from a `.jar` (path or the
  `NYORA_HELPER_JAR` environment variable) with `java` and binds a client to the
  managed process. The process is owned and stopped on `close()`. Most users
  never need this — it is for running a private helper instead of the cloud.

### Context-manager usage

The client holds an `httpx` connection. Use it as a context manager so the
connection (and any managed helper) is released on exit:

```python
with Nyora() as client:
    sources = client.sources.list()
# connection closed here
```

Equivalently, call `client.close()` yourself:

```python
client = Nyora()
try:
    sources = client.sources.list()
finally:
    client.close()
```

### Low-level HTTP and health

- `health() -> dict[str, Any]` — the endpoint's `/health` payload.
- `get(path, *, params=None) -> Any` — raw GET; returns parsed JSON or text.
- `post(path, *, params=None, json=None, content=None) -> Any` — raw POST.
- `delete(path, *, params=None) -> Any` — raw DELETE.

All raise `nyora.NyoraHTTPError` on a 4xx/5xx response.

### Service objects

The client attaches six services. Methods that return model objects reference
[`nyora.models`](#model-dataclasses); methods documented as returning
`dict`/`list` return the raw payload.

#### `client.sources` — `SourcesService`

| Method | Returns |
| --- | --- |
| `list()` | `list[Source]` — installed sources |
| `catalog()` | `list[Source]` — every catalog source |
| `refresh()` | `list[Source]` — after refreshing from the feed |
| `install(source_id)` | `Source \| dict` |
| `uninstall(source_id)` | `dict` |
| `pin(source_id)` | `dict` |
| `filters(source_id)` | `list[SourceFilter]` |
| `find(query)` | `Source` (raises `LookupError`) |

`find(query)` returns the first source whose id **or** name contains `query`
(case-insensitive), and raises `LookupError` if none match.

#### `client.manga` — `MangaService`

| Method | Returns |
| --- | --- |
| `popular(source_id, page=1)` | `SearchPage` |
| `latest(source_id, page=1)` | `SearchPage` |
| `search(source_id, query, page=1, *, filters=None)` | `SearchPage` |
| `global_search(query, *, limit_per_source=8)` | `list[GlobalSearchGroup]` |
| `details(source_id, manga_url, *, manga_id=None)` | `MangaDetails` |
| `pages(source_id, chapter_url, *, branch=None)` | `list[MangaPage]` |
| `alternatives(title)` | `list[dict]` |
| `suggestions()` | `list[Manga]` |
| `prefs(manga_id)` | `MangaPrefs` |
| `save_prefs(manga_id, *, reader_mode="", brightness=0.0, contrast=1.0, saturation=1.0, hue=0.0, palette="")` | `dict` |
| `clear_prefs(manga_id)` | `dict` |

`details` takes an optional `manga_id=` to disambiguate an entry when the source
needs it; the manga URL alone is usually enough. `pages` takes an optional
`branch=` to select a scanlation branch/translation.

```python
with Nyora() as client:
    source = client.sources.find("mangadex")
    results = client.manga.search(source.id, "berserk", page=1)
    details = client.manga.details(source.id, results.entries[0].url)
    pages = client.manga.pages(source.id, details.chapters[0].url)
    for page in pages:
        print(page.url, page.headers)
```

#### `client.library` — `LibraryService`

| Method | Returns |
| --- | --- |
| `history(limit=100)` | `list[HistoryEntry]` |
| `record_history(*, manga_id, chapter_id, page, percent)` | `dict` |
| `remove_history(manga_id, chapter_id=None)` | `dict` |
| `clear_history()` | `dict` |
| `favourites(category_id=None)` | `list[Manga]` |
| `toggle_favourite(manga_id)` | `dict` |
| `is_favourite(manga_id)` | `bool` |
| `bookmarks(manga_id=None)` | `list[dict]` |
| `add_bookmark(*, manga_id, chapter_id, page, title="")` | `dict` |
| `remove_bookmark(*, manga_id, chapter_id, page)` | `dict` |
| `categories()` | `list[Category]` |
| `create_category(title)` | `Category \| dict` |
| `rename_category(category_id, title)` | `dict` |
| `delete_category(category_id)` | `dict` |
| `add_to_category(manga_id, category_id)` | `dict` |
| `remove_from_category(manga_id, category_id)` | `dict` |
| `updates()` | `list[dict]` |
| `refresh_updates()` | `dict` |
| `mark_update_seen(update_id)` | `dict` |

#### `client.downloads` — `DownloadsService`

| Method | Returns |
| --- | --- |
| `list()` | `list[Download]` |
| `start(*, source_id, manga_url, chapter_url, manga_title="", chapter_title="")` | `Download` |
| `enqueue(*, source_id, manga_url, chapters, manga_title="")` | `list[Download]` |
| `cancel(download_id)` | `dict` |
| `settings()` | `DownloadSettings` |
| `save_settings(*, max_concurrent=None, format=None)` | `DownloadSettings` |

#### `client.backup` — `BackupService`

| Method | Returns |
| --- | --- |
| `export()` | backup payload (`Any`) |
| `import_(backup_json)` | `BackupImportResult` |

#### `client.system` — `SystemService`

Composes two sub-services: `client.system.local` and `client.system.tracker`.

| Method | Returns |
| --- | --- |
| `stats()` | `Stats` |
| `network_settings()` | `dict` |
| `save_network_settings(**settings)` | `dict` |
| `ota_status()` | `dict` |
| `ota_check()` | `dict` |
| `local.scan(folder)` | `list[dict]` |
| `local.chapter(cbz)` | `dict` |
| `tracker.anilist_search(query)` | `dict` |
| `tracker.anilist_scrobble(*, token, media_id, progress)` | `dict` |

```{note}
Cloud account and library sync are **not** on `client.system`. They live in the
standalone {py:class}`nyora.sync.NyoraSync` client (OAuth2/JWT against the Nyora
sync server). See the [sync guide](sync.md).
```

```{note}
The full set of library, downloads, backup, and tracker features requires a
deployment that implements those endpoints. Browse, search, details, and pages
work against the default public cloud.
```

---

## `nyora.AsyncNyora`

A lightweight async client for read-style requests:

```python
from nyora import AsyncNyora

async def main():
    async with AsyncNyora.attach() as client:
        payload = await client.get("/sources")
        health = await client.health()
```

It exposes `attach`, `get(path, *, params=None)`, `health()`, and `close()`, and
resolves its base URL the same way as the synchronous client (falling back to the
cloud).

---

## Error handling

The exception hierarchy lives in `nyora.errors` and is re-exported from the
top-level package. All SDK errors derive from `NyoraError`, so catching it
catches everything.

| Exception | Raised when |
| --- | --- |
| `NyoraError` | Base class for all SDK failures. |
| `HelperNotFoundError` | No endpoint could be discovered for a managed/attached client. |
| `HelperLaunchError` | A managed helper process failed to start. |
| `NyoraHTTPError` | The endpoint returned a 4xx/5xx. Has `.status_code` and `.body`. |

```python
from nyora import Nyora, NyoraError, NyoraHTTPError

try:
    with Nyora() as client:
        page = client.manga.popular("mangadex")
except NyoraHTTPError as exc:
    print("HTTP", exc.status_code, exc.body)
except NyoraError as exc:
    print("Nyora error:", exc)
```

`sources.find(...)` raises the standard library `LookupError` (not a
`NyoraError`) when nothing matches. The sync client raises
{py:class}`nyora.sync.NotSignedInError` (a `RuntimeError`) when a sync operation
is attempted before signing in — see the [sync guide](sync.md).

---

## Model dataclasses

All models live in `nyora.models` and are slotted dataclasses with a tolerant
`from_json` classmethod that coerces raw camelCase payloads defensively — missing
or malformed fields fall back to sensible defaults rather than raising. Fields
below use the Python (snake_case) names.

### `Source`

A content source (site). Fields: `id`, `name`, `lang`, `base_url`, `engine`,
`content_type`, `is_installed`, `is_pinned`, `is_nsfw`, `is_obsolete`,
`icon_url`, `version`, `notes`, `can_uninstall`.

### `SourceFilter`

A search filter advertised by a source. Fields: `name`, `type_name`, `values`.

### `Manga`

A manga entry as returned in listings and details. Fields: `id`, `title`,
`alt_titles`, `url`, `public_url`, `rating` (`-1.0` when unknown), `is_nsfw`,
`content_rating`, `cover_url`, `large_cover_url`, `state`, `authors`, `source`,
`source_id`, `description`, `tags`, `chapters`, `unread`, `progress`.

### `MangaChapter`

A chapter belonging to a manga. Fields: `id`, `title`, `number` (may be
fractional), `volume`, `url`, `scanlator`, `upload_date` (epoch ms), `branch`,
`pages`, `index`.

### `MangaPage`

A readable image page. Fields: `url`, `headers` (request headers required to
fetch the image, e.g. `Referer`). `MangaPage.from_json` also accepts a bare
string URL.

### `SearchPage`

One page of results. Fields: `entries` (a `list[Manga]`), `has_next_page`.

### `MangaDetails`

Full metadata plus chapters. Fields: `manga` (a `Manga`), `chapters`
(a `list[MangaChapter]`).

### Library and system models

These appear in responses from library, downloads, and system endpoints:

- `HistoryEntry` — `manga`, `chapter_id`, `page`, `percent`, `updated_at`.
- `Category` — `id`, `title`, `manga_count`.
- `Download` — `id`, `source_id`, `manga_title`, `chapter_title`, `chapter_url`,
  `status`, `total_pages`, `completed_pages`, `failed_pages`, `file_path`,
  `error`.
- `DownloadSettings` — `max_concurrent_downloads`, `format`.
- `MangaPrefs` — `manga_id`, `reader_mode`, `brightness`, `contrast`,
  `saturation`, `hue`, `palette`, `present`.
- `GlobalSearchGroup` — `source_id`, `source_name`, `entries`, `error`.
- `Stats` — `total_chapters`, `distinct_manga`, `favourites_count`,
  `longest_streak_days`, `top_sources`.
- `BackupImportResult` — `ok`, `imported_favourites`, `imported_history`.

See the [API reference](../reference/api.md) for the full autodoc, including
every field default and `from_json` behavior.
