"""Auto-provision a Java runtime so the engine works with no Java installed.

The parser engine is a JVM jar; running it needs a JRE. Rather than make users
install Java (especially painful on Windows), this module downloads a minimal
Eclipse Temurin JRE for the current OS/arch on first run, caches it, and reuses
it forever after. Everything here is stdlib-only so the package stays
dependency-free.

Resolution used by :func:`ensure_java`:

1. A usable system ``java`` (>= :data:`MIN_FEATURE`) if one is on ``$JAVA`` /
   ``$JAVA_HOME`` / ``PATH`` — no download needed.
2. A previously cached auto-downloaded JRE.
3. A fresh download from the Adoptium API (one-time, ~40 MB).
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

#: Temurin feature version to download when provisioning a JRE.
FEATURE = 21
#: Minimum acceptable major version for a *system* java before we fall back to
#: downloading (kotatsu-parsers needs 17+).
MIN_FEATURE = 17

#: Override the java executable outright (skips detection + download).
JAVA_ENV = "JAVA"
#: Force auto-download even if a system java exists.
FORCE_DOWNLOAD_ENV = "NYORA_FORCE_JRE_DOWNLOAD"
#: Disable auto-download (system java only; error if absent).
NO_DOWNLOAD_ENV = "NYORA_NO_JRE_DOWNLOAD"


class JreError(RuntimeError):
    """Raised when no Java runtime is available and one can't be provisioned."""


def cache_dir() -> Path:
    """Per-user cache directory for auto-downloaded JREs (OS-appropriate)."""
    override = os.getenv("NYORA_CACHE_DIR")
    if override:
        return Path(override).expanduser() / "jre"
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches" / "nyora"
    elif sys.platform.startswith("win"):
        local = os.getenv("LOCALAPPDATA")
        base = (Path(local) if local else Path.home() / "AppData" / "Local") / "nyora"
    else:
        xdg = os.getenv("XDG_CACHE_HOME")
        base = (Path(xdg) if xdg else Path.home() / ".cache") / "nyora"
    return base / "jre"


def _java_exe(java_home: Path) -> Path:
    """Path to the ``java`` binary inside a JRE/JDK home."""
    name = "java.exe" if os.name == "nt" else "java"
    return java_home / "bin" / name


def _major_version(java: str) -> int | None:
    """Return the major Java version of ``java``, or ``None`` if unknown."""
    try:
        out = subprocess.run(
            [java, "-version"], capture_output=True, text=True, timeout=10
        )
    except Exception:
        return None
    text = f"{out.stderr}\n{out.stdout}"
    m = re.search(r'version "(\d+)(?:\.(\d+))?', text)
    if not m:
        return None
    major = int(m.group(1))
    # Legacy "1.8" style → feature version is the minor (8).
    if major == 1 and m.group(2):
        return int(m.group(2))
    return major


def find_system_java() -> str | None:
    """Locate a system ``java`` via ``$JAVA`` → ``$JAVA_HOME`` → ``PATH``."""
    override = os.getenv(JAVA_ENV)
    if override and shutil.which(override):
        return override
    home = os.getenv("JAVA_HOME")
    if home:
        cand = _java_exe(Path(home))
        if cand.exists():
            return str(cand)
    return shutil.which("java")


def _os_arch() -> tuple[str, str]:
    """Map the current platform to Adoptium ``(os, arch)`` tokens."""
    if sys.platform == "darwin":
        os_token = "mac"
    elif sys.platform.startswith("win"):
        os_token = "windows"
    else:
        os_token = "linux"

    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64", "x64"):
        arch = "x64"
    elif machine in ("arm64", "aarch64"):
        arch = "aarch64"
    elif machine in ("armv7l", "arm"):
        arch = "arm"
    elif machine in ("i386", "i686", "x86"):
        arch = "x86"
    else:
        arch = machine
    return os_token, arch


def _adoptium_url(os_token: str, arch: str) -> str:
    """Adoptium 'latest binary' redirect URL for a JRE of the current platform."""
    return (
        f"https://api.adoptium.net/v3/binary/latest/{FEATURE}/ga/"
        f"{os_token}/{arch}/jre/hotspot/normal/eclipse"
    )


def _cached_java() -> str | None:
    """Return a working java from a previously provisioned JRE, if present."""
    root = cache_dir() / f"temurin{FEATURE}"
    if not root.is_dir():
        return None
    for cand in root.rglob("bin/java*"):
        if cand.name in ("java", "java.exe") and os.access(cand, os.X_OK | os.R_OK):
            return str(cand)
    return None


def _download(url: str, dest: Path, log) -> None:
    """Stream ``url`` to ``dest`` with coarse progress logging."""
    req = urllib.request.Request(url, headers={"User-Agent": "nyora-extension-server"})
    with urllib.request.urlopen(req) as resp:  # noqa: S310 (trusted Adoptium host)
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        step = max(total // 10, 4 * 1024 * 1024) if total else 8 * 1024 * 1024
        next_mark = step
        with dest.open("wb") as fh:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if done >= next_mark:
                    if total:
                        log(f"    …{done // (1024 * 1024)}MB / {total // (1024 * 1024)}MB")
                    else:
                        log(f"    …{done // (1024 * 1024)}MB")
                    next_mark += step


def _extract(archive: Path, into: Path) -> None:
    """Extract a ``.tar.gz`` or ``.zip`` archive into ``into``."""
    if archive.suffix == ".zip" or zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(into)
    else:
        with tarfile.open(archive) as tf:
            tf.extractall(into)


def download_jre(log=None) -> str:
    """Download and cache a Temurin JRE for this platform; return its ``java``.

    Raises:
        JreError: If the platform is unsupported or the download/extract fails.
    """
    def _log(*a: object) -> None:
        if log:
            log(*a)

    os_token, arch = _os_arch()
    url = _adoptium_url(os_token, arch)
    root = cache_dir() / f"temurin{FEATURE}"
    root.mkdir(parents=True, exist_ok=True)

    suffix = ".zip" if os_token == "windows" else ".tar.gz"
    _log(f"  provisioning Temurin {FEATURE} JRE for {os_token}/{arch} (one-time)…")
    try:
        with tempfile.NamedTemporaryFile(
            dir=root, prefix="dl-", suffix=suffix, delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)
        _download(url, tmp_path, _log)
        _log("  extracting…")
        _extract(tmp_path, root)
        tmp_path.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001 — surface a single actionable error
        raise JreError(
            f"Failed to auto-download a JRE from Adoptium ({url}): {exc}. "
            "Install a JRE 17+ yourself and set $JAVA_HOME, or set "
            f"{NO_DOWNLOAD_ENV}=1 to require a system java."
        ) from exc

    java = _cached_java()
    if not java:
        raise JreError(
            f"Downloaded a JRE but no java executable was found under {root}."
        )
    if os.name != "nt":
        try:
            os.chmod(java, 0o755)
        except OSError:
            pass
    _log(f"  ✓ JRE ready ({java})")
    return java


def ensure_java(log=None) -> str:
    """Return a usable ``java`` path, provisioning one if necessary.

    Order: ``$JAVA`` override → cached download → adequate system java →
    fresh download. Honors :data:`FORCE_DOWNLOAD_ENV` / :data:`NO_DOWNLOAD_ENV`.

    Raises:
        JreError: If no java can be found and none can be downloaded.
    """
    force = os.getenv(FORCE_DOWNLOAD_ENV) == "1"
    no_download = os.getenv(NO_DOWNLOAD_ENV) == "1"

    # An explicit $JAVA override always wins.
    override = os.getenv(JAVA_ENV)
    if override and shutil.which(override):
        return override

    if not force:
        cached = _cached_java()
        if cached:
            return cached
        system = find_system_java()
        if system:
            major = _major_version(system)
            if major is None or major >= MIN_FEATURE:
                return system
            if log:
                log(f"  system java is too old (v{major}); need {MIN_FEATURE}+")

    if no_download:
        raise JreError(
            f"No suitable Java runtime found and {NO_DOWNLOAD_ENV}=1 disables "
            "auto-download. Install a JRE 17+ and set $JAVA_HOME."
        )
    return download_jre(log=log)
