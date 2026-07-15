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

import json
import os
import sys
from pathlib import Path

from platformdirs import user_config_dir

BASE_URL_ENV = "NYORA_BASE_URL"
HELPER_PORT_FILE_ENV = "NYORA_HELPER_PORT_FILE"
HELPER_JAR_ENV = "NYORA_HELPER_JAR"
CONFIG_FILE_ENV = "NYORA_CONFIG_FILE"


def config_file() -> Path:
    """Path of the persisted SDK config (``NYORA_CONFIG_FILE`` override, else the
    platform user-config dir). Stores the preferred server URL and blocklist cache
    location so ``nyora`` uses *your* server, not the cloud, across runs."""
    configured = os.getenv(CONFIG_FILE_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path(user_config_dir("nyora", appauthor=False)) / "config.json"


def read_config() -> dict:
    """Return the persisted config dict (``{}`` if absent/corrupt)."""
    path = config_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_config(data: dict) -> None:
    """Persist the config dict to :func:`config_file`."""
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_base_url_from_config() -> str | None:
    """Return the user's persisted preferred server URL, or ``None``."""
    url = read_config().get("base_url")
    return url.rstrip("/") if isinstance(url, str) and url.strip() else None


def set_config_base_url(url: str | None) -> None:
    """Persist (or clear, when ``url`` is falsy) the preferred server URL."""
    data = read_config()
    if url:
        data["base_url"] = url.rstrip("/")
    else:
        data.pop("base_url", None)
    write_config(data)


def read_theme_from_config() -> str | None:
    """Return the user's persisted TUI colour-scheme id, or ``None``."""
    theme = read_config().get("theme")
    return theme if isinstance(theme, str) and theme.strip() else None


def set_config_theme(theme_id: str | None) -> None:
    """Persist (or clear, when ``theme_id`` is falsy) the TUI colour scheme."""
    data = read_config()
    if theme_id:
        data["theme"] = theme_id
    else:
        data.pop("theme", None)
    write_config(data)


def read_ui_lang() -> str | None:
    """Return the user's persisted TUI interface language code, or ``None``."""
    lang = read_config().get("ui_lang")
    return lang if isinstance(lang, str) and lang.strip() else None


def set_ui_lang(code: str | None) -> None:
    """Persist (or clear, when ``code`` is falsy) the TUI interface language."""
    data = read_config()
    if code:
        data["ui_lang"] = code
    else:
        data.pop("ui_lang", None)
    write_config(data)


def read_onboarded() -> bool:
    """Return whether the user has passed the welcome screen at least once."""
    return bool(read_config().get("onboarded"))


def set_onboarded(value: bool = True) -> None:
    """Mark (or clear) the one-time welcome screen as seen."""
    data = read_config()
    if value:
        data["onboarded"] = True
    else:
        data.pop("onboarded", None)
    write_config(data)


def read_show_nsfw() -> bool:
    """Return whether adult (18+) sources should be shown."""
    return bool(read_config().get("show_nsfw"))


def set_show_nsfw(value: bool) -> None:
    """Persist the 18+ content preference."""
    data = read_config()
    data["show_nsfw"] = bool(value)
    write_config(data)


def read_languages() -> list[str]:
    """Return the user's chosen language filter (empty = all languages)."""
    langs = read_config().get("languages")
    return [str(x) for x in langs] if isinstance(langs, list) else []


def set_languages(langs: list[str]) -> None:
    """Persist the language filter (a list of locale codes; empty = all)."""
    data = read_config()
    data["languages"] = [str(x) for x in langs]
    write_config(data)


def read_reader_prefs() -> dict:
    """Return persisted reader preferences (``mode``, ``fit``), or ``{}``."""
    prefs = read_config().get("reader")
    return prefs if isinstance(prefs, dict) else {}


def set_reader_pref(key: str, value: str) -> None:
    """Persist a single reader preference (e.g. ``mode`` or ``fit``)."""
    data = read_config()
    prefs = data.get("reader")
    if not isinstance(prefs, dict):
        prefs = {}
    prefs[key] = value
    data["reader"] = prefs
    write_config(data)


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
