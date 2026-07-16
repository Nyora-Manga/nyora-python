"""Full-screen Textual reader for Nyora's bundled parser engine.

A dense, keyboard-driven terminal reader: two-pane source/result tables with
vim navigation, a popular/latest/search mode switch, a fuzzy command palette,
light/dark themes, cloud + local library/history/downloads, three reader modes
(webtoon / paged / paged-rtl), and terminal-graphics page rendering.

Backed by the self-contained :class:`nyora.Nyora` client (which launches the
bundled local engine) plus optional cloud sync (:class:`nyora_tui.sync.TuiSync`)
and a local store (:mod:`nyora_tui.store`). Degrades gracefully on network/parse
errors instead of crashing. Requires the ``[tui]`` extra (``pip install
"nyora[tui]"``); without it, :func:`main` prints an install hint and exits.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

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




def _fetch_details(client: Nyora, source_id: str, url: str, title: str) -> MangaDetails:
    details = client.manga.details(source_id, url)
    if title and not details.manga.title:
        details.manga.title = title
    return details


def _fetch_pages(client: Nyora, source_id: str, url: str, branch: str | None):
    return client.manga.pages(source_id, url, branch=branch)


def _fetch_browse(client: Nyora, source_id: str, mode: str, query: str, page: int) -> SearchPage:
    """Fetch one page of results for a browse ``mode`` (popular/latest/search)."""
    if mode == "search" and query.strip():
        return client.manga.search(source_id, query.strip(), page=page)
    if mode == "latest":
        return client.manga.latest(source_id, page=page)
    return client.manga.popular(source_id, page=page)


def _relative_age(epoch_ms: int) -> str:
    """Render an epoch-millisecond timestamp as a compact relative age (e.g. ``3d``)."""
    if not epoch_ms:
        return "—"
    import time as _time

    secs = _time.time() - epoch_ms / 1000.0
    if secs < 0:
        secs = 0.0
    for unit, size in (
        ("y", 31_536_000), ("mo", 2_592_000), ("d", 86_400), ("h", 3_600), ("m", 60)
    ):
        if secs >= size:
            return f"{int(secs // size)}{unit}"
    return "now"


def _hist_when(iso: str) -> str:
    """Render an ISO-8601 timestamp as a compact relative age (e.g. ``3d``)."""
    if not iso:
        return "—"
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return "—"
    return _relative_age(int(dt.timestamp() * 1000))


def _rating_badge(rating: float) -> str:
    """Render a normalized 0..1 rating as a five-star score, or ``—`` when unknown."""
    if rating is None or rating < 0:
        return "—"
    return f"{rating * 5:.1f}★"


def _truncate(text: str, limit: int) -> str:
    """Truncate ``text`` to ``limit`` characters with an ellipsis when clipped."""
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


# Locale code -> human-readable language name, for grouping the source list.
_LANG_NAMES = {
    "en": "English", "ja": "Japanese", "zh": "Chinese", "zh-hans": "Chinese (Simplified)",
    "zh-hant": "Chinese (Traditional)", "ko": "Korean", "es": "Spanish",
    "es-419": "Spanish (LatAm)",
    "fr": "French", "pt": "Portuguese", "pt-br": "Portuguese (Brazil)", "ru": "Russian",
    "de": "German", "it": "Italian", "id": "Indonesian", "ar": "Arabic", "tr": "Turkish",
    "vi": "Vietnamese", "th": "Thai", "pl": "Polish", "uk": "Ukrainian", "nl": "Dutch",
    "fa": "Persian", "fil": "Filipino", "ms": "Malay", "hi": "Hindi", "he": "Hebrew",
    "ca": "Catalan", "hu": "Hungarian", "ro": "Romanian", "cs": "Czech", "bg": "Bulgarian",
    "el": "Greek", "sv": "Swedish", "da": "Danish", "fi": "Finnish", "no": "Norwegian",
    "multi": "Multi-language",
}


def _lang_display(code: str) -> str:
    """Return a readable language name for a locale ``code`` (``en`` -> ``English``)."""
    c = (code or "").strip().lower()
    if not c:
        return "Other / Unknown"
    return _LANG_NAMES.get(c, code.upper())


def _lang_sort_key(code: str):
    """Sort key that floats English then Multi-language up, unknown to the bottom."""
    c = (code or "").strip().lower()
    if not c:
        return (3, "")
    priority = {"en": 0, "multi": 1}
    return (priority.get(c, 2), _lang_display(c).casefold())


# --------------------------------------------------------------------------- #
# Frontend selection.
# --------------------------------------------------------------------------- #
def main() -> int:
    """Entry point for the ``nyora-tui`` console script (and bare ``nyora-cli``).

    Launches the Textual reader. Exits cleanly (``0``) when stdout is not a TTY
    (piped/redirected/CI) or when the TUI dependencies are not installed.
    """
    if not _has_interactive_terminal():
        _print_no_tty_notice()
        return 0
    try:
        if not _run_textual():
            print(_INSTALL_HINT)
    except (KeyboardInterrupt, EOFError):  # pragma: no cover - interactive
        print()
    return 0


def _print_no_tty_notice() -> None:
    """Explain that the TUI needs a real terminal and how to launch it."""
    print("Nyora terminal reader needs an interactive terminal (a TTY).")
    print("stdout is not a TTY here (piped, redirected, or non-interactive shell).")
    print("Run 'nyora' (or 'nyora-tui') directly in a terminal to use it.")
    print("For scripting, use subcommands instead, e.g. 'nyora-cli sources'.")


# --------------------------------------------------------------------------- #
# Textual frontend.
# --------------------------------------------------------------------------- #
def _run_textual() -> bool:  # noqa: C901 - a rich single-file TUI; cohesion beats fragmentation
    try:
        import textual  # noqa: F401
    except ImportError:
        return False

    import time

    from rich.markup import escape as _esc  # escape source/title text before markup
    from textual import work
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.command import DiscoveryHit, Hit, Hits, Provider
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import ModalScreen, Screen
    from textual.theme import Theme
    from textual.widgets import (
        Button,
        DataTable,
        Footer,
        Header,
        Input,
        Label,
        ListItem,
        ListView,
        Static,
    )

    # Named colour schemes (light accent / dark accent) live in nyora.theme so
    # the CLI palette can track the reader's chosen scheme too. Over a shared
    # neutral base per appearance. Sakura leads — it is the default.
    from nyora.theme import SCHEMES as _SCHEMES
    from nyora_tui.i18n import t  # localised UI strings (TUI is available in ~40 languages)
    from nyora_tui.store import Downloads, LocalLibrary, manga_id_of
    from nyora_tui.sync import BROWSER_UA, TuiSync
    # `label` = neutral secondary-text colour, readable on either appearance. Only
    # the accent carries scheme identity — like nyora-web.
    _DARK_BASE = {"bg": "#0C0C0E", "surface": "#16161A", "panel": "#26262B", "fg": "#F2F2F4",
                  "muted": "#A1A1A6", "label": "#AEB6C6"}
    _LIGHT_BASE = {"bg": "#F4F4F6", "surface": "#FFFFFF", "panel": "#D9D9DE", "fg": "#111114",
                   "muted": "#57575E", "label": "#4C5560"}

    def _make_theme(name: str, accent: str, base: dict, is_dark: bool) -> Theme:
        return Theme(
            name=name,
            primary=accent,
            secondary=base["label"],
            accent=accent,
            foreground=base["fg"],
            background=base["bg"],
            surface=base["surface"],
            panel=base["panel"],
            # 'success' follows the scheme accent (no fixed green that clashes with
            # a pink/blue/teal theme). Warning/error stay semantic (amber/red).
            success=accent,
            warning="#E0B354" if is_dark else "#9A6A00",
            error="#EB7D9B" if is_dark else "#B23A5B",
            dark=is_dark,
            variables={
                "block-cursor-background": accent,
                "block-cursor-foreground": base["bg"],
                "block-cursor-text-style": "bold",
                "footer-key-foreground": accent,
                "footer-description-foreground": base["muted"],
                "footer-background": base["surface"],
                "input-selection-background": f"{accent} 30%",
                "input-cursor-background": accent,
                "scrollbar": base["panel"],
                "scrollbar-hover": accent,
                "scrollbar-active": accent,
                "scrollbar-background": base["bg"],
                "border": base["panel"],
            },
        )

    _THEMES: dict[str, Theme] = {}
    for _sid, _nm, _light, _dark in _SCHEMES:
        _THEMES[_sid] = _make_theme(_sid, _dark, _DARK_BASE, True)
        _THEMES[f"{_sid}-light"] = _make_theme(f"{_sid}-light", _light, _LIGHT_BASE, False)
    from nyora.theme import DEFAULT_SCHEME as _DEFAULT_THEME

    def _scheme_of(theme_name: str) -> str:
        return theme_name[:-6] if theme_name.endswith("-light") else theme_name

    def _is_light(theme_name: str) -> bool:
        return theme_name.endswith("-light")

    def _theme_name(scheme: str, light: bool) -> str:
        return f"{scheme}-light" if light else scheme

    SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    _WELCOME = (
        "[$primary]❀[/] [b $accent]Nyora[/]  [dim]· terminal manga reader[/]\n\n"
        "[$secondary]Getting started[/]\n"
        "  [b]1[/]  Pick a source on the left — type to filter, [b]enter[/] to open\n"
        "  [b]2[/]  Browse:  [b]/[/] search   ·   [b]p[/] popular   ·   [b]l[/] latest\n"
        "  [b]3[/]  [b]enter[/] a title → chapters → [b]enter[/] to read\n\n"
        "[$secondary]Handy keys[/]\n"
        "  [b]j k[/] move   [b]g G[/] top/bottom   [b]x[/] toggle 18+   [b]a[/] account\n"
        "  [b]t[/] theme   [b]L[/] languages   [b],[/] settings   [b]?[/] all keys\n"
        "  [b]ctrl+p[/] command palette   ·   [b]q[/] quit\n\n"
        "[dim]Sources are grouped by language ([b]L[/] to jump). Change your app\n"
        "language, theme and sources anytime with [b],[/] (settings).[/]"
    )

    def _timed(fn, *a, **k):
        """Run ``fn`` via ``_safe`` and also return elapsed milliseconds."""
        t0 = time.perf_counter()
        res, err = _safe(fn, *a, **k)
        return res, err, (time.perf_counter() - t0) * 1000.0

    # Resolve the best terminal-image renderer and cache the terminal cell size
    # *before* Textual starts — textual-image can only query the terminal for
    # graphics support and cell geometry while stdin/stdout are still ours (the
    # `import` below performs that probe). Sending the full-resolution source
    # image lets a graphics terminal downscale it itself — the sharpest result
    # a terminal can produce ("full-res").
    #
    # textual-image's TGP probe uses a 100 ms timeout and misses Ghostty/Kitty —
    # both fully support the Kitty graphics protocol with unicode placeholders
    # (unlike wezterm/konsole, whose placeholder support is broken and where
    # Sixel is preferred). So on exactly those two terminals we force TGP for
    # true full-resolution pages instead of falling back to low-res half-cells.
    # `NYORA_TUI_IMAGE=tgp|sixel|halfcell|auto` overrides the choice.
    _IMAGE_CLS = None
    _CELL_W, _CELL_H = 10, 20
    _PROTOCOL = "none"
    try:
        import os as _os

        from textual_image.widget import HalfcellImage as _HalfcellImage
        from textual_image.widget import Image as _AutoImage
        from textual_image.widget import SixelImage as _SixelImage
        from textual_image.widget import TGPImage as _TGPImage

        _override = (_os.environ.get("NYORA_TUI_IMAGE") or "").strip().lower()
        _term = (_os.environ.get("TERM") or "").lower()
        _prog = (_os.environ.get("TERM_PROGRAM") or "").lower()
        _kitty_like = bool(
            "ghostty" in _term
            or "ghostty" in _prog
            or _os.environ.get("GHOSTTY_RESOURCES_DIR")
            or "kitty" in _term
            or _os.environ.get("KITTY_WINDOW_ID")
        )
        # Windows Terminal: WT_SESSION has been set since 2019 but Sixel only
        # landed in WT 1.22 (Feb 2024), and WT exposes no version variable — so we
        # must NOT force Sixel from WT_SESSION (older WT would spray raw escape
        # codes). We also can't reliably tell whether a WT answered the geometry
        # query, because textual-image's get_cell_size() silently returns a VT340
        # default when unanswered. So on Windows we trust the capability-probing
        # auto renderer (which degrades to half-cell if graphics aren't detected)
        # and let capable-WT users opt in with NYORA_TUI_IMAGE=sixel.
        _forced = {
            "tgp": _TGPImage,
            "sixel": _SixelImage,
            "halfcell": _HalfcellImage,
            "auto": _AutoImage,
        }
        if _override in _forced:
            _IMAGE_CLS = _forced[_override]
            _PROTOCOL = _override
        elif _kitty_like:
            _IMAGE_CLS = _TGPImage
            _PROTOCOL = "tgp"
        else:
            _IMAGE_CLS = _AutoImage
            try:
                from textual_image.renderable import Image as _AutoRenderable

                _PROTOCOL = _AutoRenderable.__module__.rsplit(".", 1)[-1]
            except Exception:  # noqa: BLE001
                _PROTOCOL = "auto"
        try:
            from textual_image._terminal import get_cell_size

            cell = get_cell_size()
            if cell and cell.width and cell.height:
                _CELL_W, _CELL_H = int(cell.width), int(cell.height)
        except Exception:  # noqa: BLE001 - no TTY / query unsupported
            pass
    except Exception:  # noqa: BLE001 - textual-image absent or no graphics support
        _IMAGE_CLS = None

    # Kitty's unicode-placeholder scheme caps an image at 297 cells tall; slice
    # comfortably under that so full-width pages never overflow it.
    _MAX_IMAGE_CELLS = 240

    def _mount_image(container, img, cols: int, *, fill_width: bool = True) -> None:
        """Render ``img`` into ``container`` at ``cols`` cells wide.

        ``fill_width=True`` (webtoon) stretches to the full content width and
        slices very tall pages into bands to stay under the Kitty placeholder
        limit. ``fill_width=False`` (paged) sizes the widget to an explicit
        ``cols`` × aspect-correct height so a *whole page* fits the viewport and
        is centred by the container. Without a graphics protocol we degrade to
        half-cell pixels. Explicit cell sizing renders far more reliably than
        ``auto`` for graphics widgets mounted dynamically (auto can collapse to 0).
        """
        from PIL import Image as PILImage

        w, h = img.size
        if w <= 0 or h <= 0:
            return
        cols = max(8, int(cols))
        if _IMAGE_CLS is not None:
            scale = max(1, cols * _CELL_W) / w
            if fill_width and (h * scale) / _CELL_H > _MAX_IMAGE_CELLS:
                band_px = max(1, int(_MAX_IMAGE_CELLS * _CELL_H / scale))
                bands = [img.crop((0, y, w, min(y + band_px, h))) for y in range(0, h, band_px)]
            else:
                bands = [img]
            for band in bands:
                bw, bh = band.size
                cells_h = max(1, round((cols * _CELL_W) * (bh / bw) / _CELL_H))
                widget = _IMAGE_CLS(band)
                widget.styles.width = "100%" if fill_width else cols
                widget.styles.height = cells_h
                container.mount(widget)
            return
        from rich_pixels import Pixels

        target = max(10, cols - 2)
        new_h = max(1, int((target / w) * h))
        px = Pixels.from_image(img.resize((target, new_h), PILImage.Resampling.LANCZOS))
        container.mount(Static(px))

    # ----------------------------------------------------------------------- #
    # Command palette (Ctrl+P) — fuzzy power-user actions.
    # ----------------------------------------------------------------------- #
    class NyoraCommands(Provider):
        """Expose the app's headline actions to Textual's command palette."""

        def _specs(self):
            app: Any = self.app
            return [
                (t("nav.popular"), app.action_popular, "Browse popular in this source"),
                (t("nav.latest"), app.action_latest, "Browse latest updates in this source"),
                (t("nav.search"), app.action_focus_search, "Search the current source"),
                (t("nav.language"), app.action_language_nav, "Jump to a source language"),
                ("Refresh", app.action_refresh, "Re-fetch the current view"),
                ("Next page", app.action_next_page, "Go to the next page"),
                ("Previous page", app.action_prev_page, "Go to the previous page"),
                ("Toggle NSFW", app.action_toggle_nsfw, "Show or hide adult sources/results"),
                (t("nav.filter"), app.action_focus_filter, "Jump to the source filter"),
                (t("nav.library"), app.action_library, "Your synced favourites"),
                (t("nav.history"), app.action_history, "Recent reading history"),
                (t("nav.account"), app.action_account, "Sign in or out of Nyora sync"),
                (t("theme.title"), app.action_themes, "Pick a colour theme + light/dark"),
                (t("nav.settings"), app.action_settings, "Change language, theme, sources"),
                (t("keys.title"), app.action_help, "Show the keybinding cheat sheet"),
            ]

        async def discover(self) -> Hits:
            for name, cb, help_text in self._specs():
                yield DiscoveryHit(name, cb, help=help_text)

        async def search(self, query: str) -> Hits:
            matcher = self.matcher(query)
            for name, cb, help_text in self._specs():
                score = matcher.match(name)
                if score > 0:
                    yield Hit(score, matcher.highlight(name), cb, help=help_text)

    # ----------------------------------------------------------------------- #
    # Full-screen keybindings reference.
    # ----------------------------------------------------------------------- #
    class KeysScreen(Screen):
        """A full-screen, two-column reference of every keybinding."""

        BINDINGS = [Binding("escape,question_mark,f1,q", "close", "Close")]
        CSS = """
        KeysScreen { background: $background; }
        #keys_title {
            height: 1; padding: 0 2; background: $surface; color: $secondary;
            text-style: bold; border-bottom: solid $panel;
        }
        #keys_cols { padding: 1 1 0 1; height: 1fr; }
        .keys_col { width: 1fr; padding: 0 2; }
        #keys_foot {
            dock: bottom; height: 1; padding: 0 2; background: $surface;
            color: $text-muted; border-top: solid $panel;
        }
        """

        @staticmethod
        def _hdr(key: str) -> str:
            return f"[b $accent]{_esc(t(key))}[/]"

        def _left(self) -> list[str]:
            return [
                self._hdr("keys.h_navigate"),
                "  [b]j k[/] / [b]↑ ↓[/]    move in a list",
                "  [b]g[/] / [b]G[/]        top / bottom",
                "  [b]↓[/] / [b]esc[/]      filter box → source list",
                "  [b]tab[/]           cycle panes",
                "  [b]enter[/]         open selection",
                "  [b]esc[/]           back",
                "",
                self._hdr("keys.h_sections"),
                "  [b]1[/]  browse / sources     [b]2[/]  library",
                "  [b]3[/]  history              [b]a[/]  account / sync",
                "  [b]t[/]  colour theme         [b]L[/]  language navigator",
                "  [b],[/]  settings             [b]?[/]  this help",
                "",
                self._hdr("keys.h_browse"),
                "  [b]/[/]  search             [b]f[/]  filter sources",
                "  [b]p[/]  popular            [b]l[/]  latest",
                "  [b]n[/] / [b]N[/]  next / prev page",
                "  [b]r[/]  refresh            [b]x[/]  toggle 18+",
                "",
                self._hdr("keys.h_details"),
                "  [b]enter[/]  read chapter     [b]f[/]  favourite",
                "  [b]d[/]      download chapter",
            ]

        def _right(self) -> list[str]:
            return [
                self._hdr("keys.h_reader"),
                "  [b]m[/]  cycle mode (webtoon/paged/paged-rtl)",
                "  [b]f[/]  fit (width / height)",
                "  [b]n[/] / [b]p[/]  next / previous chapter",
                "  [b]d[/]  save chapter to Downloads",
                "  [b]esc[/]  back",
                "",
                self._hdr("keys.h_reader_webtoon"),
                "  [b]j k[/] / [b]↑ ↓[/]  scroll     [b]space[/]  page down",
                "  [b]b[/]  page up          [b]ctrl+d/u[/]  half page",
                "  [b]g[/] / [b]G[/]  top / bottom",
                "",
                self._hdr("keys.h_reader_paged"),
                "  [b]← →[/] (or [b]h l[/])  turn page (RTL-aware)",
                "  [b]space[/]  next page     [b]g[/] / [b]G[/]  first / last",
                "",
                self._hdr("keys.h_library"),
                "  [b]tab[/] / [b]← →[/]  switch Favourites / Downloads",
                "  [b]enter[/]  open        [b]u[/] / [b]del[/]  remove",
                "  [b]r[/]  sync with cloud",
                "",
                self._hdr("keys.h_global"),
                "  [b]t[/]  theme (+[b]space[/] light/dark)   [b]ctrl+p[/]  palette",
                "  [b]?[/] / [b]F1[/]  this screen        [b]q[/]  quit",
            ]

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static(f"❀ {_esc(t('keys.title'))}", id="keys_title")
            with Horizontal(id="keys_cols"):
                yield Static("\n".join(self._left()), classes="keys_col")
                yield Static("\n".join(self._right()), classes="keys_col")
            yield Static(f"[dim]{_esc(t('keys.hint'))}[/]", id="keys_foot")
            yield Footer()

        def action_close(self) -> None:
            self.app.pop_screen()

    # ----------------------------------------------------------------------- #
    # Colour-scheme picker (live preview).
    # ----------------------------------------------------------------------- #
    class ThemePickerScreen(ModalScreen):
        """Pick a colour scheme with live preview; enter applies, esc reverts."""

        BINDINGS = [
            Binding("escape", "cancel", "Cancel"),
            Binding("enter", "choose", "Apply"),
            Binding("space", "toggle_light", "Light/Dark"),
            Binding("j,down", "cursor_down", "Down", show=False),
            Binding("k,up", "cursor_up", "Up", show=False),
        ]
        CSS = """
        ThemePickerScreen { align: center middle; }
        #theme_box {
            width: 44; height: auto; max-height: 90%;
            border: round $primary; background: $surface; padding: 1 2;
        }
        #theme_head { padding: 0 0 1 0; }
        #theme_list { height: auto; max-height: 20; background: $surface; }
        #theme_list > ListItem { padding: 0 1; }
        """

        def __init__(self, schemes, current: str) -> None:
            super().__init__()
            self._schemes = schemes
            self._original = current
            self._light = _is_light(current)

        def compose(self) -> ComposeResult:
            with Vertical(id="theme_box"):
                yield Static("", id="theme_head")
                items = []
                start = 0
                cur_scheme = _scheme_of(self._original)
                for i, (sid, name, light, dark) in enumerate(self._schemes):
                    if sid == cur_scheme:
                        start = i
                    # dual swatch: dark ● + light ● so both variants are visible
                    items.append(ListItem(Label(f"[{dark}]●[/][{light}]●[/]  {name}")))
                yield ListView(*items, id="theme_list", initial_index=start)

        def on_mount(self) -> None:
            self._render_head()

        def _render_head(self) -> None:
            appear = f"{t('theme.light')} ☀" if self._light else f"{t('theme.dark')} ☾"
            self.query_one("#theme_head", Static).update(
                f"[b $accent]❀ {_esc(t('theme.title'))}[/]   [dim]·[/]  [b]{appear}[/]\n"
                f"[dim]{_esc(t('theme.hint'))}[/]"
            )

        def action_cursor_down(self) -> None:
            self.query_one("#theme_list", ListView).action_cursor_down()

        def action_cursor_up(self) -> None:
            self.query_one("#theme_list", ListView).action_cursor_up()

        def action_toggle_light(self) -> None:
            self._light = not self._light
            self._render_head()
            self._preview()

        def _preview(self) -> None:
            idx = self.query_one("#theme_list", ListView).index
            if idx is not None and 0 <= idx < len(self._schemes):
                self.app.theme = _theme_name(self._schemes[idx][0], self._light)

        def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
            self._preview()

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            # ListView consumes Enter to emit Selected, so apply from here.
            self.action_choose()

        def action_choose(self) -> None:
            app: Any = self.app
            idx = self.query_one("#theme_list", ListView).index
            if idx is not None and 0 <= idx < len(self._schemes):
                chosen = _theme_name(self._schemes[idx][0], self._light)
                app.theme = chosen
                app._persist_theme(chosen)
            app.pop_screen()
            app._on_theme_changed(app.theme)

        def action_cancel(self) -> None:
            app: Any = self.app
            app.theme = self._original
            app.pop_screen()
            app._on_theme_changed(app.theme)

    # ----------------------------------------------------------------------- #
    # Language navigator — jump the source list to any of the 40 languages.
    # ----------------------------------------------------------------------- #
    class LanguageNavScreen(ModalScreen):
        """Filterable list of source languages; select one to jump to its group."""

        BINDINGS = [Binding("escape", "cancel", "Cancel")]
        CSS = """
        LanguageNavScreen { align: center middle; }
        #lang_box {
            width: 52; height: auto; max-height: 90%;
            border: round $primary; background: $surface; padding: 1 2;
        }
        #lang_head { padding: 0 0 1 0; }
        #lang_filter {
            height: 3; padding: 0 1; border: round $panel; background: $background;
        }
        #lang_filter:focus { border: round $primary; }
        #lang_list { height: auto; max-height: 18; background: $surface; }
        """

        def __init__(self, langs) -> None:
            super().__init__()
            self._langs = langs  # list of (code, display, count)
            self._view = list(langs)

        def compose(self) -> ComposeResult:
            from textual.widgets import OptionList

            with Vertical(id="lang_box"):
                yield Static(
                    f"[b $accent]❀ {_esc(t('langnav.title'))}[/]\n"
                    f"[dim]{_esc(t('langnav.hint'))}[/]",
                    id="lang_head",
                )
                yield Input(placeholder=t("langnav.filter"), id="lang_filter")
                yield OptionList(id="lang_list")

        def on_mount(self) -> None:
            self._fill("")
            self.query_one("#lang_filter", Input).focus()

        def _fill(self, query: str) -> None:
            from textual.widgets import OptionList
            from textual.widgets.option_list import Option

            ol = self.query_one("#lang_list", OptionList)
            ol.clear_options()
            q = query.strip().lower()
            self._view = [
                x for x in self._langs if not q or q in x[1].lower() or q in x[0].lower()
            ]
            for code, disp, count in self._view:
                ol.add_option(Option(f"{_esc(disp)}   [dim]({count})[/]", id=code))

        def on_input_changed(self, event: Input.Changed) -> None:
            self._fill(event.value)

        def on_input_submitted(self, event: Input.Submitted) -> None:
            # Enter in the filter jumps to the first match.
            if self._view:
                self.dismiss(self._view[0][0])

        def on_option_list_option_selected(self, event) -> None:
            self.dismiss(event.option.id)

        def action_cancel(self) -> None:
            self.dismiss(None)

    # ----------------------------------------------------------------------- #
    # Welcome / sign-in (branded, guest-optional — mirrors nyora-web).
    # ----------------------------------------------------------------------- #
    class WelcomeScreen(Screen):
        """First-run branded welcome: sign in, create an account, or read as guest."""

        BINDINGS = [Binding("escape", "guest", "Continue as guest")]
        CSS = """
        WelcomeScreen { align: center middle; background: $background; }
        #w_box {
            width: 78; height: auto; max-height: 96%;
            border: round $primary; background: $surface; padding: 2 4;
        }
        #w_form Input { margin-top: 1; }
        #w_msg { min-height: 1; margin-top: 1; color: $text-muted; }
        #w_actions { height: 3; margin-top: 1; }
        #w_actions Button { margin-right: 2; }
        """

        def __init__(self, sync) -> None:
            super().__init__()
            self._sync = sync

        def compose(self) -> ComposeResult:
            with VerticalScroll(id="w_box"):
                yield Static("[b $accent]NYORA[/]   [dim]破壊[/]")
                yield Static(f"[$secondary]{_esc(t('app.tagline'))}[/]")
                yield Static("")
                yield Static(f"[b]{_esc(t('welcome.headline'))}[/]")
                yield Static(f"[dim]{_esc(t('welcome.blurb'))}[/]")
                yield Static("")
                yield Static(f"[$secondary]{_esc(t('welcome.features'))}[/]")
                yield Static("")
                yield Static(f"[b]{_esc(t('welcome.start_reading'))}[/]")
                with Vertical(id="w_form"):
                    yield Input(placeholder=t("welcome.email"), id="w_email")
                    yield Input(placeholder=t("welcome.password"), password=True, id="w_pw")
                yield Static("", id="w_msg")
                with Horizontal(id="w_actions"):
                    yield Button(t("welcome.sign_in"), id="w_signin", variant="primary")
                    yield Button(t("welcome.create_account"), id="w_register")
                    yield Button(t("welcome.guest"), id="w_guest")
                yield Static(f"[dim]{_esc(t('welcome.guest_hint'))}[/]")

        def on_mount(self) -> None:
            self.query_one("#w_email", Input).focus()

        def _creds(self) -> tuple[str, str]:
            return (
                self.query_one("#w_email", Input).value.strip(),
                self.query_one("#w_pw", Input).value.strip(),
            )

        def _msg(self, text: str) -> None:
            self.query_one("#w_msg", Static).update(text)

        def on_input_submitted(self, event: Input.Submitted) -> None:
            self._do_signin()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "w_signin":
                self._do_signin()
            elif event.button.id == "w_register":
                self._do_register()
            else:
                self.action_guest()

        def _finish(self) -> None:
            # Move on to the preferences step; onboarding completes there.
            self.app.pop_screen()
            self.app.push_screen(PreferencesScreen(self._sync))

        def action_guest(self) -> None:
            self._finish()

        def _do_signin(self) -> None:
            email, pw = self._creds()
            if not email or not pw:
                self._msg(f"[warning]{_esc(t('welcome.enter_creds'))}[/]")
                return
            self._msg(f"[dim]{_esc(t('welcome.signing_in'))}[/]")
            try:
                self._sync.sign_in(email, pw)
                self._msg(f"[success]{_esc(t('welcome.welcome_back'))}[/]")
                app: Any = self.app
                app._full_sync()   # push local up + pull account down (web parity)
                self._finish()
            except Exception as exc:  # noqa: BLE001
                self._msg(f"[error]{_esc(t('welcome.signin_failed', error=str(exc)))}[/]")

        def _do_register(self) -> None:
            email, pw = self._creds()
            if not email or not pw:
                self._msg(f"[warning]{_esc(t('welcome.enter_creds'))}[/]")
                return
            self._msg(f"[dim]{_esc(t('welcome.creating'))}[/]")
            try:
                self._sync.register(email, pw)
                if not self._sync.is_signed_in:
                    self._sync.sign_in(email, pw)
                self._msg(f"[success]{_esc(t('welcome.account_ready'))}[/]")
                app: Any = self.app
                app._full_sync()   # migrate local (guest) data up to the new account
                self._finish()
            except Exception as exc:  # noqa: BLE001
                self._msg(f"[error]{_esc(t('welcome.signup_failed', error=str(exc)))}[/]")

    # ----------------------------------------------------------------------- #
    # Set up your shelf — app language + theme + source languages + 18+.
    # ----------------------------------------------------------------------- #
    class PreferencesScreen(Screen):
        """One-time setup: app language, colour theme, source languages and 18+.

        Language and theme apply live (the interface re-labels itself and the
        theme previews as you change them), so the choice is what you see.
        """

        BINDINGS = [
            Binding("ctrl+s", "start", "Save"),
            Binding("enter", "start", "Save", show=False),
            Binding("escape", "cancel", "Cancel"),
        ]
        CSS = """
        PreferencesScreen { align: center middle; background: $background; }
        #p_box {
            width: 82; height: auto; max-height: 96%;
            border: round $primary; background: $surface; padding: 2 4;
        }
        #p_box Select { margin-top: 1; width: 100%; }
        .p_row { height: 3; margin-top: 1; }
        .p_row Static { padding-top: 1; }
        #p_langs { height: auto; max-height: 10; margin-top: 1; border: round $panel; }
        #p_actions { height: 3; margin-top: 1; }
        .p_head { margin-top: 1; }
        """

        def __init__(self, sync, *, settings: bool = False) -> None:
            super().__init__()
            self._sync = sync
            self._settings = settings  # True when re-opened as Settings (not first-run)
            self._populated = False
            self._tries = 0
            self._orig_theme: str | None = None
            self._orig_lang: str | None = None

        def _kicker(self) -> str:
            return "" if self._settings else t("prefs.youre_in")

        def _title(self) -> str:
            return t("nav.settings") if self._settings else t("prefs.title")

        def _start_label(self) -> str:
            return t("prefs.save") if self._settings else t("prefs.start_reading")

        def compose(self) -> ComposeResult:
            from textual.widgets import Select, SelectionList, Switch

            from nyora_tui.i18n import available_languages, current_language

            cur = self.app.theme
            scheme, light = _scheme_of(cur), _is_light(cur)
            lang_opts = [(name, code) for code, name in available_languages()]
            theme_opts = [(name, sid) for sid, name, _l, _d in _SCHEMES]

            with VerticalScroll(id="p_box"):
                yield Static(f"[$secondary]{_esc(self._kicker())}[/]", id="p_kicker")
                yield Static(f"[b]{_esc(self._title())}[/]", id="p_title")
                yield Static(f"[dim]{_esc(t('prefs.blurb'))}[/]", id="p_blurb")

                yield Static(f"[$secondary]{_esc(t('prefs.app_language'))}[/]", classes="p_head",
                             id="p_lang_head")
                yield Select(lang_opts, value=current_language(), allow_blank=False, id="p_uilang")

                yield Static(f"[$secondary]{_esc(t('prefs.theme'))}[/]", classes="p_head",
                             id="p_theme_head")
                yield Select(theme_opts, value=scheme, allow_blank=False, id="p_scheme")
                with Horizontal(classes="p_row", id="p_light_row"):
                    yield Switch(value=light, id="p_light_sw")
                    yield Static(f"  {_esc(t('theme.light'))}", id="p_light_lbl")

                with Horizontal(classes="p_row", id="p_nsfw_row"):
                    yield Switch(value=not getattr(self.app, "_hide_nsfw", True), id="p_nsfw_sw")
                    yield Static(f"  {_esc(t('prefs.show_nsfw'))}", id="p_nsfw_lbl")

                yield Static(
                    f"[$secondary]{_esc(t('prefs.source_langs'))}[/]   "
                    f"[dim]· {_esc(t('prefs.source_langs_hint'))}[/]",
                    classes="p_head", id="p_srclang_head",
                )
                yield SelectionList(id="p_langs")
                with Horizontal(id="p_actions"):
                    yield Button(self._start_label(), id="p_start", variant="primary")

        def on_mount(self) -> None:
            from nyora_tui.i18n import current_language

            # Snapshot the live-previewed state so Cancel can revert it.
            self._orig_theme = self.app.theme
            self._orig_lang = current_language()
            self._timer = self.set_interval(0.3, self._populate)
            self._populate()

        def _populate(self) -> None:
            from collections import Counter

            from textual.widgets import SelectionList
            from textual.widgets.selection_list import Selection

            if self._populated:
                return
            srcs = getattr(self.app, "_sources", [])
            self._tries += 1
            if not srcs:
                if self._tries >= 34:  # ~10s: sources never arrived; stop retrying
                    self._timer.stop()  # leave _populated False so Save won't wipe langs
                return
            sl = self.query_one("#p_langs", SelectionList)
            preselect = set(getattr(self.app, "_languages", set()) or set())
            counts = Counter((s.lang or "").strip().lower() for s in srcs)
            for code in sorted(counts, key=_lang_sort_key):
                sl.add_option(
                    Selection(f"{_lang_display(code)}   ({counts[code]})", code, code in preselect)
                )
            self._populated = True
            self._timer.stop()

        def on_select_changed(self, event) -> None:
            """Apply app-language and theme choices live as they change."""
            from textual.widgets import Select

            if event.value is Select.BLANK:
                return
            if event.select.id == "p_uilang":
                from nyora_tui.i18n import set_language

                set_language(str(event.value))
                self._relabel()
            elif event.select.id == "p_scheme":
                self._apply_theme_preview()

        def on_switch_changed(self, event) -> None:
            if event.switch.id == "p_light_sw":
                self._apply_theme_preview()

        def _apply_theme_preview(self) -> None:
            from textual.widgets import Select, Switch

            scheme = self.query_one("#p_scheme", Select).value
            if scheme is Select.BLANK:
                return
            light = self.query_one("#p_light_sw", Switch).value
            self.app.theme = _theme_name(str(scheme), light)

        def _relabel(self) -> None:
            """Re-render the screen's own labels after an app-language change."""
            pairs = {
                "p_kicker": f"[$secondary]{_esc(self._kicker())}[/]",
                "p_title": f"[b]{_esc(self._title())}[/]",
                "p_blurb": f"[dim]{_esc(t('prefs.blurb'))}[/]",
                "p_lang_head": f"[$secondary]{_esc(t('prefs.app_language'))}[/]",
                "p_theme_head": f"[$secondary]{_esc(t('prefs.theme'))}[/]",
                "p_light_lbl": f"  {_esc(t('theme.light'))}",
                "p_nsfw_lbl": f"  {_esc(t('prefs.show_nsfw'))}",
                "p_srclang_head": (
                    f"[$secondary]{_esc(t('prefs.source_langs'))}[/]   "
                    f"[dim]· {_esc(t('prefs.source_langs_hint'))}[/]"
                ),
            }
            for wid, text in pairs.items():
                try:
                    self.query_one(f"#{wid}", Static).update(text)
                except Exception:  # noqa: BLE001 - a missing label must never crash
                    pass
            try:
                self.query_one("#p_start", Button).label = self._start_label()
            except Exception:  # noqa: BLE001
                pass

        def on_button_pressed(self, event: Button.Pressed) -> None:
            self.action_start()

        def action_cancel(self) -> None:
            """Escape: cancel in Settings (revert preview); complete onboarding on first run."""
            if not self._settings:
                # First run: Escape means "start with these choices" — otherwise
                # onboarding never completes and re-triggers on every launch.
                self.action_start()
                return
            from nyora_tui.i18n import set_language

            if self._orig_theme is not None:
                self.app.theme = self._orig_theme
            if self._orig_lang is not None:
                set_language(self._orig_lang)
            self.app.pop_screen()

        def action_start(self) -> None:
            from textual.widgets import Select, SelectionList, Switch

            from nyora.config import (
                set_config_theme,
                set_languages,
                set_onboarded,
                set_show_nsfw,
                set_ui_lang,
            )
            from nyora_tui.i18n import set_language

            # Persist the app language + theme chosen above (already applied live).
            uilang = self.query_one("#p_uilang", Select).value
            if uilang is not Select.BLANK:
                set_ui_lang(str(uilang))
                set_language(str(uilang))
            set_config_theme(self.app.theme)

            show = self.query_one("#p_nsfw_sw", Switch).value
            set_show_nsfw(show)
            # Only persist source-languages once the picker actually populated —
            # a Save before sources load would otherwise wipe the saved filter.
            if self._populated:
                langs = [str(v) for v in self.query_one("#p_langs", SelectionList).selected]
                set_languages(langs)
                lang_set = set(langs)
            else:
                lang_set = set(getattr(self.app, "_languages", set()) or set())
            set_onboarded(True)
            app: Any = self.app
            app._apply_content_prefs(show, lang_set)
            self.app.pop_screen()

    # ----------------------------------------------------------------------- #
    # Library (synced favourites).
    # ----------------------------------------------------------------------- #
    class LibraryScreen(Screen):
        """Library with two tabs — Favourites and Downloads. Local-first; when
        signed in, favourites also sync to the cloud."""

        BINDINGS = [
            Binding("escape,b", "app.pop_screen", "Back"),
            Binding("q", "app.quit", "Quit"),
            Binding("tab,right,l", "next_tab", "Switch tab"),
            Binding("left,h", "next_tab", "Tab", show=False),
            Binding("r", "reload", "Sync"),
            Binding("u,delete", "remove", "Remove"),
            Binding("j,down", "cursor_down", "Down", show=False),
            Binding("k,up", "cursor_up", "Up", show=False),
            Binding("g", "top", "Top", show=False),
            Binding("G", "bottom", "Bottom", show=False),
        ]
        CSS = """
        #lib_tabs {
            height: 1; padding: 0 2; background: $surface; border-bottom: solid $panel;
        }
        #lib_table { height: 1fr; padding: 0 1; }
        #lib_msg { padding: 2 3; }
        """

        def __init__(self, client, sync, sources, lib, dl) -> None:
            super().__init__()
            self._client = client
            self._sync = sync
            self._lib = lib
            self._dl = dl
            self._by_id = {s.id: s for s in sources}
            self._tab = "fav"
            self._items: list = []

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static("", id="lib_tabs")
            yield DataTable(id="lib_table", cursor_type="row", zebra_stripes=True)
            yield Static("", id="lib_msg")
            yield Footer()

        def on_mount(self) -> None:
            self._render_tabs()
            self._build()
            if self._sync.is_signed_in:
                self._sync_cloud()

        def _render_tabs(self) -> None:
            def pill(tab: str, label: str, action: str) -> str:
                style = "b $background on $primary" if tab == self._tab else "$text-muted"
                return f"[@click={action}][{style}] {label} [/][/]"

            n_fav = len(self._lib.favourites())
            n_dl = len(self._dl.entries())
            fav_label = f"{t('library.favourites')} · {n_fav}"
            dl_label = f"{t('downloads.title')} · {n_dl}"
            self.query_one("#lib_tabs", Static).update(
                f"{pill('fav', fav_label, 'tab_fav')}   {pill('dl', dl_label, 'tab_dl')}"
            )

        def action_tab_fav(self) -> None:
            self._tab = "fav"
            self._render_tabs()
            self._build()

        def action_tab_dl(self) -> None:
            self._tab = "dl"
            self._render_tabs()
            self._build()

        def action_next_tab(self) -> None:
            (self.action_tab_dl if self._tab == "fav" else self.action_tab_fav)()

        def _build(self) -> None:
            table = self.query_one("#lib_table", DataTable)
            table.clear(columns=True)
            msg = self.query_one("#lib_msg", Static)
            if self._tab == "fav":
                table.add_columns("title", "source")
                self._items = self._lib.favourites()
                if not self._items:
                    msg.update(f"[dim]{t('library.empty')}[/]")
                    return
                msg.update("")
                for i, it in enumerate(self._items):
                    src = self._by_id.get(it.get("source", ""))
                    name = src.name if src else (it.get("source") or "—")
                    table.add_row(_esc(_truncate(it.get("title", ""), 58)), _esc(name), key=str(i))
            else:
                table.add_columns("manga", "chapter", "pages", "when")
                self._items = self._dl.entries()
                if not self._items:
                    msg.update(f"[dim]{t('downloads.empty')}[/]")
                    return
                msg.update("")
                for i, it in enumerate(self._items):
                    table.add_row(
                        _esc(_truncate(it.get("manga_title", ""), 34)),
                        _esc(_truncate(it.get("chapter_title", ""), 26)),
                        str(it.get("pages", 0)),
                        _esc(_hist_when(it.get("downloaded_at", ""))),
                        key=str(i),
                    )
            table.focus()

        def action_reload(self) -> None:
            if self._tab == "fav" and self._sync.is_signed_in:
                self.query_one("#lib_msg", Static).update(f"[dim]{_esc(t('toast.syncing'))}[/]")
                self._sync_cloud()
            else:
                self._build()

        @work(exclusive=True, thread=True, group="libsync")
        def _sync_cloud(self) -> None:
            rows, _err = _safe(self._sync.library)
            self.app.call_from_thread(self._merged, rows or [])

        def _merged(self, rows) -> None:
            self._lib.merge_cloud_favourites(rows)
            self._render_tabs()
            self._build()

        def action_remove(self) -> None:
            row = self._t().cursor_row
            if not (0 <= row < len(self._items)):
                return
            it = self._items[row]
            if self._tab == "fav":
                mid = it.get("manga_id", "")
                self._lib.remove_favourite(mid)
                if self._sync.is_signed_in:
                    _safe(self._sync.unfavourite, mid)
                self.notify(t("toast.removed"), severity="information")
            self._render_tabs()
            self._build()

        def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
            idx = int(event.row_key.value) if event.row_key.value is not None else -1
            if not (0 <= idx < len(self._items)):
                return
            it = self._items[idx]
            if self._tab == "fav":
                self._open_details(it)
            else:
                self._open_download(it)

        def _open_details(self, it) -> None:
            from nyora.models import Manga

            src = self._by_id.get(it.get("source", ""))
            if src is None:
                self.notify(t("toast.not_installed"), severity="warning")
                return
            manga = Manga(id=it.get("manga_id", ""), title=it.get("title", ""),
                          url=it.get("url", ""), cover_url=it.get("cover", ""))
            self.app.push_screen(DetailsScreen(self._client, self._sync, src, manga))

        def _open_download(self, it) -> None:
            import types

            chapter = types.SimpleNamespace(
                title=it.get("chapter_title", ""), id=it.get("chapter_id", ""),
                url="", branch=None, number=0,
            )
            self.app.push_screen(
                PagesScreen(None, None, None, None, chapter, local_cbz=it.get("file", ""))
            )

        def _t(self):
            return self.query_one("#lib_table", DataTable)

        def action_cursor_down(self) -> None:
            self._t().action_cursor_down()

        def action_cursor_up(self) -> None:
            self._t().action_cursor_up()

        def action_top(self) -> None:
            self._t().move_cursor(row=0)

        def action_bottom(self) -> None:
            self._t().move_cursor(row=self._t().row_count - 1)

    # ----------------------------------------------------------------------- #
    # History (local reading progress; also synced to the cloud when signed in).
    # ----------------------------------------------------------------------- #
    class HistoryScreen(Screen):
        """Recent reading history; enter re-opens the title."""

        BINDINGS = [
            Binding("escape,b", "app.pop_screen", "Back"),
            Binding("q", "app.quit", "Quit"),
            Binding("r", "reload", "Refresh"),
            Binding("j,down", "cursor_down", "Down", show=False),
            Binding("k,up", "cursor_up", "Up", show=False),
            Binding("g", "top", "Top", show=False),
            Binding("G", "bottom", "Bottom", show=False),
        ]
        CSS = """
        #hist_head {
            height: 1; padding: 0 2; background: $surface; color: $secondary;
            text-style: bold; border-bottom: solid $panel;
        }
        #hist_table { height: 1fr; padding: 0 1; }
        #hist_msg { padding: 2 3; }
        """

        def __init__(self, client, sync, sources, lib, dl) -> None:
            super().__init__()
            self._client = client
            self._sync = sync
            self._lib = lib
            self._by_id = {s.id: s for s in sources}
            self._items: list = []

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static(t("history.title"), id="hist_head")
            yield DataTable(id="hist_table", cursor_type="row", zebra_stripes=True)
            yield Static("", id="hist_msg")
            yield Footer()

        def on_mount(self) -> None:
            self.query_one("#hist_table", DataTable).add_columns("title", "chapter", "%", "when")
            self.action_reload()

        def action_reload(self) -> None:
            # Pull cloud history first when signed in (bidirectional, like the
            # library and nyora-web), then render — else render the local store.
            if self._sync.is_signed_in:
                self.query_one("#hist_msg", Static).update(f"[dim]{_esc(t('toast.syncing'))}[/]")
                self._sync_cloud()
            else:
                self._build()

        @work(exclusive=True, thread=True, group="histsync")
        def _sync_cloud(self) -> None:
            rows, _err = _safe(self._sync.history)
            self.app.call_from_thread(self._merged, rows or [])

        def _merged(self, rows) -> None:
            self._lib.merge_cloud_history(rows)
            self._build()

        def _build(self) -> None:
            msg = self.query_one("#hist_msg", Static)
            table = self.query_one("#hist_table", DataTable)
            table.clear()
            self._items = self._lib.history()
            if not self._items:
                msg.update(f"[dim]{t('history.empty')}[/]")
                self.query_one("#hist_head", Static).update(t("history.title"))
                return
            msg.update("")
            for i, it in enumerate(self._items):
                pct = int(float(it.get("percent", 0.0) or 0.0) * 100)
                table.add_row(
                    _esc(_truncate(it.get("title", ""), 44)),
                    _esc(_truncate(it.get("chapter_title", "") or "—", 26)),
                    f"{pct}%",
                    _esc(_hist_when(it.get("updated_at", ""))),
                    key=str(i),
                )
            self.query_one("#hist_head", Static).update(
                f"{t('history.title')} · {len(self._items)}"
            )
            table.focus()

        def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
            idx = int(event.row_key.value) if event.row_key.value is not None else -1
            if not (0 <= idx < len(self._items)):
                return
            from nyora.models import Manga

            it = self._items[idx]
            src = self._by_id.get(it.get("source", ""))
            if src is None:
                self.notify(t("toast.not_installed"), severity="warning")
                return
            manga = Manga(id=it.get("manga_id", ""), title=it.get("title", ""),
                          url=it.get("url", ""), cover_url=it.get("cover", ""))
            self.app.push_screen(DetailsScreen(self._client, self._sync, src, manga))

        def _t(self):
            return self.query_one("#hist_table", DataTable)

        def action_cursor_down(self) -> None:
            self._t().action_cursor_down()

        def action_cursor_up(self) -> None:
            self._t().action_cursor_up()

        def action_top(self) -> None:
            self._t().move_cursor(row=0)

        def action_bottom(self) -> None:
            self._t().move_cursor(row=self._t().row_count - 1)

    # ----------------------------------------------------------------------- #
    # Root browse screen.
    # ----------------------------------------------------------------------- #
    class NyoraTui(App):
        """Nerd-grade terminal reader: dense tables, vim keys, live telemetry."""

        TITLE = "nyora"
        SUB_TITLE = "terminal reader"
        COMMANDS = App.COMMANDS | {NyoraCommands}
        CSS = """
        Screen { background: $background; }
        #sidebar { width: 36; height: 100%; background: $surface; border-right: solid $panel; }
        #src_filter {
            height: 3; margin: 1 1 0 1; padding: 0 1;
            border: round $panel; background: $background; color: $foreground;
        }
        #src_filter:focus { border: round $primary; }
        #src_table { height: 1fr; padding: 0 1; background: $surface; }
        #main { width: 1fr; height: 100%; }
        #modebar { height: 1; padding: 0 2; color: $text-muted; }
        #q {
            height: 3; margin: 0 2 1 2; padding: 0 1;
            border: round $panel; background: $surface; color: $foreground;
        }
        #q:focus { border: round $primary; }
        #welcome { height: 1fr; padding: 2 4; color: $text-muted; }
        #results { height: 1fr; padding: 0 1; display: none; }
        #statusbar {
            dock: bottom; height: 1; padding: 0 2;
            background: $surface; color: $text-muted; border-top: solid $panel;
        }
        DataTable { background: $surface; }
        DataTable > .datatable--header {
            background: $surface; color: $secondary; text-style: bold;
        }
        DataTable:focus > .datatable--cursor {
            background: $primary; color: $background; text-style: bold;
        }
        DataTable > .datatable--cursor { background: $panel; color: $foreground; }
        """
        BINDINGS = [
            Binding("q", "quit", "Quit"),
            Binding("slash", "focus_search", "Search", show=False),
            Binding("f", "focus_filter", "Filter", show=False),
            Binding("p", "popular", "Popular", show=False),
            Binding("l", "latest", "Latest", show=False),
            Binding("n", "next_page", "Next", show=False),
            Binding("N", "prev_page", "Prev", show=False),
            Binding("r", "refresh", "Refresh", show=False),
            Binding("x", "toggle_nsfw", "NSFW", show=False),
            Binding("1", "focus_sidebar", "Browse", show=False),
            Binding("2", "library", "Library"),
            Binding("3", "history", "History"),
            Binding("a", "account", "Account", show=False),
            Binding("t", "themes", "Theme", show=False),
            Binding("L", "language_nav", "Languages", show=False),
            Binding("comma", "settings", "Settings", show=False),
            Binding("question_mark,f1", "help", "Help"),
            Binding("escape", "focus_sidebar", "Sources", show=False),
            Binding("j", "cursor_down", "Down", show=False),
            Binding("k", "cursor_up", "Up", show=False),
            Binding("g", "cursor_top", "Top", show=False),
            Binding("G", "cursor_bottom", "Bottom", show=False),
        ]

        def __init__(self) -> None:
            super().__init__()
            # Load the UI language before anything composes, so the first render
            # (source filter / search placeholders included) is already localised.
            from nyora_tui.i18n import init_from_config

            init_from_config()
            self._client = Nyora()
            self._sync = TuiSync()
            self._lib = LocalLibrary()
            self._dl = Downloads()
            self._sources: list[Source] = []
            self._src_view: list[Source] = []
            # visual rows, each ("hdr", lang) for a group header or ("src", idx) for a source
            self._src_rows: list[tuple[str, object]] = []
            self._results: list = []
            self._current_source: Source | None = None
            self._mode = "popular"
            self._page = 1
            self._query = ""
            self._hide_nsfw = False
            self._languages: set[str] = set()
            self._last_ms = 0.0
            self._loading = False
            self._spin = 0
            self._status_msg = "select a source"

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Horizontal():
                with Vertical(id="sidebar"):
                    yield Input(placeholder=t("sources.filter"), id="src_filter")
                    yield DataTable(id="src_table", cursor_type="row", zebra_stripes=True)
                with Vertical(id="main"):
                    yield Static("", id="modebar")
                    yield Input(placeholder=t("common.search_placeholder"), id="q")
                    yield Static(_WELCOME, id="welcome")
                    yield DataTable(id="results", cursor_type="row", zebra_stripes=True)
            yield Static("", id="statusbar")
            yield Footer()

        def _reveal_results(self) -> None:
            """Swap the welcome panel for the results table on first browse."""
            self.query_one("#welcome", Static).display = False
            self.query_one("#results", DataTable).display = True

        # -- lifecycle ----------------------------------------------------- #
        def on_mount(self) -> None:
            from nyora_tui.i18n import init_from_config

            init_from_config()  # load the persisted UI language before any screen
            for theme in _THEMES.values():
                self.register_theme(theme)
            from nyora.config import read_theme_from_config

            saved = read_theme_from_config()
            self.theme = saved if saved in _THEMES else _DEFAULT_THEME
            # Drop Textual's stock themes so the command palette only offers ours.
            for name in list(self.available_themes):
                if name not in _THEMES:
                    try:
                        self.unregister_theme(name)
                    except Exception:  # noqa: BLE001
                        pass
            self.watch(self, "theme", self._on_theme_changed, init=False)
            src = self.query_one("#src_table", DataTable)
            src.add_columns("source", " ")
            res = self.query_one("#results", DataTable)
            res.add_columns("#", "title", "rating", "state", "tags", "!")
            from nyora.config import read_languages, read_onboarded, read_show_nsfw

            self._hide_nsfw = not read_show_nsfw()
            self._languages = set(read_languages())
            self._render_modebar()
            self.set_interval(0.09, self._tick)
            self._load_sources()
            self.query_one("#src_filter", Input).focus()
            if not read_onboarded():
                self.push_screen(WelcomeScreen(self._sync))

        # -- theming ------------------------------------------------------- #
        def _cell_colors(self) -> tuple[str, str, str]:
            """(label, accent, nsfw) hex for DataTable cells, from the active theme."""
            th = self.current_theme
            return (th.secondary or "#C7A6D9", th.primary or "#FFB1C8", th.error or "#EB7D9B")

        def _persist_theme(self, theme_id: str) -> None:
            try:
                from nyora.config import set_config_theme

                set_config_theme(theme_id)
            except Exception:  # noqa: BLE001 - persistence is best-effort
                pass

        def _on_theme_changed(self, _theme: str) -> None:
            # Recolor themed table cells (Rich hex) to match the new palette.
            try:
                if self.query_one("#src_table", DataTable).row_count:
                    self._render_sources(self.query_one("#src_filter", Input).value)
                if self._results:
                    self._fill_results_table()
            except Exception:  # noqa: BLE001
                pass

        def action_themes(self) -> None:
            self.push_screen(ThemePickerScreen(_SCHEMES, self.theme))

        def on_unmount(self) -> None:
            try:
                self._client.close()
            except Exception:
                pass

        # -- telemetry ----------------------------------------------------- #
        def _tick(self) -> None:
            if self._loading:
                self._spin = (self._spin + 1) % len(SPINNER)
            self._render_statusbar()

        def _render_modebar(self) -> None:
            def pill(mode: str, label: str, action: str) -> str:
                style = "b $background on $primary" if mode == self._mode else "$text-muted"
                # @click makes the pill a mouse target that fires the app action.
                return f"[@click=app.{action}][{style}] {label} [/][/]"

            src = (
                _esc(self._current_source.name)
                if self._current_source else t("sources.none_selected")
            )
            nsfw = f"  [warning]· {_esc(t('sources.nsfw_hidden'))}[/]" if self._hide_nsfw else ""
            pills = "  ".join(
                (
                    pill("popular", t("nav.popular"), "popular"),
                    pill("latest", t("nav.latest"), "latest"),
                    pill("search", t("nav.search"), "focus_search"),
                )
            )
            try:
                self.query_one("#modebar", Static).update(f"{pills}   [dim]›[/]  [b]{src}[/]{nsfw}")
            except Exception:  # noqa: BLE001 - modebar not mounted yet
                pass

        def _render_statusbar(self) -> None:
            spin = f"[$primary]{SPINNER[self._spin]}[/] " if self._loading else ""
            parts = [f"{spin}{self._status_msg}"]
            if self._current_source is not None:
                s = self._current_source
                parts.append(f"[$secondary]{_esc(s.id)}[/]")
                if s.lang:
                    parts.append(_lang_display(s.lang))
            parts.append(f"pg {self._page}")
            if self._last_ms:
                parts.append(f"[$success]{self._last_ms:.0f}ms[/]")
            who = self._sync.email if self._sync.is_signed_in else t("status.guest")
            parts.append(f"[$primary]{_esc(who or 'guest')}[/]")
            try:
                self.query_one("#statusbar", Static).update("  [dim]·[/]  ".join(parts))
            except Exception:  # noqa: BLE001 - status bar not mounted yet / recomposing
                pass

        def _set_status(self, msg: str, *, loading: bool = False) -> None:
            self._status_msg = msg
            self._loading = loading
            self._render_statusbar()

        # -- sources ------------------------------------------------------- #
        def _load_sources(self) -> None:
            self._set_status(t("status.loading_sources"), loading=True)
            self._load_sources_worker()

        @work(exclusive=True, thread=True, group="sources")
        def _load_sources_worker(self) -> None:
            sources, err, ms = _timed(_list_sources, self._client)
            self.call_from_thread(self._on_sources, sources, err, ms)

        def _on_sources(self, sources, err, ms: float) -> None:
            self._last_ms = ms
            if err:
                self._set_status(f"[error]{_esc(t('status.sources_failed', error=str(err)))}[/]")
                return
            self._sources = sources or []
            base = getattr(self._client, "base_url", "")
            self.sub_title = f"{len(self._sources)} sources · bundled engine · {base}"
            self._set_status(t("status.sources_ready", count=len(self._sources)))
            self._render_sources()

        def _visible_sources(self) -> list:
            src = self._sources
            if self._languages:
                src = [s for s in src if (s.lang or "").strip().lower() in self._languages]
            if self._hide_nsfw:
                src = [s for s in src if not s.is_nsfw]
            return src

        def _apply_content_prefs(self, show_nsfw: bool, languages: set[str]) -> None:
            """Apply onboarding content prefs (18+ + language filter) live."""
            self._hide_nsfw = not show_nsfw
            self._languages = set(languages)
            self._render_sources(self.query_one("#src_filter", Input).value)
            self._render_modebar()

        # -- cloud sync (full push+pull on sign-in, like nyora-web) ------------
        @work(exclusive=True, thread=True, group="fullsync")
        def _full_sync(self) -> None:
            """web parity: on sign-in, push the local (guest) library up and pull
            the account's favourites + history down, then merge — one round trip."""
            if not self._sync.is_signed_in:
                return
            res, _err = _safe(self._sync.sync_now, self._lib.favourites(), self._lib.history())
            if res is not None:
                cloud_favs, cloud_hist = res
                self.call_from_thread(self._apply_full_sync, cloud_favs, cloud_hist)

        def _apply_full_sync(self, favs: list, hist: list) -> None:
            self._lib.merge_cloud_favourites(favs)
            self._lib.merge_cloud_history(hist)
            self.notify(t("account.synced"), severity="information")

        def _render_sources(self, query: str = "") -> None:
            from collections import Counter

            table = self.query_one("#src_table", DataTable)
            table.clear()
            filtered = _filter_sources(self._visible_sources(), query)
            # Divide by language: sort into language blocks (English/Multi first,
            # unknown last), each introduced by a group header row.
            ordered = sorted(
                filtered, key=lambda s: (_lang_sort_key(s.lang), (s.name or s.id).casefold())
            )
            self._src_view = ordered
            self._src_rows = []
            counts = Counter((s.lang or "").strip().lower() for s in ordered)
            label_c, accent_c, nsfw_c = self._cell_colors()
            current: object = object()
            for i, s in enumerate(ordered):
                lang = (s.lang or "").strip().lower()
                if lang != current:
                    current = lang
                    # DataTable cells render via Rich markup (no Textual $vars).
                    table.add_row(
                        f"[bold {label_c}]▸ {_esc(_lang_display(s.lang))}[/]",
                        f"[dim]{counts[lang]}[/]",
                        key=f"hdr:{lang}",
                    )
                    self._src_rows.append(("hdr", lang))
                star = f" [{accent_c}]★[/]" if s.is_pinned else ""
                name = _esc(_truncate(s.name, 26))
                flag = ""
                if s.is_nsfw:
                    name = f"[{nsfw_c}]{name}[/]"  # 18+ sources always show red
                    flag = f"[{nsfw_c}]18+[/]"
                table.add_row(f"  {name}{star}", flag, key=f"src:{i}")
                self._src_rows.append(("src", i))

        # -- results ------------------------------------------------------- #
        def _fetch(self) -> None:
            if self._current_source is None:
                self._set_status(f"[warning]{_esc(t('status.select_source_first'))}[/]")
                return
            self._reveal_results()
            self._render_modebar()
            self.query_one("#results", DataTable).clear()
            self._set_status(f"{self._mode} · {_esc(self._current_source.name)}", loading=True)
            self._fetch_worker(self._current_source.id, self._mode, self._query, self._page)

        @work(exclusive=True, thread=True, group="results")
        def _fetch_worker(self, source_id: str, mode: str, query: str, page: int) -> None:
            page_obj, err, ms = _timed(_fetch_browse, self._client, source_id, mode, query, page)
            self.call_from_thread(self._on_results, page_obj, err, ms)

        def _on_results(self, page_obj, err, ms: float) -> None:
            self._last_ms = ms
            table = self.query_one("#results", DataTable)
            table.clear()
            if err:
                self._set_status(f"[error]{_esc(str(err))}[/]")
                return
            rows = page_obj.entries if page_obj else []
            if self._hide_nsfw:
                rows = [m for m in rows if not m.is_nsfw]
            self._results = rows
            self._fill_results_table()
            more = " · [dim]n→more[/]" if page_obj and page_obj.has_next_page else ""
            self._set_status(f"{t('status.results', count=len(rows))}{more}")
            if rows:
                self.query_one("#results", DataTable).focus()

        def _fill_results_table(self) -> None:
            """(Re)build the results table from ``self._results`` in the active palette."""
            table = self.query_one("#results", DataTable)
            table.clear()
            _label, _accent, nsfw_c = self._cell_colors()
            for i, m in enumerate(self._results):
                tags = ", ".join(t.get("title", "") for t in m.tags[:3] if t.get("title"))
                flag = f"[{nsfw_c}]18[/]" if m.is_nsfw else ""
                table.add_row(
                    str(i + 1),
                    _esc(_truncate(m.title, 46)),
                    _rating_badge(m.rating),
                    _esc(_truncate(m.state or "—", 10)),
                    _esc(_truncate(tags, 26)),
                    flag,
                    key=str(i),
                )

        # -- events -------------------------------------------------------- #
        def on_input_changed(self, event: Input.Changed) -> None:
            if event.input.id == "src_filter":
                self._render_sources(event.value)

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "src_filter":
                self.query_one("#src_table", DataTable).focus()
            elif event.input.id == "q":
                self._query = event.value
                self._mode = "search" if event.value.strip() else "popular"
                self._page = 1
                self._fetch()

        def on_key(self, event) -> None:
            # Pressing ↓ in the filter box drops focus into the source list (the
            # intuitive move); the search box likewise drops into results.
            if event.key != "down":
                return
            focused = self.focused
            if focused is self.query_one("#src_filter", Input):
                self.query_one("#src_table", DataTable).focus()
                event.stop()
            elif focused is self.query_one("#q", Input) and self.query_one("#results").display:
                self.query_one("#results", DataTable).focus()
                event.stop()

        def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
            key = event.row_key.value or ""
            if event.data_table.id == "src_table":
                if key.startswith("src:"):
                    idx = int(key[4:])
                    if 0 <= idx < len(self._src_view):
                        self._current_source = self._src_view[idx]
                        self._mode, self._query, self._page = "popular", "", 1
                        self.query_one("#q", Input).value = ""
                        self._fetch()
                return
            if event.data_table.id == "results":
                idx = int(key) if key else -1
                if 0 <= idx < len(self._results):
                    self.push_screen(
                        DetailsScreen(
                            self._client, self._sync, self._current_source, self._results[idx]
                        )
                    )

        # -- actions ------------------------------------------------------- #
        def _focused_table(self) -> DataTable | None:
            w = self.focused
            return w if isinstance(w, DataTable) else None

        def _skip_headers(self, table: DataTable, direction: int) -> None:
            """When landing on a language-header row in the source list, step past it."""
            if table.id != "src_table":
                return

            def on_hdr() -> bool:
                pos = table.cursor_row
                return 0 <= pos < len(self._src_rows) and self._src_rows[pos][0] == "hdr"

            for _ in range(4):
                if not on_hdr():
                    break
                table.action_cursor_down() if direction >= 0 else table.action_cursor_up()
            # The first visual row is always a header, so moving up can strand the
            # cursor there — reverse downward onto the nearest real source row.
            for _ in range(4):
                if not on_hdr():
                    break
                table.action_cursor_down()

        def action_cursor_down(self) -> None:
            if t := self._focused_table():
                t.action_cursor_down()
                self._skip_headers(t, +1)

        def action_cursor_up(self) -> None:
            if t := self._focused_table():
                t.action_cursor_up()
                self._skip_headers(t, -1)

        def action_cursor_top(self) -> None:
            if t := self._focused_table():
                t.move_cursor(row=0)
                self._skip_headers(t, +1)

        def action_cursor_bottom(self) -> None:
            if t := self._focused_table():
                t.move_cursor(row=t.row_count - 1)
                self._skip_headers(t, -1)

        def action_focus_sidebar(self) -> None:
            self.query_one("#src_table", DataTable).focus()

        def action_focus_search(self) -> None:
            self.query_one("#q", Input).focus()

        def action_focus_filter(self) -> None:
            self.query_one("#src_filter", Input).focus()

        def action_settings(self) -> None:
            """Re-open onboarding preferences as a settings screen (change anytime)."""
            self.push_screen(PreferencesScreen(self._sync, settings=True))

        def action_language_nav(self) -> None:
            """Open the language navigator and jump the source list to the choice."""
            from collections import Counter

            # List over ALL sources (not just the currently-visible/filtered set) so
            # a language hidden by the onboarding filter can still be picked — and
            # picking it un-hides that language below.
            counts = Counter((s.lang or "").strip().lower() for s in self._sources)
            langs = [
                (code, _lang_display(code), counts[code])
                for code in sorted(counts, key=_lang_sort_key)
                if code
            ]
            if not langs:
                return
            self.push_screen(LanguageNavScreen(langs), self._on_language_chosen)

        def _on_language_chosen(self, code: str | None) -> None:
            if not code:
                return
            # If the language filter is hiding this language, add it (and persist)
            # so the jump actually reveals its sources instead of no-op'ing.
            if self._languages and code not in self._languages:
                self._languages = self._languages | {code}
                try:
                    from nyora.config import set_languages

                    set_languages(sorted(self._languages))
                except Exception:  # noqa: BLE001 - persistence is best-effort
                    pass
            # Clear any text filter, then jump AFTER the deferred re-render settles
            # (setting Input.value posts a Changed that re-renders asynchronously,
            # which would otherwise reset the cursor we move here).
            self.query_one("#src_filter", Input).value = ""
            self.call_after_refresh(self._jump_to_language, code)

        def _jump_to_language(self, code: str) -> None:
            self._render_sources("")
            table = self.query_one("#src_table", DataTable)
            try:
                row = table.get_row_index(f"hdr:{code}")
            except Exception:  # noqa: BLE001 - language may not be present
                return
            table.move_cursor(row=row, animate=False)
            table.focus()

        def action_popular(self) -> None:
            self._mode, self._page, self._query = "popular", 1, ""
            self.query_one("#q", Input).value = ""
            self._fetch()

        def action_latest(self) -> None:
            self._mode, self._page, self._query = "latest", 1, ""
            self.query_one("#q", Input).value = ""
            self._fetch()

        def action_next_page(self) -> None:
            self._page += 1
            self._fetch()

        def action_prev_page(self) -> None:
            if self._page > 1:
                self._page -= 1
                self._fetch()

        def action_refresh(self) -> None:
            if self.focused is self.query_one("#src_table", DataTable):
                self._load_sources()
            else:
                self._fetch()

        def action_toggle_nsfw(self) -> None:
            self._hide_nsfw = not self._hide_nsfw
            from nyora.config import set_show_nsfw

            set_show_nsfw(not self._hide_nsfw)
            self._render_sources(self.query_one("#src_filter", Input).value)
            if self._current_source is not None:
                self._fetch()
            else:
                self._render_modebar()

        def action_help(self) -> None:
            self.push_screen(KeysScreen())

        def action_account(self) -> None:
            self.push_screen(AccountScreen(self._sync))

        def action_library(self) -> None:
            self.push_screen(
                LibraryScreen(self._client, self._sync, self._sources, self._lib, self._dl)
            )

        def action_history(self) -> None:
            self.push_screen(
                HistoryScreen(self._client, self._sync, self._sources, self._lib, self._dl)
            )

    # ----------------------------------------------------------------------- #
    # Account (sign in / out) modal.
    # ----------------------------------------------------------------------- #
    class AccountScreen(ModalScreen):
        """Sign in or out of Nyora cloud sync."""

        BINDINGS = [Binding("escape", "dismiss", "Close")]
        CSS = """
        AccountScreen { align: center middle; }
        #acct {
            width: 54; height: auto; border: round $primary; background: $surface; padding: 1 2;
        }
        #acct Input { margin-top: 1; }
        #acct_msg { margin-top: 1; }
        """

        def __init__(self, sync) -> None:
            super().__init__()
            self._sync = sync

        def compose(self) -> ComposeResult:
            with Vertical(id="acct"):
                if self._sync.is_signed_in:
                    email = f"[$success]{_esc(str(self._sync.email))}[/]"
                    yield Static(t("account.signed_in_as", email=email))
                    yield Static(f"[dim]{_esc(t('account.sign_out'))} · esc[/]", id="acct_msg")
                else:
                    yield Static(f"[b]{_esc(t('account.sign_in'))}[/]")
                    yield Input(placeholder=t("welcome.email"), id="acct_email")
                    yield Input(placeholder=t("welcome.password"), password=True, id="acct_pw")
                    yield Static(f"[dim]{_esc(t('account.sign_in'))} · esc[/]", id="acct_msg")

        def on_mount(self) -> None:
            if not self._sync.is_signed_in:
                self.query_one("#acct_email", Input).focus()

        def on_key(self, event) -> None:
            if event.key == "enter" and self._sync.is_signed_in:
                self._sync.sign_out()
                self.app.pop_screen()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if self._sync.is_signed_in:
                return
            email = self.query_one("#acct_email", Input).value.strip()
            pw = self.query_one("#acct_pw", Input).value.strip()
            if not email or not pw:
                self.query_one("#acct_msg", Static).update(
                    f"[warning]{_esc(t('welcome.enter_creds'))}[/]"
                )
                return
            try:
                self._sync.sign_in(email, pw)
                app: Any = self.app
                app._full_sync()   # push local up + pull account down (web parity)
                app.pop_screen()
            except Exception as exc:  # noqa: BLE001 - surface auth failure inline
                self.query_one("#acct_msg", Static).update(f"[error]{_esc(str(exc))}[/]")

    # ----------------------------------------------------------------------- #
    # Details + chapters.
    # ----------------------------------------------------------------------- #
    class DetailsScreen(Screen):
        """Full metadata, cover art, and a dense chapter table for one manga."""

        BINDINGS = [
            Binding("escape,b", "app.pop_screen", "Back"),
            Binding("q", "app.quit", "Quit"),
            Binding("f", "favourite", "Favourite"),
            Binding("d", "download", "Download ch"),
            Binding("j,down", "cursor_down", "Down", show=False),
            Binding("k,up", "cursor_up", "Up", show=False),
            Binding("g", "cursor_top", "Top", show=False),
            Binding("G", "cursor_bottom", "Bottom", show=False),
        ]
        CSS = """
        #d_side { width: 46; background: $surface; border-right: solid $panel; padding: 1 2; }
        #d_cover { height: auto; }
        #d_meta { height: auto; padding: 1 0 0 0; }
        #d_main { width: 1fr; }
        #d_head {
            height: 1; padding: 0 2; background: $surface; color: $secondary;
            text-style: bold; border-bottom: solid $panel;
        }
        #chapters { height: 1fr; padding: 0 1; }
        """

        def __init__(self, client, sync, source, manga) -> None:
            super().__init__()
            self._client = client
            self._sync = sync
            self._source = source
            self._manga = manga
            self._details: MangaDetails | None = None

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Horizontal():
                # Top-aligned scrollable column: metadata first (title pinned to
                # the top), cover below it, so an absent cover leaves no gap.
                with VerticalScroll(id="d_side"):
                    yield Static(t("details.loading"), id="d_meta")
                    yield Vertical(id="d_cover")
                with Vertical(id="d_main"):
                    yield Static(t("details.chapters"), id="d_head")
                    yield DataTable(id="chapters", cursor_type="row", zebra_stripes=True)
            yield Footer()

        def on_mount(self) -> None:
            t = self.query_one("#chapters", DataTable)
            t.add_columns("#", "chapter", "vol", "branch", "scanlator", "age")
            self._load()

        @work(exclusive=True, thread=True, group="details")
        def _load(self) -> None:
            details, err = _safe(
                _fetch_details, self._client, self._source.id, self._manga.url, self._manga.title
            )
            self.app.call_from_thread(self._on_details, details, err)

        def _on_details(self, details, err) -> None:
            if err or details is None:
                self.query_one("#d_meta", Static).update(f"[error]{_esc(str(err))}[/]")
                return
            self._details = details
            self._render_meta()
            self.query_one("#d_head", Static).update(
                f"{t('details.chapters')} · {len(details.chapters)}"
            )
            self._render_chapters()
            self.query_one("#chapters", DataTable).focus()
            self._load_cover(details.manga)

        def _render_meta(self) -> None:
            if self._details is None:
                return
            app: Any = self.app
            m = self._details.manga
            fav = app._lib.is_favourite(manga_id_of(m))
            heart = "[$accent]♥ in library[/]" if fav else "[dim]♡ press f to favourite[/]"
            authors = ", ".join(m.authors) if m.authors else "Unknown"
            tags = ", ".join(t.get("title", "") for t in m.tags if t.get("title"))
            lines = [
                f"[b $accent]{_esc(m.title)}[/]",
                heart,
                "",
                f"[$secondary]rating[/]  {_rating_badge(m.rating)}   "
                f"[$secondary]state[/]  {_esc(m.state or '—')}"
                + ("   [error]NSFW[/]" if m.is_nsfw else ""),
                f"[$secondary]author[/]  {_esc(authors)}",
                f"[$secondary]source[/]  {_esc(self._source.name)}",
                f"[$secondary]chaps[/]   {len(self._details.chapters)}",
            ]
            if m.alt_titles:
                alt = _esc(_truncate(", ".join(m.alt_titles), 60))
                lines.append(f"[$secondary]alt[/]     {alt}")
            if tags:
                lines.append(f"[$secondary]tags[/]    {_esc(_truncate(tags, 120))}")
            lines += ["", _esc(m.description) if m.description else "[dim](no description)[/]"]
            self.query_one("#d_meta", Static).update("\n".join(lines))

        def _render_chapters(self) -> None:
            if self._details is None:
                return
            app: Any = self.app
            mid = manga_id_of(self._details.manga)
            table = self.query_one("#chapters", DataTable)
            table.clear()
            for i, c in enumerate(self._details.chapters):
                num = f"{c.number:g}" if c.number else str(i + 1)
                got = app._dl.is_downloaded(mid, c)
                title = ("[success]⤓[/] " if got else "") + _esc(_truncate(c.title or c.id, 46))
                table.add_row(
                    num,
                    title,
                    str(c.volume or "—"),
                    _esc(_truncate(c.branch or "—", 12)),
                    _esc(_truncate(c.scanlator or "—", 14)),
                    _relative_age(c.upload_date),
                    key=str(i),
                )

        @work(exclusive=True, thread=True, group="cover")
        def _load_cover(self, manga) -> None:
            url = (
                manga.large_cover_url
                or manga.cover_url
                or self._manga.large_cover_url
                or self._manga.cover_url
            )
            if not url:
                return
            import io

            import httpx
            from PIL import Image

            try:
                with httpx.Client(timeout=20.0, follow_redirects=True) as http:
                    res = http.get(url, headers={"User-Agent": BROWSER_UA})
                res.raise_for_status()
                img = Image.open(io.BytesIO(res.content)).convert("RGB")
            except Exception:  # noqa: BLE001 - cover is decorative; never break details
                return
            self.app.call_from_thread(self._mount_cover, img)

        def _mount_cover(self, img) -> None:
            try:
                container = self.query_one("#d_cover", Vertical)
                _mount_image(container, img, 42)
            except Exception:  # noqa: BLE001
                pass

        def _table(self):
            return self.query_one("#chapters", DataTable)

        def action_cursor_down(self) -> None:
            self._table().action_cursor_down()

        def action_cursor_up(self) -> None:
            self._table().action_cursor_up()

        def action_cursor_top(self) -> None:
            self._table().move_cursor(row=0)

        def action_cursor_bottom(self) -> None:
            self._table().move_cursor(row=self._table().row_count - 1)

        def action_favourite(self) -> None:
            """Toggle favourite locally; mirror to the cloud when signed in."""
            if self._details is None:
                return
            app: Any = self.app
            manga = self._details.manga
            fav = app._lib.toggle_favourite(self._source.id, manga)
            if self._sync.is_signed_in:
                if fav:
                    _safe(self._sync.favourite, self._source.id, manga)
                else:
                    _safe(self._sync.unfavourite, manga_id_of(manga))
            self._render_meta()
            self.notify(
                t("toast.added") if fav else t("toast.removed"), severity="information"
            )

        def action_download(self) -> None:
            """Download the highlighted chapter into the managed downloads folder."""
            if self._details is None:
                return
            row = self._table().cursor_row
            if not (0 <= row < len(self._details.chapters)):
                return
            chapter = self._details.chapters[row]
            self.notify(
                t("reader.downloading", title=chapter.title or chapter.id),
                severity="information",
            )
            self._download_chapter(chapter)

        @work(exclusive=False, thread=True, group="dl")
        def _download_chapter(self, chapter) -> None:
            from nyora.cli import _download_cbz

            if self._details is None:
                return
            app: Any = self.app
            manga = self._details.manga
            pages, err = _safe(
                _fetch_pages, self._client, self._source.id, chapter.url, chapter.branch
            )
            if err or not pages:
                self.app.call_from_thread(
                    self.notify,
                    t("reader.no_pages_error", error=str(err or "empty")),
                    severity="error",
                )
                return
            cbz = app._dl.cbz_path(self._source.name, manga, chapter)
            saved, _total = _download_cbz(pages, cbz)
            app._dl.record(self._source.id, self._source.name, manga, chapter, cbz, saved)
            self.app.call_from_thread(self._after_download, chapter, saved, cbz.name)

        def _after_download(self, chapter, count: int, name: str) -> None:
            self.notify(
                t("reader.saved_full", name=name, count=count) + " → Downloads/nyora-tui",
                severity="information",
            )
            if self._details is not None:
                self._render_chapters()  # show the ⤓ marker

        def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
            if self._details is None:
                return
            idx = int(event.row_key.value) if event.row_key.value is not None else -1
            if 0 <= idx < len(self._details.chapters):
                self.app.push_screen(
                    PagesScreen(
                        self._client, self._source, self._sync, self._details,
                        self._details.chapters[idx],
                    )
                )

    # ----------------------------------------------------------------------- #
    # Reader (continuous webtoon).
    # ----------------------------------------------------------------------- #
    class PagesScreen(Screen):
        """Reader with three modes — WEBTOON (scroll), PAGED (LTR), PAGED_RTL —
        order-aware chapter navigation, fit control, and cloud history."""

        BINDINGS = [
            Binding("escape", "app.pop_screen", "Back"),
            Binding("q", "app.quit", "Quit"),
            Binding("m", "cycle_mode", "Mode"),
            Binding("f", "toggle_fit", "Fit"),
            Binding("n", "next_chapter", "Next ch"),
            Binding("p", "prev_chapter", "Prev ch"),
            Binding("d", "download", "Download"),
            # webtoon scroll
            Binding("j,down", "scroll_down", "Down", show=False),
            Binding("k,up", "scroll_up", "Up", show=False),
            Binding("ctrl+d", "half_down", "½", show=False),
            Binding("ctrl+u", "half_up", "½", show=False),
            Binding("space", "advance", "Page/Down"),
            Binding("b", "page_up", "Page↑", show=False),
            # paged navigation (arrows are RTL-aware, like the web reader)
            Binding("right,l", "arrow_right", "→", show=False),
            Binding("left,h", "arrow_left", "←", show=False),
            Binding("g", "first", "First", show=False),
            Binding("G", "last", "Last", show=False),
        ]
        CSS = """
        PagesScreen { background: $background; }
        #reader_head {
            height: 1; padding: 0 2; background: $surface; color: $secondary;
            text-style: bold; border-bottom: solid $panel;
        }
        #pages_container { background: $background; align-horizontal: center; }
        #reader_status { padding: 2 3; }
        .pageslot { height: auto; width: 100%; }
        /* Paged view: one page centred in the viewport (whole page visible). */
        .paged_page {
            width: 100%; height: 1fr; align: center middle; content-align: center middle;
        }
        #reader_foot {
            dock: bottom; height: 1; padding: 0 2; background: $surface;
            color: $text-muted; border-top: solid $panel;
        }
        """

        def __init__(self, client, source, sync, details, chapter, local_cbz=None) -> None:
            super().__init__()
            self._client = client
            self._source = source
            self._sync = sync
            self._details = details
            self.chapter = chapter
            self._local_cbz = local_cbz  # set → read pages from a .cbz on disk
            from nyora.config import read_reader_prefs

            prefs = read_reader_prefs()
            mode = prefs.get("mode")
            fit = prefs.get("fit")
            self._mode: str = mode if mode in ("WEBTOON", "PAGED", "PAGED_RTL") else "WEBTOON"
            # Paged modes default to HEIGHT (contain) so a whole page fits on screen.
            self._fit: str = fit if fit in ("WIDTH", "HEIGHT") else "HEIGHT"
            self._gen = 0                    # view generation (avoids id collisions on rebuild)
            self._pages: list = []
            self._images: list = []          # decoded PIL images (None until fetched/failed)
            self._errors: list = []          # per-page error string or None
            self._page_idx = 0               # current page in paged modes
            self._loaded = 0
            self._failed = 0
            self._done_flag = False

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static("", id="reader_head")
            with VerticalScroll(id="pages_container"):
                yield Static(t("reader.resolving"), id="reader_status")
            yield Static("", id="reader_foot")
            yield Footer()

        def on_mount(self) -> None:
            self.set_interval(0.25, self._update_foot)
            self._render_head()
            if self._local_cbz:
                self._load_local()
            else:
                self._load()

        # -- header / footer ---------------------------------------------- #
        def _render_head(self) -> None:
            proto = _PROTOCOL if _PROTOCOL != "none" else t("reader.no_graphics")
            title = _esc(self.chapter.title or self.chapter.id)
            mode = {
                "WEBTOON": t("reader.mode_webtoon"),
                "PAGED": t("reader.mode_paged"),
                "PAGED_RTL": t("reader.mode_paged_rtl"),
            }[self._mode]
            offline = f" [success]· {_esc(t('reader.offline'))}[/]" if self._local_cbz else ""
            self.query_one("#reader_head", Static).update(
                f"[b]{title}[/]   [dim]· {mode} · {self._fit.lower()} · img:[/] {proto}{offline}"
            )

        @work(exclusive=True, thread=True, group="local")
        def _load_local(self) -> None:
            import io

            from PIL import Image

            from nyora_tui.store import Downloads

            imgs: list = []
            for data in Downloads.cbz_images(self._local_cbz):
                try:
                    imgs.append(Image.open(io.BytesIO(data)).convert("RGB"))
                except Exception:  # noqa: BLE001
                    imgs.append(None)
            self.app.call_from_thread(self._on_local, imgs)

        def _on_local(self, imgs: list) -> None:
            container = self.query_one("#pages_container", VerticalScroll)
            container.remove_children()
            if not imgs:
                container.mount(Static(f"[warning]{_esc(t('reader.no_offline_pages'))}[/]"))
                self._done_flag = True
                return
            self._pages = [None] * len(imgs)
            self._images = list(imgs)
            self._errors = [None] * len(imgs)
            self._loaded = sum(1 for i in imgs if i is not None)
            self._done_flag = True
            self._page_idx = 0
            self._build_view()

        def _update_foot(self) -> None:
            try:
                foot = self.query_one("#reader_foot", Static)
            except Exception:  # noqa: BLE001
                return
            proto = (
                f"[$secondary]{_PROTOCOL}[/]"
                if _PROTOCOL != "none"
                else f"[error]{_esc(t('reader.no_graphics'))}[/]"
            )
            fail = (
                f"  ·  [warning]{_esc(t('reader.failed_count', count=self._failed))}[/]"
                if self._failed else ""
            )
            if self._mode == "WEBTOON":
                c = self.query_one("#pages_container", VerticalScroll)
                maxy = max(1, c.max_scroll_y)
                pct = min(100, int(c.scroll_offset.y / maxy * 100)) if maxy else 100
                pos = t("reader.pos_webtoon", loaded=self._loaded, total=len(self._pages), pct=pct)
            else:
                pos = t("reader.pos_paged", n=self._page_idx + 1, total=len(self._pages) or "?")
            hint = t("reader.foot_hint")
            foot.update(f"{pos}{fail}  ·  {proto}  ·  [dim]{hint}[/]")

        # -- page loading ------------------------------------------------- #
        @work(exclusive=True, thread=True, group="pages")
        def _load(self) -> None:
            pages, err = _safe(
                _fetch_pages, self._client, self._source.id, self.chapter.url, self.chapter.branch
            )
            self.app.call_from_thread(self._on_pages, pages, err)

        def _on_pages(self, pages, err) -> None:
            container = self.query_one("#pages_container", VerticalScroll)
            container.remove_children()
            if err:
                container.mount(Static(f"[error]{_esc(t('reader.resolve_failed'))}[/]\n{_esc(str(err))}"))
                self._done_flag = True
                return
            self._pages = pages or []
            if not self._pages:
                container.mount(
                    Static(
                        f"[warning]{_esc(t('reader.no_pages_title'))}[/]\n"
                        f"[dim]{_esc(t('reader.no_pages_hint'))}[/]"
                    )
                )
                self._done_flag = True
                return
            n = len(self._pages)
            self._images = [None] * n
            self._errors = [None] * n
            self._page_idx = 0
            self._loaded = self._failed = 0
            self._done_flag = False
            self._build_view()
            self._record_history()
            self._download_images()

        def _build_view(self) -> None:
            """Lay out the container for the current mode (on load / mode / fit switch).

            Each rebuild bumps a generation counter and scopes child ids to it, so
            new pages never collide with predecessors still being removed — this is
            what makes the mode switcher reliably re-render (a stale ``children``
            guard previously left the screen blank on switch).
            """
            self._gen += 1
            container = self.query_one("#pages_container", VerticalScroll)
            container.remove_children()
            self.call_after_refresh(self._populate_view, self._gen)

        def _populate_view(self, gen: int) -> None:
            if gen != self._gen or not self._pages:
                return  # superseded by a newer build, or nothing to show
            container = self.query_one("#pages_container", VerticalScroll)
            if self._mode == "WEBTOON":
                container.mount_all(
                    Vertical(
                        Static(f"[dim]page {i + 1} · loading…[/]"),
                        id=f"pg_{self._gen}_{i}",
                        classes="pageslot",
                    )
                    for i in range(len(self._pages))
                )
                for i, img in enumerate(self._images):
                    if img is not None:
                        self._place_webtoon(i, img)
                    elif self._errors[i]:
                        self._slot(i).mount(
                            Static(f"[error]page {i + 1}: {_esc(str(self._errors[i]))}[/]")
                        )
            else:
                container.mount(Vertical(id=f"page_now_{self._gen}", classes="pageslot paged_page"))
                self._show_page()

        # -- concurrent download ------------------------------------------ #
        @work(exclusive=True, thread=True, group="images")
        def _download_images(self) -> None:
            import io
            from concurrent.futures import ThreadPoolExecutor, as_completed

            import httpx
            from PIL import Image

            http = httpx.Client(timeout=30.0, follow_redirects=True)

            def fetch(index: int, page):
                url = getattr(page, "url", "") or ""
                if not url.lower().startswith(("http://", "https://")):
                    return index, None, f"non-absolute url: {url[:50]}"
                headers = {"Referer": self.chapter.url, "User-Agent": BROWSER_UA}
                headers.update(getattr(page, "headers", {}))
                try:
                    res = http.get(url, headers=headers)
                    if res.status_code != 200:
                        return index, None, f"HTTP {res.status_code}"
                    return index, Image.open(io.BytesIO(res.content)).convert("RGB"), None
                except Exception as exc:  # noqa: BLE001
                    return index, None, f"{type(exc).__name__}: {exc}"

            pages = list(self._pages)
            try:
                with ThreadPoolExecutor(max_workers=5) as pool:
                    futures = [pool.submit(fetch, i, p) for i, p in enumerate(pages)]
                    for fut in as_completed(futures):
                        index, img, err = fut.result()
                        self.app.call_from_thread(self._on_image, index, img, err, pages)
            finally:
                http.close()
            self.app.call_from_thread(self._done)

        def _on_image(self, index: int, img, err, pages) -> None:
            if pages is not self._pages and pages != self._pages:
                return  # a chapter change superseded this download
            if index >= len(self._images):
                return
            if img is None:
                self._failed += 1
                self._errors[index] = err
            else:
                self._loaded += 1
                self._images[index] = img
            if self._mode == "WEBTOON":
                if img is not None:
                    self._place_webtoon(index, img)
                else:
                    try:
                        self._slot(index).remove_children()
                        self._slot(index).mount(
                            Static(f"[error]page {index + 1}: {_esc(str(err))}[/]")
                        )
                    except Exception:  # noqa: BLE001
                        pass
            elif index == self._page_idx:
                self._show_page()

        def _done(self) -> None:
            self._done_flag = True
            if self._loaded == 0 and _PROTOCOL != "none" and self._mode == "WEBTOON":
                self.query_one("#pages_container", VerticalScroll).mount(
                    Static(
                        f"[warning]Rendered 0 of {len(self._pages)} pages (img: {_PROTOCOL}).[/]\n"
                        f"[dim]Downloads finished but this terminal isn't showing {_PROTOCOL} "
                        f"images inside the TUI. Try NYORA_TUI_IMAGE=halfcell, "
                        f"or press d to save.[/]",
                        id="reader_note",
                    ),
                    before=0,
                )

        # -- rendering helpers -------------------------------------------- #
        def _slot(self, i: int) -> Vertical:
            return self.query_one(f"#pg_{self._gen}_{i}", Vertical)

        def _fit_cols(self, img) -> int:
            """Width in cells that fits the whole page in the viewport (contain).

            Returns the min of the width-fit and height-fit widths, so a portrait
            page is limited by height (whole page visible) and a wide spread by
            width. ``WIDTH`` fit skips the height limit (fill width, may scroll).
            """
            cols = self.app.console.width
            if self._fit == "HEIGHT":
                # Rows available for the page: minus header, footer and a margin.
                rows = max(4, self.app.console.height - 4)
                w, h = img.size
                by_h = int(rows * (w / h) * (_CELL_H / _CELL_W))
                return max(8, min(cols, by_h))
            return cols

        def _place_webtoon(self, index: int, img) -> None:
            try:
                slot = self._slot(index)
                slot.remove_children()
                # Webtoon always fills the width and scrolls vertically.
                _mount_image(slot, img, self.app.console.width, fill_width=True)
            except Exception as exc:  # noqa: BLE001
                self._errors[index] = str(exc)

        def _show_page(self) -> None:
            try:
                view = self.query_one(f"#page_now_{self._gen}", Vertical)
            except Exception:  # noqa: BLE001
                return
            view.remove_children()
            i = self._page_idx
            img = self._images[i] if i < len(self._images) else None
            if img is not None:
                try:
                    # Paged: contain-fit (whole page) unless the user forces WIDTH.
                    _mount_image(view, img, self._fit_cols(img), fill_width=self._fit == "WIDTH")
                except Exception as exc:  # noqa: BLE001
                    view.mount(Static(f"[error]page {i + 1}: render: {_esc(str(exc))}[/]"))
            elif self._errors[i]:
                view.mount(Static(f"[error]page {i + 1}: {_esc(str(self._errors[i]))}[/]"))
            else:
                view.mount(Static(f"[dim]page {i + 1} · loading…[/]"))
            self._update_foot()

        # -- history ------------------------------------------------------- #
        @work(exclusive=True, thread=True, group="history")
        def _record_history(self) -> None:
            # The offline reader (opened from a local .cbz) has no source/details
            # to attribute history to — skip rather than crash on self._source.id.
            if self._source is None:
                return
            manga = self._details.manga if self._details else self.chapter
            total = len(self._details.chapters) if self._details else 0
            pct = (self._page_idx + 1) / len(self._pages) if self._pages else 0.0
            # Local history always; cloud history when signed in.
            app: Any = self.app
            _safe(
                app._lib.record_history,
                self._source.id,
                manga,
                self.chapter,
                page=self._page_idx,
                total=total,
                percent=pct,
            )
            if self._sync and self._sync.is_signed_in:
                _safe(
                    self._sync.record_history,
                    self._source.id,
                    manga,
                    self.chapter,
                    page=self._page_idx,
                    total=total,
                    percent=pct,
                )

        # -- chapter navigation (order-aware) ----------------------------- #
        def _open_chapter(self, chapter) -> None:
            self.chapter = chapter
            self._pages = []
            self._images = []
            self._errors = []
            self._page_idx = 0
            self._loaded = self._failed = 0
            self._done_flag = False
            self._render_head()
            container = self.query_one("#pages_container", VerticalScroll)
            container.remove_children()
            container.mount(Static(t("reader.resolving"), id="reader_status"))
            self._load()

        def action_next_chapter(self) -> None:
            nxt = self._details.next_chapter(self.chapter) if self._details else None
            if nxt:
                self._open_chapter(nxt)
            else:
                self.notify(t("reader.no_next"), severity="warning")

        def action_prev_chapter(self) -> None:
            prv = self._details.previous_chapter(self.chapter) if self._details else None
            if prv:
                self._open_chapter(prv)
            else:
                self.notify(t("reader.no_prev"), severity="warning")

        # -- mode / fit ---------------------------------------------------- #
        def action_cycle_mode(self) -> None:
            order = ["WEBTOON", "PAGED", "PAGED_RTL"]
            self._mode = order[(order.index(self._mode) + 1) % len(order)]
            from nyora.config import set_reader_pref

            set_reader_pref("mode", self._mode)
            self._render_head()
            if self._pages:
                self._build_view()
            self._update_foot()

        def action_toggle_fit(self) -> None:
            self._fit = "HEIGHT" if self._fit == "WIDTH" else "WIDTH"
            from nyora.config import set_reader_pref

            set_reader_pref("fit", self._fit)
            self._render_head()
            if self._pages:
                self._build_view()

        # -- paged navigation --------------------------------------------- #
        def _page_step(self, delta: int) -> None:
            target = self._page_idx + delta
            if target < 0:
                self.action_prev_chapter()
                return
            if target >= len(self._pages):
                self.action_next_chapter()
                return
            self._page_idx = target
            self._show_page()
            self._record_history()

        def action_arrow_right(self) -> None:
            if self._mode == "WEBTOON":
                return
            self._page_step(-1 if self._mode == "PAGED_RTL" else 1)

        def action_arrow_left(self) -> None:
            if self._mode == "WEBTOON":
                return
            self._page_step(1 if self._mode == "PAGED_RTL" else -1)

        def action_first(self) -> None:
            if self._mode == "WEBTOON":
                self.action_scroll_home()
            else:
                self._page_idx = 0
                self._show_page()

        def action_last(self) -> None:
            if self._mode == "WEBTOON":
                self.action_scroll_end()
            elif self._pages:
                self._page_idx = len(self._pages) - 1
                self._show_page()

        def action_advance(self) -> None:
            # space: next page (paged) / page-down (webtoon)
            if self._mode == "WEBTOON":
                self._reader().scroll_page_down(animate=True, duration=0.3, easing="out_cubic")
            else:
                self._page_step(1)

        # -- webtoon scrolling -------------------------------------------- #
        def _reader(self) -> VerticalScroll:
            return self.query_one("#pages_container", VerticalScroll)

        def action_scroll_down(self) -> None:
            if self._mode == "WEBTOON":
                self._reader().scroll_relative(y=3, animate=True, duration=0.10, easing="out_cubic")

        def action_scroll_up(self) -> None:
            if self._mode == "WEBTOON":
                self._reader().scroll_relative(
                    y=-3, animate=True, duration=0.10, easing="out_cubic"
                )

        def action_half_down(self) -> None:
            if self._mode == "WEBTOON":
                self._reader().scroll_relative(
                    y=12, animate=True, duration=0.22, easing="out_cubic"
                )

        def action_half_up(self) -> None:
            if self._mode == "WEBTOON":
                self._reader().scroll_relative(
                    y=-12, animate=True, duration=0.22, easing="out_cubic"
                )

        def action_page_up(self) -> None:
            if self._mode == "WEBTOON":
                self._reader().scroll_page_up(animate=True, duration=0.3, easing="out_cubic")
            else:
                self._page_step(-1)

        def action_scroll_home(self) -> None:
            self._reader().scroll_home(animate=True, duration=0.4, easing="out_cubic")

        def action_scroll_end(self) -> None:
            self._reader().scroll_end(animate=True, duration=0.4, easing="out_cubic")

        # -- download ------------------------------------------------------ #
        def action_download(self) -> None:
            if self._local_cbz:
                self.notify(t("reader.already_downloaded"), severity="information")
                return
            if not self._pages or self._source is None:
                self.notify(t("reader.nothing_to_download"), severity="warning")
                return
            self.notify(
                t("reader.downloading", title=self.chapter.title or self.chapter.id),
                severity="information",
            )
            self._save_cbz()

        @work(exclusive=False, thread=True, group="dl")
        def _save_cbz(self) -> None:
            from nyora.cli import _download_cbz

            app: Any = self.app
            manga = self._details.manga if self._details else self.chapter
            cbz = app._dl.cbz_path(self._source.name, manga, self.chapter)
            saved, _total = _download_cbz(self._pages, cbz)
            app._dl.record(self._source.id, self._source.name, manga, self.chapter, cbz, saved)
            self.app.call_from_thread(
                self.notify,
                t("reader.saved_full", name=cbz.name, count=saved) + " → Downloads/nyora-tui",
                severity="information",
            )

    NyoraTui().run()
    return True


if __name__ == "__main__":
    raise SystemExit(main())
