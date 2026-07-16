"""Run the bundled Nyora parser engine locally.

``nyora-extension-server`` launches the JVM parser engine (``nyora-helper.jar``,
the same native kotatsu-parsers backend the Nyora cloud runs) on ``127.0.0.1``,
waits for it to report healthy, and writes a *port file* so the ``nyora`` SDK /
CLI / TUI auto-discovers it with **zero configuration** — point-your-own-server,
no cloud required. Ctrl-C stops it cleanly and removes the port file.

The jar is bundled in the wheel. A Java runtime (17+) is used if present;
otherwise a minimal Temurin JRE is auto-downloaded and cached on first run
(see :mod:`nyora_extension_server.jre`), so **no Java install is required** —
including on Windows.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from importlib import resources
from pathlib import Path

# Environment the bundled jar reads (matches the production systemd unit).
PORT_ENV = "NYORA_HELPER_PORT"
#: Optional SOCKS5 proxy the engine routes source fetches through (e.g. a local
#: Cloudflare WARP exit) — same var the cloud nodes use to beat CF/IP bans.
PROXY_ENV = "NYORA_RESIDENTIAL_PROXY"
JAVA_ENV = "JAVA"  # override the java executable

DEFAULT_PORT = 8788


def bundled_jar() -> Path:
    """Absolute path to the parser engine jar shipped inside this package."""
    return Path(str(resources.files("nyora_extension_server") / "_jar" / "nyora-helper.jar"))


def find_java() -> str | None:
    """Locate a ``java`` executable (``$JAVA`` override, ``$JAVA_HOME``, PATH)."""
    override = os.getenv(JAVA_ENV)
    if override and shutil.which(override):
        return override
    home = os.getenv("JAVA_HOME")
    if home:
        cand = Path(home) / "bin" / ("java.exe" if os.name == "nt" else "java")
        if cand.exists():
            return str(cand)
    return shutil.which("java")


def default_port_file() -> Path:
    """Port-file path the ``nyora`` SDK reads to auto-discover a local engine.

    Mirrors ``nyora.config.default_port_file`` exactly so running this server is
    all it takes for the SDK/CLI/TUI to use it.
    """
    configured = os.getenv("NYORA_HELPER_PORT_FILE")
    if configured:
        return Path(configured).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Nyora" / "helper.port"
    if sys.platform.startswith("win"):
        appdata = os.getenv("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Nyora" / "helper.port"
    xdg = os.getenv("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "nyora" / "helper.port"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _healthy(port: int, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


class EngineError(RuntimeError):
    """Raised when the engine can't be launched (no Java, bad jar, no health)."""


def serve(
    *,
    port: int | None = None,
    jar: str | os.PathLike[str] | None = None,
    java: str | None = None,
    heap: str = "1g",
    proxy: str | None = None,
    write_port_file: bool = True,
    quiet: bool = False,
) -> int:
    """Launch the engine and block until it exits or Ctrl-C.

    Returns the process exit code. Raises :class:`EngineError` on startup failure.
    """
    def log(*a: object) -> None:
        if not quiet:
            print(*a, file=sys.stderr, flush=True)

    if java:
        java_bin = java
    else:
        from nyora_extension_server.jre import JreError, ensure_java

        try:
            java_bin = ensure_java(log=log)
        except JreError as exc:
            raise EngineError(str(exc)) from exc

    jar_path = Path(jar).expanduser() if jar else bundled_jar()
    if not jar_path.exists():
        raise EngineError(f"Parser engine jar not found: {jar_path}")

    chosen = port if port else DEFAULT_PORT
    if port is None and not _port_available(DEFAULT_PORT):
        chosen = _free_port()  # default busy → pick a free one so it just works

    env = dict(os.environ)
    env[PORT_ENV] = str(chosen)
    proxy = proxy or os.getenv(PROXY_ENV)
    if proxy:
        env[PROXY_ENV] = proxy

    cmd = [
        java_bin, f"-Xmx{heap}", "-Xss512k", "-XX:+UseSerialGC",
        "-jar", str(jar_path),
    ]
    log(f"nyora-extension-server → starting engine on 127.0.0.1:{chosen} (java: {java_bin})")
    if proxy:
        log(f"  routing source fetches via proxy {proxy}")

    proc = subprocess.Popen(cmd, env=env)

    # Wait for /health (jar cold-start + parser index warmup can take a bit).
    up = False
    for _ in range(90):
        if proc.poll() is not None:
            raise EngineError(f"Engine exited during startup (code {proc.returncode}).")
        if _healthy(chosen):
            up = True
            break
        time.sleep(1)
    if not up:
        proc.terminate()
        raise EngineError("Engine did not become healthy within 90s.")

    port_file = default_port_file()
    if write_port_file:
        port_file.parent.mkdir(parents=True, exist_ok=True)
        port_file.write_text(str(chosen), encoding="utf-8")
        log(f"  wrote port file {port_file} — the `nyora` SDK/CLI/TUI will now use this server")
    log(f"✓ ready at http://127.0.0.1:{chosen}   (Ctrl-C to stop)")

    stopping = {"v": False}

    def _stop(*_a: object) -> None:
        if stopping["v"]:
            return
        stopping["v"] = True
        log("\nstopping engine…")
        try:
            proc.terminate()
        except Exception:
            pass

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    try:
        proc.wait()
    finally:
        if write_port_file:
            try:
                if port_file.exists() and port_file.read_text().strip() == str(chosen):
                    port_file.unlink()
            except Exception:
                pass
    return proc.returncode or 0
