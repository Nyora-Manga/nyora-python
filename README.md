<div align="center">

<img src="https://nyora.pages.dev/icon.png" width="120" alt="Nyora" />

# Nyora — Python

### Read like the world can wait.

The official Python SDK for **Nyora** — a thin cloud client that scripts your
library, browses **~960 manga sources**, and fetches chapters and pages straight
from Python. `pip install`, create a client, and you're scripting manga in 60
seconds.

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <a href="https://pypi.org/project/nyora/"><img alt="PyPI version" src="https://img.shields.io/pypi/v/nyora?style=for-the-badge&logo=pypi&logoColor=white" /></a>
  <a href="https://pypi.org/project/nyora/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/nyora?style=for-the-badge&logo=python&logoColor=white" /></a>
  <a href="https://www.apache.org/licenses/LICENSE-2.0"><img alt="License: Apache 2.0" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=for-the-badge" /></a>
</p>

</div>

---

## What it is

`nyora` is a **thin cloud client** for the Nyora manga engine. It talks to the
public **Nyora cloud helper** at `https://api.hasanraza.tech` — the
kotatsu-parsers JVM engine with **~960 sources** — over a small typed REST API.
There is nothing to compile and no parser engine, JVM, Node.js, or bundle on your
machine: a bare `Nyora()` points at the cloud by default, so you get the full
catalog the moment you install.

This one install gives you three surfaces:

- a **Python library** you `import nyora` to script from your own code,
- the **`nyora-cli`** command (one-shot subcommands + JSON output),
- a **terminal reader (TUI)**, plus **Nyora Cloud Sync** for a signed-in library.

```bash
pip install nyora
```

📖 Full documentation: **[nyora.pages.dev/docs/python](https://nyora.pages.dev/docs/python/)**

---

## Quickstart

```python
from nyora import Nyora

with Nyora() as client:                       # defaults to the Nyora cloud
    source = client.sources.find("mangadex")  # resolve by id or fuzzy name
    page = client.manga.popular(source.id)    # SearchPage of entries
    entry = page.entries[0]

    details = client.manga.details(source.id, entry.url)
    pages = client.manga.pages(source.id, details.chapters[0].url)

    for p in pages:
        print(p.url)                           # page image URLs
```

The client exposes two typed namespaces:

- **`client.sources`** — `list()` the loaded sources, `catalog()` the full
  ~960-source catalog, or `find(query)` by **id** or fuzzy **name**.
- **`client.manga`** — `popular(...)`, `latest(...)`, `search(...)`,
  `details(...)`, and `pages(...)`.

### List and search sources

```python
from nyora import Nyora

with Nyora() as client:
    for src in client.sources.catalog()[:10]:
        print(src.id, src.name, src.lang)

    src = client.sources.find("asura")
    results = client.manga.search(src.id, "Solo Leveling")
    print(results.entries[0].title)
```

### Browse popular / latest

```python
with Nyora() as client:
    src = client.sources.find("mangadex").id

    popular = client.manga.popular(src, page=1)
    latest = client.manga.latest(src, page=1)

    for entry in popular.entries[:5]:
        print(entry.title, "—", entry.url)
```

### Details and pages

```python
with Nyora() as client:
    src = client.sources.find("mangadex").id
    entry = client.manga.popular(src).entries[0]

    details = client.manga.details(src, entry.url)   # metadata + full chapter list
    print(details.manga.title, "-", len(details.chapters), "chapters")

    pages = client.manga.pages(src, details.chapters[0].url)  # branch=... optional
    print([p.url for p in pages])
```

### Async fan-out

`AsyncNyora` mirrors the read API for concurrent requests across many sources:

```python
import asyncio
from nyora import AsyncNyora

async def main():
    async with AsyncNyora() as client:
        payload = await client.get("/sources")
        print(len(payload.get("sources", [])), "sources")

asyncio.run(main())
```

> Point the client somewhere else with `Nyora(base_url=...)` or the
> `NYORA_BASE_URL` environment variable — otherwise it uses
> `https://api.hasanraza.tech`.

---

## Cloud Sync

`NyoraSync` is Nyora's account + library sync. It signs in against the sync
server `https://stream.hasanraza.tech` (OAuth2 password grant + rotating JWT),
then does last-write-wins `upsert`/`select` over your per-user tables
(`nyora_manga`, `nyora_favourite`, `nyora_history`, `nyora_bookmark`, …). **One
account is shared across the iOS app, the TUI, and the SDKs** — favourite a manga
anywhere and it shows up everywhere.

```python
from nyora.sync import NyoraSync

sync = NyoraSync()                          # -> https://stream.hasanraza.tech

sync.register("me@example.com", "hunter2")  # or sync.sign_in(...) if you have an account
sync.sign_in("me@example.com", "hunter2")

# Push favourites (last-write-wins upsert)
sync.upsert("nyora_favourite", [
    {"manga_id": "abc123", "source": "mangadex", "title": "Solo Leveling"},
])

# Pull them back (optionally only rows changed after an ISO timestamp)
rows = sync.select("nyora_favourite")
print(rows)

sync.sign_out()
```

- **Methods:** `register`, `sign_in`, `sign_out`, `upsert(table, rows)`,
  `select(table, since=None)`, plus the `is_signed_in` property.
- **Tokens persist** to `~/.config/nyora/sync.json` (respects `XDG_CONFIG_HOME`),
  so a session survives restarts. `sign_out()` deletes them.
- Access tokens auto-refresh on a `401` using the stored refresh token.

---

## Command line (`nyora-cli`)

Installing the package adds the **`nyora-cli`** command (aliased as `nyora`).

> **Running bare `nyora-cli` launches the terminal reader (TUI).** Pass a
> subcommand for a one-shot command instead.

```bash
nyora-cli                              # no subcommand -> launches the TUI
nyora-cli --help                       # list all commands and options
nyora-cli sources --search asura
nyora-cli search  -s asura "Solo Leveling"
```

| Command | Description |
|---|---|
| `sources [--search Q]` | List the source catalog, or fuzzy-filter by name |
| `search -s SRC [-p PAGE] QUERY` | Search a source |
| `popular -s SRC [-p PAGE]` | Browse a source's popular titles |
| `latest -s SRC [-p PAGE]` | Browse a source's latest updates |
| `details -s SRC URL` | Fetch manga details and the full chapter list |
| `pages -s SRC CHAPTER_URL [--branch B]` | Resolve page image URLs |
| `download -s SRC CHAPTER_URL [-o OUT]` | Download one chapter as a `.cbz` archive |
| `batch -s SRC MANGA_URL [-o DIR]` | Download every chapter, one `.cbz` each, into `DIR` |
| `version` | Print the package version |

`-s/--source` accepts a source **id** or a fuzzy **name**. Add the global
`--json` flag to any subcommand to emit raw JSON for piping into `jq`:

```bash
nyora-cli --json popular -s mangadex -p 1 | jq '.entries[].title'
```

---

## Terminal reader (TUI)

Run bare `nyora-cli` (or `nyora-tui`) to open the terminal reader: pick a source,
browse popular/latest/search, open a title, and page through a chapter — without
leaving the shell. It is non-TTY safe (prints a notice and exits cleanly when not
interactive).

The TUI is also the front-end for **Cloud Sync**:

- Type **`sync`** at the source filter to open the account menu (sign in /
  register / sign out).
- Type **`lib`** to browse your synced library.
- When signed in, a manga's details show a **"Favourite to library?"** prompt —
  favourites sync to your cloud account.

```bash
nyora-cli        # launches the TUI
nyora-tui        # also launches the TUI
```

---

## Installation

```bash
pip install nyora
```

Requires **Python 3.10+** and a network connection (all catalog/parsing work
happens on the Nyora cloud helper). Prefer isolation? Use a virtualenv or
[`pipx install nyora`](https://pipx.pypa.io/).

| Install | Command | Adds |
|---|---|---|
| Default | `pip install nyora` | Library + `nyora-cli` + TUI + Cloud Sync |
| Docs | `pip install "nyora[docs]"` | Sphinx + Furo to build the docs |
| Dev | `pip install "nyora[dev]"` | Build, test, lint, publish tooling |

---

## Also from Nyora

Nyora is a complete manga ecosystem — native apps for Android/iOS/macOS/Windows/
Linux/Web, a JavaScript SDK (`npm install nyora-sdk`), and drop-in extensions:
**[nyora-mihon](https://github.com/Hasan72341/nyora-mihon)** brings the whole
catalog to stock Mihon and **[nyora-aidoku](https://github.com/Hasan72341/nyora-aidoku)**
brings it to stock Aidoku on iOS — no app modification required.

---

## Privacy & license

No ads, no tracking, no telemetry. `nyora` is fully auditable, Apache-2.0
open-source code. Developed and maintained by **Md Hasan Raza** —
[GitHub](https://github.com/Hasan72341).

> Nyora is not affiliated with any of the manga sources it can access.
