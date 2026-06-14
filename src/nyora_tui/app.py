"""Interactive terminal reader for Nyora's embedded parser runtime.

Provides three progressively-degrading frontends sharing the same navigation
flow (pick source -> search/popular -> browse results -> details + chapters ->
chapter pages):

* a full-screen ``textual`` app when ``textual`` is importable;
* a ``rich``-based interactive prompt fallback;
* a plain-text ``input()`` fallback when neither is available.

All three drive :class:`nyora.direct.Nyora`, the independent JS runtime, and
degrade gracefully on network/parse errors instead of crashing.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from nyora import Nyora

if TYPE_CHECKING:
    from nyora.models import MangaDetails, SearchPage, Source

_INSTALL_HINT = 'Install TUI dependencies with: pip install "nyora[tui]"'


def _has_interactive_terminal() -> bool:
    """Return ``True`` only when stdout (and stdin) look like a real TTY.

    The interactive reader requires a terminal to draw to and read keystrokes
    from. When stdout is redirected to a pipe/file (``sys.stdout.isatty()`` is
    ``False``) — as happens under CI, ``nyora-cli | cat``, or non-interactive
    shells — launching textual/rich would crash. We detect that here so the
    caller can print a friendly notice and exit cleanly instead.
    """
    stdout = getattr(sys, "stdout", None)
    stdin = getattr(sys, "stdin", None)
    try:
        if stdout is None or not stdout.isatty():
            return False
        if stdin is not None and not stdin.isatty():
            return False
    except Exception:  # noqa: BLE001 - some stream stubs raise on isatty()
        return False
    return True


# --------------------------------------------------------------------------- #
# Shared data helpers (frontend-agnostic, never raise to the UI layer).
# --------------------------------------------------------------------------- #
def _safe(fn, *args, **kwargs):
    """Run ``fn`` and return ``(result, None)`` or ``(None, message)``."""
    try:
        return fn(*args, **kwargs), None
    except Exception as exc:  # noqa: BLE001 - UI must never crash on parse/net errors
        return None, f"{type(exc).__name__}: {exc}"


def _list_sources(client: Nyora) -> list[Source]:
    sources = client.sources.list()
    sources.sort(key=lambda s: (s.name or s.id).casefold())
    return sources


def _filter_sources(sources: list[Source], query: str) -> list[Source]:
    needle = query.casefold().strip()
    if not needle:
        return sources
    return [s for s in sources if needle in s.id.casefold() or needle in s.name.casefold()]


def _fetch_results(client: Nyora, source_id: str, query: str, page: int) -> SearchPage:
    if query.strip():
        return client.manga.search(source_id, query.strip(), page=page)
    return client.manga.popular(source_id, page=page)


def _fetch_details(client: Nyora, source_id: str, url: str, title: str) -> MangaDetails:
    return client.manga.details(source_id, url, title=title)


def _fetch_pages(client: Nyora, source_id: str, url: str, branch: str | None):
    return client.manga.pages(source_id, url, branch=branch)


# --------------------------------------------------------------------------- #
# Frontend selection.
# --------------------------------------------------------------------------- #
def main() -> int:
    """Entry point for the ``nyora-tui`` console script (and bare ``nyora-cli``).

    Selects the richest usable frontend (textual -> rich -> plain ``input()``)
    and drives the shared source -> results -> details -> pages navigation flow,
    all backed by :class:`nyora.direct.Nyora`.

    Safe to launch from a non-interactive context: when no interactive terminal
    is attached (``sys.stdout`` is not a TTY) the reader does **not** start and
    cannot crash — it prints a short notice explaining that an interactive
    terminal is required and returns ``0``. Returns an exit code (``0`` on a
    clean exit); ``None`` is never returned so callers may treat the result as
    an ``int``.
    """
    if not _has_interactive_terminal():
        _print_no_tty_notice()
        return 0
    try:
        if _run_textual():
            return 0
        if _run_rich():
            return 0
        _run_plain()
    except (KeyboardInterrupt, EOFError):  # pragma: no cover - interactive
        print()
        return 0
    return 0


def _print_no_tty_notice() -> None:
    """Explain that the TUI needs a real terminal and how to launch it."""
    print("Nyora terminal reader needs an interactive terminal (a TTY).")
    print("stdout is not a TTY here (piped, redirected, or non-interactive shell).")
    print("Run 'nyora-cli' (or 'nyora-tui') directly in a terminal to use it.")
    print("For scripting, use subcommands instead, e.g. 'nyora-cli sources'.")


# --------------------------------------------------------------------------- #
# Textual frontend.
# --------------------------------------------------------------------------- #
def _run_textual() -> bool:
    try:
        import textual  # noqa: F401
    except ImportError:
        return False

    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.screen import Screen
    from textual.widgets import (
        Footer, Header, Input, Label, ListItem, ListView,
        Static
    )
    from textual.worker import Worker, WorkerState

    class _Row(ListItem):
        def __init__(self, label: str, payload) -> None:
            super().__init__(Label(label))
            self.payload = payload

    class NyoraTui(App):
        """The main terminal UI application for Nyora.
        
        Provides a macOS-style multi-pane layout to filter sources on the left
        and browse manga search/popular results on the right.
        """
        TITLE = "Nyora"
        SUB_TITLE = "macOS-style Explorer • nyora.pages.dev"
        CSS = """
        Screen { background: $surface; }
        #sidebar { width: 35; border-right: solid $primary; height: 100%; }
        #main { width: 1fr; height: 100%; padding: 0 1; }
        #search-bar { height: 3; margin-bottom: 1; border-bottom: solid $primary-background; }
        #src_filter { width: 1fr; }
        #src_list { height: 1fr; }
        #results { height: 1fr; }
        #status { dock: bottom; padding: 0 1; color: $text-muted; }
        """
        BINDINGS = [
            Binding("q", "quit", "Quit"),
            Binding("escape", "focus_sidebar", "Focus Sources", show=False),
            Binding("ctrl+s", "focus_search", "Search"),
            Binding("ctrl+f", "focus_filter", "Filter"),
        ]

        def __init__(self) -> None:
            super().__init__()
            self._client = Nyora()
            self._sources = []
            self._current_source = None
            self._page = 1
            self._query = ""

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            with Horizontal():
                with Vertical(id="sidebar"):
                    yield Input(placeholder="Filter sources... (ctrl+f)", id="src_filter")
                    yield ListView(id="src_list")
                    yield Static("", id="src_status")
                with Vertical(id="main"):
                    with Horizontal(id="search-bar"):
                        yield Input(placeholder="Search catalogue... (ctrl+s, blank=popular)", id="q")
                    yield ListView(id="results")
                    yield Static("Select a source to browse", id="status")
            yield Footer()

        def action_focus_sidebar(self) -> None:
            self.query_one("#src_list", ListView).focus()

        def action_focus_search(self) -> None:
            self.query_one("#q", Input).focus()

        def action_focus_filter(self) -> None:
            self.query_one("#src_filter", Input).focus()

        def on_mount(self) -> None:
            self._load_sources()
            self.query_one("#src_filter", Input).focus()

        def on_unmount(self) -> None:
            try:
                self._client.close()
            except Exception:
                pass

        def _load_sources(self) -> None:
            sources, err = _safe(_list_sources, self._client)
            status = self.query_one("#src_status", Static)
            if err:
                status.update(f"[red]Failed: {err}[/red]")
                return
            self._sources = sources or []
            status.update(f"{len(self._sources)} sources")
            self._render_sources(self._sources)

        def _render_sources(self, sources) -> None:
            lv = self.query_one("#src_list", ListView)
            lv.clear()
            for s in sources[:500]:
                lang = f" [{s.lang}]" if s.lang else ""
                nsfw = " [red]18+[/red]" if s.is_nsfw else ""
                lv.append(_Row(f"{s.name}{lang}{nsfw}\n[dim]{s.id}[/dim]", s))

        def on_input_changed(self, event: Input.Changed) -> None:
            if event.input.id == "src_filter":
                self._render_sources(_filter_sources(self._sources, event.value))

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "src_filter":
                lv = self.query_one("#src_list", ListView)
                if lv.children:
                    lv.focus()
            elif event.input.id == "q":
                self._query = event.value
                self._page = 1
                if self._current_source:
                    self._fetch_results()

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            lv = event.control
            payload = getattr(event.item, "payload", None)
            if lv.id == "src_list" and payload:
                self._current_source = payload
                self._query = ""
                self._page = 1
                self.query_one("#q", Input).value = ""
                self._fetch_results()
                self.query_one("#q", Input).focus()
            elif lv.id == "results" and payload:
                self.push_screen(DetailsScreen(self._client, self._current_source, payload))

        def _fetch_results(self) -> None:
            self.query_one("#status", Static).update("Loading...")
            self.query_one("#results", ListView).clear()
            self.run_worker(self._do_fetch, exclusive=True, thread=True, name="results")

        def _do_fetch(self):
            return _safe(_fetch_results, self._client, self._current_source.id, self._query, self._page)

        def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
            if event.worker.name != "results" or event.state != WorkerState.SUCCESS:
                return
            page, err = event.worker.result
            status = self.query_one("#status", Static)
            lv = self.query_one("#results", ListView)
            lv.clear()
            if err:
                status.update(f"[red]Error: {err}[/red]")
                return
            for m in page.entries:
                tags = ", ".join(t.get("title", "") for t in m.tags[:3] if t.get("title"))
                meta = f"[dim]{tags}[/dim]" if tags else ""
                lv.append(_Row(f"[b]{m.title}[/b]\n{meta}", m))
            status.update(f"Page {self._page} - {len(page.entries)} entries")

    class DetailsScreen(Screen):
        """Displays full metadata and the chapter list for a selected manga.
        
        Fetches the details lazily on mount via a background worker.
        """
        BINDINGS = [
            Binding("escape", "app.pop_screen", "Back", show=False),
            Binding("b", "app.pop_screen", "Back"),
            Binding("q", "app.quit", "Quit"),
        ]

        def __init__(self, app_client, source, manga) -> None:
            super().__init__()
            self._client = app_client
            self._source = source
            self._manga = manga

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            with Horizontal():
                with Vertical(id="sidebar"):
                    yield Static("Loading details...", id="desc")
                with Vertical(id="main"):
                    yield Static("[b]Chapters[/b]", id="chap_head")
                    yield ListView(id="chapters")
            yield Footer()

        def on_mount(self) -> None:
            self.run_worker(self._do_fetch, exclusive=True, thread=True, name="details")
            self.query_one("#chapters", ListView).focus()

        def _do_fetch(self):
            return _safe(_fetch_details, self._client, self._source.id, self._manga.url, self._manga.title)

        def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
            if event.worker.name != "details" or event.state != WorkerState.SUCCESS:
                return
            details, err = event.worker.result
            if err:
                self.query_one("#desc", Static).update(f"[red]Error: {err}[/red]")
                return
            m = details.manga
            authors = ", ".join(m.authors) if m.authors else "Unknown"
            desc = f"[b]{m.title}[/b]\n\n[b]Authors:[/b] {authors}\n[b]State:[/b] {m.state or 'n/a'}\n\n{m.description or ''}"
            self.query_one("#desc", Static).update(desc)
            self.query_one("#chap_head", Static).update(f"[b]Chapters ({len(details.chapters)})[/b]")
            lv = self.query_one("#chapters", ListView)
            lv.clear()
            for c in details.chapters:
                lv.append(_Row(f"{c.title or c.id} [dim]<{c.branch or '-'}>[/dim]", c))

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            payload = getattr(event.item, "payload", None)
            if payload:
                self.app.push_screen(PagesScreen(self._client, self._source, payload))

    class PagesScreen(Screen):
        """Displays the pages of a single chapter in a continuous scrolling webtoon view.
        
        Fetches the page URLs and dynamically downloads and slices the images to
        support the Kitty terminal graphics protocol natively.
        """
        BINDINGS = [
            Binding("escape", "app.pop_screen", "Back", show=False),
            Binding("b", "app.pop_screen", "Back"),
            Binding("q", "app.quit", "Quit"),
            Binding("j", "scroll_down", "Down", show=False),
            Binding("k", "scroll_up", "Up", show=False),
            Binding("space", "page_down", "Page Down", show=False),
        ]
        CSS = """
        PagesScreen { background: transparent; }
        #pages_container { background: transparent; }
        """
        def __init__(self, client, source, chapter):
            super().__init__()
            self.client, self.source, self.chapter = client, source, chapter
            self._pages = []

        def action_scroll_down(self) -> None:
            self.query_one("#pages_container").scroll_relative(y=3)

        def action_scroll_up(self) -> None:
            self.query_one("#pages_container").scroll_relative(y=-3)

        def action_page_down(self) -> None:
            self.query_one("#pages_container").scroll_page_down()

        def compose(self) -> ComposeResult:
            from textual.containers import VerticalScroll
            yield Header(show_clock=False)
            yield Static(f"[b]{self.chapter.title or self.chapter.id}[/b]")
            with VerticalScroll(id="pages_container"):
                yield Static("Loading...", id="status")
            yield Footer()
        def on_mount(self) -> None:
            self.run_worker(self._do_fetch, exclusive=True, thread=True, name="pages")
        def _do_fetch(self):
            return _safe(_fetch_pages, self.client, self.source.id, self.chapter.url, self.chapter.branch)
        def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
            if event.worker.name == "pages" and event.state == WorkerState.SUCCESS:
                pages, err = event.worker.result
                if err:
                    self.query_one("#status", Static).update(f"Error: {err}")
                    return
                self._pages = pages
                self.query_one("#status", Static).update(f"{len(pages)} pages found. Loading webtoon...")
                self.run_worker(self._download_images, exclusive=True, thread=True, name="images")

        def _download_images(self):
            import io
            import httpx
            from PIL import Image
            from nyora.runtime import BROWSER_UA
            
            http = self.client._runtime._http
            for i, p in enumerate(self._pages):
                try:
                    headers = {"Referer": self.chapter.url, "User-Agent": BROWSER_UA}
                    headers.update(getattr(p, "headers", {}))
                    res = http.get(p.url, headers=headers)
                    if res.status_code == 200:
                        img = Image.open(io.BytesIO(res.content)).convert("RGB")
                        self.app.call_from_thread(self._add_image, img, i)
                    else:
                        self.app.call_from_thread(self._add_error, i, f"HTTP {res.status_code}")
                except Exception as e:
                    self.app.call_from_thread(self._add_error, i, str(e))
            self.app.call_from_thread(self._done)

        def _add_image(self, img, idx):
            container = self.query_one("#pages_container")
            try:
                import os
                term_prog = os.environ.get("TERM_PROGRAM", "").lower()
                term = os.environ.get("TERM", "").lower()
                
                if "ghostty" in term_prog or "kitty" in term_prog or "wezterm" in term_prog or "ghostty" in term or "kitty" in term:
                    from textual_image.widget import TGPImage as TextualImage
                else:
                    from textual_image.widget import Image as TextualImage
                    
                term_w = self.app.console.width
                w, h = img.size
                lines = int(term_w * (h / w) * 0.5)
                
                # textual-image TGPImage crashes if a single image exceeds 169 lines (ValueError: Image too large)
                # Slice the image into chunks of max 150 lines
                max_lines = 150
                if lines > max_lines:
                    max_h_per_chunk = int(max_lines / (term_w * 0.5) * w)
                    for y in range(0, h, max_h_per_chunk):
                        chunk_img = img.crop((0, y, w, min(y + max_h_per_chunk, h)))
                        chunk_w, chunk_h = chunk_img.size
                        widget = TextualImage(chunk_img)
                        widget.styles.width = "100%"
                        chunk_lines = int(term_w * (chunk_h / chunk_w) * 0.5)
                        widget.styles.height = max(1, chunk_lines)
                        container.mount(widget)
                else:
                    widget = TextualImage(img)
                    widget.styles.width = "100%"
                    widget.styles.height = max(1, lines)
                    container.mount(widget)
            except ImportError:
                from PIL import Image as PILImage
                from rich_pixels import Pixels
                term_w = self.app.console.width - 4
                if term_w < 10:
                    term_w = 80
                w, h = img.size
                new_h = int((term_w / w) * h)
                if new_h > 0 and term_w > 0:
                    img = img.resize((term_w, new_h), PILImage.Resampling.LANCZOS)
                px = Pixels.from_image(img)
                container.mount(Static(px))

        def _add_error(self, idx, err):
            container = self.query_one("#pages_container")
            container.mount(Static(f"[red]Failed to load page {idx+1}: {err}[/red]"))

        def _done(self):
            self.query_one("#status", Static).update(f"[green]All {len(self._pages)} pages loaded![/green]")

    NyoraTui().run()
    return True


def _run_rich() -> bool:
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.prompt import Prompt
        from rich.table import Table
        from rich.markup import escape
    except ImportError:
        return False

    console = Console()

    def choose(items: list, render, prompt: str, allow_query: bool = False):
        """Render a numbered list; return (index|None, query_string)."""
        while True:
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("#", justify="right", style="dim")
            for col in render.columns:
                table.add_column(col)
            for i, item in enumerate(items[:60], 1):
                table.add_row(str(i), *[escape(str(x)) for x in render.row(item)])
            console.print(table)
            hint = "number to select"
            if allow_query:
                hint += ", text to (re)search"
            ans = Prompt.ask(f"{prompt} ([dim]{hint}, 'b' back, 'q' quit[/dim])").strip()
            if ans.lower() == "q":
                raise SystemExit(0)
            if ans.lower() == "b":
                return None, None
            if ans.isdigit():
                idx = int(ans) - 1
                if 0 <= idx < min(len(items), 60):
                    return idx, None
                console.print("[red]Out of range.[/red]")
                continue
            if allow_query:
                return None, ans
            console.print("[red]Enter a number.[/red]")

    class _R:
        def __init__(self, columns, row):
            self.columns = columns
            self.row = row

    console.print(
        Panel.fit("[bold]Nyora[/bold] terminal reader\nembedded JS parser runtime")
    )

    with Nyora() as client:
        sources, err = _safe(_list_sources, client)
        if err:
            console.print(f"[red]Failed to load sources: {escape(err)}[/red]")
            return True

        while True:  # source loop
            q = Prompt.ask("Filter sources ([dim]blank = all, 'q' quit[/dim])").strip()
            if q.lower() == "q":
                break
            filtered = _filter_sources(sources, q)
            if not filtered:
                console.print("[yellow]No sources matched.[/yellow]")
                continue
            src_render = _R(
                ["Name", "Lang", "ID"],
                lambda s: (s.name, s.lang or "-", s.id),
            )
            idx, _ = choose(filtered, src_render, "Pick a source")
            if idx is None:
                continue
            source = filtered[idx]
            _rich_browse(console, client, source, choose, _R, Panel)
    return True


def _rich_browse(console, client, source, choose, _R, Panel) -> None:
    from rich.prompt import Prompt
    from rich.markup import escape

    query = ""
    page = 1
    while True:  # results loop
        result, err = _safe(_fetch_results, client, source.id, query, page)
        if err:
            console.print(f"[red]Error loading results: {escape(err)}[/red]")
            new_q = Prompt.ask("Search query ([dim]blank popular, 'b' back[/dim])").strip()
            if new_q.lower() == "b":
                return
            query, page = new_q, 1
            continue
        if not result.entries:
            console.print("[yellow]No results.[/yellow]")
        mode = "search:" + escape(query) if query.strip() else "popular"
        console.print(f"[cyan]{escape(source.name)}[/cyan] - {mode} - page {page}")
        render = _R(
            ["Title", "Tags"],
            lambda m: (
                m.title,
                ", ".join(t.get("title", "") for t in m.tags[:3] if t.get("title")),
            ),
        )
        prompt = "Pick manga"
        if result.has_next_page:
            prompt += " ([green]+[/green] next page"
            prompt += ", [green]-[/green] prev)" if page > 1 else ")"
        ans_idx, ans_q = _choose_with_paging(console, result.entries, render, prompt, choose)
        if ans_idx == "next":
            page += 1
            continue
        if ans_idx == "prev":
            page = max(1, page - 1)
            continue
        if ans_idx is None and ans_q is None:
            return  # back
        if ans_q is not None:
            query, page = ans_q, 1
            continue
        manga = result.entries[ans_idx]
        _rich_details(console, client, source, manga, choose, _R, Panel)


def _choose_with_paging(console, items, render, prompt, choose):
    """Wrap choose() but intercept +/- for paging before delegating."""
    from rich.prompt import Prompt
    from rich.table import Table
    from rich.markup import escape

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right", style="dim")
    for col in render.columns:
        table.add_column(col)
    for i, item in enumerate(items[:60], 1):
        table.add_row(str(i), *[escape(str(x)) for x in render.row(item)])
    console.print(table)
    while True:
        ans = Prompt.ask(
            f"{prompt} ([dim]number, text to search, 'b' back, 'q' quit[/dim])"
        ).strip()
        low = ans.lower()
        if low == "q":
            raise SystemExit(0)
        if low == "b":
            return None, None
        if ans == "+":
            return "next", None
        if ans == "-":
            return "prev", None
        if ans.isdigit():
            idx = int(ans) - 1
            if 0 <= idx < min(len(items), 60):
                return idx, None
            console.print("[red]Out of range.[/red]")
            continue
        return None, ans


def _rich_details(console, client, source, manga, choose, _R, Panel) -> None:
    from rich.markup import escape
    details, err = _safe(_fetch_details, client, source.id, manga.url, manga.title)
    if err:
        console.print(f"[red]Failed to load details: {escape(err)}[/red]")
        return
    m = details.manga
    authors = ", ".join(m.authors) if m.authors else "Unknown"
    tags = ", ".join(t.get("title", "") for t in m.tags if t.get("title"))
    body = [
        f"[bold]{escape(m.title)}[/bold]",
        f"Authors: {escape(authors)}",
        f"State: {escape(m.state or 'n/a')}",
    ]
    if tags:
        body.append(f"Tags: {escape(tags)}")
    body.append("")
    body.append(escape(m.description or "(no description)"))
    console.print(Panel("\n".join(body), title="Details"))

    if not details.chapters:
        console.print("[yellow]No chapters found.[/yellow]")
        return
    render = _R(
        ["Chapter", "Branch"],
        lambda c: (c.title or c.id, c.branch or "-"),
    )
    while True:  # chapter loop
        idx, _ = choose(details.chapters, render, "Pick a chapter")
        if idx is None:
            return
        chapter = details.chapters[idx]
        _rich_pages(console, client, source, chapter)


def _rich_pages(console, client, source, chapter) -> None:
    from rich.table import Table
    from rich.prompt import Prompt
    from rich.markup import escape
    from pathlib import Path
    from nyora.cli import _download_pages

    pages, err = _safe(_fetch_pages, client, source.id, chapter.url, chapter.branch)
    if err:
        console.print(f"[red]Failed to load pages: {escape(err)}[/red]")
        return
    table = Table(title=f"{escape(chapter.title or chapter.id)} - {len(pages)} pages")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Image URL")
    for i, p in enumerate(pages, 1):
        table.add_row(str(i), escape(p.url))
    console.print(table)
    ans = Prompt.ask("Press Enter to go back, or type 'd' to download").strip().lower()
    if ans == "d":
        console.print("[cyan]Downloading...[/cyan]")
        out_dir = Path("nyora-download").expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        saved = _download_pages(pages, out_dir)
        console.print(f"[green]Saved {len(saved)} pages to {out_dir}[/green]")
        console.input("Press Enter to go back...")


# --------------------------------------------------------------------------- #
# Plain-text fallback (no rich, no textual).
# --------------------------------------------------------------------------- #
def _run_plain() -> None:
    print("Nyora terminal reader (plain mode)")
    print(_INSTALL_HINT + " for the full TUI experience.\n")

    def pick(items, render, label):
        for i, item in enumerate(items[:60], 1):
            print(f"{i:>3}. {render(item)}")
        while True:
            ans = input(f"{label} (number, text=search, b=back, q=quit): ").strip()
            if ans.lower() == "q":
                raise SystemExit(0)
            if ans.lower() == "b":
                return None, None
            if ans.isdigit():
                idx = int(ans) - 1
                if 0 <= idx < min(len(items), 60):
                    return idx, None
                print("Out of range.")
                continue
            return None, ans

    with Nyora() as client:
        sources, err = _safe(_list_sources, client)
        if err:
            print(f"Failed to load sources: {err}")
            return
        while True:
            q = input("\nFilter sources (blank=all, q=quit): ").strip()
            if q.lower() == "q":
                return
            filtered = _filter_sources(sources, q)
            if not filtered:
                print("No sources matched.")
                continue
            idx, _ = pick(
                filtered, lambda s: f"{s.name} [{s.lang or '-'}] ({s.id})", "Pick source"
            )
            if idx is None:
                continue
            _plain_browse(client, filtered[idx], pick)


def _plain_browse(client, source, pick) -> None:
    query = ""
    page = 1
    while True:
        result, err = _safe(_fetch_results, client, source.id, query, page)
        if err:
            print(f"Error: {err}")
            nq = input("Search (blank=popular, b=back): ").strip()
            if nq.lower() == "b":
                return
            query, page = nq, 1
            continue
        mode = f"search:{query}" if query.strip() else "popular"
        print(f"\n{source.name} - {mode} - page {page}")
        if not result.entries:
            print("No results.")
        idx, nq = pick(result.entries, lambda m: m.title, "Pick manga")
        if idx is None and nq is None:
            return
        if nq is not None:
            query, page = nq, 1
            continue
        _plain_details(client, source, result.entries[idx], pick)


def _plain_details(client, source, manga, pick) -> None:
    details, err = _safe(_fetch_details, client, source.id, manga.url, manga.title)
    if err:
        print(f"Failed to load details: {err}")
        return
    m = details.manga
    print(f"\n=== {m.title} ===")
    print(f"Authors: {', '.join(m.authors) if m.authors else 'Unknown'}")
    print(f"State: {m.state or 'n/a'}")
    print(f"\n{m.description or '(no description)'}\n")
    if not details.chapters:
        print("No chapters found.")
        return
    while True:
        idx, _ = pick(
            details.chapters,
            lambda c: f"{c.title or c.id}" + (f" <{c.branch}>" if c.branch else ""),
            "Pick chapter",
        )
        if idx is None:
            return
        _plain_pages(client, source, details.chapters[idx])


def _plain_pages(client, source, chapter) -> None:
    from pathlib import Path
    from nyora.cli import _download_pages

    pages, err = _safe(_fetch_pages, client, source.id, chapter.url, chapter.branch)
    if err:
        print(f"Failed to load pages: {err}")
        return
    print(f"\n{chapter.title or chapter.id} - {len(pages)} pages")
    for i, p in enumerate(pages, 1):
        print(f"{i:>3}. {p.url}")
    
    ans = input("\nPress Enter to go back, or type 'd' to download: ").strip().lower()
    if ans == "d":
        print("Downloading...")
        out_dir = Path("nyora-download").expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        saved = _download_pages(pages, out_dir)
        print(f"Saved {len(saved)} pages to {out_dir}")
        input("Press Enter to go back...")


if __name__ == "__main__":
    raise SystemExit(main())
