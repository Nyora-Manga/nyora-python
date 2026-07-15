"""Auto-paging iterators over paginated Nyora results.

Browse and search endpoints return one :class:`~nyora.models.SearchPage` at a
time. A pager turns that into a lazy iterator that walks every page for you —
iterate a pager to get individual :class:`~nyora.models.Manga`, or use
:meth:`MangaPager.pages` to iterate a page at a time (the Google-client-library
pattern).

Example:
    >>> from nyora import Nyora
    >>> with Nyora() as client:
    ...     for manga in client.manga.iter_popular("mangadex", limit=50):
    ...         print(manga.title)
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nyora.models import Manga, SearchPage


class MangaPager:
    """A lazy, auto-paging iterator over :class:`~nyora.models.Manga`.

    Iterating the pager yields individual manga across all pages. Use
    :meth:`pages` to iterate whole :class:`~nyora.models.SearchPage` objects.
    """

    def __init__(
        self,
        fetch: Callable[[int], SearchPage],
        *,
        start_page: int = 1,
        max_pages: int | None = None,
        limit: int | None = None,
    ) -> None:
        """Build a pager.

        Args:
            fetch: Callable mapping a 1-based page number to a ``SearchPage``.
            start_page: The first page to fetch.
            max_pages: Stop after this many pages (``None`` = until exhausted).
            limit: Stop after yielding this many manga (``None`` = no cap).
        """
        self._fetch = fetch
        self._start_page = start_page
        self._max_pages = max_pages
        self._limit = limit

    def pages(self) -> Iterator[SearchPage]:
        """Iterate whole :class:`~nyora.models.SearchPage` objects, lazily."""
        page = self._start_page
        fetched = 0
        while True:
            search_page = self._fetch(page)
            yield search_page
            fetched += 1
            if not search_page.has_next_page:
                return
            if self._max_pages is not None and fetched >= self._max_pages:
                return
            page += 1

    def __iter__(self) -> Iterator[Manga]:
        yielded = 0
        for search_page in self.pages():
            for manga in search_page.entries:
                yield manga
                yielded += 1
                if self._limit is not None and yielded >= self._limit:
                    return


class AsyncMangaPager:
    """The async counterpart of :class:`MangaPager` (``async for`` support)."""

    def __init__(
        self,
        fetch: Callable[[int], Awaitable[SearchPage]],
        *,
        start_page: int = 1,
        max_pages: int | None = None,
        limit: int | None = None,
    ) -> None:
        self._fetch = fetch
        self._start_page = start_page
        self._max_pages = max_pages
        self._limit = limit

    async def pages(self) -> AsyncIterator[SearchPage]:
        """Iterate whole :class:`~nyora.models.SearchPage` objects, lazily."""
        page = self._start_page
        fetched = 0
        while True:
            search_page = await self._fetch(page)
            yield search_page
            fetched += 1
            if not search_page.has_next_page:
                return
            if self._max_pages is not None and fetched >= self._max_pages:
                return
            page += 1

    async def __aiter__(self) -> AsyncIterator[Manga]:
        yielded = 0
        async for search_page in self.pages():
            for manga in search_page.entries:
                yield manga
                yielded += 1
                if self._limit is not None and yielded >= self._limit:
                    return
