# Library / SDK guide

This is the complete guide to the **Nyora library** (`pip install nyora`,
`import nyora`). It covers the two client paths, every service method with its
signature and return type, context-manager usage, error handling, and the model
dataclasses.

```{note}
The library and the `nyora-cli` terminal tool are **separate**. This guide is
about the importable `nyora` package only.
```

## Two client paths

Nyora ships two distinct clients. Pick based on whether you want an in-process
runtime or want to talk to an external Nyora helper.

| Client | Import | Backend | Use when |
| --- | --- | --- | --- |
| `nyora.Nyora` (a.k.a. `nyora.direct.Nyora`) | `from nyora import Nyora` | Embedded QuickJS parser runtime, in-process | **Default.** You want a self-contained SDK with no external process. |
| `nyora.NyoraHelper` (a.k.a. `nyora.client.Nyora`) | `from nyora import NyoraHelper` | REST over HTTP to a running Nyora helper | You already have a Nyora app/helper running and want its full library, downloads, history, and sync features. |
| `nyora.AsyncNyora` | `from nyora import AsyncNyora` | Async REST to a running helper | You need `async`/`await` read access to a helper. |

The direct client and the helper client expose **different** capabilities. The
direct client is read-and-browse over the bundled parsers; the helper client
adds the user's library, downloads, history, backup, and cloud sync (because
those live in the helper, not in the parsers).

---

## The default client: `nyora.direct.Nyora`

```python
from nyora import Nyora

client = Nyora(timeout=60.0)
```

`Nyora(*, timeout=60.0)` constructs the client and its embedded
`nyora.runtime.ParserRuntime`. `timeout` is the per-call runtime timeout in
seconds.

### Context-manager usage

The embedded runtime holds resources (the QuickJS context). Always close it.
The context manager is the idiomatic way:

```python
with Nyora() as client:
    sources = client.sources.list()
# runtime is closed here
```

Equivalently, call `client.close()` yourself:

```python
client = Nyora()
try:
    sources = client.sources.list()
finally:
    client.close()
```

### Attributes

- `client.ota` — the `nyora.ota.OtaManager` backing over-the-air updates.
- `client.sources` — a `DirectSourcesService`.
- `client.manga` — a `DirectMangaService`.

### Top-level methods

#### `update(*, force=False) -> OtaUpdateResult`

Fetch the latest OTA parser bundle, then reload the embedded runtime so new
parsers are live in the same process. Pass `force=True` to re-download even when
already current. Returns an `nyora.ota.OtaUpdateResult`.

```python
with Nyora() as client:
    result = client.update()
    print(result.updated, result.version, result.bundle_path)
```

#### `check_update() -> tuple[bool, int | None, int | None]`

Check whether a newer bundle is available **without** applying it. Returns
`(available, installed_version, latest_version)`; versions are `None` when
unknown.

```python
with Nyora() as client:
    available, installed, latest = client.check_update()
```

#### `Nyora.helper(base_url=None, *, timeout=60.0) -> nyora.client.Nyora`

Classmethod. Attach to an already-running external helper and return a
`nyora.client.Nyora` REST client (see the "The helper client" section
below). `base_url` is auto-discovered from `NYORA_BASE_URL` or the helper port
file when `None`.

```python
helper = Nyora.helper()
print(helper.health())
helper.close()
```

#### `Nyora.managed_helper(jar_path, *, timeout=60.0, launch_timeout=20.0) -> nyora.client.Nyora`

Classmethod. Launch a JVM helper from `jar_path` and return a
`nyora.client.Nyora` client bound to the managed process. The process is stopped
when the client is closed.

#### `close() -> None`

Close the embedded runtime and release its resources. Called automatically on
context-manager exit.

### `client.sources` — `DirectSourcesService`

Operates over the **bundled** source catalog (no network needed to list).

#### `list() -> list[Source]`

List every bundled source.

```python
with Nyora() as client:
    for source in client.sources.list():
        print(source.id, source.name, source.lang)
```

Returns a list of [`Source`](#source).

#### `find(query: str) -> Source`

Return the first bundled source whose id **or** name contains `query`
(case-insensitive). Raises `LookupError` if none match.

```python
with Nyora() as client:
    source = client.sources.find("mangadex")
```

### `client.manga` — `DirectMangaService`

Drives the parser runtime to browse, search, and read.

#### `popular(source_id: str, page: int = 1) -> SearchPage`

A page of popular manga from a source.

```python
page = client.manga.popular(source.id, page=1)
print(len(page.entries), page.has_next_page)
```

Returns a [`SearchPage`](#searchpage).

#### `latest(source_id: str, page: int = 1) -> SearchPage`

A page of the latest-updated manga. Same shape as `popular`.

#### `search(source_id: str, query: str, page: int = 1) -> SearchPage`

Search a source for `query`.

```python
results = client.manga.search(source.id, "berserk", page=1)
```

Returns a [`SearchPage`](#searchpage).

#### `details(source_id: str, manga_url: str, *, title: str = "") -> MangaDetails`

Full metadata plus the chapter list for one manga. `title` is an optional known
title passed through to help the parser resolve the entry.

```python
details = client.manga.details(source.id, entry.url, title=entry.title)
print(details.manga.title, len(details.chapters))
```

Returns a [`MangaDetails`](#mangadetails).

#### `pages(source_id: str, chapter_url: str, *, branch: str | None = None) -> list[MangaPage]`

Resolve the readable image pages of one chapter. `branch` optionally selects a
scanlation branch/translation.

```python
pages = client.manga.pages(source.id, chapter.url)
for page in pages:
    print(page.url, page.headers)
```

Returns a list of [`MangaPage`](#mangapage).

---

## The helper client: `nyora.client.Nyora`

Use this when an external Nyora helper is running (a Nyora app, the JVM helper,
or an embedded `nyora.server.NyoraServer` — see the [server guide](server.md)).
It speaks the camelCase helper REST contract over HTTP and exposes the **full**
feature set: library, downloads, backup, cloud sync, trackers.

```python
from nyora import NyoraHelper  # this is nyora.client.Nyora

with NyoraHelper.attach() as client:
    for source in client.sources.list():
        print(source.id, source.name)
```

### Construction and discovery

- `NyoraHelper(base_url=None, *, timeout=60.0, helper=None)` — connect. When
  `base_url` is `None`, the URL is discovered from the `NYORA_BASE_URL`
  environment variable, then the helper port file. Raises
  `nyora.HelperNotFoundError` if nothing is found.
- `NyoraHelper.attach(base_url=None, *, timeout=60.0)` — classmethod alias for
  attaching to an already-running helper.
- `NyoraHelper.managed(jar_path=None, *, java="java", timeout=60.0, launch_timeout=20.0)`
  — classmethod that launches a helper jar (path or `NYORA_HELPER_JAR`) and binds
  a client to it. The process is owned and stopped on `close()`.

Use it as a context manager; on exit it closes the HTTP connection and stops any
managed helper.

### Low-level HTTP and health

- `health() -> dict[str, Any]` — the helper's `/health` payload.
- `get(path, *, params=None) -> Any` — raw GET; returns parsed JSON or text.
- `post(path, *, params=None, json=None, content=None) -> Any` — raw POST.
- `delete(path, *, params=None) -> Any` — raw DELETE.

All raise `nyora.NyoraHTTPError` on a 4xx/5xx response.

### Service objects

The helper client attaches six services. Methods that return model objects
reference [`nyora.models`](#model-dataclasses); methods documented as returning
`dict`/`list` return the raw helper payload.

#### `client.sources` — `SourcesService`

| Method | Returns |
| --- | --- |
| `list()` | `list[Source]` — installed sources |
| `catalog()` | `list[Source]` — every catalog source |
| `refresh()` | `list[Source]` — after refreshing from the feed |
| `install(source_id)` | `Source | dict` |
| `uninstall(source_id)` | `dict` |
| `pin(source_id)` | `dict` |
| `filters(source_id)` | `list[SourceFilter]` |
| `find(query)` | `Source` (raises `LookupError`) |

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

Note: on the **helper** client, `details` takes `manga_id` (not `title`), unlike
the direct client's `details`.

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
| `create_category(title)` | `Category | dict` |
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

Composes three sub-services: `client.system.sync`, `client.system.local`,
`client.system.tracker`.

| Method | Returns |
| --- | --- |
| `stats()` | `Stats` |
| `network_settings()` | `dict` |
| `save_network_settings(**settings)` | `dict` |
| `ota_status()` | `dict` |
| `ota_check()` | `dict` |
| `sync.status()` | `dict` |
| `sync.sign_in(id_token)` | `dict` |
| `sync.sign_out()` | `dict` |
| `sync.sync()` | `dict` |
| `sync.restore_from_cloud()` | `dict` |
| `sync.has_local_data()` | `bool` |
| `local.scan(folder)` | `list[dict]` |
| `local.chapter(cbz)` | `dict` |
| `tracker.anilist_search(query)` | `dict` |
| `tracker.anilist_scrobble(*, token, media_id, progress)` | `dict` |

### `nyora.AsyncNyora`

A lightweight async helper client for read-style requests:

```python
from nyora import AsyncNyora

async def main():
    async with AsyncNyora.attach() as client:
        payload = await client.get("/sources")
        health = await client.health()
```

It exposes `attach`, `get(path, *, params=None)`, `health()`, and `close()`.

---

## Error handling

The full exception hierarchy lives in `nyora.errors` and is re-exported from the
top-level package. All SDK errors derive from `NyoraError`, so catching it
catches everything.

| Exception | Raised when |
| --- | --- |
| `NyoraError` | Base class for all SDK failures (also OTA and runtime errors). |
| `HelperNotFoundError` | No running helper could be discovered for a helper client. |
| `HelperLaunchError` | A managed helper process failed to start. |
| `NyoraHTTPError` | The helper returned a 4xx/5xx. Has `.status_code` and `.body`. |

`ParserRuntimeError` (in `nyora.runtime`, also a `NyoraError`) surfaces parser
runtime failures from the direct client.

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
`NyoraError`) when nothing matches.

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

### Helper-only models

These appear in responses from the **helper** client:

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
