# The interactive terminal reader (TUI)

Nyora ships an interactive **terminal reader** for browsing sources, searching,
and listing chapter pages without writing any code. It is built on the same
in-process {py:class}`nyora.direct.Nyora` client used everywhere else, so it
needs no helper, no Node, and no JVM.

```{note}
The TUI is part of the base install (`pip install nyora` pulls in `rich` and
`textual` as core dependencies). There is nothing extra to install.
```

## Starting it

There are two equivalent ways to launch it:

```bash
nyora-cli      # bare command, no subcommand -> launches the TUI
nyora-tui      # dedicated launcher
```

```{important}
Running **`nyora-cli` with no subcommand launches the TUI.** Any subcommand
(`nyora-cli sources`, `nyora-cli search ...`, …) runs the non-interactive CLI
instead — see the [CLI manual](cli.md). Both `nyora-cli` and `nyora-tui`
ultimately call {py:func}`nyora_tui.app.main`.
```

## Requirements: an interactive terminal

The reader draws a full-screen UI and reads keystrokes, so it requires a real
**TTY** on both stdout and stdin.

If stdout (or stdin) is **not** a TTY — for example under CI, when piped
(`nyora-cli | cat`), or redirected to a file — the reader does **not** start.
Instead it prints a short notice and exits cleanly with code `0`:

```text
Nyora terminal reader needs an interactive terminal (a TTY).
stdout is not a TTY here (piped, redirected, or non-interactive shell).
Run 'nyora-cli' (or 'nyora-tui') directly in a terminal to use it.
For scripting, use subcommands instead, e.g. 'nyora-cli sources'.
```

This is intentional: it means a bare `nyora-cli` is always safe to run from a
script or hook without hanging or crashing. For automation, use the CLI
subcommands (with `--json`) or the [library](library.md) directly.

## Three frontends (automatic fallback)

The reader picks the richest frontend your environment supports, in order:

1. **Textual** — a full-screen app with panes, lists, and a footer. Used
   whenever `textual` is importable (it is, in the default install).
2. **Rich** — an interactive prompt with formatted tables, used if `textual`
   is unavailable.
3. **Plain** — a minimal numbered-list `input()` loop, used if neither `rich`
   nor `textual` is available.

All three share the same navigation flow and back-end, and all three degrade
gracefully on network/parse errors (an error is shown in place; the UI never
crashes).

## Navigation flow

Every frontend walks the same path:

```text
Sources  ->  Results (popular / search)  ->  Details + chapters  ->  Chapter pages
```

1. **Sources** — filter the source catalog by name or id, then open one.
2. **Results** — type a query to search, or leave it blank for *popular*. Browse
   the entries; pick one to open it.
3. **Details** — see authors, state, tags, and description, plus the chapter
   list. Pick a chapter.
4. **Pages** — the chapter's image URLs are listed (the reader resolves them; it
   does not download images — use `nyora-cli download` to save a chapter as a
   `.cbz` archive).

## Keybindings and controls

### Textual frontend

| Key | Where | Action |
| --- | ----- | ------ |
| type text | source filter / search box | Live-filter sources, or set the search query. |
| `Enter` | filter/search box | Submit; moves focus into the list (search refetches from page 1). |
| `↑` / `↓`, `Enter` | any list | Move the selection and open the highlighted item. |
| `n` | results screen | Next page (when more results are available). |
| `p` | results screen | Previous page. |
| `Esc` | results / details / pages | Go **back** one screen. |
| `Esc` | sources screen | Quit the app. |
| `q` | anywhere | Quit the app. |

The header shows `Nyora — embedded parser runtime`; the footer lists the active
keybindings for the current screen. Fetches run on background workers, so the UI
stays responsive while loading.

### Rich frontend (fallback)

Interaction is prompt-driven. At each prompt you type:

| Input | Action |
| ----- | ------ |
| a number | Select that numbered row. |
| text | (Re)search with that text (on the results prompt) or filter sources. |
| `+` | Next page (results prompt, when a next page exists). |
| `-` | Previous page (results prompt). |
| `b` | Go back. |
| `q` | Quit. |

On the chapter-pages view it prints the image URLs and waits for `Enter` to go
back.

### Plain frontend (last-resort fallback)

A numbered list with a single prompt accepting: a **number** to select, **text**
to search, `b` to go back, and `q` to quit. The pages view prints the URLs and
waits for `Enter`.

## Exiting

- Textual: `q` or `Esc` from the sources screen.
- Rich/Plain: `q` at any prompt.
- `Ctrl+C` (or end-of-input) anywhere exits cleanly.

In all cases the process returns exit code `0`, and the embedded
{py:class}`nyora.direct.Nyora` client is closed on the way out.

## When to use the CLI instead

The TUI is for interactive exploration. For anything scripted or automated —
listing sources, batch downloads, machine-readable output — use the
[`nyora-cli` subcommands](cli.md) with `--json`, or drive the
[library](library.md) and the [AI-agent guide](agents.md) directly.
