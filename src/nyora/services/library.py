"""Library, history, favourites, bookmarks, and categories."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nyora.models import Category, HistoryEntry, Manga

if TYPE_CHECKING:
    from nyora.client import Nyora


class LibraryService:
    """Manage reading history, favourites, bookmarks, and categories.

    Attached to a client as ``client.library``.
    """

    def __init__(self, client: Nyora) -> None:
        """Bind the service to a helper client.

        Args:
            client: The owning :class:`nyora.client.Nyora` instance.
        """
        self._client = client

    def history(self, limit: int = 100) -> list[HistoryEntry]:
        """Return recent reading history.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            The most recent :class:`~nyora.models.HistoryEntry` records.
        """
        data = self._client.get("/library/history", params={"limit": limit})
        return [HistoryEntry.from_json(item) for item in data.get("entries", [])]

    def record_history(
        self,
        *,
        manga_id: str,
        chapter_id: str,
        page: int,
        percent: float,
    ) -> dict[str, Any]:
        """Record reading progress for a chapter.

        Args:
            manga_id: Identifier of the manga.
            chapter_id: Identifier of the chapter read.
            page: Last-read page index.
            percent: Read progress fraction within the chapter.

        Returns:
            The raw helper response.
        """
        return self._client.post(
            "/library/history/record",
            params={
                "mangaId": manga_id,
                "chapterId": chapter_id,
                "page": page,
                "percent": percent,
            },
        )

    def remove_history(self, manga_id: str, chapter_id: str | None = None) -> dict[str, Any]:
        """Remove history for a manga, optionally narrowed to one chapter.

        Args:
            manga_id: Identifier of the manga.
            chapter_id: Optional chapter to remove; omit to remove all history
                for the manga.

        Returns:
            The raw helper response.
        """
        params = {"mangaId": manga_id}
        if chapter_id:
            params["chapterId"] = chapter_id
        return self._client.post("/library/history/remove", params=params)

    def clear_history(self) -> dict[str, Any]:
        """Clear all reading history.

        Returns:
            The raw helper response.
        """
        return self._client.post("/library/history/clear")

    def favourites(self, category_id: int | None = None) -> list[Manga]:
        """List favourited manga, optionally filtered by category.

        Args:
            category_id: Optional category to filter by.

        Returns:
            The favourited :class:`~nyora.models.Manga` entries.
        """
        params = {"categoryId": category_id} if category_id is not None else None
        data = self._client.get("/library/favourites", params=params)
        return [Manga.from_json(item) for item in data.get("entries", [])]

    def toggle_favourite(self, manga_id: str) -> dict[str, Any]:
        """Toggle a manga's favourite state.

        Args:
            manga_id: Identifier of the manga.

        Returns:
            The raw helper response.
        """
        return self._client.post("/library/favourites/toggle", params={"mangaId": manga_id})

    def is_favourite(self, manga_id: str) -> bool:
        """Check whether a manga is favourited.

        Args:
            manga_id: Identifier of the manga.

        Returns:
            ``True`` if the manga is favourited.
        """
        data = self._client.get("/library/favourites/check", params={"mangaId": manga_id})
        return bool(data.get("isFavourite", data.get("present", False)))

    def bookmarks(self, manga_id: str | None = None) -> list[dict[str, Any]]:
        """List bookmarks, optionally scoped to one manga.

        Args:
            manga_id: Optional manga to scope to.

        Returns:
            Raw bookmark dicts.
        """
        params = {"mangaId": manga_id} if manga_id else None
        data = self._client.get("/library/bookmarks", params=params)
        return data.get("entries", [])

    def add_bookmark(
        self,
        *,
        manga_id: str,
        chapter_id: str,
        page: int,
        title: str = "",
    ) -> dict[str, Any]:
        """Add a bookmark at a specific page.

        Args:
            manga_id: Identifier of the manga.
            chapter_id: Identifier of the chapter.
            page: Page index to bookmark.
            title: Optional bookmark label.

        Returns:
            The raw helper response.
        """
        return self._client.post(
            "/library/bookmarks/add",
            params={
                "mangaId": manga_id,
                "chapterId": chapter_id,
                "page": page,
                "title": title,
            },
        )

    def remove_bookmark(self, *, manga_id: str, chapter_id: str, page: int) -> dict[str, Any]:
        """Remove a bookmark at a specific page.

        Args:
            manga_id: Identifier of the manga.
            chapter_id: Identifier of the chapter.
            page: Page index of the bookmark to remove.

        Returns:
            The raw helper response.
        """
        return self._client.post(
            "/library/bookmarks/remove",
            params={"mangaId": manga_id, "chapterId": chapter_id, "page": page},
        )

    def categories(self) -> list[Category]:
        """List the user's library categories.

        Returns:
            The :class:`~nyora.models.Category` records.
        """
        data = self._client.get("/library/categories")
        return [Category.from_json(item) for item in data.get("categories", [])]

    def create_category(self, title: str) -> Category | dict[str, Any]:
        """Create a new library category.

        Args:
            title: Title for the new category.

        Returns:
            The created :class:`~nyora.models.Category`, or the raw response.
        """
        data = self._client.post("/library/categories/create", params={"title": title})
        return Category.from_json(data["category"]) if "category" in data else data

    def rename_category(self, category_id: int, title: str) -> dict[str, Any]:
        """Rename a category.

        Args:
            category_id: Identifier of the category.
            title: New title.

        Returns:
            The raw helper response.
        """
        return self._client.post(
            "/library/categories/rename",
            params={"id": category_id, "title": title},
        )

    def delete_category(self, category_id: int) -> dict[str, Any]:
        """Delete a category.

        Args:
            category_id: Identifier of the category to delete.

        Returns:
            The raw helper response.
        """
        return self._client.post("/library/categories/delete", params={"id": category_id})

    def add_to_category(self, manga_id: str, category_id: int) -> dict[str, Any]:
        """Add a manga to a category.

        Args:
            manga_id: Identifier of the manga.
            category_id: Identifier of the category.

        Returns:
            The raw helper response.
        """
        return self._client.post(
            "/library/categories/add",
            params={"mangaId": manga_id, "categoryId": category_id},
        )

    def remove_from_category(self, manga_id: str, category_id: int) -> dict[str, Any]:
        """Remove a manga from a category.

        Args:
            manga_id: Identifier of the manga.
            category_id: Identifier of the category.

        Returns:
            The raw helper response.
        """
        return self._client.post(
            "/library/categories/remove",
            params={"mangaId": manga_id, "categoryId": category_id},
        )

    def updates(self) -> list[dict[str, Any]]:
        """List pending library update entries.

        Returns:
            Raw update-entry dicts.
        """
        return self._client.get("/library/updates").get("entries", [])

    def refresh_updates(self) -> dict[str, Any]:
        """Trigger a refresh of library updates.

        Returns:
            The raw helper response.
        """
        return self._client.post("/library/updates/refresh")

    def mark_update_seen(self, update_id: str) -> dict[str, Any]:
        """Mark a library update as seen.

        Args:
            update_id: Identifier of the update entry.

        Returns:
            The raw helper response.
        """
        return self._client.post("/library/updates/seen", params={"id": update_id})
