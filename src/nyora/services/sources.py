"""Source catalog operations."""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any, cast

from nyora.models import Source, SourceFilter

if TYPE_CHECKING:
    from nyora.client import Nyora


class SourcesService:
    """Browse, manage, and inspect the helper's content sources.

    Attached to a client as ``client.sources``.
    """

    def __init__(self, client: Nyora) -> None:
        """Bind the service to a helper client.

        Args:
            client: The owning :class:`nyora.client.Nyora` instance.
        """
        self._client = client

    def list(self) -> builtins.list[Source]:
        """List the installed sources.

        Returns:
            The installed :class:`~nyora.models.Source` records.
        """
        data = cast(dict[str, Any], self._client.get("/sources"))
        return [Source.from_json(item) for item in data.get("sources", data.get("entries", []))]

    def catalog(self) -> builtins.list[Source]:
        """List every source available in the catalog (installed or not).

        Returns:
            All catalog :class:`~nyora.models.Source` records.
        """
        data = cast(dict[str, Any], self._client.get("/sources/catalog"))
        return [Source.from_json(item) for item in data.get("entries", [])]

    def refresh(self) -> builtins.list[Source]:
        """Refresh the source catalog from the remote feed.

        Returns:
            The refreshed list of :class:`~nyora.models.Source` records.
        """
        data = cast(dict[str, Any], self._client.post("/sources/refresh"))
        return [Source.from_json(item) for item in data.get("sources", data.get("entries", []))]

    def install(self, source_id: str) -> Source | dict[str, Any]:
        """Install a source by id.

        Args:
            source_id: Identifier of the source to install.

        Returns:
            The installed :class:`~nyora.models.Source`, or the raw response
            dict when no ``source`` field is present.
        """
        data = cast(dict[str, Any], self._client.post("/sources/install", params={"id": source_id}))
        if "source" in data:
            return Source.from_json(data["source"])
        return data

    def uninstall(self, source_id: str) -> dict[str, Any]:
        """Uninstall a source by id.

        Args:
            source_id: Identifier of the source to uninstall.

        Returns:
            The raw helper response.
        """
        return cast(
            dict[str, Any],
            self._client.delete("/sources/uninstall", params={"id": source_id}),
        )

    def pin(self, source_id: str) -> dict[str, Any]:
        """Toggle the pinned state of a source.

        Args:
            source_id: Identifier of the source to pin/unpin.

        Returns:
            The raw helper response.
        """
        return cast(dict[str, Any], self._client.post("/sources/pin", params={"id": source_id}))

    def filters(self, source_id: str) -> builtins.list[SourceFilter]:
        """List the search filters a source advertises.

        Args:
            source_id: Identifier of the source to query.

        Returns:
            The source's :class:`~nyora.models.SourceFilter` definitions.
        """
        data = cast(dict[str, Any], self._client.get("/sources/filters", params={"id": source_id}))
        entries = data.get("filters", data.get("entries", []))
        return [SourceFilter.from_json(item) for item in entries]

    def find(self, query: str) -> Source:
        """Find an installed source by a case-insensitive id or name substring.

        Args:
            query: Substring matched against each source's id and name.

        Returns:
            The first matching :class:`~nyora.models.Source`.

        Raises:
            LookupError: If no installed source matches ``query``.
        """
        needle = query.casefold()
        for source in self.list():
            if needle in source.id.casefold() or needle in source.name.casefold():
                return source
        raise LookupError(f"No installed source matched {query!r}")
