"""Tests for the ``nyora-cli`` argparse entrypoint, fully offline.

``nyora.cli`` is written concurrently; if it is not importable yet the whole
module is skipped so the suite stays green. When present, the data subcommands
are driven against a fake :class:`nyora.direct.Nyora` so no network or embedded
JS engine is involved.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from nyora.models import MangaDetails, MangaPage, SearchPage, Source
from tests.conftest import (
    SAMPLE_CHAPTER_RAW,
    SAMPLE_MANGA_RAW,
    SAMPLE_PAGE_RAW,
)

cli = pytest.importorskip("nyora.cli", reason="nyora.cli written concurrently")


class FakeSources:
    def list(self) -> list[Source]:
        return [
            Source.from_json(
                {"id": "mangadex", "name": "MangaDex", "lang": "en", "baseUrl": "https://m.test"}
            )
        ]

    def find(self, query: str) -> Source:
        return self.list()[0]


class FakeManga:
    def popular(self, source_id: str, page: int = 1) -> SearchPage:
        return SearchPage.from_json({"entries": [dict(SAMPLE_MANGA_RAW)], "hasNextPage": False})

    def latest(self, source_id: str, page: int = 1) -> SearchPage:
        return SearchPage.from_json({"entries": [dict(SAMPLE_MANGA_RAW)], "hasNextPage": False})

    def search(self, source_id: str, query: str, page: int = 1) -> SearchPage:
        return SearchPage.from_json({"entries": [dict(SAMPLE_MANGA_RAW)], "hasNextPage": False})

    def details(self, source_id: str, manga_url: str, *, title: str = "") -> MangaDetails:
        return MangaDetails.from_json(
            {"manga": dict(SAMPLE_MANGA_RAW), "chapters": [dict(SAMPLE_CHAPTER_RAW)]}
        )

    def pages(
        self, source_id: str, chapter_url: str, *, branch: str | None = None
    ) -> list[MangaPage]:
        return [MangaPage.from_json(dict(SAMPLE_PAGE_RAW))]


class FakeNyora:
    instances: int = 0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        FakeNyora.instances += 1
        self.sources = FakeSources()
        self.manga = FakeManga()
        self.closed = False

    def update(self, *, force: bool = False) -> Any:
        from pathlib import Path

        from nyora.ota import OtaUpdateResult

        return OtaUpdateResult(
            updated=True, version=1, bundle_path=Path("/tmp/b.js"), sources_path=Path("/tmp/s.json")
        )

    def check_update(self) -> tuple[bool, int | None, int | None]:
        return (False, 1, 1)

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> FakeNyora:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


@pytest.fixture(autouse=True)
def patch_nyora(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch the symbol where cli imports/uses it. Cover both possible bindings.
    monkeypatch.setattr("nyora.direct.Nyora", FakeNyora, raising=False)
    if hasattr(cli, "Nyora"):
        monkeypatch.setattr(cli, "Nyora", FakeNyora, raising=False)


def test_sources_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["sources"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "mangadex" in out


def test_sources_json(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["--json", "sources"])
    assert rc == 0
    out = capsys.readouterr().out
    # --json must emit parseable JSON
    payload = json.loads(out)
    assert isinstance(payload, list)
    assert payload[0]["id"] == "mangadex"


def test_search(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["search", "-s", "mangadex", "naruto"])
    assert rc == 0
    assert "Test Manga" in capsys.readouterr().out


def test_popular(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["popular", "-s", "mangadex"]) == 0


def test_latest(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["latest", "-s", "mangadex"]) == 0


def test_details(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["details", "-s", "mangadex", "/manga/manga-1"])
    assert rc == 0
    assert "Test Manga" in capsys.readouterr().out


def test_pages(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["pages", "-s", "mangadex", "/chapter/ch-1"])
    assert rc == 0
    assert "page-1.jpg" in capsys.readouterr().out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["version"])
    assert rc == 0
    assert capsys.readouterr().out.strip() != ""


def test_update(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["update"])
    assert rc == 0


def test_bare_invocation_launches_tui(monkeypatch: pytest.MonkeyPatch) -> None:
    """``main([])`` (no subcommand) must delegate to the TUI entry point.

    The TUI is stubbed to a sentinel so no real terminal app starts; we assert
    the stub is called exactly once and that its return code is propagated.
    ``cli._launch_tui`` imports ``nyora_tui.app.main`` lazily, so patching the
    name on ``nyora_tui.app`` is what the CLI actually resolves.
    """
    calls: list[tuple[Any, ...]] = []

    def fake_tui_main(*args: Any, **kwargs: Any) -> int:
        calls.append(args)
        return 7

    import nyora_tui.app as tui_app

    monkeypatch.setattr(tui_app, "main", fake_tui_main)

    rc = cli.main([])
    assert rc == 7
    assert len(calls) == 1


def test_bare_invocation_none_return_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``None`` return from the TUI is normalised to a clean ``0`` exit."""
    import nyora_tui.app as tui_app

    monkeypatch.setattr(tui_app, "main", lambda *a, **k: None)

    assert cli.main([]) == 0
