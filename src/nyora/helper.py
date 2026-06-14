"""Managed Nyora helper process support.

Provides :class:`HelperProcess`, which launches a JVM Nyora helper jar, waits
for it to write its port file and report healthy, and stops it cleanly on exit.
Used by :meth:`nyora.client.Nyora.managed` to own a helper for the lifetime of
a client.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx

from nyora.config import HELPER_JAR_ENV, default_port_file, read_base_url_from_port_file
from nyora.errors import HelperLaunchError, HelperNotFoundError


class HelperProcess:
    """Owns a JVM helper process started by Python.

    Launches the helper jar with a port-file flag, polls for the port file and a
    healthy ``/health`` response, and exposes the resolved base URL. Use as a
    context manager to ensure the process is stopped.

    Attributes:
        jar_path: Resolved path to the helper jar.
        java: The ``java`` executable used to launch it.
        port_file: Path the helper writes its port to.
        base_url: The resolved base URL once started.
    """

    def __init__(
        self,
        jar_path: str | os.PathLike[str] | None = None,
        *,
        java: str = "java",
        port_file: str | os.PathLike[str] | None = None,
        timeout: float = 20.0,
    ) -> None:
        """Configure the managed helper.

        Args:
            jar_path: Path to the helper jar. When ``None`` it is read from the
                ``NYORA_HELPER_JAR`` environment variable.
            java: The ``java`` executable to invoke.
            port_file: Override path for the helper port file. Defaults to
                :func:`nyora.config.default_port_file`.
            timeout: Seconds to wait for the helper to become healthy.

        Raises:
            HelperNotFoundError: If no jar path is provided or discoverable.
        """
        configured = jar_path or os.getenv(HELPER_JAR_ENV)
        if not configured:
            raise HelperNotFoundError(
                "Missing helper jar. Pass jar_path=... or set NYORA_HELPER_JAR."
            )
        self.jar_path = Path(configured).expanduser().resolve()
        self.java = java
        self.port_file = Path(port_file).expanduser() if port_file else default_port_file()
        self.timeout = timeout
        self.process: subprocess.Popen[str] | None = None
        self.base_url = ""

    def start(self) -> str:
        """Launch the helper and wait until it is healthy.

        Returns:
            The helper's base URL.

        Raises:
            HelperNotFoundError: If the jar file does not exist.
            HelperLaunchError: If the helper exits early or does not become
                healthy within the timeout.
        """
        if not self.jar_path.exists():
            raise HelperNotFoundError(f"Helper jar not found: {self.jar_path}")
        self.port_file.parent.mkdir(parents=True, exist_ok=True)
        self.port_file.unlink(missing_ok=True)

        cmd = [
            self.java,
            f"-Dnyora.helper.port-file={self.port_file}",
            "-jar",
            str(self.jar_path),
        ]
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + self.timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                stderr = self.process.stderr.read() if self.process.stderr else ""
                raise HelperLaunchError(f"Nyora helper exited early: {stderr.strip()}")
            base_url = read_base_url_from_port_file(self.port_file)
            if base_url:
                try:
                    response = httpx.get(f"{base_url}/health", timeout=1.5)
                    if response.status_code == 200:
                        self.base_url = base_url
                        return base_url
                except httpx.HTTPError as exc:
                    last_error = exc
            time.sleep(0.2)

        self.stop()
        message = f"Timed out waiting for Nyora helper at {self.port_file}"
        if last_error:
            message = f"{message}: {last_error}"
        raise HelperLaunchError(message)

    def stop(self) -> None:
        """Terminate the helper process if running.

        Sends ``SIGTERM`` and escalates to ``SIGKILL`` if it does not exit
        promptly. Safe to call when no process is running.
        """
        process = self.process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        self.process = None

    def __enter__(self) -> HelperProcess:
        """Start the helper and return this process wrapper."""
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        """Stop the helper on context exit."""
        self.stop()
