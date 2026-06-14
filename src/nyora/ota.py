"""Over-the-air parser feed management for Nyora Python.

This module keeps the JavaScript parser bundle and source catalog current
without a package release. :class:`OtaManager` fetches a signed manifest from
the public OTA feed, verifies each artifact by SHA-256, and writes the bundle,
catalog, and manifest atomically into a per-user cache directory. When nothing
is cached, reads transparently fall back to the assets shipped inside the
package, so the SDK works fully offline on first run.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import httpx
from platformdirs import user_cache_dir

from nyora.errors import NyoraError

OTA_BASE = "https://Hasan72341.github.io/nyora-ota-parsers"

_MANIFEST_NAME = "manifest.json"
_BUNDLE_NAME = "parsers.bundle.js"
_SOURCES_NAME = "sources.json"


@dataclass
class OtaUpdateResult:
    """Outcome of an OTA update attempt.

    Attributes:
        updated: ``True`` if new artifacts were downloaded and written;
            ``False`` if the cache was already current.
        version: The manifest version now installed in the cache.
        bundle_path: Filesystem path to the cached parser bundle.
        sources_path: Filesystem path to the cached source catalog.
    """

    updated: bool
    version: int
    bundle_path: Path
    sources_path: Path


class OtaManager:
    """Manages the over-the-air parser bundle and source catalog.

    Coordinates fetching the OTA manifest, downloading and SHA-256-verifying the
    parser bundle and source catalog, and caching them atomically per user.
    Reads fall back to the bundled package assets when the cache is empty.

    Example:
        >>> ota = OtaManager()
        >>> available, installed, latest = ota.is_update_available()
        >>> if available:
        ...     result = ota.update()
        ...     print("updated to", result.version)
    """

    def __init__(self, cache_dir: Path | None = None, *, timeout: float = 30.0) -> None:
        """Initialize the manager.

        Args:
            cache_dir: Directory for cached OTA artifacts. Defaults to the
                per-user cache directory (``.../nyora/ota``).
            timeout: HTTP timeout in seconds for manifest and artifact fetches.
        """
        self._cache_dir = (
            Path(cache_dir)
            if cache_dir is not None
            else Path(user_cache_dir("nyora", appauthor=False)) / "ota"
        )
        self._timeout = timeout

    @property
    def cache_dir(self) -> Path:
        """The directory where OTA artifacts are cached."""
        return self._cache_dir

    def fetch_manifest(self) -> dict[str, Any]:
        """Download and parse the remote OTA manifest.

        Returns:
            The manifest as a dict (containing ``version`` and per-artifact
            ``url``/``sha256`` entries).

        Raises:
            NyoraError: If the manifest cannot be fetched, is invalid JSON, or
                is not a JSON object.
        """
        url = f"{OTA_BASE}/{_MANIFEST_NAME}"
        try:
            response = httpx.get(url, timeout=self._timeout, follow_redirects=True)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise NyoraError(f"Failed to fetch OTA manifest: {exc}") from exc
        if not isinstance(data, dict):
            raise NyoraError("OTA manifest is not a JSON object")
        return data

    def installed_version(self) -> int | None:
        """Return the manifest version currently cached, if any.

        Returns:
            The cached integer version, or ``None`` when nothing is cached or
            the cached manifest is unreadable.
        """
        path = self._cache_dir / _MANIFEST_NAME
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        version = data.get("version") if isinstance(data, dict) else None
        return int(version) if isinstance(version, int) else None

    def is_update_available(self) -> tuple[bool, int | None, int | None]:
        """Check whether the remote feed offers a newer version.

        Network or manifest errors are treated as "no update available" rather
        than propagating, so this is safe to call opportunistically.

        Returns:
            A tuple ``(available, installed_version, latest_version)``. Either
            version may be ``None`` when unknown.
        """
        installed = self.installed_version()
        try:
            manifest = self.fetch_manifest()
        except NyoraError:
            return (False, installed, None)
        latest_raw = manifest.get("version")
        latest = int(latest_raw) if isinstance(latest_raw, int) else None
        if latest is None:
            return (False, installed, None)
        available = installed is None or latest > installed
        return (available, installed, latest)

    def update(self, *, force: bool = False) -> OtaUpdateResult:
        """Download and cache the latest parser bundle and source catalog.

        The remote manifest is fetched, each artifact is downloaded and verified
        against its SHA-256, and all files are written atomically. When the
        cache is already current and ``force`` is ``False``, nothing is
        downloaded.

        Args:
            force: Re-download and overwrite even when already up to date.

        Returns:
            An :class:`OtaUpdateResult` describing what was applied.

        Raises:
            NyoraError: If the manifest or an artifact cannot be fetched, or if
                an artifact fails SHA-256 verification.
        """
        manifest = self.fetch_manifest()
        latest_raw = manifest.get("version")
        latest = int(latest_raw) if isinstance(latest_raw, int) else 0
        installed = self.installed_version()

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = self._cache_dir / _BUNDLE_NAME
        sources_path = self._cache_dir / _SOURCES_NAME

        if (
            not force
            and installed is not None
            and latest <= installed
            and bundle_path.exists()
            and sources_path.exists()
        ):
            return OtaUpdateResult(
                updated=False,
                version=installed,
                bundle_path=bundle_path,
                sources_path=sources_path,
            )

        bundle_bytes = self._download_verified(manifest.get("bundle"), "bundle")
        sources_bytes = self._download_verified(manifest.get("sources"), "sources")

        self._atomic_write(bundle_path, bundle_bytes)
        self._atomic_write(sources_path, sources_bytes)
        self._atomic_write(
            self._cache_dir / _MANIFEST_NAME,
            json.dumps(manifest, separators=(",", ":")).encode("utf-8"),
        )

        return OtaUpdateResult(
            updated=True,
            version=latest,
            bundle_path=bundle_path,
            sources_path=sources_path,
        )

    def read_bundle_text(self) -> str:
        """Return the parser bundle source.

        Returns:
            The cached bundle text, or the package-bundled fallback when no
            cache exists.
        """
        return self._read_cached_or_asset(_BUNDLE_NAME)

    def read_sources_text(self) -> str:
        """Return the source catalog JSON.

        Returns:
            The cached catalog text, or the package-bundled fallback when no
            cache exists.
        """
        return self._read_cached_or_asset(_SOURCES_NAME)

    def _read_cached_or_asset(self, name: str) -> str:
        """Read a cached artifact by name, falling back to a bundled asset.

        Args:
            name: The artifact filename to read.

        Returns:
            The artifact text from the cache, or from the package assets.
        """
        cached = self._cache_dir / name
        if cached.exists():
            return cached.read_text(encoding="utf-8")
        return _read_asset_text(name)

    def _download_verified(self, entry: Any, label: str) -> bytes:
        """Download a manifest artifact and verify its SHA-256.

        Args:
            entry: The manifest entry with ``url`` and optional ``sha256``.
            label: Human-readable artifact label for error messages.

        Returns:
            The verified artifact bytes.

        Raises:
            NyoraError: If the entry is malformed, the download fails, or the
                checksum does not match.
        """
        if not isinstance(entry, dict):
            raise NyoraError(f"OTA manifest missing {label!r} entry")
        url = entry.get("url")
        expected = entry.get("sha256")
        if not isinstance(url, str) or not url:
            raise NyoraError(f"OTA manifest {label!r} entry missing url")
        try:
            response = httpx.get(url, timeout=self._timeout, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NyoraError(f"Failed to download OTA {label}: {exc}") from exc
        payload = response.content
        if isinstance(expected, str) and expected:
            actual = hashlib.sha256(payload).hexdigest()
            if actual.lower() != expected.lower():
                raise NyoraError(
                    f"OTA {label} sha256 mismatch: expected {expected}, got {actual}"
                )
        return payload

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        """Write bytes to ``path`` atomically via a temp file and rename.

        Args:
            path: Destination file path.
            data: Bytes to write.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise


def _read_asset_text(name: str) -> str:
    """Read a bundled package asset by filename.

    Args:
        name: The asset filename within ``nyora.assets``.

    Returns:
        The asset contents as text.

    Raises:
        FileNotFoundError: If the asset cannot be located in the package or the
            repository root fallback.
    """
    try:
        return resources.files("nyora.assets").joinpath(name).read_text(encoding="utf-8")
    except FileNotFoundError:
        root = Path(__file__).resolve().parents[2]
        return root.joinpath(name).read_text(encoding="utf-8")
