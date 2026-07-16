"""Tests for the ``nyora-cli`` argparse entrypoint, fully offline.

``nyora.cli`` is written concurrently; if it is not importable yet the whole
module is skipped so the suite stays green. When present, the data subcommands
are driven against a fake cloud :class:`nyora.Nyora` client so no network is
involved.
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

    def iter_popular(self, source_id: str, *, limit: int | None = None, **_: Any) -> Any:
        from nyora.pagers import MangaPager

        return MangaPager(lambda page: self.popular(source_id, page), limit=limit)

    def iter_latest(self, source_id: str, *, limit: int | None = None, **_: Any) -> Any:
        from nyora.pagers import MangaPager

        return MangaPager(lambda page: self.latest(source_id, page), limit=limit)

    def iter_search(self, source_id: str, query: str, *, limit: int | None = None, **_: Any) -> Any:
        from nyora.pagers import MangaPager

        return MangaPager(lambda page: self.search(source_id, query, page), limit=limit)


class FakeNyora:
    instances: int = 0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        FakeNyora.instances += 1
        self.sources = FakeSources()
        self.manga = FakeManga()
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> FakeNyora:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


@pytest.fixture(autouse=True)
def patch_nyora(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch the symbol where cli imports/uses it (cli does `from nyora.client import Nyora`).
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
    monkeypatch.setattr("sys.argv", ["nyora"])  # invoked as bare `nyora`

    rc = cli.main([])
    assert rc == 7
    assert len(calls) == 1


def test_bare_nyora_cli_prints_help_not_tui(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`nyora-cli` (no subcommand) prints help — only bare `nyora` opens the TUI."""
    import nyora_tui.app as tui_app

    launched = []
    monkeypatch.setattr(tui_app, "main", lambda *a, **k: launched.append(1))
    monkeypatch.setattr("sys.argv", ["nyora-cli"])  # invoked as `nyora-cli`

    rc = cli.main([])
    assert rc == 0
    assert not launched, "nyora-cli must not launch the TUI"
    assert "usage: nyora-cli" in capsys.readouterr().out


def test_bare_invocation_none_return_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``None`` return from the TUI is normalised to a clean ``0`` exit."""
    import nyora_tui.app as tui_app

    monkeypatch.setattr(tui_app, "main", lambda *a, **k: None)

    assert cli.main([]) == 0


def test_popular_limit_autopaginates(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["popular", "-s", "mangadex", "--limit", "5"])
    assert rc == 0
    assert "Test Manga" in capsys.readouterr().out


def test_search_all_json(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["--json", "search", "-s", "mangadex", "naruto", "--all"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "entries" in payload and payload["has_next_page"] is False


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "nyora" in capsys.readouterr().out


def test_apply_range() -> None:
    chapters = list(range(10))
    assert cli._apply_range(chapters, "1-3") == [0, 1, 2]
    assert cli._apply_range(chapters, "5-") == [4, 5, 6, 7, 8, 9]
    assert cli._apply_range(chapters, "-3") == [0, 1, 2]
    with pytest.raises(ValueError):
        cli._apply_range(chapters, "abc")
    with pytest.raises(ValueError):
        cli._apply_range(chapters, "1-x")


def _raise(exc: Exception) -> Any:
    def _f(*_a: Any, **_k: Any) -> Any:
        raise exc

    return _f


def test_grab_json_manifest(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Avoid real downloads: stub the CBZ writer.
    monkeypatch.setattr(cli, "_download_with_progress", lambda pages, path, **_k: (len(pages), 1))
    rc = cli.main(["--json", "grab", "-s", "mangadex", "berserk"])
    assert rc == 0
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["source"] == "mangadex"
    assert manifest["manga"]["title"] == "Test Manga"
    assert len(manifest["downloaded"]) == 1
    assert manifest["downloaded"][0]["pages"] == 1


def test_batch_json_manifest(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # --json batch must emit only the manifest — no "Fetching…"/"Done…" chatter
    # or progress bars leaking onto stdout (they would corrupt the JSON).
    monkeypatch.setattr(cli, "_download_with_progress", lambda pages, path, **_k: (len(pages), 1))
    rc = cli.main(["--json", "batch", "-s", "mangadex", "-o", "out", "/m/1"])
    assert rc == 0
    manifest = json.loads(capsys.readouterr().out)  # parses => nothing else on stdout
    assert manifest["source"] == "mangadex"
    assert manifest["out_dir"] == "out"
    assert manifest["downloaded"][0]["pages"] == 1


def test_json_error_is_structured(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nyora.errors import NyoraError

    monkeypatch.setattr(FakeManga, "search", _raise(NyoraError("engine down")))
    rc = cli.main(["--json", "search", "-s", "mangadex", "q"])
    assert rc == 1
    assert json.loads(capsys.readouterr().out) == {"error": "engine down"}


def test_completion(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["completion", "bash"])
    assert rc == 0
    assert "register-python-argcomplete" in capsys.readouterr().out


def test_rating_and_flags() -> None:
    # _rating/_flags now return themed Rich markup; assert the payload, not exact styling.
    assert "4.5★" in cli._rating(0.9)
    assert "—" in cli._rating(-1.0)
    assert "18+" in cli._flags(nsfw=True)
    assert cli._flags() == ""
