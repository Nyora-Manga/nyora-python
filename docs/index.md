# Nyora Python

**Read like the world can wait.**

`nyora` is the official Python package for **Nyora** — a fast, free, ad-free,
open-source manga engine. It is **self-contained**: `pip install nyora` bundles the
kotatsu-parsers engine and launches it locally on demand (a JRE is auto-downloaded
if you have no Java) — so there is **nothing else to run**: no server to host, no
Node process, no scraper to maintain. You get one typed API over **390 live,
health-checked sources across 40 languages** to browse and search manga, manhwa,
and manhua, fetch details and chapter lists, resolve page image URLs, and download
chapters — from your code or your terminal. Prefer a server? Point it at any Nyora
instance with `base_url=` and the bundled engine steps aside.

```bash
pip3 install nyora
```

## One install, three tools

`pip install nyora` is a single package, but it ships **three distinct
front-ends** over the same engine. Reach for whichever fits the job — they are
documented separately so you always know which one a page is about.

| | What it is | You invoke it as | Guide |
| --- | --- | --- | --- |
| 🐍 **Library** | A typed Python SDK you `import` and call from your own code (sync **and** async). | `import nyora` | {doc}`guide/library` |
| ⌨️ **CLI** | A scriptable command-line tool — one subcommand per operation, with `--json` for machine output. | `nyora …` / `nyora-cli …` | {doc}`guide/cli` |
| 📖 **TUI** | A full interactive terminal reader — browse, search, and read in the terminal. | `nyora` *(no subcommand)* / `nyora-tui` | {doc}`guide/tui` |

The rule of thumb: if you are **writing Python**, use the library; if you are
**scripting a shell or an agent**, use the CLI; if you just want to **read**, use
the TUI.

### 🐍 The Python library — `import nyora`

A typed SDK you call from your own code. Open a `Nyora()` client, find a
source, search it, fetch details, and resolve page URLs. Synchronous
(`Nyora`) and asynchronous (`AsyncNyora`) clients are both included.

```python
from nyora import Nyora

with Nyora() as client:
    src = client.sources.find("mangadex")
    page = client.manga.popular(src.id)
    print(page.entries[0].title)
```

→ {doc}`guide/library` · {doc}`guide/agents` (driving Nyora from an LLM agent)

### ⌨️ The `nyora-cli` tool — `nyora-cli` (or `nyora`)

A command-line tool installed alongside the library. Run subcommands like
`search`, `details`, `download`, `batch`, and `grab`; add `--json` to any of
them for machine-readable output (ideal for scripts and agents).

```bash
nyora-cli search -s asura "Solo Leveling"
nyora-cli --json grab -s mangadex "berserk" -c 1 -o ./out   # search → download in one call
```

→ {doc}`guide/cli`

### 📖 The terminal reader — bare `nyora`

Running `nyora` (or `nyora-cli`) with **no subcommand** — or the explicit
`nyora-tui` — launches the full interactive reader: browse and search sources,
read chapters inline (three reader modes), manage a local library and downloads,
and sign in to sync.

```bash
nyora            # launches the TUI
```

→ {doc}`guide/tui`

## Cloud sync (optional)

All three front-ends can sign in to sync a user's library — favourites, history,
and bookmarks — across devices through {py:class}`nyora.sync.NyoraSync`, which
talks to the Nyora sync server at
[`https://sync.nyora.xyz`](https://sync.nyora.xyz). It is entirely optional: the
library, CLI, and TUI all work fully offline without an account, and the TUI has
a built-in account menu and synced-library view.

→ {doc}`guide/sync`

```{admonition} Other Nyora clients
:class: seealso

Beyond this Python SDK, Nyora also ships a JavaScript/TypeScript SDK
([`nyora-sdk`](https://www.npmjs.com/package/nyora-sdk)), **nyora-mihon** (an
on-device Android APK that brings ~900 sources to stock Mihon), and
**nyora-aidoku** (WASM `.aix` proxy sources for stock Aidoku). Those are separate
distributions; this site documents the Python package.
```

## Documentation

```{toctree}
:maxdepth: 2

quickstart
guide/library
guide/cli
guide/tui
guide/sync
guide/agents
reference/api
```
