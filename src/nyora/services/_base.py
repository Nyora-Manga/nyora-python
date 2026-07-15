"""Shared base for client-bound service objects."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nyora.client import Nyora


class _Service:
    """Binds a service to its owning :class:`~nyora.client.Nyora` client."""

    def __init__(self, client: Nyora) -> None:
        self._client = client
