# Nyora Python

**Read like the world can wait.**

`nyora` is the official Python package for **Nyora** — a fast, free, ad-free,
open-source manga engine. It brings Nyora's full source-and-parser engine to
Python: browse and search 1000+ manga, manhwa, and manhua sources, fetch manga
details and chapter lists, and resolve page image URLs — all from your code or
your terminal.

It is **pure Python**. There is no JVM helper, no desktop app, no Node.js, and
no Java to install. The parser bundle runs in-process via QuickJS, HTTP goes
through `httpx`, and HTML parsing uses `selectolax`. New and fixed sources
arrive over the air, so you do not need to upgrade the package to get them.

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

---

The **library** (`pip install nyora`, `import nyora`) and the **`nyora-cli`
tool** are documented separately throughout these docs. When something is about
writing Python, it lives under the library guide; when it is about the
command-line tool or terminal reader, it lives under the CLI and TUI guides.

## Documentation

```{toctree}
:maxdepth: 2

quickstart
guide/library
guide/cli
guide/tui
guide/server
guide/ota
guide/agents
reference/api
```
