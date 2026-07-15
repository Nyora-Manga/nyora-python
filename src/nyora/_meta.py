"""SDK version and User-Agent metadata."""

from __future__ import annotations

import platform
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

import httpx

try:
    __version__ = _pkg_version("nyora")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0"

#: Identifies the SDK (and its stack) on every request, like Google client libs.
USER_AGENT = (
    f"nyora-python/{__version__} httpx/{httpx.__version__} "
    f"python/{platform.python_version()}"
)
