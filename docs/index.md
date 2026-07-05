# Nyora Python

**Read like the world can wait.**

`nyora` is the official Python package for **Nyora** — a fast, free, ad-free,
open-source manga engine. It is a thin, typed client over the **Nyora cloud**
(the kotatsu-parsers engine, ~960 sources) at
[`https://api.hasanraza.tech`](https://api.hasanraza.tech): browse and search
manga, manhwa, and manhua sources, fetch manga details and chapter lists, and
resolve page image URLs — all from your code or your terminal.

The default `Nyora()` client talks to the cloud, so there is **nothing else to
run**: no local server and no Node process to manage. HTTP is handled by `httpx`.
Sources are maintained centrally in the cloud, so you get new and fixed sources
without upgrading the package.

```bash
pip3 install nyora
```

## Two ways to use Nyora

This package gives you two clearly separate things.

### 🐍 The Python library — `import nyora`

A typed SDK you call from your own code. Open a `Nyora()` client, find a
source, search it, fetch details, and resolve page URLs. Synchronous and async
clients are both included.

```python
from nyora import Nyora

with Nyora() as client:
    src = client.sources.find("mangadex")
    page = client.manga.popular(src.id)
    print(page.entries[0].title)
```

→ {doc}`guide/library`

### ⌨️ The `nyora-cli` tool — `nyora-cli`

A command-line tool installed alongside the library. Run subcommands like
`search`, `details`, and `download`, or run bare `nyora-cli` with **no
subcommand** to launch the full terminal reader (TUI).

```bash
nyora-cli search -s asura "Solo Leveling"
nyora-cli                 # launches the TUI
```

→ {doc}`guide/cli` · {doc}`guide/tui`

## Cloud Sync

Signed-in users can sync their library — favourites, history, and bookmarks —
across devices through {py:class}`nyora.sync.NyoraSync`, which talks to the
Nyora sync server at
[`https://stream.hasanraza.tech`](https://stream.hasanraza.tech). The terminal
reader has a built-in account menu and synced library view.

→ {doc}`guide/sync`

---

The **library** (`pip install nyora`, `import nyora`) and the **`nyora-cli`
tool** are documented separately throughout these docs. When something is about
writing Python, it lives under the library guide; when it is about the
command-line tool or terminal reader, it lives under the CLI and TUI guides.

```{admonition} Other Nyora clients
:class: seealso

Beyond this Python SDK, Nyora also ships **nyora-mihon** (an on-device Android
APK that brings ~900 sources to stock Mihon) and **nyora-aidoku** (~959 WASM
`.aix` proxy sources for stock Aidoku). Those are separate distributions; this
site documents the Python package.
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
