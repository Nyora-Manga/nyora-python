"""Command-line interface for the Nyora SDK.

Exposes the Nyora cloud helper through a small argparse-based command tree: list
sources, run popular/latest/search, fetch manga details and chapter pages,
download chapters as .cbz, and show the version. Running ``nyora-cli`` with no
subcommand launches the interactive terminal reader (TUI).
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from nyora.client import Nyora
from nyora.errors import NyoraError
from nyora.models import Manga, MangaDetails, MangaPage, SearchPage, Source

#: User-Agent for direct image downloads (the cloud helper rewrites cover/page
#: hosts; a browser UA keeps CDNs happy).
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

try:  # pragma: no cover - rich is an optional/tui extra
    from rich.console import Console
    from rich.table import Table

    _RICH = True
except ImportError:  # pragma: no cover
    Console = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]
    _RICH = False


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``nyora-cli`` command.

    When invoked with **no subcommand** (``nyora-cli`` on its own, or an
    otherwise-empty ``argv``), launch the interactive terminal reader by
    delegating to :func:`nyora_tui.app.main` and return its exit code (``0`` on
    a clean exit). Every existing subcommand
    (``sources``/``search``/``popular``/``latest``/``details``/``pages``/
    ``download``/``update``/``serve``/``version``) keeps working unchanged, and
    ``nyora-cli --help`` still lists them.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        return _launch_tui()

    try:
        return args.handler(args)
    except (NyoraError, LookupError) as exc:
        _error(str(exc))
        return 1
    except KeyboardInterrupt:  # pragma: no cover - interactive
        _error("interrupted")
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
    sub = parser.add_subparsers(dest="command", metavar="command")

    p_sources = sub.add_parser("sources", help="list or search available sources")
    p_sources.add_argument("--search", metavar="Q", default=None, help="filter sources by text")
    p_sources.set_defaults(handler=_cmd_sources)

    p_search = sub.add_parser("search", help="search a source")
    _add_source_arg(p_search)
    p_search.add_argument("-p", "--page", type=int, default=1, help="page number (default: 1)")
    p_search.add_argument("query", help="search query")
    p_search.set_defaults(handler=_cmd_search)

    p_popular = sub.add_parser("popular", help="list popular manga from a source")
    _add_source_arg(p_popular)
    p_popular.add_argument("-p", "--page", type=int, default=1, help="page number (default: 1)")
    p_popular.set_defaults(handler=_cmd_popular)

    p_latest = sub.add_parser("latest", help="list latest manga from a source")
    _add_source_arg(p_latest)
    p_latest.add_argument("-p", "--page", type=int, default=1, help="page number (default: 1)")
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
    p_batch.add_argument("manga_url", help="manga URL")
    p_batch.set_defaults(handler=_cmd_batch)

    p_version = sub.add_parser("version", help="show package version")
    p_version.set_defaults(handler=_cmd_version)

    return parser


def _add_source_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-s",
        "--source",
        required=True,
        metavar="SRC",
        help="source id or fuzzy name",
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
        page = nyora.manga.search(source.id, args.query, args.page)
        _emit_search_page(args, page, title=f"Search: {args.query}")
    return 0


def _cmd_popular(args: argparse.Namespace) -> int:
    with Nyora() as nyora:
        source = nyora.sources.find(args.source)
        page = nyora.manga.popular(source.id, args.page)
        _emit_search_page(args, page, title=f"Popular ({source.name})")
    return 0


def _cmd_latest(args: argparse.Namespace) -> int:
    with Nyora() as nyora:
        source = nyora.sources.find(args.source)
        page = nyora.manga.latest(source.id, args.page)
        _emit_search_page(args, page, title=f"Latest ({source.name})")
    return 0


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
        for index, page in enumerate(pages, start=1):
            _print(f"{index:>4}  {page.url}")
    return 0


def _cmd_download(args: argparse.Namespace) -> int:
    with Nyora() as nyora:
        source = nyora.sources.find(args.source)
        pages = nyora.manga.pages(source.id, args.chapter_url, branch=args.branch)
        if not pages:
            _error("no pages to download")
            return 1
        cbz_path = _resolve_cbz_path(args.out, _slug_from_url(args.chapter_url))
        saved, total = _download_cbz(pages, cbz_path)

    if saved == 0:
        _error("no pages could be downloaded")
        return 1
    if args.json:
        _print_json({"file": str(cbz_path), "pages": saved, "total": total})
    else:
        _print(f"Saved {saved}/{total} pages to {cbz_path}")
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    with Nyora() as nyora:
        source = nyora.sources.find(args.source)
        _print("Fetching manga details...")
        details = nyora.manga.details(source.id, args.manga_url)
        if not details.chapters:
            _error("no chapters found for this manga")
            return 1

        base_out_dir = Path(args.out).expanduser()
        base_out_dir.mkdir(parents=True, exist_ok=True)
        total = len(details.chapters)
        _print(f"Found {total} chapters. Saving .cbz archives to {base_out_dir}...")

        archives = 0
        total_pages = 0
        for i, chapter in enumerate(details.chapters, start=1):
            label = chapter.title or chapter.id
            _print(f"\n[{i}/{total}] Downloading {label}...")
            cbz_path = base_out_dir / f"{_safe_name(label) or f'chapter-{i:04d}'}.cbz"
            try:
                pages = nyora.manga.pages(source.id, chapter.url, branch=chapter.branch)
                if not pages:
                    _error(f"no pages found for chapter {label}")
                    continue
                saved, _ = _download_cbz(pages, cbz_path)
                if saved:
                    archives += 1
                    total_pages += saved
                    _print(f"  -> {cbz_path.name} ({saved} pages)")
            except Exception as exc:  # noqa: BLE001 - keep batch going past one bad chapter
                _error(f"failed to download chapter {label}: {exc}")

    _print(f"\nBatch complete. Wrote {archives} .cbz archives ({total_pages} pages total).")
    return 0


def _cmd_version(args: argparse.Namespace) -> int:
    package_version = _package_version()
    if args.json:
        _print_json({"package": package_version})
        return 0
    _print(f"nyora {package_version}")
    return 0


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _download_cbz(pages: list[MangaPage], cbz_path: Path) -> tuple[int, int]:
    """Download every page and pack them into a single ``.cbz`` archive.

    A CBZ is a ZIP of in-order image files. Images are already compressed, so the
    archive uses the ``STORE`` method. Returns ``(saved, total)``; the archive is
    not written if no page could be fetched.
    """
    cbz_path.parent.mkdir(parents=True, exist_ok=True)
    width = len(str(len(pages)))
    saved = 0
    with (
        httpx.Client(follow_redirects=True, timeout=60.0) as client,
        zipfile.ZipFile(cbz_path, "w", zipfile.ZIP_STORED) as archive,
    ):
        for index, page in enumerate(pages, start=1):
            headers = _page_headers(page)
            try:
                response = client.get(page.url, headers=headers)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                _error(f"page {index}: {exc}")
                continue
            suffix = _suffix_for(page.url, response.headers.get("content-type", ""))
            archive.writestr(f"{index:0{width}d}{suffix}", response.content)
            saved += 1
    if saved == 0:
        cbz_path.unlink(missing_ok=True)
    return saved, len(pages)


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


def _render_sources(sources: list[Source]) -> None:
    if _RICH:
        from rich.markup import escape
        table = Table(title=f"Sources ({len(sources)})")
        table.add_column("id", style="cyan", no_wrap=True)
        table.add_column("name")
        table.add_column("lang", style="green")
        for src in sources:
            table.add_row(src.id, escape(src.name), src.lang)
        _console().print(table)
        return
    for src in sources:
        _print(f"{src.id}\t{src.name}\t{src.lang}")
    _print(f"({len(sources)} sources)")


def _render_entries(entries: list[Manga], *, title: str, has_next: bool) -> None:
    if _RICH:
        from rich.markup import escape
        table = Table(title=f"{escape(title)} ({len(entries)})")
        table.add_column("#", style="dim", justify="right")
        table.add_column("title")
        table.add_column("url", style="blue", no_wrap=False)
        for index, manga in enumerate(entries, start=1):
            table.add_row(str(index), escape(manga.title), escape(manga.url))
        _console().print(table)
        if has_next:
            _console().print("[dim]more pages available[/dim]")
        return
    for index, manga in enumerate(entries, start=1):
        _print(f"{index:>4}  {manga.title}\t{manga.url}")
    _print(f"({len(entries)} entries{', more available' if has_next else ''})")


def _render_details(details: MangaDetails) -> None:
    manga = details.manga
    if _RICH:
        from rich.markup import escape
        console = _console()
        console.print(f"[bold]{escape(manga.title)}[/bold]")
        if manga.authors:
            console.print(f"[dim]Authors:[/dim] {escape(', '.join(manga.authors))}")
        if manga.state:
            console.print(f"[dim]State:[/dim] {escape(manga.state)}")
        if manga.tags:
            tags = ", ".join(str(tag.get("title") or tag.get("name") or "") for tag in manga.tags)
            console.print(f"[dim]Tags:[/dim] {escape(tags)}")
        if manga.description:
            console.print(f"\n{escape(manga.description)}\n")
        table = Table(title=f"Chapters ({len(details.chapters)})")
        table.add_column("#", style="dim", justify="right")
        table.add_column("title")
        table.add_column("url", style="blue")
        for index, chapter in enumerate(details.chapters, start=1):
            table.add_row(str(index), escape(chapter.title or chapter.id), escape(chapter.url))
        console.print(table)
        return
    _print(manga.title)
    if manga.authors:
        _print(f"Authors: {', '.join(manga.authors)}")
    if manga.state:
        _print(f"State: {manga.state}")
    if manga.description:
        _print(f"\n{manga.description}\n")
    _print(f"Chapters ({len(details.chapters)}):")
    for index, chapter in enumerate(details.chapters, start=1):
        _print(f"{index:>4}  {chapter.title}\t{chapter.url}")


# --------------------------------------------------------------------------- #
# Output primitives
# --------------------------------------------------------------------------- #


def _console() -> Any:
    return Console()


def _print(message: str) -> None:
    print(message)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
