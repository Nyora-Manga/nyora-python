# Cloud sync guide

Nyora Cloud Sync lets a signed-in user keep their library — favourites, reading
history, and bookmarks — in sync across devices. It is exposed through a single
client, {py:class}`nyora.sync.NyoraSync`, which is independent of the browsing
{py:class}`nyora.Nyora` client.

```{note}
Sync is **optional**. Browsing, searching, and reading work anonymously through
`nyora.Nyora`. You only need `NyoraSync` to store or retrieve a user's library.
```

## How it works

`NyoraSync` talks to the Nyora **sync server** at
[`https://sync.nyora.xyz`](https://sync.nyora.xyz) using an
**OAuth2 password grant** for sign-in and a **JWT** bearer token for every
request thereafter. On top of that it offers a generic, **last-write-wins**
`upsert`/`select` over a small set of per-user tables. When an access token
expires, the client transparently refreshes it with the stored refresh token and
retries the request once.

Access and refresh tokens are held in memory and, unless disabled, persisted to
disk so a process (or the terminal reader) stays signed in across runs.

## Import and construct

```python
from nyora import NyoraSync          # or: from nyora.sync import NyoraSync

sync = NyoraSync()
```

`NyoraSync(base_url=None, *, timeout=30.0, token_path=None)`:

- `base_url` — the sync server URL. Defaults to
  `https://sync.nyora.xyz`, or the `NYORA_SYNC_URL` environment variable
  when set.
- `timeout` — per-request HTTP timeout in seconds.
- `token_path` — where to persist tokens. `None` (the default) uses the standard
  user config path (see [Token persistence](#token-persistence)). Pass an
  explicit path to override it, or an empty string to disable persistence
  entirely (tokens then live only in memory).

`NyoraSync` is a context manager; use `with` (or call `close()`) to release the
underlying HTTP connection:

```python
with NyoraSync() as sync:
    ...
```

## Accounts

### Sign in

```python
sync = NyoraSync()
sync.sign_in("me@example.com", "hunter2")
print(sync.is_signed_in)   # True
print(sync.email)          # "me@example.com"
```

`sign_in(email, password)` performs the OAuth2 password grant and stores (and
persists) the returned tokens.

### Register

```python
sync.register("new@example.com", "hunter2")
```

`register(email, password)` creates a new account and signs it in. The server
may have registration disabled, in which case the request raises.

### Sign out

```python
sync.sign_out()
```

`sign_out()` forgets the in-memory tokens **and** deletes the persisted token
file, so the next process starts signed out.

### State

- `sync.is_signed_in -> bool` — whether an access token is currently held.
- `sync.email -> str | None` — the signed-in account's email, or `None`.

## Reading and writing library data

Two generic methods move rows to and from the server. Both require an active
session and raise {py:class}`nyora.sync.NotSignedInError` otherwise.

### `upsert(table, rows) -> int`

Last-write-wins upsert of `rows` (a list of dicts) into `table`. Returns the
number of rows written. An empty `rows` list is a no-op that returns `0`.

```python
written = sync.upsert(
    "nyora_favourite",
    [{"manga_id": "abc", "sort_key": 0, "updated_at": "2026-07-05T12:00:00Z"}],
)
```

Deletes are modeled as tombstones — upsert a row carrying a `deleted_at`
timestamp rather than removing it, so the delete propagates by last-write-wins.

### `select(table, since=None) -> list[dict]`

Fetch rows from `table`. Pass an ISO-8601 `since` timestamp to receive only rows
changed after that instant (an incremental pull); omit it for a full fetch.

```python
all_favs = sync.select("nyora_favourite")
recent = sync.select("nyora_history", since="2026-07-01T00:00:00Z")
```

## Tables

Sync operates over these per-user tables:

| Table | Holds |
| ----- | ----- |
| `nyora_manga` | Manga metadata (title, cover, authors, source reference, …). |
| `nyora_favourite` | Favourited manga, referencing `nyora_manga` by id. |
| `nyora_history` | Reading-history records (progress per chapter). |
| `nyora_bookmark` | Page bookmarks within chapters. |

A typical "favourite this manga" operation writes one row to `nyora_manga`
(the metadata) and one to `nyora_favourite` (the favourite link):

```python
from datetime import datetime, timezone

now = datetime.now(timezone.utc).isoformat()

sync.upsert("nyora_manga", [{
    "id": "abc",
    "title": "Berserk",
    "url": "abc",
    "source_ref": '{"source": "mangadex"}',
    "updated_at": now,
}])
sync.upsert("nyora_favourite", [{
    "manga_id": "abc",
    "sort_key": 0,
    "added_at": now,
    "updated_at": now,
}])
```

To pull the library back, `select` the favourites and join them against the
manga metadata:

```python
favourites = [f for f in sync.select("nyora_favourite") if not f.get("deleted_at")]
manga = {m["id"]: m for m in sync.select("nyora_manga")}
for fav in favourites:
    meta = manga.get(fav["manga_id"], {})
    print(meta.get("title"), meta.get("source_ref"))
```

(The terminal reader does exactly this for its `lib` view — see the
[TUI guide](tui.md).)

## Token persistence

Unless disabled, tokens are written to a JSON file so sign-in survives across
runs. The default location is:

```text
$XDG_CONFIG_HOME/nyora/sync.json      # when XDG_CONFIG_HOME is set
~/.config/nyora/sync.json             # otherwise
```

The file stores the `access_token`, `refresh_token`, and `email`. It is created
on sign-in and deleted on sign-out. To keep tokens in memory only, construct the
client with an empty `token_path`:

```python
sync = NyoraSync(token_path="")   # no file is read or written
```

## Errors

- {py:class}`nyora.sync.NotSignedInError` — a `RuntimeError` raised when
  `upsert`, `select`, or a token refresh is attempted without a valid session.
  Call `sign_in()` first.
- Network and HTTP failures surface as `httpx` errors
  (`httpx.HTTPStatusError` for non-2xx responses); a failed sign-in raises rather
  than silently leaving you signed out.

```python
from nyora import NyoraSync
from nyora.sync import NotSignedInError

sync = NyoraSync()
try:
    rows = sync.select("nyora_favourite")
except NotSignedInError:
    sync.sign_in("me@example.com", "hunter2")
    rows = sync.select("nyora_favourite")
```

## See also

- [TUI guide](tui.md) — the reader's built-in `sync` account menu, `lib` library
  view, and "Favourite to library?" prompt.
- [API reference](../reference/api.md) — full autodoc of `nyora.sync`.
