# The interactive terminal reader (TUI)

Nyora ships an interactive **terminal reader** for browsing sources, searching,
reading chapters, and syncing a library without writing any code. It drives the
same self-contained {py:class}`nyora.Nyora` client used everywhere else — the
parser engine is bundled and launches locally on demand, so there is no server
to host and no Node process.

Its interface is available in **~40 languages** and follows your chosen colour
theme. On first run a short setup lets you pick your **app language**, a **colour
theme** (light or dark, previewed live), your **source languages**, and whether
to show 18+ sources — all changeable anytime from **Settings** (`,`).

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

1. **Textual** — a full-screen app with a source sidebar, a results pane, and an
   in-terminal webtoon reader that renders chapter pages as images. Used
   whenever `textual` is importable (it is, in the default install).
2. **Rich** — an interactive prompt with formatted tables, used if `textual` is
   unavailable. This frontend also exposes the **cloud sync** account menu and
   synced library.
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
4. **Pages** — in the Textual frontend the chapter's images are downloaded and
   rendered inline as a continuous webtoon view (using the Kitty terminal
   graphics protocol where available, falling back to pixel rendering). In the
   Rich and Plain frontends the page image URLs are listed. To save a chapter to
   disk, use `nyora-cli download` for a `.cbz` archive.

## Cloud sync in the reader

The Rich frontend has a built-in account menu and a synced library, backed by
{py:class}`nyora.sync.NyoraSync` (see the [sync guide](sync.md)). At the "Filter
sources" prompt you can type:

| Input | Action |
| ----- | ------ |
| `sync` (or `account`) | Open the **account menu** — sign in with email + password, or sign out. When signed in, the prompt shows your email. |
| `lib` (or `library`) | Open your **synced library** — the favourites you have pushed to the cloud, joined with their manga metadata. |

Sign-in tokens persist to `~/.config/nyora/sync.json`, so the reader stays
signed in across runs. When you open a manga's **details** while signed in, the
reader offers a **"Favourite to library?"** prompt — press `f` to push that
manga to your cloud library (it lands in the `nyora_manga` and `nyora_favourite`
tables). An empty library shows a hint to favourite manga with `f` from details.

## Keybindings and controls

### Textual frontend

| Key | Where | Action |
| --- | ----- | ------ |
| type text | source filter box (`ctrl+f`) | Live-filter the source list. |
| type text | search box (`ctrl+s`) | Set the search query for the current source. |
| `Enter` | filter / search box | Submit; the source list gains focus, or the search refetches. |
| `↑` / `↓`, `Enter` | any list | Move the selection and open the highlighted item. |
| `ctrl+f` | anywhere | Focus the source filter box. |
| `ctrl+s` | anywhere | Focus the search box. |
| `j` / `k` / `Space` | pages screen | Scroll the webtoon down / up / page-down. |
| `b` / `Esc` | results / details / pages | Go **back** one screen. |
| `Esc` | sources screen | Focus the source list. |
| `t` | sources screen | Open the **colour-theme** picker (light/dark, live preview). |
| `L` | sources screen | Open the **language navigator** — jump the list to any source language. |
| `,` | anywhere | Open **Settings** — app language, theme, source languages, 18+. |
| `ctrl+p` | anywhere | Command palette (fuzzy actions, always available). |
| `m` / `f` | pages screen | Cycle reader **mode** (webtoon / paged / paged-rtl) / **fit**. |
| `n` / `p` | pages screen | Next / previous **chapter**. |
| `q` | anywhere | Quit the app. |

The interface language is chosen at first-run setup and via **Settings** (`,`);
it is shown in your language across ~40 locales, with English as a safe fallback
for anything untranslated.

The header shows `Nyora`; the footer lists the active keybindings for the
current screen. Fetches and image downloads run on background workers, so the UI
stays responsive while loading.

### Rich frontend (fallback)

Interaction is prompt-driven. At the source prompt, `sync`/`lib` open the
account and library views described above. At each list prompt you type:

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

- Textual: `q` from anywhere.
- Rich/Plain: `q` at any prompt.
- `Ctrl+C` (or end-of-input) anywhere exits cleanly.

In all cases the process returns exit code `0`, and the cloud
{py:class}`nyora.Nyora` client is closed on the way out.

## When to use the CLI instead

The TUI is for interactive exploration. For anything scripted or automated —
listing sources, batch downloads, machine-readable output — use the
[`nyora-cli` subcommands](cli.md) with `--json`, or drive the
[library](library.md) and the [AI-agent guide](agents.md) directly.
