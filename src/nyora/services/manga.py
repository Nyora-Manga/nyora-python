"""Manga browse, search, reader, and metadata operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from nyora.models import (
    GlobalSearchGroup,
    Manga,
    MangaDetails,
    MangaPage,
    MangaPrefs,
    SearchPage,
)
from nyora.pagers import MangaPager
from nyora.services._base import _Service

if TYPE_CHECKING:
    pass


class MangaService(_Service):
    """Browse, search, read, and configure manga via the helper.

    Attached to a client as ``client.manga``.
    """


    def popular(self, source_id: str, page: int = 1) -> SearchPage:
        """Fetch a page of popular manga from a source.

        Args:
            source_id: Identifier of the source to query.
            page: One-based page number.

        Returns:
            A :class:`~nyora.models.SearchPage` of entries.
        """
        return self._browse("/sources/popular", source_id, page=page)

    def latest(self, source_id: str, page: int = 1) -> SearchPage:
        """Fetch a page of the latest updated manga from a source.

        Args:
            source_id: Identifier of the source to query.
            page: One-based page number.

        Returns:
            A :class:`~nyora.models.SearchPage` of entries.
        """
        return self._browse("/sources/latest", source_id, page=page)

    def search(
        self,
        source_id: str,
        query: str,
        page: int = 1,
        *,
        filters: list[dict[str, Any]] | None = None,
    ) -> SearchPage:
        """Search a source for manga matching a query.

        Args:
            source_id: Identifier of the source to query.
            query: Free-text search query.
            page: One-based page number.
            filters: Optional source-specific filter selections.

        Returns:
            A :class:`~nyora.models.SearchPage` of matching entries.
        """
        params: dict[str, Any] = {"id": source_id, "q": query, "page": page}
        if filters:
            params["filters"] = filters
        return SearchPage.from_json(self._client.get("/sources/search", params=params))

    def iter_popular(
        self,
        source_id: str,
        *,
        start_page: int = 1,
        max_pages: int | None = None,
        limit: int | None = None,
    ) -> MangaPager:
        """Auto-paging iterator over popular manga across all pages.

        Args:
            source_id: Identifier of the source to query.
            start_page: First (1-based) page to fetch.
            max_pages: Stop after this many pages (``None`` = until exhausted).
            limit: Stop after yielding this many manga (``None`` = no cap).

        Returns:
            A :class:`~nyora.pagers.MangaPager` — iterate for :class:`~nyora.models.Manga`.
        """
        return MangaPager(
            lambda page: self.popular(source_id, page),
            start_page=start_page,
            max_pages=max_pages,
            limit=limit,
        )

    def iter_latest(
        self,
        source_id: str,
        *,
        start_page: int = 1,
        max_pages: int | None = None,
        limit: int | None = None,
    ) -> MangaPager:
        """Auto-paging iterator over the latest-updated manga across all pages."""
        return MangaPager(
            lambda page: self.latest(source_id, page),
            start_page=start_page,
            max_pages=max_pages,
            limit=limit,
        )

    def iter_search(
        self,
        source_id: str,
        query: str,
        *,
        start_page: int = 1,
        max_pages: int | None = None,
        limit: int | None = None,
        filters: list[dict[str, Any]] | None = None,
    ) -> MangaPager:
        """Auto-paging iterator over search results across all pages."""
        return MangaPager(
            lambda page: self.search(source_id, query, page, filters=filters),
            start_page=start_page,
            max_pages=max_pages,
            limit=limit,
        )

    def global_search(self, query: str, *, limit_per_source: int = 8) -> list[GlobalSearchGroup]:
        """Search every installed source at once.

        Args:
            query: Free-text search query.
            limit_per_source: Maximum entries to return per source.

        Returns:
            One :class:`~nyora.models.GlobalSearchGroup` per source.
        """
        data = cast(dict[str, Any], self._client.get(
            "/search/global",
            params={"q": query, "limitPerSource": limit_per_source},
        ))
        return [GlobalSearchGroup.from_json(item) for item in data.get("groups", [])]

    def details(
        self,
        source_id: str,
        manga_url: str,
        *,
        manga_id: str | None = None,
    ) -> MangaDetails:
        """Fetch full metadata and chapters for one manga.

        Args:
            source_id: Identifier of the owning source.
            manga_url: The manga's URL.
            manga_id: Optional known manga id to disambiguate.

        Returns:
            A :class:`~nyora.models.MangaDetails`.
        """
        params = {"id": source_id, "url": manga_url}
        if manga_id:
            params["mangaId"] = manga_id
        return MangaDetails.from_json(self._client.get("/manga/details", params=params))

    def pages(
        self,
        source_id: str,
        chapter_url: str,
        *,
        branch: str | None = None,
    ) -> list[MangaPage]:
        """Resolve the readable image pages of a chapter.

        Args:
            source_id: Identifier of the owning source.
            chapter_url: The chapter's URL.
            branch: Optional scanlation branch/translation to select.

        Returns:
            An ordered list of :class:`~nyora.models.MangaPage` objects.
        """
        params = {"id": source_id, "url": chapter_url}
        if branch:
            params["branch"] = branch
        data = self._client.get("/manga/pages", params=params)
        entries = data.get("pages", data if isinstance(data, list) else [])
        return [MangaPage.from_json(item) for item in entries]

    def alternatives(self, title: str) -> list[dict[str, Any]]:
        """Find alternative editions/sources for a title.

        Args:
            title: The manga title to look up.

        Returns:
            Raw alternative-entry dicts from the helper.
        """
        data = cast(
            dict[str, Any],
            self._client.get("/manga/alternatives", params={"title": title}),
        )
        return cast(list[dict[str, Any]], data.get("entries", []))

    def suggestions(self) -> list[Manga]:
        """Return personalized manga suggestions.

        Returns:
            Suggested :class:`~nyora.models.Manga` entries.
        """
        data = cast(dict[str, Any], self._client.get("/suggestions"))
        return [Manga.from_json(item) for item in data.get("entries", [])]

    def prefs(self, manga_id: str) -> MangaPrefs:
        """Fetch the stored reader preferences for a manga.

        Args:
            manga_id: Identifier of the manga.

        Returns:
            The manga's :class:`~nyora.models.MangaPrefs`.
        """
        return MangaPrefs.from_json(self._client.get("/manga/prefs", params={"mangaId": manga_id}))

    def save_prefs(
        self,
        manga_id: str,
        *,
        reader_mode: str = "",
        brightness: float = 0.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        hue: float = 0.0,
        palette: str = "",
    ) -> dict[str, Any]:
        """Save reader preferences for a manga.

        Args:
            manga_id: Identifier of the manga.
            reader_mode: Reader layout/mode.
            brightness: Brightness adjustment.
            contrast: Contrast multiplier.
            saturation: Saturation multiplier.
            hue: Hue rotation.
            palette: Named color palette.

        Returns:
            The raw helper response.
        """
        return cast(dict[str, Any], self._client.post(
            "/manga/prefs/save",
            params={
                "mangaId": manga_id,
                "readerMode": reader_mode,
                "brightness": brightness,
                "contrast": contrast,
                "saturation": saturation,
                "hue": hue,
                "palette": palette,
            },
        ))

    def clear_prefs(self, manga_id: str) -> dict[str, Any]:
        """Clear stored reader preferences for a manga.

        Args:
            manga_id: Identifier of the manga.

        Returns:
            The raw helper response.
        """
        return cast(
            dict[str, Any],
            self._client.post("/manga/prefs/clear", params={"mangaId": manga_id}),
        )

    def _browse(self, path: str, source_id: str, *, page: int) -> SearchPage:
        """Issue a paginated browse request and parse the page.

        Args:
            path: The browse endpoint path.
            source_id: Identifier of the source to query.
            page: One-based page number.

        Returns:
            A :class:`~nyora.models.SearchPage`.
        """
        return SearchPage.from_json(self._client.get(path, params={"id": source_id, "page": page}))
