"""Cloud sync facade for the Nyora TUI.

A thin wrapper over :class:`nyora.sync.NyoraSync` — the schema-aware library and
history logic lives in the SDK; this just exposes it under TUI-friendly names.
"""

from __future__ import annotations

from typing import Any

from nyora.sync import NyoraSync

#: User-Agent for direct image downloads (cover/page CDNs expect a browser UA).
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class TuiSync:
    """Thin, TUI-oriented facade over :class:`nyora.sync.NyoraSync`."""

    def __init__(self) -> None:
        self._sync = NyoraSync()

    # -- account ---------------------------------------------------------------

    @property
    def is_signed_in(self) -> bool:
        return self._sync.is_signed_in

    @property
    def email(self) -> str | None:
        return self._sync.email

    def sign_in(self, email: str, password: str) -> None:
        self._sync.sign_in(email, password)

    def register(self, email: str, password: str) -> None:
        self._sync.register(email, password)

    def sign_out(self) -> None:
        self._sync.sign_out()

    # -- library / history (delegate to the SDK's schema-aware sync) -----------

    def favourite(self, source_id: str, manga: Any) -> None:
        self._sync.favourite(source_id, manga)

    def unfavourite(self, manga_id: str) -> None:
        self._sync.unfavourite(manga_id)

    def library(self) -> list[dict[str, Any]]:
        return self._sync.favourites()

    def record_history(
        self,
        source_id: str,
        manga: Any,
        chapter: Any,
        *,
        page: int = 0,
        total: int = 0,
        percent: float = 0.0,
    ) -> None:
        self._sync.record_history(
            source_id, manga, chapter, page=page, total=total, percent=percent
        )

    def history(self) -> list[dict[str, Any]]:
        return self._sync.history()
