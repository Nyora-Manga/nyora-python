"""Nyora extension server — run the Nyora parser engine locally via pipx.

    pipx install nyora-extension-server
    nyora-extension-server          # engine on 127.0.0.1:8788, port-file written

The `nyora` SDK/CLI/TUI then auto-discovers and uses it — no cloud required.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .jre import JreError, download_jre, ensure_java
from .server import EngineError, bundled_jar, default_port_file, find_java, serve

__all__ = [
    "__version__",
    "serve",
    "bundled_jar",
    "default_port_file",
    "find_java",
    "ensure_java",
    "download_jre",
    "JreError",
    "EngineError",
]
