<div align="center">

<img src="https://nyora.pages.dev/icon.png" width="120" alt="Nyora" />

# Nyora — Python

### Read like the world can wait.

The official Python package for **Nyora** — script your library, search 1000+ manga sources, and fetch chapters and pages straight from Python. Pure Python: no JVM, no desktop app, no Node.js, no Java. Just `pip install` and you're scripting manga in 60 seconds.

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <a href="https://pypi.org/project/nyora/"><img alt="PyPI version" src="https://img.shields.io/pypi/v/nyora?style=for-the-badge&logo=pypi&logoColor=white" /></a>
  <a href="https://pypi.org/project/nyora/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/nyora?style=for-the-badge&logo=python&logoColor=white" /></a>
</p>

<p>
  <a href="https://www.gnu.org/licenses/gpl-3.0"><img alt="License: GPL v3" src="https://img.shields.io/badge/License-GPLv3-blue.svg?style=for-the-badge" /></a>
  <a href="https://github.com/Hasan72341/nyora-python/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/Hasan72341/nyora-python?style=for-the-badge&logo=github&logoColor=white" /></a>
  <a href="https://github.com/Hasan72341/nyora-python/pulls"><img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-FF4655?style=for-the-badge&logo=github&logoColor=white" /></a>
</p>

<p>
  <a href="https://nyora.pages.dev/docs/python/"><img alt="Documentation" src="https://img.shields.io/badge/Docs-nyora.pages.dev%2Fdocs%2Fpython-0ae448?style=for-the-badge&logo=readthedocs&logoColor=white" /></a>
  <a href="https://pypi.org/project/nyora/"><img alt="Install from PyPI" src="https://img.shields.io/badge/Install-pip_install_nyora-3776AB?style=for-the-badge&logo=pypi&logoColor=white" /></a>
  <a href="https://nyora.pages.dev"><img alt="Website" src="https://img.shields.io/badge/Website-nyora.pages.dev-FF4655?style=for-the-badge&logo=githubpages&logoColor=white" /></a>
</p>

</div>

---

`nyora` is a pure-Python library, command-line tool, and terminal reader for the **Nyora** manga engine. Import it to drive 1000+ sources from your own code, pipe JSON into your scripts, or read manga in your terminal — installed with a single `pip install`, with **no JVM, no Node.js, no Java, and no companion app to launch**. It's fully open source, ad-free, and makes zero analytics or telemetry calls — the only network traffic is to the sources you ask for and the signed parser bundle.

```bash
pip3 install nyora
```

```python
from nyora import Nyora

with Nyora() as client:
    source = client.sources.find("mangadex")
    page = client.manga.popular(source.id)
    print(page.entries[0].title)          # you're scripting manga. that's it.
```

📖 **Full documentation: [nyora.pages.dev/docs/python](https://nyora.pages.dev/docs/python/)**

---

## Table of contents

- [Why you'll love it](#why-youll-love-it)
- [60-second quickstart](#60-second-quickstart)
- [About](#about)
- [Python library (`pip install nyora`)](#python-library-pip-install-nyora)
- [Command line (`nyora-cli`)](#command-line-nyora-cli)
- [Installation](#installation)
- [What it can and cannot do](#what-it-can-and-cannot-do)
- [FAQ](#faq)
- [Contributing](#contributing)
- [Development setup](#development-setup)
- [Where things live](#where-things-live)
- [Build from source](#build-from-source)
- [Nyora on every platform](#nyora-on-every-platform)
- [Privacy & open source](#privacy--open-source)
- [Acknowledgements](#acknowledgements)
- [License](#license)

---

## Why you'll love it

- **Installs in one line, runs anywhere Python runs.** Pure Python with Python-installed dependencies — nothing to compile, no JVM, no Node.js, no Java, no desktop app.
- **1000+ sources, one API.** Search, browse popular/latest, pull full chapter lists, and resolve page image URLs through a single clean, typed client.
- **Sync *and* async.** Drive it sequentially with `Nyora`, or fan out across many sources concurrently with `AsyncNyora` — same namespaces, same shapes.
- **Read in your terminal.** A full Textual-based TUI ships in the box: bare `nyora-cli` opens it. Pick a source, browse, open a title, page through a chapter — without leaving the shell.
- **Scriptable by design.** Add `--json` to any command and pipe straight into `jq` or your own tooling.
- **Always current.** Sources update **over the air** — sha256-verified, atomic — so new and fixed parsers arrive without upgrading the package.
- **Private by default.** No accounts, no ads, no tracking, no telemetry. Fully auditable, GPL-3.0 open source.

---

## 60-second quickstart

```bash
pip3 install nyora
```

**Read in your terminal — zero code:**

```bash
nyora-cli                              # launches the terminal reader (TUI)
```

**Or script it — find a source, search, fetch pages:**

```python
from nyora import Nyora

with Nyora() as client:
    source = client.sources.find("asura")                 # fuzzy name or id
    results = client.manga.search(source.id, "Solo Leveling")
    entry = results.entries[0]

    details = client.manga.details(source.id, entry.url, title=entry.title)
    pages = client.manga.pages(source.id, details.chapters[0].url)

    for p in pages:
        print(p.url)                                       # page image URLs
```

**Or stay in the shell and pipe JSON:**

```bash
nyora-cli --json popular -s mangadex -p 1 | jq '.entries[].title'
```

That's the whole loop: install, pick a source, browse or search, fetch pages. Everything below goes deeper.

---

## About

Nyora is a fast, free, ad-free, open-source manga reader that runs on **every** platform — with whole-page AI translation, 1000+ sources, offline downloads, and free cloud sync across all your devices. `nyora` brings that same source-and-parser engine to Python: a pip-installable library, a command-line tool (`nyora-cli`), and a terminal reader (TUI).

It runs the full Nyora parser bundle in-process through Python-installed dependencies — pure Python, end to end, with nothing to compile and no companion app to launch.

This single install gives you **both** surfaces below — a Python library you import, and the `nyora-cli` command-line tool. They are documented as clearly separate surfaces.

---

## Python library (`pip install nyora`)

`import nyora` to drive Nyora's source/parser engine from your own code. Open a `Nyora()` client, find a source, search it, fetch details, and resolve page image URLs — all with a clean, typed API. No JVM helper, no desktop app, no Node.js, no Java.

```python
from nyora import Nyora

with Nyora() as client:
    source = client.sources.find("mangadex")          # resolve by id or fuzzy name
    page = client.manga.popular(source.id)            # SearchPage of entries
    entry = page.entries[0]

    details = client.manga.details(source.id, entry.url, title=entry.title)
    pages = client.manga.pages(source.id, details.chapters[0].url)

    for p in pages:
        print(p.url)
```

The client exposes two typed namespaces:

- **`client.sources`** — `list()` the full bundled catalogue, or `find(...)` a source by **id** or fuzzy **name** (e.g. `"asura"`).
- **`client.manga`** — `popular(...)`, `latest(...)`, `search(...)`, `details(...)`, and `pages(...)`.

### Browse popular and latest

```python
from nyora import Nyora

with Nyora() as client:
    src = client.sources.find("mangadex").id

    popular = client.manga.popular(src, page=1)
    latest = client.manga.latest(src, page=1)

    for entry in popular.entries[:5]:
        print(entry.title, "—", entry.url)
```

### Async fan-out across many sources

For concurrent fan-out across many sources, use the async client, which exposes the same namespaces:

```python
import asyncio
from nyora import AsyncNyora

async def main():
    async with AsyncNyora() as client:
        source = await client.sources.find("asura")
        results = await client.manga.search(source.id, "Solo Leveling")
        print(results.entries[0].title)

asyncio.run(main())
```

### Attach to a running helper

You can also attach to an already-running Nyora helper (the desktop helper, another app, or `nyora-cli serve`) over its REST contract instead of running the engine in-process:

```python
from nyora import NyoraHelper

with NyoraHelper.attach("http://127.0.0.1:54123") as client:
    print(client.health())
```

### Over-the-air source updates

The parser bundle and source catalogue update **over the air**, so new and fixed sources arrive without upgrading the package:

```python
from nyora import Nyora

with Nyora() as client:
    available, installed, latest = client.check_update()
    if available:
        result = client.update()        # sha256-verified, atomic
        print("updated to OTA version", result.version)
```

→ Library guide: **[nyora.pages.dev/docs/python/guide/library](https://nyora.pages.dev/docs/python/guide/library.html)** · API reference: **[/reference/api](https://nyora.pages.dev/docs/python/reference/api.html)**

---

## Command line (`nyora-cli`)

Installing the package adds the **`nyora-cli`** command (also aliased as `nyora`). It drives the same pure-Python engine as the library.

> **Running bare `nyora-cli` with no subcommand launches the terminal reader (TUI).** Pass a subcommand to run a one-shot command instead.

```bash
nyora-cli                                    # no subcommand -> launches the TUI
nyora-cli --help                             # list all commands and options
nyora-cli sources --search asura             # one-shot subcommand
nyora-cli search -s asura "Solo Leveling"
```

### Subcommands

| Command | Description |
|---|---|
| `sources [--search Q]` | List the source catalogue, or fuzzy-find sources by name |
| `search -s SRC [-p PAGE] QUERY` | Search a source for a query |
| `popular -s SRC [-p PAGE]` | Browse a source's popular titles |
| `latest -s SRC [-p PAGE]` | Browse a source's latest updates |
| `details -s SRC URL` | Fetch manga details and the full chapter list |
| `pages -s SRC CHAPTER_URL [--branch B]` | Resolve page image URLs for a chapter |
| `download -s SRC CHAPTER_URL [-o OUT]` | Download a chapter as a single `.cbz` archive (`OUT` is a `.cbz` file or a directory; default `<chapter>.cbz`) |
| `batch -s SRC MANGA_URL [-o DIR]` | Batch download ALL chapters of a manga, one `.cbz` per chapter, into `DIR` |
| `update [--force]` | Self-update the parser bundle over the air (OTA) |
| `serve [--host H] [--port P]` | Run the pure-Python REST helper |
| `version` | Print the package and installed OTA version |

`-s/--source` accepts a source **id** or a fuzzy **name** (e.g. `asura`). Add the global `--json` flag to any subcommand to emit raw JSON instead of a pretty table — ideal for piping into `jq` or wiring into scripts:

```bash
nyora-cli --json popular -s mangadex -p 1
```

### Terminal reader (TUI)

Run bare `nyora-cli` (or `nyora-tui`) to open the full terminal reader, built on [Textual](https://github.com/Textualize/textual): pick a source, browse popular/latest/search, open a title, and page through a chapter — all without leaving the shell. It is non-TTY safe: in a non-interactive shell it prints a friendly notice and exits cleanly.

```bash
nyora-cli        # launches the TUI
nyora-tui        # also launches the TUI
```

### Pure-Python REST helper

`nyora-cli serve` starts a small stdlib HTTP server that exposes the engine over the same camelCase REST contract the desktop helper uses, so any other Nyora app (or `NyoraHelper.attach(...)`) can connect:

```bash
nyora-cli serve --host 127.0.0.1 --port 0
# -> http://127.0.0.1:54123
```

It binds the requested host/port (port `0` picks a free port), prints the base URL, and writes a `helper.port` file so other Nyora processes can auto-discover it. Endpoints include `/health`, `/sources`, `/sources/popular`, `/sources/latest`, `/sources/search`, `/manga/details`, and `/manga/pages`.

→ CLI guide: **[/guide/cli](https://nyora.pages.dev/docs/python/guide/cli.html)** · TUI guide: **[/guide/tui](https://nyora.pages.dev/docs/python/guide/tui.html)** · Server guide: **[/guide/server](https://nyora.pages.dev/docs/python/guide/server.html)**

---

## Installation

### From PyPI (recommended)

```bash
pip3 install nyora
```

This installs the `nyora` Python library **and** the `nyora-cli` command (aliased as `nyora`), including the Textual-based terminal reader and the REST helper. It is pure Python with only Python-installed dependencies — no JVM helper, desktop app, Node.js, or Java to install.

**Frictionless and safe by design.** `nyora` is published to PyPI straight from this public, GPL-3.0 repository — you can read every line before you run it. There's no account to create, no ads, no tracking, and no telemetry. The only network calls it makes are to the sources you explicitly ask for and to fetch the sha256-verified OTA parser bundle. Your library, history, and downloads stay on your machine, under your control.

| Install | Command | Adds |
|---|---|---|
| Default | `pip3 install nyora` | Library + `nyora-cli` + TUI + REST helper |
| Docs tooling | `pip3 install "nyora[docs]"` | Sphinx + Furo to build these docs |
| Dev tooling | `pip3 install "nyora[dev]"` | Build, test, lint, and publish tooling |

> **Tip — keep it isolated.** If you'd rather not touch your global environment, install into a virtual environment (`python -m venv .venv && source .venv/bin/activate`) or use [`pipx`](https://pipx.pypa.io/) (`pipx install nyora`) to get the CLI on your `PATH` in its own sandbox.

### Requirements

- **Python 3.10 or newer** (tested through 3.14).
- A network connection for source requests and OTA parser-bundle updates.

### Updating

Two layers update independently:

- **The package** (library + CLI): `pip3 install --upgrade nyora`.
- **The sources** (parser bundle + catalogue): `nyora-cli update` (add `--force` to re-pull). New and fixed sources arrive over the air without a package upgrade.

Check what you're running with `nyora-cli version`.

### Troubleshooting

- **`nyora-cli: command not found`** — ensure your Python `Scripts`/`bin` directory is on your `PATH`, or invoke it as `python -m nyora`.
- **Stale or missing sources** — run `nyora-cli update` (or `--force`), then `nyora-cli version` to confirm the installed OTA version.
- **Permission errors writing the cache** — the OTA bundle is written into the user cache directory; make sure that location is writable for your user.

---

## What it can and cannot do

| Capability | Supported | Notes |
|---|---|---|
| List the full source catalogue | Yes | `client.sources.list()` / `nyora-cli sources` |
| Resolve a source by id or fuzzy name | Yes | `client.sources.find(...)` |
| Popular / latest / search browsing | Yes | `client.manga.popular` · `.latest` · `.search` |
| Manga details + full chapter list | Yes | `client.manga.details(...)` |
| Resolve page image URLs | Yes | `client.manga.pages(...)` |
| Download a chapter to a `.cbz` archive | Yes | `nyora-cli download` |
| Synchronous **and** async clients | Yes | `Nyora` and `AsyncNyora` |
| Run as a REST helper / attach to one | Yes | `nyora-cli serve` · `NyoraHelper.attach(...)` |
| OTA self-update of sources | Yes | sha256-verified, atomic writes |
| Pure Python — no JVM / Node.js / Java | Yes | Runs the parser bundle in-process |
| Host the consumer reading UI | No | Use the platform apps for a full reader |
| Bundled OCR / image translation pipeline | No | Translation lives in the consumer apps; the library gives you the page URLs to build on |
| Bypass a source's own access controls | No | It parses publicly accessible providers only |

---

## FAQ

**Is it really free?**
Yes. `nyora` is 100% free and open source under GPL-3.0. There are no paid tiers, no ads, and no upsells.

**Do I need an account?**
No. There's nothing to sign up for. Install the package and start reading or scripting immediately.

**Will my data be private?**
Yes. There are no analytics, no telemetry, and no accounts. The only network calls `nyora` makes are to the sources you explicitly request and to fetch the sha256-verified OTA parser bundle. Your library, history, and downloads live on your own machine.

**Is it safe? Can I audit it?**
Every line is public, GPL-3.0 source code in this repository, and the wheel on PyPI is built from it. You're welcome to read the code, run it in a virtual environment, and inspect exactly what it talks to over the network.

**How do I update?**
Upgrade the package with `pip3 install --upgrade nyora`, and refresh the sources with `nyora-cli update`. The two update independently — most source fixes arrive over the air without a package upgrade.

**Do I have to write code to use it?**
No. Run bare `nyora-cli` to open the terminal reader (TUI) and browse with the keyboard, or use one-shot subcommands like `nyora-cli search -s asura "Solo Leveling"`. The Python API is there when you want it.

**A source stopped working — what do I do?**
Run `nyora-cli update --force` first; many breakages are fixed in the OTA bundle. If it persists, please [open an issue](https://github.com/hasan72341/Nyora/issues) so it can be tracked and fixed.

**Does it translate manga like the apps do?**
Not in the box. Whole-page OCR/translation lives in the consumer apps. `nyora` gives you the page image URLs so you can build that (or anything else) on top.

---

## Contributing

Contributions are genuinely welcome — and you can start **today**. `nyora` is fully open Python: there's no private engine, no closed core, and no special access required. If you can run `uv sync`, you can run the whole thing and change anything you like.

### Ways to contribute (every skill level)

You don't need to be a Python expert — or even write code — to help:

- **Report a bug.** Hit a broken source, a confusing error, or a crash? [Open an issue](https://github.com/hasan72341/Nyora/issues) with what you ran and what happened. Clear bug reports are worth a lot.
- **Request or help a source.** Want a source supported, or noticed one parsing wrong? File an issue. Sources are driven by the OTA parser bundle, so flagging breakage helps everyone.
- **Improve the docs.** The Sphinx docs live in `docs/` (`guide/` and `reference/`). Typos, clearer examples, and new how-to recipes are all great first PRs.
- **Test releases.** Try a new version on your platform and Python (3.10–3.14) and report what works or breaks — especially the CLI and TUI in different terminals.
- **Improve or translate the UI strings.** The Textual TUI lives in `src/nyora_tui/`; clearer wording and better keyboard flows are welcome.
- **Write code.** Add API examples, sharpen typing, fix bugs, or extend the CLI/TUI. See "Good first contributions" below.
- **Star and share.** Genuinely one of the most helpful things you can do — it helps other readers find the project. If `nyora` saved you time, a star and a link go a long way.

### Good first contributions

Pulled from how this repo is actually laid out:

- **A new CLI subcommand.** Subcommands live in `src/nyora/cli.py` and call into the `client.sources` / `client.manga` namespaces — a small, self-contained surface to add to. Mirror an existing one and add a row to the subcommands table above.
- **A new library example or recipe.** Add a focused snippet to `docs/guide/library.md` showing a real task (e.g. exporting a chapter list to CSV, fanning out a global search with `AsyncNyora`).
- **A TUI nicety.** `src/nyora_tui/app.py` is a single Textual app — small ergonomic fixes (key bindings, empty-state messages, status text) are friendly first changes.
- **A REST endpoint or `--json` polish.** The stdlib server in `src/nyora/server.py` and the `--json` output in `cli.py` are easy places to add value for scripters.
- **Docs and typing.** Tightening docstrings, type hints, or the API reference in `docs/reference/api.md` is always appreciated.

### PR & issue etiquette

- **Keep PRs focused.** One change per PR is much easier to review and merge than a grab-bag.
- **Describe the change.** A sentence or two on *what* and *why*, plus how you tested it, is plenty.
- **Run the checks first** (see [Development setup](#development-setup)): `ruff`, `mypy`, and `pytest` should pass.
- **Be kind.** Reviews are a conversation. Newcomers are welcome and questions are fine — ask early rather than guess.
- **Match the existing style.** Typed, dependency-light, pure Python. If you're unsure where something belongs, open an issue first and we'll point you at the right file.

Issues and discussion happen here: **[github.com/hasan72341/Nyora/issues](https://github.com/hasan72341/Nyora/issues)**.

---

## Development setup

This is the contributor quickstart (distinct from the end-user `pip install`). The project is managed with [`uv`](https://github.com/astral-sh/uv).

```bash
# 1. Clone
git clone https://github.com/Hasan72341/nyora-python
cd nyora-python

# 2. Install everything (deps + dev + docs tooling) into a managed venv
uv sync --extra dev --extra docs

# 3. Smoke test — confirm the core symbols import cleanly
uv run python -c "from nyora import Nyora, Manga, Source; print(Nyora, Manga, Source)"

# 4. Run it
uv run nyora-cli sources --search asura
uv run nyora-cli                       # launches the TUI
```

**Prerequisites:** Python 3.10+ and `uv`. That's it — pure Python, nothing to compile, no JVM/Node.js/Java.

**Run the checks** (please do this before opening a PR):

```bash
uv run ruff check .          # lint
uv run ruff format .         # format
uv run mypy                  # type-check (packages: nyora, nyora_tui)
uv run pytest                # tests (live in tests/)
```

**Where to look first:** start in `src/nyora/client.py` to see how the `sources` and `manga` namespaces are wired, then follow into `src/nyora/services/` for the actual operations. For the CLI, read `src/nyora/cli.py`; for the TUI, `src/nyora_tui/app.py`.

### Bumping the bundled sources (internal)

The parser bundle (`parsers.bundle.js`) and source catalogue (`sources.json`) are force-included into the wheel (see `pyproject.toml`) and otherwise refreshed over the air at runtime. Day-to-day contributors don't need to touch these — source fixes ship through the OTA channel, not the package.

---

## Where things live

A quick map so you can navigate the repo:

| Path | What's there |
|---|---|
| `src/nyora/client.py` | The `Nyora` / `AsyncNyora` clients and the `sources` / `manga` namespaces |
| `src/nyora/services/` | The operations behind the namespaces — `sources.py`, `manga.py`, `downloads.py`, `library.py`, `backup.py`, `system.py` |
| `src/nyora/models.py` | Typed dataclasses (`Source`, `Manga`, `MangaDetails`, `MangaChapter`, `SearchPage`, …) |
| `src/nyora/cli.py` | The `nyora-cli` command, subcommands, and `--json` output |
| `src/nyora/server.py` | The stdlib REST helper (`nyora-cli serve`) |
| `src/nyora/ota.py` | Over-the-air bundle updates (sha256-verified, atomic) |
| `src/nyora/runtime.py`, `parser_bridge.py`, `direct.py` | The in-process engine and parser bridge |
| `src/nyora/helper.py` | `NyoraHelper.attach(...)` for talking to a running helper |
| `src/nyora_tui/app.py` | The Textual terminal reader |
| `tests/` | The pytest suite (`test_cli.py`, `test_server.py`, `test_ota.py`, …) |
| `docs/` | Sphinx docs — `guide/` and `reference/` |
| `pyproject.toml` | Project metadata, dependencies, and tool config (ruff, mypy, pytest) |

---

## Build from source

For local development in this repository, the project is managed with [`uv`](https://github.com/astral-sh/uv).

```bash
uv sync --extra dev --extra docs
uv run python -c "from nyora import Nyora, Manga, Source; print(Nyora, Manga, Source)"
```

`uv sync` resolves and installs all dependencies into a managed virtual environment, and the `uv run` smoke test confirms the core symbols import cleanly. Requires Python 3.10+.

Build the documentation locally with:

```bash
bash scripts/build-docs.sh
```

### Packaging

```bash
uv lock
uv build
uv run twine check dist/*
```

The parser bundle and source catalogue are force-included into the wheel, so a fresh install can run the engine immediately and update over the air from there.

---

## Nyora on every platform

The Nyora reader is everywhere your screens are — and your library, history, bookmarks, and progress sync for free across all of them.

| Platform | Repo | Get it |
|---|---|---|
| Python | [nyora-python](https://github.com/Hasan72341/nyora-python) **(you are here)** | [`pip3 install nyora`](https://pypi.org/project/nyora/) |
| Android | [nyora-android](https://github.com/Hasan72341/nyora-android) | [APK](https://github.com/Hasan72341/nyora-android/releases/latest) |
| macOS | [nyora-mac](https://github.com/Hasan72341/nyora-mac) | [.dmg / brew](https://github.com/Hasan72341/nyora-mac/releases/latest) |
| Windows | [nyora-windows](https://github.com/Hasan72341/nyora-windows) | [.exe (x64/ARM64)](https://github.com/Hasan72341/nyora-windows/releases/latest) |
| Linux | [nyora-linux](https://github.com/Hasan72341/nyora-linux) | [deb · rpm · curl](https://github.com/Hasan72341/nyora-linux/releases/latest) |
| iOS / iPadOS | [nyora-ios](https://github.com/Hasan72341/nyora-ios) | [sideload IPA](https://github.com/Hasan72341/nyora-ios/releases/latest) |
| Web | [nyora-web](https://github.com/Hasan72341/nyora-web) | [nyoraweb.pages.dev](https://nyoraweb.pages.dev) |

> **Want a big, mechanical, high-impact contribution?** The iOS engine (`NyoraEngine`) is porting roughly **1,300 sources** as mostly-mechanical template subclasses — the framework and one template are done, leaving ~1,331 parsers to port across 3,659 classes. It's highly parallelizable and the headliner "help wanted" across the project. If that's your kind of thing, it's a great place to make a dent.

---

## Privacy & open source

Nyora is 100% free, ad-free, and contains no tracking. `nyora` is fully auditable open-source code: there are no analytics, no telemetry, and no accounts. The only network calls it makes are to the sources you ask for and to fetch the sha256-verified OTA parser bundle. Licensed under **GPL-3.0-only**.

## Acknowledgements

Nyora's source and parser engine builds on the work of the open-source manga community. `nyora` is developed and maintained by **Md Hasan Raza** — [GitHub](https://github.com/Hasan72341) · hasanraza96@outlook.com.

If `nyora` is useful to you, the kindest thing you can do is **star the repo and share it** — it helps other readers and scripters find the project, and it's the simplest way to say thanks. Pull requests, however small, are always welcome.

## License

Licensed under **GPL-3.0-only**. See the project metadata in `pyproject.toml` for details.

---

> Nyora is not affiliated with any of the manga sources it can access.