"""Nyora cloud sync — account + library sync against the self-hosted sync server.

:class:`NyoraSync` talks to the Nyora sync server (``https://stream.hasanraza.tech``)
using an OAuth2 password flow + JWT, then a generic last-write-wins upsert/select
over the per-user tables (``nyora_manga``, ``nyora_favourite``, tracking, …). It
mirrors the iOS ``NyoraSyncClient`` and replaces the old Supabase-based sync.

Tokens are held in memory and, when a ``token_path`` is given, persisted to disk
so a process can stay signed in across runs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

DEFAULT_SYNC_URL = "https://stream.hasanraza.tech"


def _default_token_path() -> Path:
    base = os.getenv("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "nyora" / "sync.json"


class NyoraSync:
    """Account and library sync against the Nyora sync server.

    Example:
        >>> sync = NyoraSync()
        >>> sync.sign_in("me@example.com", "hunter2")
        >>> sync.upsert("nyora_manga", [{"key": "...", "source": "...", "title": "..."}])
        >>> rows = sync.select("nyora_manga")
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 30.0,
        token_path: str | os.PathLike[str] | None = None,
    ) -> None:
        """Create a sync client.

        Args:
            base_url: Sync server base URL. Defaults to ``https://stream.hasanraza.tech``
                (or the ``NYORA_SYNC_URL`` env var).
            timeout: Per-request HTTP timeout in seconds.
            token_path: Where to persist tokens. ``None`` uses the default user
                config path; pass ``False``-y string to disable persistence.
        """
        self.base_url = (base_url or os.getenv("NYORA_SYNC_URL") or DEFAULT_SYNC_URL).rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)
        self._token_path: Path | None = (
            Path(token_path) if token_path is not None else _default_token_path()
        )
        self.email: str | None = None
        self._access: str | None = None
        self._refresh: str | None = None
        self._load_tokens()

    # -- state -----------------------------------------------------------------

    @property
    def is_signed_in(self) -> bool:
        """Whether an access token is currently held."""
        return self._access is not None

    def _load_tokens(self) -> None:
        if not self._token_path or not self._token_path.exists():
            return
        try:
            data = json.loads(self._token_path.read_text())
            self._access = data.get("access_token")
            self._refresh = data.get("refresh_token")
            self.email = data.get("email")
        except (OSError, ValueError):
            pass

    def _save_tokens(self) -> None:
        if not self._token_path:
            return
        try:
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            self._token_path.write_text(
                json.dumps(
                    {"access_token": self._access, "refresh_token": self._refresh, "email": self.email}
                )
            )
        except OSError:
            pass

    def _store(self, tokens: dict[str, Any]) -> None:
        self._access = tokens.get("access_token")
        self._refresh = tokens.get("refresh_token")
        self._save_tokens()

    # -- auth ------------------------------------------------------------------

    def register(self, email: str, password: str) -> None:
        """Register a new account (server may have registration disabled)."""
        res = self._http.post("/auth/register", json={"email": email, "password": password})
        res.raise_for_status()
        self.email = email.lower().strip()
        self._store(res.json())

    def sign_in(self, email: str, password: str) -> None:
        """Sign in with the OAuth2 password grant and store the tokens."""
        tokens = self._token_form(
            {"grant_type": "password", "username": email, "password": password}
        )
        self.email = email.lower().strip()
        self._store(tokens)

    def sign_out(self) -> None:
        """Forget the stored tokens."""
        self._access = self._refresh = self.email = None
        if self._token_path and self._token_path.exists():
            try:
                self._token_path.unlink()
            except OSError:
                pass

    def _refresh_tokens(self) -> None:
        if not self._refresh:
            raise NotSignedInError()
        tokens = self._token_form(
            {"grant_type": "refresh_token", "refresh_token": self._refresh}
        )
        self._store(tokens)

    def _token_form(self, fields: dict[str, str]) -> dict[str, Any]:
        res = self._http.post("/auth/token", data=fields)
        res.raise_for_status()
        return res.json()

    # -- sync transport --------------------------------------------------------

    def _sync(self, payload: dict[str, Any], *, retry: bool = True) -> dict[str, Any]:
        if not self._access:
            raise NotSignedInError()
        res = self._http.post(
            "/functions/v1/nyora-sync",
            json=payload,
            headers={"Authorization": f"Bearer {self._access}"},
        )
        if res.status_code == 401 and retry and self._refresh:
            self._refresh_tokens()
            return self._sync(payload, retry=False)
        res.raise_for_status()
        return res.json()

    def upsert(self, table: str, rows: list[dict[str, Any]]) -> int:
        """Last-write-wins upsert of ``rows`` into ``table``. Returns rows written."""
        if not rows:
            return 0
        return int(self._sync({"action": "upsert", "table": table, "rows": rows}).get("count", 0))

    def select(self, table: str, since: str | None = None) -> list[dict[str, Any]]:
        """Fetch rows from ``table``, optionally only those changed after ``since``."""
        payload: dict[str, Any] = {"action": "select", "table": table}
        if since is not None:
            payload["since"] = since
        return list(self._sync(payload).get("data", []))

    def delete_extension_repo(self, type: str, base_url: str) -> None:
        """Hard-delete one extension-repo row for the signed-in user."""
        self._sync({"action": "deleteExtensionRepo", "type": type, "base_url": base_url})

    # -- lifecycle -------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> NyoraSync:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class NotSignedInError(RuntimeError):
    """Raised when a sync operation is attempted without signing in."""

    def __init__(self) -> None:
        super().__init__("not signed in; call sign_in() first")
