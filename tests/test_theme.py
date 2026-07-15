"""The shared colour-scheme table drives both the TUI themes and CLI palette."""

from __future__ import annotations

import pytest

from nyora import theme


def test_accent_honours_scheme_and_appearance() -> None:
    assert theme.accent_for("sakura") == "#FFB1C8"        # dark variant
    assert theme.accent_for("sakura-light") == "#8C4A60"  # light variant
    assert theme.accent_for("totoro") == "#A6C8FF"


def test_accent_falls_back_to_default() -> None:
    assert theme.accent_for(None) == theme.accent_for(theme.DEFAULT_SCHEME)
    assert theme.accent_for("does-not-exist") == theme.accent_for(theme.DEFAULT_SCHEME)


def test_scheme_of_and_is_light() -> None:
    assert theme.scheme_of("totoro-light") == "totoro"
    assert theme.scheme_of("totoro") == "totoro"
    assert theme.is_light("totoro-light") and not theme.is_light("totoro")


def test_mix_endpoints_and_midpoint() -> None:
    assert theme.mix("#000000", "#ffffff", 0.0) == "#000000"
    assert theme.mix("#000000", "#ffffff", 1.0) == "#ffffff"
    assert theme.mix("#000000", "#ffffff", 0.5) == "#808080"


def test_cli_palette_follows_persisted_theme(monkeypatch: pytest.MonkeyPatch) -> None:
    """`nyora-cli`'s brand colour is the accent of whatever theme is persisted."""
    cli = pytest.importorskip("nyora.cli")
    monkeypatch.setattr("nyora.config.read_theme_from_config", lambda: "totoro")
    built = cli._build_theme()
    # Rich lower-cases hex; compare case-insensitively.
    assert theme.accent_for("totoro").lower() in str(built.styles["nyora.brand"]).lower()
