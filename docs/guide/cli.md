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

A single install ships the **full experience** — Rich colour tables, the
interactive TUI, terminal-image rendering, and shell completion are all core:

```bash
pip install nyora
```

(The `[tui]` and `[completion]` extras still exist as no-op aliases, so older
`pip install "nyora[tui]"` commands keep working.)

Three equivalent entry points are installed (`nyora`, `nyora-cli`,
`nyora-tui`). `nyora` and `nyora-cli` are the same program (`nyora.cli:main`);
`nyora-tui` launches the TUI directly. This page uses `nyora-cli` throughout.

Every subcommand runs against a bundled local engine by default, so there is
nothing else to run. Point at a server with `nyora config set-url` or the
`NYORA_BASE_URL` environment variable.

**Shell completion** is powered by `argcomplete` (bundled). Enable it with:

```bash
nyora-cli completion            # prints the setup line for your shell
```

## Synopsis

```text
nyora-cli [--json] <command> [options]
nyora-cli                       # no command -> launches the TUI
nyora-cli --help                # lists all commands
nyora-cli -V | --version        # print version and exit
```

`--json` is a **global** flag and must appear *before* the subcommand:

```bash
nyora-cli --json sources          # correct
nyora-cli sources --json          # WRONG: unknown option to `sources`
```

The commands are: `sources`, `search`, `popular`, `latest`, `details`, `pages`,
`download`, `open`, `batch`, `config`, `upgrade`, `blocklist`, `completion`,
and `version`.

## Global options

| Option | Effect |
| ------ | ------ |
| `--json` | Emit raw JSON to stdout instead of pretty tables/text. Must come before the subcommand. |
| `-V`, `--version` | Print `nyora <version>` and exit. |
| `-h`, `--help` | Show help and exit. Works on the program and on each subcommand. |

### `-s` / `--source` fuzzy resolution

Every command that targets a source (`search`, `popular`, `latest`, `details`,
`pages`, `download`, `open`, `batch`) takes a required `-s SRC` / `--source SRC`. `SRC`
is matched **case-insensitively** as a substring against each source's `id`
**and** `name`, and the **first** match wins (sources are taken in catalog
order). So `-s mangadex`, `-s MangaDex`, and `-s dex` typically all resolve to
the same source. If nothing matches, the command exits non-zero with
`error: No installed source matched '<SRC>'`.

To see the exact ids and names available, run `nyora-cli sources`.

---

## `sources` — list or search available sources

List the sources available from the engine, optionally filtered.

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
┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━┳━━━┓
┃ id       ┃ name     ┃ lang ┃   ┃
┡━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━╇━━━┩
│ mangadex │ MangaDex │ en   │   │
└──────────┴──────────┴──────┴───┘
```

The last column shows flags: `★` for a pinned source and `18+` for an adult
source.

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
nyora-cli [--json] search -s SRC [-p PAGE] [-n LIMIT | --all] QUERY
```

| Arg / flag | Required | Default | Description |
| ---------- | -------- | ------- | ----------- |
| `-s`, `--source SRC` | **yes** | — | Source id or fuzzy name (see above). |
| `-p`, `--page PAGE` | no | `1` | One-based page number (ignored when `-n`/`--all` is set). |
| `-n`, `--limit N` | no | (off) | Auto-paginate and collect up to **N** results across pages. |
| `--all` | no | (off) | Auto-paginate and collect **every** result across all pages. |
| `QUERY` | **yes** | — | Free-text search query (positional). |

**Example**

```bash
nyora-cli search -s mangadex "berserk"
```

```text
                       Search: berserk (2)
┏━━━┳━━━━━━━━━━━━┳━━━━━━━━┳━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ # ┃ title      ┃ rating ┃   ┃ url                        ┃
┡━━━╇━━━━━━━━━━━━╇━━━━━━━━╇━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 1 │ Berserk    │  4.9★  │   │ /title/801513ba-a712-...   │
│ 2 │ Berserk... │  4.2★  │   │ /title/15db0fff-95c0-...   │
└───┴────────────┴────────┴───┴────────────────────────────┘
```

The `rating` column is a five-star score (`—` when unknown) and the blank column
carries an `18+` marker for adult titles.

**Auto-pagination.** `-n`/`--all` walk multiple pages for you (backed by the
SDK's {py:class}`~nyora.pagers.MangaPager`):

```bash
nyora-cli search -s mangadex "berserk" -n 100   # up to 100 across pages
nyora-cli popular -s mangadex --all             # everything
```

**JSON** emits a {py:class}`~nyora.models.SearchPage` object:
`{"entries": [...Manga...], "has_next_page": true}`. With `-n`/`--all`, all
collected entries are returned in one page with `"has_next_page": false`.

---

## `popular` — list popular manga from a source

```text
nyora-cli [--json] popular -s SRC [-p PAGE] [-n LIMIT | --all]
```

| Arg / flag | Required | Default | Description |
| ---------- | -------- | ------- | ----------- |
| `-s`, `--source SRC` | **yes** | — | Source id or fuzzy name. |
| `-p`, `--page PAGE` | no | `1` | One-based page number. |
| `-n`, `--limit N` | no | (off) | Collect up to N results across pages. |
| `--all` | no | (off) | Collect every result across all pages. |

**Example**

```bash
nyora-cli popular -s mangadex -p 2
nyora-cli popular -s mangadex --limit 50   # auto-paginated
```

Output is the same table shape as `search` (titled `Popular (MangaDex)`).
JSON output is a {py:class}`~nyora.models.SearchPage`.

---

## `latest` — list latest manga from a source

```text
nyora-cli [--json] latest -s SRC [-p PAGE] [-n LIMIT | --all]
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
YACReader, Komga, etc.). Pages are downloaded **concurrently** (with a progress
bar unless `--json`) but written **in reading order**, named by zero-padded index
with an extension inferred from the URL or response `Content-Type` (e.g.
`001.jpg`, `002.webp`). Each page is fetched with a browser `User-Agent`, the
source-required per-page headers, and a `Referer` derived from the image origin.

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

Individual page failures are counted (not saved) and skipped; the command still
packs the rest. It exits `1` only when **nothing** was saved (no pages, or every
page failed) — in that case no `.cbz` is written.

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

## `open` — download a chapter and open it

Like `download`, but after writing the `.cbz` it opens the archive in your OS's
default application (`open` on macOS, `xdg-open` on Linux, the shell association
on Windows). Same flags as `download`; there is no `--json` archive output.

```text
nyora-cli open -s SRC [--branch BRANCH] [-o OUT] CHAPTER_URL
```

```bash
nyora-cli open -s mangadex "/chapter/aaaa-bbbb-cccc"
```

---

## `batch` — download every chapter of a manga as `.cbz` archives

Fetch a manga's details and download **every** chapter (or a `--range`), writing
one **`.cbz`** per chapter into the output directory, named after a
filesystem-safe version of the chapter title. Chapters are taken in normalized
**reading order** (oldest first), so ranges are stable regardless of how the
source sorts them. A chapter that yields no pages or fails is reported and
skipped; the batch keeps going.

```text
nyora-cli batch -s SRC [-o DIR] [--range A-B] MANGA_URL
```

| Arg / flag | Required | Default | Description |
| ---------- | -------- | ------- | ----------- |
| `-s`, `--source SRC` | **yes** | — | Source id or fuzzy name. |
| `-o`, `--out DIR` | no | `nyora-batch` | Output **directory** for the per-chapter `.cbz` files (created if missing; `~` is expanded). |
| `--range A-B` | no | (all) | Only chapters A..B in reading order (1-based). `5-` = from 5 to the end; `-3` = the first three. |
| `MANGA_URL` | **yes** | — | Manga URL (positional). |

**Example** — download chapters 1–10 only:

```bash
nyora-cli batch -s mangadex -o ./berserk --range 1-10 "/title/801513ba-a712-..."
```

```text
Fetching manga details...
Downloading 10 chapters as .cbz to berserk
  Chapter_1.cbz  (18/18 pages)
  Chapter_2.cbz  (20/20 pages)
  …
Done — 10 archives, 192 pages, in berserk
```

Each `.cbz` is a standard Comic Book ZIP, so the whole output directory drops
straight into any comic reader or library server.

---

## `completion` — print shell completion setup

Prints the one line to enable tab-completion for your shell (auto-detected from
`$SHELL`). Powered by `argcomplete`, which ships in core.

```text
nyora-cli completion [bash|zsh|fish]
```

```bash
$ nyora-cli completion
# Nyora completion for zsh — add this line to your shell config:
eval "$(register-python-argcomplete nyora)"   # ~/.zshrc
```

Add the printed line to your shell config (or run it in the current session),
then reload. Command names, options, and choices then complete on `TAB`.

---

## `version` — show package version

```text
nyora-cli [--json] version
```

Takes no options.

**Example**

```bash
nyora-cli version
```

```text
nyora 2.1.0
```

**JSON** emits `{"package": "2.1.0"}`. The global `-V`/`--version` flag prints the
same version string.

---

## Exit codes

| Code | Meaning |
| ---- | ------- |
| `0` | Success. For `download`, at least one page was saved. The bare-`nyora-cli` TUI also returns `0` on a clean exit and when no interactive terminal is attached. |
| `1` | A {py:class}`~nyora.errors.NyoraError` or `LookupError` was raised — e.g. an unresolved `-s/--source`, a network/cloud failure, or (for `download`) no pages could be saved. The message is printed to stderr as `error: <message>`. |
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

**Collect the top 100 popular titles across pages as JSON:**

```bash
nyora-cli --json popular -s mangadex --limit 100 | jq '.entries | length'
```

**Download every chapter of a manga (or a range), one `.cbz` each, into a folder:**

```bash
nyora-cli batch -s mangadex -o ./berserk "$url"                 # all chapters
nyora-cli batch -s mangadex -o ./berserk --range 1-10 "$url"    # first ten
```

**Download the first chapter and open it in your default reader:**

```bash
nyora-cli open -s mangadex "$ch"
```

**List just the page image URLs of a chapter:**

```bash
nyora-cli --json pages -s mangadex "$ch" | jq -r '.[].url'
```

**Count the available sources:**

```bash
nyora-cli --json sources | jq 'length'
```

**Open the interactive reader** (must be a real terminal):

```bash
nyora-cli            # or: nyora-tui
```
