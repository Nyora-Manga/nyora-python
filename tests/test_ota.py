"""Tests for :class:`nyora.ota.OtaManager` (fully offline).

``nyora.ota`` performs HTTP through module-level ``httpx.get``; we monkeypatch
that with a tiny fake transport serving a manifest, bundle and sources catalog
from in-memory bytes, so nothing touches the network.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from nyora import ota as ota_module
from nyora.errors import NyoraError
from nyora.ota import OtaManager, OtaUpdateResult

BUNDLE_BYTES = b"/* fake bundle */ var NyoraParsers = {};"
SOURCES_BYTES = json.dumps([{"id": "mangadex", "title": "MangaDex"}]).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest(version: int = 7) -> dict[str, Any]:
    return {
        "version": version,
        "bundle": {
            "url": f"{ota_module.OTA_BASE}/parsers.bundle.js",
            "sha256": _sha256(BUNDLE_BYTES),
            "bytes": len(BUNDLE_BYTES),
        },
        "sources": {
            "url": f"{ota_module.OTA_BASE}/sources.json",
            "sha256": _sha256(SOURCES_BYTES),
            "bytes": len(SOURCES_BYTES),
        },
    }


def _install_fake_http(
    monkeypatch: pytest.MonkeyPatch,
    *,
    manifest: dict[str, Any] | None = None,
    bundle: bytes = BUNDLE_BYTES,
    sources: bytes = SOURCES_BYTES,
) -> None:
    """Route ``nyora.ota.httpx.get`` to in-memory responses by URL suffix."""
    body = manifest if manifest is not None else _manifest()

    def fake_get(url: str, *_args: Any, **_kwargs: Any) -> httpx.Response:
        request = httpx.Request("GET", url)
        if url.endswith("manifest.json"):
            return httpx.Response(
                200, json=body, request=request, headers={"content-type": "application/json"}
            )
        if url.endswith("parsers.bundle.js"):
            return httpx.Response(200, content=bundle, request=request)
        if url.endswith("sources.json"):
            return httpx.Response(200, content=sources, request=request)
        return httpx.Response(404, content=b"not found", request=request)

    monkeypatch.setattr(ota_module.httpx, "get", fake_get)


def test_cache_dir_uses_constructor_path(tmp_path: Path) -> None:
    manager = OtaManager(cache_dir=tmp_path / "ota")
    assert manager.cache_dir == tmp_path / "ota"


def test_fetch_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_http(monkeypatch)
    manager = OtaManager(cache_dir=tmp_path / "ota")
    manifest = manager.fetch_manifest()
    assert manifest["version"] == 7
    assert manifest["bundle"]["sha256"] == _sha256(BUNDLE_BYTES)


def test_installed_version_none_when_empty(tmp_path: Path) -> None:
    manager = OtaManager(cache_dir=tmp_path / "ota")
    assert manager.installed_version() is None


def test_update_writes_and_verifies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_http(monkeypatch)
    cache = tmp_path / "ota"
    manager = OtaManager(cache_dir=cache)

    result = manager.update()

    assert isinstance(result, OtaUpdateResult)
    assert result.updated is True
    assert result.version == 7
    assert result.bundle_path.read_bytes() == BUNDLE_BYTES
    assert result.sources_path.read_bytes() == SOURCES_BYTES
    # manifest persisted so installed_version() picks it up
    assert manager.installed_version() == 7
    assert (cache / "manifest.json").exists()


def test_read_bundle_and_sources_prefer_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_http(monkeypatch)
    manager = OtaManager(cache_dir=tmp_path / "ota")
    manager.update()
    assert manager.read_bundle_text() == BUNDLE_BYTES.decode("utf-8")
    assert json.loads(manager.read_sources_text())[0]["id"] == "mangadex"


def test_update_rejects_bad_bundle_sha(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bad = _manifest()
    bad["bundle"]["sha256"] = "0" * 64
    _install_fake_http(monkeypatch, manifest=bad)
    manager = OtaManager(cache_dir=tmp_path / "ota")
    with pytest.raises(NyoraError):
        manager.update()
    # nothing committed
    assert manager.installed_version() is None


def test_is_update_available(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_http(monkeypatch)
    manager = OtaManager(cache_dir=tmp_path / "ota")

    available, installed, latest = manager.is_update_available()
    assert available is True
    assert installed is None
    assert latest == 7

    manager.update()
    available, installed, latest = manager.is_update_available()
    assert available is False
    assert installed == 7
    assert latest == 7


def test_update_skips_when_current(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_http(monkeypatch)
    manager = OtaManager(cache_dir=tmp_path / "ota")
    manager.update()
    again = manager.update()
    assert again.version == 7
    # already up to date -> nothing new downloaded
    assert again.updated is False


def test_force_redownloads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_http(monkeypatch)
    manager = OtaManager(cache_dir=tmp_path / "ota")
    manager.update()
    forced = manager.update(force=True)
    assert forced.updated is True
    assert forced.version == 7


def test_read_bundle_text_falls_back_to_asset_offline(tmp_path: Path) -> None:
    # No OTA cache and no network: must fall back to the bundled/repo asset.
    manager = OtaManager(cache_dir=tmp_path / "empty-ota")
    text = manager.read_bundle_text()
    assert isinstance(text, str)
    assert len(text) > 0


def test_read_sources_text_falls_back_to_asset_offline(tmp_path: Path) -> None:
    manager = OtaManager(cache_dir=tmp_path / "empty-ota")
    text = manager.read_sources_text()
    assert isinstance(text, str)
    # repo sources.json is valid JSON
    json.loads(text)
