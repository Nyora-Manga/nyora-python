"""Command-line interface for the Nyora SDK.

Exposes the Nyora parser engine through a small argparse-based command tree: list
sources, run popular/latest/search, fetch manga details and chapter pages,
download chapters as .cbz, and show the version. Running ``nyora-cli`` with no
subcommand launches the interactive terminal reader (TUI).
"""
# PYTHON_ARGCOMPLETE_OK

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.theme import Theme

from nyora.client import Nyora
from nyora.errors import NyoraError
from nyora.models import Manga, MangaDetails, MangaPage, SearchPage, Source

# --------------------------------------------------------------------------- #
# Visual identity — the CLI palette tracks the *same* colour scheme the reader
# picked in the TUI (persisted in config, shared table in nyora.theme), so the
# CLI and terminal reader always look like one product. The accent carries the
# scheme's identity; only accent-bearing styles change per theme — semantic
# colours (rating amber, 18+ red, URL blue…) stay fixed for readability.
# --------------------------------------------------------------------------- #
_FLOWER = "❀"  # sakura mark used as a small brand flourish on titles


def _build_theme() -> Theme:
    """Build the Rich theme from the reader's persisted colour scheme."""
    from nyora import theme as _t
    from nyora.config import read_theme_from_config

    accent = _t.accent_for(read_theme_from_config())
    border = _t.mix(accent, "#7d7d85", 0.5)   # muted accent for table borders
    return Theme(
        {
            "nyora.brand": f"bold {accent}",
            "nyora.title": f"bold {accent}",
            "nyora.header": f"bold {accent}",
            "nyora.border": border,
            "nyora.muted": "grey58",
            "nyora.index": "grey42",
            "nyora.link": "#8fb8ff",       # soft blue for URLs (readable on any accent)
            "nyora.rating": "#f6c177",      # amber stars
            "nyora.lang": "#8fd6c0",        # teal language tags
            "nyora.nsfw": "bold #ff6b6b",   # 18+ badge
            "nyora.pin": "#f6c177",
            "nyora.ok": "bold #a7e0a0",
            "nyora.warn": "#f6c177",
            "nyora.err": "bold #ff6b6b",
            # Override Rich's defaults (table titles are italic by default) so our
            # bold accent titles render cleanly.
            "table.title": "",
            "table.caption": "dim",
        }
    )

#: User-Agent for direct image downloads (the helper rewrites cover/page
#: hosts; a browser UA keeps CDNs happy).
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``nyora-cli`` command.

    With no subcommand, launch the interactive terminal reader
    (:func:`nyora_tui.app.main`). Otherwise dispatch to the named subcommand;
    ``nyora-cli --help`` lists them. ``NyoraError``/``LookupError`` map to exit
    code 1, argparse usage errors to 2, and ``Ctrl+C`` to 130.
    """
    parser = _build_parser()
    import argcomplete  # core dep; no-op unless the shell requests completion

    argcomplete.autocomplete(parser)
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        return _launch_tui()

    try:
        return args.handler(args)
    except (NyoraError, LookupError) as exc:
        _fail(args, str(exc))
        return 1
    except KeyboardInterrupt:  # pragma: no cover - interactive
        _fail(args, "interrupted")
        return 130


def _launch_tui() -> int:
    """Launch the interactive TUI and return its exit code.

    The TUI's ``main()`` may return ``None`` (treated as a clean ``0`` exit) or
    an explicit integer code. ``NyoraError``/``LookupError`` and keyboard
    interrupts are handled here so the bare-``nyora-cli`` path mirrors the
    subcommand error handling.
    """
    from nyora_tui.app import main as tui_main

    try:
        result = tui_main()
    except (NyoraError, LookupError) as exc:
        _error(str(exc))
        return 1
    except KeyboardInterrupt:  # pragma: no cover - interactive
        _error("interrupted")
        return 130
    return result if isinstance(result, int) else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nyora-cli",
        description="Independent Nyora SDK command-line interface.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit raw JSON instead of pretty output",
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"nyora {_package_version()}"
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    p_sources = sub.add_parser("sources", help="list or search available sources")
    p_sources.add_argument("--search", metavar="Q", default=None, help="filter sources by text")
    p_sources.set_defaults(handler=_cmd_sources)

    p_search = sub.add_parser("search", help="search a source")
    _add_browse_args(p_search)
    p_search.add_argument("query", help="search query")
    p_search.set_defaults(handler=_cmd_search)

    p_popular = sub.add_parser("popular", help="list popular manga from a source")
    _add_browse_args(p_popular)
    p_popular.set_defaults(handler=_cmd_popular)

    p_latest = sub.add_parser("latest", help="list latest manga from a source")
    _add_browse_args(p_latest)
    p_latest.set_defaults(handler=_cmd_latest)

    p_details = sub.add_parser("details", help="fetch manga details and chapters")
    _add_source_arg(p_details)
    p_details.add_argument("url", help="manga URL")
    p_details.set_defaults(handler=_cmd_details)

    p_pages = sub.add_parser("pages", help="fetch chapter page image URLs")
    _add_source_arg(p_pages)
    p_pages.add_argument("--branch", default=None, help="chapter branch")
    p_pages.add_argument("chapter_url", help="chapter URL")
    p_pages.set_defaults(handler=_cmd_pages)

    p_download = sub.add_parser("download", help="download a chapter as a .cbz archive")
    _add_source_arg(p_download)
    p_download.add_argument("--branch", default=None, help="chapter branch")
    p_download.add_argument(
        "-o",
        "--out",
        default=None,
        help="output .cbz file or directory (default: <chapter>.cbz in the current directory)",
    )
    p_download.add_argument("chapter_url", help="chapter URL")
    p_download.set_defaults(handler=_cmd_download)

    p_open = sub.add_parser("open", help="download a chapter as .cbz and open it")
    _add_source_arg(p_open)
    p_open.add_argument("--branch", default=None, help="chapter branch")
    p_open.add_argument("-o", "--out", default=None, help="output .cbz file or directory")
    p_open.add_argument("chapter_url", help="chapter URL")
    p_open.set_defaults(handler=_cmd_open)

    p_batch = sub.add_parser(
        "batch", help="download every chapter of a manga as .cbz archives"
    )
    _add_source_arg(p_batch)
    p_batch.add_argument(
        "-o",
        "--out",
        default="nyora-batch",
        help="output directory for the .cbz files (default: nyora-batch)",
    )
    p_batch.add_argument(
        "--range",
        dest="chapter_range",
        metavar="A-B",
        default=None,
        help="only chapters A..B in reading order (1-based, e.g. 1-10, 5-, -3)",
    )
    p_batch.add_argument("manga_url", help="manga URL")
    p_batch.set_defaults(handler=_cmd_batch)

    p_grab = sub.add_parser(
        "grab",
        help="search + resolve + download in one call (ideal for scripts/agents)",
    )
    _add_source_arg(p_grab)
    p_grab.add_argument("query", help="search query — the first match is used")
    p_grab.add_argument(
        "-c", "--chapter", type=int, default=None, metavar="N",
        help="download the Nth chapter in reading order (default: 1)",
    )
    p_grab.add_argument(
        "--range", dest="chapter_range", metavar="A-B", default=None,
        help="download chapters A..B in reading order",
    )
    p_grab.add_argument("--all", action="store_true", help="download every chapter")
    p_grab.add_argument(
        "-o", "--out", default=None, help="output directory (default: <manga-title>/)"
    )
    p_grab.set_defaults(handler=_cmd_grab)

    p_version = sub.add_parser("version", help="show package version")
    p_version.set_defaults(handler=_cmd_version)

    p_config = sub.add_parser(
        "config", help="show or set the server URL (defaults to a local bundled engine)"
    )
    p_config.add_argument(
        "action", nargs="?", default="show",
        choices=["show", "set-url", "unset-url", "path"],
        help="show (default) | set-url <URL> | unset-url | path",
    )
    p_config.add_argument("value", nargs="?", help="URL when action is set-url")
    p_config.set_defaults(handler=_cmd_config)

    p_upgrade = sub.add_parser("upgrade", help="upgrade the nyora package to the latest release")
    p_upgrade.set_defaults(handler=_cmd_upgrade)

    p_blocklist = sub.add_parser(
        "blocklist", help="show / rebuild the per-server dead-source blocklist (probes your server)"
    )
    p_blocklist.add_argument(
        "action", nargs="?", default="show", choices=["show", "refresh", "clear"],
        help="show (default) | refresh (probe & cache) | clear",
    )
    p_blocklist.set_defaults(handler=_cmd_blocklist)

    p_completion = sub.add_parser("completion", help="print shell completion setup")
    p_completion.add_argument(
        "shell", nargs="?", default=None, choices=["bash", "zsh", "fish"],
        help="target shell (default: $SHELL)",
    )
    p_completion.set_defaults(handler=_cmd_completion)

    return parser


def _add_source_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-s",
        "--source",
        required=True,
        metavar="SRC",
        help="source id or fuzzy name",
    )


def _add_browse_args(parser: argparse.ArgumentParser) -> None:
    _add_source_arg(parser)
    parser.add_argument("-p", "--page", type=int, default=1, help="page number (default: 1)")
    parser.add_argument(
        "-n", "--limit", type=int, default=None, metavar="N",
        help="collect up to N results across pages (auto-paginates)",
    )
    parser.add_argument(
        "--all", action="store_true", help="collect every result across all pages",
    )


# --------------------------------------------------------------------------- #
# Command handlers
# --------------------------------------------------------------------------- #


def _cmd_sources(args: argparse.Namespace) -> int:
    with Nyora() as nyora:
        sources = nyora.sources.list()
        if args.search:
            needle = args.search.casefold()
            sources = [
                src
                for src in sources
                if needle in src.id.casefold() or needle in src.name.casefold()
            ]
        if args.json:
            _print_json([asdict(src) for src in sources])
            return 0
        _render_sources(sources)
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    with Nyora() as nyora:
        source = nyora.sources.find(args.source)
        if _wants_all(args):
            entries = list(nyora.manga.iter_search(source.id, args.query, limit=_limit(args)))
            page = SearchPage(entries=entries, has_next_page=False)
        else:
            page = nyora.manga.search(source.id, args.query, args.page)
        _emit_search_page(args, page, title=f"Search: {args.query}")
    return 0


def _cmd_popular(args: argparse.Namespace) -> int:
    with Nyora() as nyora:
        source = nyora.sources.find(args.source)
        if _wants_all(args):
            entries = list(nyora.manga.iter_popular(source.id, limit=_limit(args)))
            page = SearchPage(entries=entries, has_next_page=False)
        else:
            page = nyora.manga.popular(source.id, args.page)
        _emit_search_page(args, page, title=f"Popular ({source.name})")
    return 0


def _cmd_latest(args: argparse.Namespace) -> int:
    with Nyora() as nyora:
        source = nyora.sources.find(args.source)
        if _wants_all(args):
            entries = list(nyora.manga.iter_latest(source.id, limit=_limit(args)))
            page = SearchPage(entries=entries, has_next_page=False)
        else:
            page = nyora.manga.latest(source.id, args.page)
        _emit_search_page(args, page, title=f"Latest ({source.name})")
    return 0


def _wants_all(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "all", False) or getattr(args, "limit", None))


def _limit(args: argparse.Namespace) -> int | None:
    return None if getattr(args, "all", False) else getattr(args, "limit", None)


def _cmd_details(args: argparse.Namespace) -> int:
    with Nyora() as nyora:
        source = nyora.sources.find(args.source)
        details = nyora.manga.details(source.id, args.url)
        if args.json:
            _print_json(_dataclass_json(details))
            return 0
        _render_details(details)
    return 0


def _cmd_pages(args: argparse.Namespace) -> int:
    with Nyora() as nyora:
        source = nyora.sources.find(args.source)
        pages = nyora.manga.pages(source.id, args.chapter_url, branch=args.branch)
        if args.json:
            _print_json([asdict(page) for page in pages])
            return 0
        console = _console()
        console.print(
            f"[nyora.brand]{_FLOWER}[/] [nyora.title]Pages[/] [nyora.muted]({len(pages)})[/]"
        )
        for index, page in enumerate(pages, start=1):
            console.print(f"[nyora.index]{index:>4}[/]  [nyora.link]{escape(page.url)}[/]")
    return 0


def _cmd_download(args: argparse.Namespace) -> int:
    with Nyora() as nyora:
        source = nyora.sources.find(args.source)
        pages = nyora.manga.pages(source.id, args.chapter_url, branch=args.branch)
        if not pages:
            _error("no pages to download")
            return 1
        cbz_path = _resolve_cbz_path(args.out, _slug_from_url(args.chapter_url))
        saved, total = _download_with_progress(pages, cbz_path, quiet=args.json)

    if saved == 0:
        _error("no pages could be downloaded")
        return 1
    if args.json:
        _print_json({"file": str(cbz_path), "pages": saved, "total": total})
    else:
        _say_saved(cbz_path, saved, total)
    return 0


def _cmd_open(args: argparse.Namespace) -> int:
    with Nyora() as nyora:
        source = nyora.sources.find(args.source)
        pages = nyora.manga.pages(source.id, args.chapter_url, branch=args.branch)
        if not pages:
            _error("no pages to download")
            return 1
        cbz_path = _resolve_cbz_path(args.out, _slug_from_url(args.chapter_url))
        saved, total = _download_with_progress(pages, cbz_path, quiet=False)
    if saved == 0:
        _error("no pages could be downloaded")
        return 1
    _say_saved(cbz_path, saved, total)
    _open_file(cbz_path)
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    # With --json we stay silent until the final manifest: progress bars and
    # status lines both go to stdout, so emitting them would corrupt the JSON.
    json_out = bool(args.json)
    with Nyora() as nyora:
        source = nyora.sources.find(args.source)
        if not json_out:
            _say("[nyora.muted]fetching details…[/]")
        details = nyora.manga.details(source.id, args.manga_url)
        chapters = details.reading_order()
        if not chapters:
            _fail(args, "no chapters found for this manga")
            return 1
        if args.chapter_range:
            try:
                chapters = _apply_range(chapters, args.chapter_range)
            except ValueError as exc:
                _fail(args, str(exc))
                return 2
            if not chapters:
                _fail(args, "range selected no chapters")
                return 1

        base_out_dir = Path(args.out).expanduser()
        base_out_dir.mkdir(parents=True, exist_ok=True)
        total = len(chapters)
        if not json_out:
            _say(
                f"[nyora.brand]{_FLOWER}[/] downloading [nyora.title]{total}[/] chapters → "
                f"[nyora.link]{escape(str(base_out_dir))}[/]"
            )

        downloaded: list[dict[str, Any]] = []
        total_pages = 0
        for i, chapter in enumerate(chapters, start=1):
            label = chapter.title or chapter.id
            cbz_path = base_out_dir / f"{_safe_name(label) or f'chapter-{i:04d}'}.cbz"
            try:
                pages = nyora.manga.pages(source.id, chapter.url, branch=chapter.branch)
                if not pages:
                    if not json_out:
                        _error(f"[{i}/{total}] no pages: {label}")
                    continue
                saved, page_total = _download_with_progress(
                    pages, cbz_path, label=f"[{i}/{total}] {label}", quiet=json_out
                )
                if saved:
                    total_pages += saved
                    downloaded.append(
                        {
                            "chapter": label,
                            "file": str(cbz_path),
                            "pages": saved,
                            "total": page_total,
                        }
                    )
            except Exception as exc:  # noqa: BLE001 - keep batch going past one bad chapter
                if not json_out:
                    _error(f"[{i}/{total}] {label}: {exc}")

    if json_out:
        _print_json(
            {
                "source": source.id,
                "manga": {"title": details.manga.title, "url": details.manga.url},
                "out_dir": str(base_out_dir),
                "downloaded": downloaded,
            }
        )
    else:
        _say(
            f"[nyora.ok]✓[/] {len(downloaded)} archives, {total_pages} pages → "
            f"[nyora.link]{escape(str(base_out_dir))}[/]"
        )
    return 0


def _cmd_grab(args: argparse.Namespace) -> int:
    """One-shot: search a source, take the first match, download chapter(s).

    Collapses ``search`` -> ``details`` -> ``download`` into a single engine
    session — ideal for scripts and AI agents. Emits a machine-readable manifest
    with ``--json``.
    """
    with Nyora() as nyora:
        source = nyora.sources.find(args.source)
        results = nyora.manga.search(source.id, args.query)
        if not results.entries:
            _fail(args, f"no results for {args.query!r} on {source.name}")
            return 1
        manga = results.entries[0]
        details = nyora.manga.details(source.id, manga.url)
        chapters = details.reading_order()
        if not chapters:
            _fail(args, "no chapters found")
            return 1

        if args.all:
            selected = chapters
        elif args.chapter_range:
            try:
                selected = _apply_range(chapters, args.chapter_range)
            except ValueError as exc:
                _fail(args, str(exc))
                return 2
        else:
            n = args.chapter or 1
            if not 1 <= n <= len(chapters):
                _fail(args, f"chapter {n} out of range (1..{len(chapters)})")
                return 1
            selected = [chapters[n - 1]]

        out_dir = (
            Path(args.out).expanduser()
            if args.out
            else Path(_safe_name(details.manga.title) or "manga")
        )
        out_dir.mkdir(parents=True, exist_ok=True)

        downloaded: list[dict[str, Any]] = []
        for i, chapter in enumerate(selected, start=1):
            pages = nyora.manga.pages(source.id, chapter.url, branch=chapter.branch)
            if not pages:
                continue
            label = chapter.title or chapter.id
            cbz = out_dir / f"{_safe_name(label) or f'chapter-{i:04d}'}.cbz"
            saved, total = _download_with_progress(pages, cbz, label=label, quiet=args.json)
            if saved:
                downloaded.append(
                    {"chapter": label, "file": str(cbz), "pages": saved, "total": total}
                )

    result = {
        "source": source.id,
        "manga": {"title": details.manga.title, "url": details.manga.url},
        "out_dir": str(out_dir),
        "downloaded": downloaded,
    }
    if args.json:
        _print_json(result)
    elif downloaded:
        _say(
            f"[nyora.ok]✓[/] grabbed [nyora.title]{len(downloaded)}[/] chapter(s) of "
            f"[nyora.title]{escape(details.manga.title)}[/] → [nyora.link]{escape(str(out_dir))}[/]"
        )
    else:
        _error("nothing downloaded")
    return 0 if downloaded else 1


def _cmd_completion(args: argparse.Namespace) -> int:
    """Print shell completion setup (powered by argcomplete)."""
    import os

    shell = args.shell or Path(os.environ.get("SHELL", "")).name or "bash"
    _print(f"# Nyora completion for {shell} — add this line to your shell config:")
    if shell == "fish":
        _print("register-python-argcomplete --shell fish nyora | source")
    else:
        _print(f'eval "$(register-python-argcomplete nyora)"   # ~/.{shell}rc')
    return 0


def _cmd_version(args: argparse.Namespace) -> int:
    package_version = _package_version()
    if args.json:
        _print_json({"package": package_version})
        return 0
    _say(f"[nyora.brand]{_FLOWER} nyora[/] [nyora.muted]v[/]{package_version}")
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    """Show or set the persisted server URL — point the SDK/CLI/TUI anywhere."""
    from nyora.client import _resolve_base_url
    from nyora.config import config_file, read_config, set_config_base_url

    action = getattr(args, "action", "show")
    if action == "set-url":
        if not args.value:
            _print("usage: nyora config set-url <URL>   (e.g. http://127.0.0.1:8788)")
            return 2
        set_config_base_url(args.value)
        _say(f"[nyora.ok]✓[/] server URL set to [nyora.link]{escape(args.value.rstrip('/'))}[/]")
        _say(f"  [nyora.muted]saved in {escape(str(config_file()))}[/]")
        return 0
    if action == "unset-url":
        set_config_base_url(None)
        _say(
            "[nyora.ok]✓[/] server URL cleared — a bare `nyora` now auto-launches its "
            "bundled engine."
        )
        return 0
    if action == "path":
        _print(str(config_file()))
        return 0
    # show
    cfg = read_config()
    resolved = _resolve_base_url(None)
    if args.json:
        _print_json({
            "config_file": str(config_file()),
            "configured": cfg.get("base_url"),
            "effective": resolved,
            "self_contained": resolved is None,
        })
        return 0
    console = _console()
    effective = (
        f"[nyora.link]{escape(resolved)}[/]"
        if resolved
        else "[nyora.muted](none) → auto-launches a local bundled engine[/]"
    )
    console.print(f"[nyora.muted]config file  [/] {escape(str(config_file()))}")
    console.print(f"[nyora.muted]configured   [/] {escape(cfg.get('base_url') or '(none)')}")
    console.print(f"[nyora.muted]effective URL[/] {effective}")
    console.print("\n[nyora.muted]Set your own server:[/]  nyora config set-url http://127.0.0.1:8788")
    console.print(
        "[nyora.muted]Standalone server:  [/]  "
        "pipx install nyora-extension-server && nyora-extension-server"
    )
    return 0


def _cmd_upgrade(args: argparse.Namespace) -> int:
    """Self-upgrade the installed ``nyora`` package (works for pip and pipx)."""
    import subprocess
    import sys

    _say(f"[nyora.brand]{_FLOWER}[/] upgrading nyora to the latest release …")
    result = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "nyora"])
    if result.returncode == 0:
        _say("[nyora.ok]✓[/] done — run `nyora version` to confirm.")
        return 0
    _error("upgrade failed. Try manually:  pip install -U nyora   (pipx: pipx upgrade nyora)")
    return 1


def _cmd_blocklist(args: argparse.Namespace) -> int:
    """Show / rebuild the per-server blocklist — auto-generates for your server."""
    from nyora.blocked_sources import (
        blocklist_cache_file,
        generate_blocklist,
        load_server_blocklist,
    )

    action = getattr(args, "action", "show")
    with Nyora() as nyora:
        base = getattr(nyora, "base_url", None)
        if action == "refresh":
            _say(
                f"[nyora.brand]{_FLOWER}[/] probing sources on "
                f"[nyora.link]{escape(str(base))}[/] (a few minutes)…"
            )

            def _progress(done: int, total: int, dead: int) -> None:
                if done == total or done % 25 == 0:
                    _err_console().print(
                        f"  [nyora.muted]{done}/{total} probed · {dead} dead[/]"
                    )

            dead = generate_blocklist(nyora, on_progress=_progress)
            _say(
                f"[nyora.ok]✓[/] {len(dead)} sources blocked "
                f"[nyora.muted]· cached at {escape(str(blocklist_cache_file(base)))}[/]"
            )
            return 0
        if action == "clear":
            path = blocklist_cache_file(base)
            if path.exists():
                path.unlink()
            _say(
                f"[nyora.ok]✓[/] cleared the generated blocklist for "
                f"[nyora.link]{escape(str(base))}[/]"
            )
            return 0
        cache = load_server_blocklist(base)
        if cache is None:
            _say(f"[nyora.muted]no generated blocklist for {escape(str(base))}[/]")
            _say("[nyora.muted]build one:[/]  nyora blocklist refresh")
        else:
            _say(
                f"[nyora.title]{len(cache)}[/] sources blocked for "
                f"[nyora.link]{escape(str(base))}[/]"
            )
            _say(f"  [nyora.muted]cache: {escape(str(blocklist_cache_file(base)))}[/]")
    return 0


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _download_cbz(
    pages: list[MangaPage],
    cbz_path: Path,
    *,
    on_progress: Callable[[int, int], None] | None = None,
    workers: int = 6,
) -> tuple[int, int]:
    """Download pages concurrently and pack them into an in-order ``.cbz``.

    A CBZ is a ZIP of page images; images are already compressed, so the archive
    uses ``STORE``. Pages are fetched with a small thread pool but written in
    reading order. ``on_progress(done, total)`` fires as each page settles.
    Returns ``(saved, total)``; nothing is written if no page could be fetched.
    """
    total = len(pages)
    width = len(str(total))
    # Preallocate by page index: threads finish out of order, but slotting each
    # result at its index keeps the archive in reading order regardless.
    results: list[tuple[str, bytes] | None] = [None] * total
    done = 0

    def fetch(index: int, page: MangaPage) -> tuple[int, tuple[str, bytes] | None]:
        try:
            response = client.get(page.url, headers=_page_headers(page))
            response.raise_for_status()
        except httpx.HTTPError:
            return index, None
        suffix = _suffix_for(page.url, response.headers.get("content-type", ""))
        return index, (f"{index + 1:0{width}d}{suffix}", response.content)

    client = httpx.Client(follow_redirects=True, timeout=60.0)
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(fetch, i, p) for i, p in enumerate(pages)]
            for future in as_completed(futures):
                index, item = future.result()
                results[index] = item
                done += 1
                if on_progress:
                    on_progress(done, total)
    finally:
        client.close()

    saved = [item for item in results if item is not None]
    if not saved:
        return 0, total
    cbz_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(cbz_path, "w", zipfile.ZIP_STORED) as archive:
        for item in results:
            if item is not None:
                archive.writestr(item[0], item[1])
    return len(saved), total


def _download_with_progress(
    pages: list[MangaPage], cbz_path: Path, *, label: str | None = None, quiet: bool = False
) -> tuple[int, int]:
    """Download a chapter, showing a Rich progress bar unless ``quiet``."""
    label = label or cbz_path.name
    if quiet:
        return _download_cbz(pages, cbz_path)

    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn

    with Progress(
        TextColumn("[nyora.title]{task.description}"),
        BarColumn(complete_style="nyora.border", finished_style="nyora.ok"),
        MofNCompleteColumn(),
        TextColumn("[nyora.muted]pages[/]"),
        console=_console(),
        transient=True,
    ) as progress:
        task = progress.add_task(_truncate(label, 40), total=len(pages))
        result = _download_cbz(
            pages, cbz_path, on_progress=lambda done, total: progress.update(task, completed=done)
        )
    saved, total = result
    tick = "nyora.ok" if saved == total else "nyora.warn"
    _say(f"  [{tick}]•[/] {escape(cbz_path.name)}  [nyora.muted]({saved}/{total} pages)[/]")
    return result


def _apply_range(chapters: list[Any], spec: str) -> list[Any]:
    """Slice ``chapters`` (reading order) by a 1-based ``A-B`` spec (``5-``, ``-3``)."""
    if "-" not in spec:
        raise ValueError(f"invalid range {spec!r}; use A-B, A- or -B (e.g. 1-10)")
    lo_str, hi_str = spec.split("-", 1)
    try:
        lo = int(lo_str) if lo_str.strip() else 1
        hi = int(hi_str) if hi_str.strip() else len(chapters)
    except ValueError:
        raise ValueError(f"invalid range {spec!r}; A and B must be integers") from None
    return chapters[max(0, lo - 1) : hi]


def _open_file(path: Path) -> None:
    """Open ``path`` in the OS default application (best-effort)."""
    import subprocess

    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        elif sys.platform.startswith("win"):
            import os

            os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as exc:  # noqa: BLE001 - opening is a convenience, never fatal
        _error(f"could not open {path}: {exc}")


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _resolve_cbz_path(out: str | None, slug: str) -> Path:
    """Resolve the ``-o/--out`` value to a concrete ``.cbz`` file path.

    ``None`` -> ``<slug>.cbz`` in the current directory; a value ending in
    ``.cbz`` is used verbatim; anything else is treated as a directory that will
    contain ``<slug>.cbz``.
    """
    name = f"{slug}.cbz"
    if out is None:
        return Path(name)
    target = Path(out).expanduser()
    if target.suffix.lower() == ".cbz":
        return target
    return target / name


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    segment = path.rsplit("/", 1)[-1] if path else ""
    return _safe_name(segment) or "chapter"


def _safe_name(value: str) -> str:
    cleaned = "".join(c if (c.isalnum() or c in "._-") else "_" for c in value)
    return cleaned.strip("_")[:120]


def _page_headers(page: MangaPage) -> dict[str, str]:
    """Headers for fetching a page image: browser UA + the source's own headers.

    Many image CDNs reject hotlinking, so when the source didn't supply a
    ``Referer`` we synthesize one from the image's own origin.
    """
    headers: dict[str, str] = {"User-Agent": BROWSER_UA}
    headers.update({str(key): str(value) for key, value in page.headers.items()})
    if "Referer" not in headers:
        parsed = urlparse(page.url)
        if parsed.scheme and parsed.netloc:
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
    return headers


def _suffix_for(url: str, content_type: str) -> str:
    path = urlparse(url).path
    ext = Path(path).suffix
    if ext and len(ext) <= 5:
        return ext
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/avif": ".avif",
    }
    return mapping.get(content_type.split(";", 1)[0].strip().lower(), ".jpg")


def _emit_search_page(args: argparse.Namespace, page: SearchPage, *, title: str) -> None:
    if args.json:
        _print_json(_dataclass_json(page))
        return
    _render_entries(page.entries, title=title, has_next=page.has_next_page)


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("nyora")
    except Exception:  # pragma: no cover - source checkout without metadata
        return "0.0.0"


def _dataclass_json(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    return obj


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def _rating(value: float) -> str:
    """Render a normalized 0..1 rating as an amber five-star score, or a dim ``—``."""
    if value is not None and value >= 0:
        return f"[nyora.rating]{value * 5:.1f}★[/]"
    return "[nyora.muted]—[/]"


def _flags(*, nsfw: bool = False, pinned: bool = False) -> str:
    return ("[nyora.pin]★[/] " if pinned else "") + ("[nyora.nsfw]18+[/]" if nsfw else "")


def _render_sources(sources: list[Source]) -> None:
    table = _table("Sources", len(sources))
    table.add_column("id", style="nyora.link", no_wrap=True)
    table.add_column("name")
    table.add_column("lang", style="nyora.lang", justify="center")
    table.add_column("", justify="center")
    for src in sources:
        # 18+ source names glow red so mature sources read at a glance.
        name = f"[nyora.nsfw]{escape(src.name)}[/]" if src.is_nsfw else escape(src.name)
        table.add_row(
            src.id, name, src.lang, _flags(nsfw=src.is_nsfw, pinned=src.is_pinned)
        )
    _console().print(table)


def _render_entries(entries: list[Manga], *, title: str, has_next: bool) -> None:
    table = _table(title, len(entries))
    if has_next:
        table.caption = "[nyora.muted]more pages available — pass -p/--page or --all[/]"
        table.caption_justify = "left"
    table.add_column("#", style="nyora.index", justify="right")
    table.add_column("title")
    table.add_column("rating", justify="right")
    table.add_column("", justify="center")
    table.add_column("url", style="nyora.link", no_wrap=False)
    for index, manga in enumerate(entries, start=1):
        table.add_row(
            str(index), escape(manga.title), _rating(manga.rating),
            _flags(nsfw=manga.is_nsfw), escape(manga.url),
        )
    _console().print(table)


def _render_details(details: MangaDetails) -> None:
    manga = details.manga
    console = _console()
    badge = "  [nyora.nsfw]18+[/]" if manga.is_nsfw else ""
    console.print(f"\n[nyora.brand]{_FLOWER}[/] [nyora.title]{escape(manga.title)}[/]{badge}")
    meta = []
    if manga.rating is not None and manga.rating >= 0:
        meta.append(f"[nyora.muted]rating[/] {_rating(manga.rating)}")
    if manga.state:
        meta.append(f"[nyora.muted]state[/] {escape(manga.state)}")
    if manga.authors:
        meta.append(f"[nyora.muted]authors[/] {escape(', '.join(manga.authors))}")
    if meta:
        console.print("   ".join(meta))
    if manga.tags:
        tags = ", ".join(str(tag.get("title") or tag.get("name") or "") for tag in manga.tags)
        console.print(f"[nyora.muted]tags[/] {escape(tags)}")
    if manga.description:
        console.print(f"\n{escape(manga.description)}\n")
    table = _table("Chapters", len(details.chapters))
    table.add_column("#", style="nyora.index", justify="right")
    table.add_column("title")
    table.add_column("url", style="nyora.link")
    for index, chapter in enumerate(details.chapters, start=1):
        table.add_row(str(index), escape(chapter.title or chapter.id), escape(chapter.url))
    console.print(table)


# --------------------------------------------------------------------------- #
# Output primitives
# --------------------------------------------------------------------------- #


_CONSOLE: Console | None = None
_ERR_CONSOLE: Console | None = None


def _console() -> Console:
    """The shared, Sakura-themed stdout console (created once).

    ``highlight=False`` disables Rich's automatic repr/number/path colouring so
    only our explicit palette shows — the CLI's look is fully intentional.
    """
    global _CONSOLE
    if _CONSOLE is None:
        _CONSOLE = Console(theme=_build_theme(), highlight=False)
    return _CONSOLE


def _err_console() -> Console:
    global _ERR_CONSOLE
    if _ERR_CONSOLE is None:
        _ERR_CONSOLE = Console(theme=_build_theme(), stderr=True, highlight=False)
    return _ERR_CONSOLE


def _table(title: str, count: int | None = None) -> Table:
    """A branded table: rounded rose border, sakura title, pink headers."""
    heading = f"[nyora.brand]{_FLOWER}[/] [nyora.title]{escape(title)}[/]"
    if count is not None:
        heading += f" [nyora.muted]({count})[/]"
    return Table(
        title=heading,
        title_justify="left",
        box=box.ROUNDED,
        border_style="nyora.border",
        header_style="nyora.header",
        pad_edge=False,
        padding=(0, 1),
    )


def _print(message: str) -> None:
    print(message)


def _say(markup: str) -> None:
    """Print a styled status line through the themed console."""
    _console().print(markup)


def _say_saved(path: Path, saved: int, total: int) -> None:
    """The shared 'saved N/M pages → path' success line."""
    _say(
        f"[nyora.ok]✓[/] saved [nyora.rating]{saved}[/]/{total} pages "
        f"→ [nyora.link]{escape(str(path))}[/]"
    )


def _print_json(payload: Any) -> None:
    # JSON is a data contract: emit it raw, never through the themed console
    # (no colour codes, no soft-wrapping) so pipes and parsers stay clean.
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _error(message: str) -> None:
    _err_console().print(f"[nyora.err]✗[/] {escape(message)}")


def _fail(args: argparse.Namespace, message: str) -> None:
    """Report a failure — as ``{"error": ...}`` JSON when ``--json``, else stderr."""
    if getattr(args, "json", False):
        _print_json({"error": message})
    else:
        _error(message)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
