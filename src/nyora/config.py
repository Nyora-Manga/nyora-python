"""Configuration helpers for local Nyora helper discovery.

Defines the environment-variable names the SDK honors and resolves the
platform-specific path of the helper port file. These helpers let
:mod:`nyora.client` and :mod:`nyora.helper` locate a running Nyora helper
without explicit configuration.

Environment variables:
    NYORA_BASE_URL: Explicit helper base URL, overriding port-file discovery.
    NYORA_HELPER_PORT_FILE: Override path for the helper port file.
    NYORA_HELPER_JAR: Path to a helper jar for managed launches.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from platformdirs import user_config_dir

BASE_URL_ENV = "NYORA_BASE_URL"
HELPER_PORT_FILE_ENV = "NYORA_HELPER_PORT_FILE"
HELPER_JAR_ENV = "NYORA_HELPER_JAR"


def default_port_file() -> Path:
    """Return the path of the helper port file for this platform.

    Honors ``NYORA_HELPER_PORT_FILE`` when set; otherwise uses the
    platform-conventional application-data location (macOS Application Support,
    Windows ``%APPDATA%``, or the XDG config dir on Linux).

    Returns:
        The resolved port-file path (which may not yet exist).
    """
    configured = os.getenv(HELPER_PORT_FILE_ENV)
    if configured:
        return Path(configured).expanduser()

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Nyora" / "helper.port"
    if sys.platform.startswith("win"):
        appdata = os.getenv("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Nyora" / "helper.port"
    return Path(user_config_dir("nyora", appauthor=False)) / "helper.port"


def read_base_url_from_port_file(port_file: Path | None = None) -> str | None:
    """Derive a helper base URL from a port file, if present.

    Args:
        port_file: Path to read. Defaults to :func:`default_port_file`.

    Returns:
        ``http://127.0.0.1:<port>`` when the file exists and holds a port, else
        ``None``.
    """
    path = port_file or default_port_file()
    if not path.exists():
        return None
    port = path.read_text(encoding="utf-8").strip()
    if not port:
        return None
    return f"http://127.0.0.1:{port}"
