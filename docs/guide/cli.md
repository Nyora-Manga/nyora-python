# The `nyora-cli` command-line tool

This page is the complete user manual for **`nyora-cli`**, the command-line tool
shipped with the Nyora Python package.

```{important}
**`nyora-cli` and the `nyora` library are separate things.**

- The **library** is what you get with `pip install nyora` and `import nyora` —
  see the [library guide](library.md).
- **`nyora-cli`** is a *console script* that wraps the library for terminal use.

This page documents only the CLI tool.
```

```{admonition} Bare `nyora-cli` launches the TUI
:class: tip

Running **`nyora-cli` with no subcommand launches the interactive terminal
reader (TUI)** — it does not print help and exit. See the [TUI guide](tui.md).
To script Nyora instead, always pass a subcommand
(`sources`, `search`, `popular`, …).
```

## Installation

The CLI is installed with the package. `rich` and `textual` are core
dependencies, so pretty tables and the TUI work out of the box:

```bash
pip install nyora
```

Three equivalent entry points are installed (`nyora`, `nyora-cli`,
`nyora-tui`). `nyora` and `nyora-cli` are the same program (`nyora.cli:main`);
`nyora-tui` launches the TUI directly. This page uses `nyora-cli` throughout.

## Synopsis

```text
nyora-cli [--json] <command> [options]
nyora-cli                       # no command -> launches the TUI
nyora-cli --help                # lists all commands
```

`--json` is a **global** flag and must appear *before* the subcommand:

```bash
nyora-cli --json sources          # correct
nyora-cli sources --json          # WRONG: unknown option to `sources`
```

## Global options

| Option | Effect |
| ------ | ------ |
| `--json` | Emit raw JSON to stdout instead of pretty tables/text. Must come before the subcommand. |
| `-h`, `--help` | Show help and exit. Works on the program and on each subcommand. |

### `-s` / `--source` fuzzy resolution

Every command that targets a source (`search`, `popular`, `latest`, `details`,
`pages`, `download`) takes a required `-s SRC` / `--source SRC`. `SRC` is matched
**case-insensitively** as a substring against each source's `id` **and** `name`,
and the **first** match wins (sources are taken in catalog order). So
`-s mangadex`, `-s MangaDex`, and `-s dex` typically all resolve to the same
source. If nothing matches, the command exits non-zero with
`error: No bundled source matched '<SRC>'`.

To see the exact ids and names available, run `nyora-cli sources`.

---

## `sources` — list or search available sources

List the sources bundled with the parser runtime, optionally filtered.

```text
nyora-cli [--json] sources [--search Q]
```

| Arg / flag | Required | Default | Description |
| ---------- | -------- | ------- | ----------- |
| `--search Q` | no | (none) | Case-insensitive substring filter over each source's `id` and `name`. |

**Example**

```bash
nyora-cli sources --search dex
```

```text
                Sources (1)
┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━┓
┃ id       ┃ name     ┃ lang ┃
┡━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━┩
│ mangadex │ MangaDex │ en   │
└──────────┴──────────┴──────┘
```

**JSON** (`nyora-cli --json sources`) emits an array of full source objects
(`asdict` of each {py:class}`~nyora.models.Source`):

```json
[
  {
    "id": "mangadex",
    "name": "MangaDex",
    "lang": "en",
    "base_url": "https://mangadex.org",
    "engine": "JavaScript",
    "content_type": "Manga",
    "is_installed": true,
    "is_pinned": false,
    "is_nsfw": false,
    "is_obsolete": false,
    "icon_url": "",
    "version": "",
    "notes": "",
    "can_uninstall": false
  }
]
```

---

## `search` — search a source

```text
nyora-cli [--json] search -s SRC [-p PAGE] QUERY
```

| Arg / flag | Required | Default | Description |
| ---------- | -------- | ------- | ----------- |
| `-s`, `--source SRC` | **yes** | — | Source id or fuzzy name (see above). |
| `-p`, `--page PAGE` | no | `1` | One-based page number. |
| `QUERY` | **yes** | — | Free-text search query (positional). |

**Example**

```bash
nyora-cli search -s mangadex "berserk"
```

```text
              Search: berserk (2)
┏━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ # ┃ title      ┃ url                        ┃
┡━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 1 │ Berserk    │ /title/801513ba-a712-...   │
│ 2 │ Berserk... │ /title/15db0fff-95c0-...   │
└───┴────────────┴────────────────────────────┘
```

**JSON** emits a {py:class}`~nyora.models.SearchPage` object:
`{"entries": [...Manga...], "has_next_page": true}`.

---

## `popular` — list popular manga from a source

```text
nyora-cli [--json] popular -s SRC [-p PAGE]
```

| Arg / flag | Required | Default | Description |
| ---------- | -------- | ------- | ----------- |
| `-s`, `--source SRC` | **yes** | — | Source id or fuzzy name. |
| `-p`, `--page PAGE` | no | `1` | One-based page number. |

**Example**

```bash
nyora-cli popular -s mangadex -p 2
```

Output is the same table shape as `search` (titled `Popular (MangaDex)`).
JSON output is a {py:class}`~nyora.models.SearchPage`.

---

## `latest` — list latest manga from a source

```text
nyora-cli [--json] latest -s SRC [-p PAGE]
```

Identical flags and output shape to `popular`, but lists the most recently
updated manga (titled `Latest (<source name>)`).

**Example**

```bash
nyora-cli latest -s mangadex
```

---

## `details` — fetch manga details and chapters

```text
nyora-cli [--json] details -s SRC URL
```

| Arg / flag | Required | Default | Description |
| ---------- | -------- | ------- | ----------- |
| `-s`, `--source SRC` | **yes** | — | Source id or fuzzy name. |
| `URL` | **yes** | — | Manga URL (positional). Source-relative URLs like `/title/...` from a listing are accepted. |

**Example**

```bash
nyora-cli details -s mangadex "/title/801513ba-a712-4b3e-9b3e-..."
```

```text
Berserk
Authors: Kentaro Miura
State: ongoing
Tags: Action, Horror, Drama

A grim, brutal dark-fantasy epic...

                 Chapters (372)
┏━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ # ┃ title        ┃ url                     ┃
┡━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 1 │ Chapter 1    │ /chapter/aaaa-...       │
│ 2 │ Chapter 2    │ /chapter/bbbb-...       │
└───┴──────────────┴─────────────────────────┘
```

**JSON** emits a {py:class}`~nyora.models.MangaDetails` object:
`{"manga": {...Manga...}, "chapters": [...MangaChapter...]}`.

---

## `pages` — fetch chapter page image URLs

Resolve a chapter to its ordered list of image URLs (does **not** download).

```text
nyora-cli [--json] pages -s SRC [--branch BRANCH] CHAPTER_URL
```

| Arg / flag | Required | Default | Description |
| ---------- | -------- | ------- | ----------- |
| `-s`, `--source SRC` | **yes** | — | Source id or fuzzy name. |
| `--branch BRANCH` | no | (none) | Scanlation branch/translation to select, when the source has multiple. |
| `CHAPTER_URL` | **yes** | — | Chapter URL (positional). |

**Example**

```bash
nyora-cli pages -s mangadex "/chapter/aaaa-bbbb-cccc"
```

```text
   1  https://cdn.example.org/data/abc/1.jpg
   2  https://cdn.example.org/data/abc/2.jpg
   3  https://cdn.example.org/data/abc/3.jpg
```

**JSON** emits an array of {py:class}`~nyora.models.MangaPage` objects, each
`{"url": "...", "headers": {...}}`. The `headers` are the request headers the
source requires to fetch each image (e.g. a `Referer`).

---

## `download` — download a chapter as a `.cbz`

Resolve a chapter's pages and pack them into a single **`.cbz`** archive — a
standard *Comic Book ZIP* readable by any comic reader (Tachiyomi/Mihon, CDisplayEx,
YACReader, Komga, etc.). Each page is fetched with a browser `User-Agent`, the
source-required per-page headers, and a `Referer` derived from the image origin
when one is not already supplied. Inside the archive the pages are stored
in-order, named by zero-padded index with an extension inferred from the URL or
the response `Content-Type` (e.g. `001.jpg`, `002.webp`).

```text
nyora-cli [--json] download -s SRC [--branch BRANCH] [-o OUT] CHAPTER_URL
```

| Arg / flag | Required | Default | Description |
| ---------- | -------- | ------- | ----------- |
| `-s`, `--source SRC` | **yes** | — | Source id or fuzzy name. |
| `--branch BRANCH` | no | (none) | Scanlation branch/translation to select. |
| `-o`, `--out OUT` | no | `<chapter>.cbz` in the current directory | Output **path**, not an image folder. If it ends in `.cbz` it is used as the file; otherwise it is treated as a directory that will contain `<chapter-slug>.cbz` (created if missing; `~` is expanded). The chapter slug is derived from the last path segment of `CHAPTER_URL`. |
| `CHAPTER_URL` | **yes** | — | Chapter URL (positional). |

**Example** — write a named archive:

```bash
nyora-cli download -s mangadex -o ./berserk-ch1.cbz "/chapter/aaaa-bbbb-cccc"
```

```text
Saved 3/3 pages to berserk-ch1.cbz
```

**Example** — drop a `<chapter>.cbz` into a directory (the path does **not** end
in `.cbz`, so it is treated as a folder):

```bash
nyora-cli download -s mangadex -o ./comics "/chapter/aaaa-bbbb-cccc"
```

```text
Saved 3/3 pages to comics/aaaa-bbbb-cccc.cbz
```

With no `-o`, the archive is written as `<chapter-slug>.cbz` in the current
directory, where the slug is the last path segment of the chapter URL.

Individual page failures are reported to stderr (`error: page N: ...`) and
skipped; the command still packs the rest. It exits `1` only when **nothing**
was saved (no pages, or every page failed) — in that case no `.cbz` is written.

**JSON** emits the archive path and counts:

```json
{
  "file": "berserk-ch1.cbz",
  "pages": 3,
  "total": 3
}
```

(`pages` is how many were fetched successfully; `total` is the chapter's page
count.)

---

## `batch` — download every chapter of a manga as `.cbz` archives

Fetch a manga's details and download **every** chapter, writing one **`.cbz`**
archive per chapter into the output directory. Each file is named after a
filesystem-safe version of the chapter title (`<safe-chapter-title>.cbz`). A
chapter that yields no pages or fails to download is reported to stderr and
skipped; the batch keeps going.

```text
nyora-cli [--json] batch -s SRC [-o DIR] MANGA_URL
```

| Arg / flag | Required | Default | Description |
| ---------- | -------- | ------- | ----------- |
| `-s`, `--source SRC` | **yes** | — | Source id or fuzzy name. |
| `-o`, `--out DIR` | no | `nyora-batch` | Output **directory** for the per-chapter `.cbz` files (created if missing; `~` is expanded). |
| `MANGA_URL` | **yes** | — | Manga URL (positional). |

**Example**

```bash
nyora-cli batch -s mangadex -o ./berserk "/title/801513ba-a712-..."
```

```text
Fetching manga details...
Found 372 chapters. Saving .cbz archives to berserk...

[1/372] Downloading Chapter 1...
  -> Chapter_1.cbz (18 pages)

[2/372] Downloading Chapter 2...
  -> Chapter_2.cbz (20 pages)

Batch complete. Wrote 372 .cbz archives (7012 pages total).
```

Each `.cbz` is a standard Comic Book ZIP, so the whole output directory drops
straight into any comic reader or library server.

---

## `update` — apply over-the-air parser updates

Fetch the latest OTA parser bundle and source catalog (SHA-256 verified) into
the per-user cache. See [OTA updates](ota.md) for the mechanism.

```text
nyora-cli [--json] update [--force]
```

| Arg / flag | Required | Default | Description |
| ---------- | -------- | ------- | ----------- |
| `--force` | no | off | Re-download and reinstall even when already up to date. |

**Example**

```bash
nyora-cli update
```

```text
Updated to OTA version 42
  bundle:  /Users/you/Library/Caches/nyora/ota/parsers.bundle.js
  sources: /Users/you/Library/Caches/nyora/ota/sources.json
```

When already current it prints
`Already up to date (OTA version 42)`.

**JSON** emits:

```json
{
  "updated": true,
  "version": 42,
  "bundlePath": "/Users/you/Library/Caches/nyora/ota/parsers.bundle.js",
  "sourcesPath": "/Users/you/Library/Caches/nyora/ota/sources.json"
}
```

---

## `serve` — run the REST helper-compatible server

Start {py:class}`~nyora.server.NyoraServer`, a stdlib HTTP server exposing the
helper-compatible REST API backed by the embedded runtime. It writes the bound
port to the standard helper port file, so other Nyora apps can attach. Runs in
the foreground until `Ctrl+C`.

```text
nyora-cli [--json] serve [--host HOST] [--port PORT]
```

| Arg / flag | Required | Default | Description |
| ---------- | -------- | ------- | ----------- |
| `--host HOST` | no | `127.0.0.1` | Interface to bind. |
| `--port PORT` | no | `0` | Port to bind, or `0` for an ephemeral free port. |

**Example**

```bash
nyora-cli serve --port 8765
```

```text
Nyora server listening at http://127.0.0.1:8765
Press Ctrl+C to stop.
```

**JSON** emits `{"baseUrl": "http://127.0.0.1:8765"}` and then keeps serving.

The REST endpoints (`/health`, `/sources`, `/sources/popular|latest|search`,
`/manga/details`, `/manga/pages`) are documented in the
[server guide](server.md) and the [AI-agent guide](agents.md).

---

## `version` — show package and OTA versions

```text
nyora-cli [--json] version
```

Takes no options.

**Example**

```bash
nyora-cli version
```

```text
nyora 0.3.0
OTA parsers: 42
```

`OTA parsers` shows the installed cache version, or `bundled` when nothing has
been fetched yet (the package's shipped fallback is in use).

**JSON** emits `{"package": "0.3.0", "ota": 42}` (`ota` is `null` when bundled).

---

## Exit codes

| Code | Meaning |
| ---- | ------- |
| `0` | Success. For `download`, at least one page was saved. The bare-`nyora-cli` TUI also returns `0` on a clean exit and when no interactive terminal is attached. |
| `1` | A {py:class}`~nyora.errors.NyoraError` or `LookupError` was raised — e.g. an unresolved `-s/--source`, a parser/network failure, or (for `download`) no pages could be saved. The message is printed to stderr as `error: <message>`. |
| `2` | argparse usage error (unknown command/option, missing required argument). |
| `130` | Interrupted with `Ctrl+C` (`KeyboardInterrupt`). |

---

## Recipes

**Pipe JSON into `jq`.** Remember `--json` goes before the subcommand.

```bash
nyora-cli --json sources | jq -r '.[].id'
```

**Get the first popular title's URL, then its chapter count:**

```bash
url=$(nyora-cli --json popular -s mangadex | jq -r '.entries[0].url')
nyora-cli --json details -s mangadex "$url" | jq '.chapters | length'
```

**Download the first chapter of the top popular manga as a `.cbz`:**

```bash
url=$(nyora-cli --json popular -s mangadex | jq -r '.entries[0].url')
ch=$(nyora-cli --json details -s mangadex "$url" | jq -r '.chapters[0].url')
nyora-cli download -s mangadex -o ./out "$ch"   # writes ./out/<chapter>.cbz
```

**Download a chapter and print just the saved `.cbz` path:**

```bash
nyora-cli --json download -s mangadex "$ch" | jq -r '.file'
```

**Download every chapter of a manga, one `.cbz` each, into a folder:**

```bash
nyora-cli batch -s mangadex -o ./berserk "$url"
```

**List just the page image URLs of a chapter:**

```bash
nyora-cli --json pages -s mangadex "$ch" | jq -r '.[].url'
```

**Keep parsers current before a batch job:**

```bash
nyora-cli update --force && nyora-cli --json sources | jq 'length'
```

**Serve the REST API for another tool to attach to:**

```bash
nyora-cli serve --port 8765 &
curl -s http://127.0.0.1:8765/sources | jq '.sources | length'
```

**Open the interactive reader** (must be a real terminal):

```bash
nyora-cli            # or: nyora-tui
```
