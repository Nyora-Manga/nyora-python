"""Tests for the ``nyora_tui`` interactive reader, fully offline.

These never start textual/rich; they exercise only the import surface and the
non-interactive (non-TTY) early-exit path of :func:`nyora_tui.app.main`, which
must print a friendly notice and return ``0`` cleanly without requiring a real
terminal or touching the network.
"""

from __future__ import annotations

import io
import sys
from typing import Any

import pytest

tui = pytest.importorskip("nyora_tui.app", reason="nyora_tui written concurrently")


class _NotATty(io.StringIO):
    """A writable stdin/stdout stand-in whose ``isatty()`` reports ``False``."""

    def isatty(self) -> bool:
        return False


class _BoomNyora:
    """Sentinel client: constructing/using it would be a bug on the no-TTY path."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - must not run
        raise AssertionError("Nyora must not be constructed on the non-TTY path")


def test_module_imports() -> None:
    """``import nyora_tui.app`` works and exposes an ``main`` entry point."""
    assert callable(tui.main)


def test_main_non_tty_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """In a non-interactive environment ``main()`` exits cleanly with ``0``.

    We force both ``sys.stdout`` and ``sys.stdin`` to report ``isatty() ==
    False`` so the reader takes its early no-TTY branch. ``nyora.Nyora`` is
    stubbed to a sentinel that raises if instantiated, proving the early return
    happens before any client/runtime is created (no network, no JS engine, no
    real terminal). textual/rich are never started.
    """
    out = _NotATty()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stdin", _NotATty())
    # Guard the name the TUI actually constructs.
    monkeypatch.setattr(tui, "Nyora", _BoomNyora, raising=False)

    rc = tui.main()
    assert isinstance(rc, int)
    assert rc == 0
    # A friendly notice (not a traceback) is emitted to stdout.
    assert "terminal" in out.getvalue().lower()


def test_has_interactive_terminal_handles_missing_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_has_interactive_terminal`` returns ``False`` (no crash) when stdout is None."""
    monkeypatch.setattr(sys, "stdout", None, raising=False)
    assert tui._has_interactive_terminal() is False


def test_has_interactive_terminal_handles_raising_isatty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stream whose ``isatty()`` raises is treated as non-interactive, not fatal."""

    class _Raises:
        def isatty(self) -> bool:
            raise OSError("no tty")

    monkeypatch.setattr(sys, "stdout", _Raises())
    assert tui._has_interactive_terminal() is False
