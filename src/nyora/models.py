"""Typed data models for the Nyora SDK.

Lightweight, slotted dataclasses that mirror the JSON returned by the Nyora
cloud helper REST API. Every model exposes a tolerant ``from_json`` classmethod
that accepts the raw camelCase payloads and coerces field types defensively, so
missing or malformed fields fall back to sensible defaults rather than raising.
These types are returned throughout :class:`nyora.Nyora` and the service
objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeVar

JsonDict = dict[str, Any]
T = TypeVar("T")


def _list(value: Any) -> list[Any]:
    """Return ``value`` if it is a list, else an empty list."""
    return value if isinstance(value, list) else []


def _dict(value: Any) -> JsonDict:
    """Return ``value`` if it is a dict, else an empty dict."""
    return value if isinstance(value, dict) else {}


def _float(value: Any, default: float = 0.0) -> float:
    """Coerce ``value`` to ``float``, returning ``default`` on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    """Coerce ``value`` to ``int``, returning ``default`` on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class MangaPage:
    """A single readable image page of a chapter.

    Attributes:
        url: The image URL.
        headers: Request headers required to fetch the image (e.g. ``Referer``).
    """

    url: str
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Any) -> MangaPage:
        """Build a :class:`MangaPage` from a raw payload.

        Args:
            data: A page object, or a bare string treated as the URL.

        Returns:
            The parsed page.
        """
        if isinstance(data, str):
            return cls(url=data)
        obj = _dict(data)
        headers = {str(k): str(v) for k, v in _dict(obj.get("headers")).items()}
        return cls(url=str(obj.get("url", "")), headers=headers)


@dataclass(slots=True)
class MangaChapter:
    """A chapter belonging to a manga.

    Attributes:
        id: Stable chapter identifier.
        title: Display title.
        number: Chapter number (may be fractional).
        volume: Volume number, or ``0`` if unknown.
        url: Source-relative or absolute chapter URL.
        scanlator: Scanlation group, if known.
        upload_date: Upload timestamp in epoch milliseconds.
        branch: Scanlation branch/translation name, if any.
        pages: Resolved pages, when already loaded.
        index: Position within the chapter list.
    """

    id: str
    title: str
    number: float = 0.0
    volume: int = 0
    url: str = ""
    scanlator: str | None = None
    upload_date: int = 0
    branch: str | None = None
    pages: list[MangaPage] = field(default_factory=list)
    index: int = 0

    @classmethod
    def from_json(cls, data: Any) -> MangaChapter:
        """Build a :class:`MangaChapter` from a raw payload.

        Args:
            data: A chapter object from the parser or helper.

        Returns:
            The parsed chapter.
        """
        obj = _dict(data)
        return cls(
            id=str(obj.get("id", "")),
            title=str(obj.get("title", "")),
            number=_float(obj.get("number")),
            volume=_int(obj.get("volume")),
            url=str(obj.get("url", "")),
            scanlator=obj.get("scanlator"),
            upload_date=_int(obj.get("uploadDate")),
            branch=obj.get("branch"),
            pages=[MangaPage.from_json(item) for item in _list(obj.get("pages"))],
            index=_int(obj.get("index")),
        )


@dataclass(slots=True)
class Manga:
    """A manga entry as returned in listings and details.

    Attributes:
        id: Stable manga identifier.
        title: Primary title.
        alt_titles: Alternative titles.
        url: Source-relative or absolute manga URL.
        public_url: Public web URL for the manga, if distinct.
        rating: Normalized rating, or ``-1.0`` when unknown.
        is_nsfw: Whether the entry is flagged adult/NSFW.
        content_rating: Source-provided content rating, if any.
        cover_url: Cover thumbnail URL.
        large_cover_url: High-resolution cover URL, if available.
        state: Publication state (e.g. ongoing/finished), if known.
        authors: Author names.
        source: Raw source metadata as a dict.
        source_id: Identifier of the owning source.
        description: Synopsis text.
        tags: Genre/tag dicts.
        chapters: Chapters, when already loaded.
        unread: Unread chapter count, for library entries.
        progress: Read progress fraction, for library entries.
    """

    id: str
    title: str
    alt_titles: list[str] = field(default_factory=list)
    url: str = ""
    public_url: str = ""
    rating: float = -1.0
    is_nsfw: bool = False
    content_rating: str | None = None
    cover_url: str = ""
    large_cover_url: str | None = None
    state: str | None = None
    authors: list[str] = field(default_factory=list)
    source: JsonDict = field(default_factory=dict)
    source_id: str = ""
    description: str = ""
    tags: list[JsonDict] = field(default_factory=list)
    chapters: list[MangaChapter] = field(default_factory=list)
    unread: int = 0
    progress: float = 0.0

    @classmethod
    def from_json(cls, data: Any) -> Manga:
        """Build a :class:`Manga` from a raw payload.

        Args:
            data: A manga object from the parser or helper.

        Returns:
            The parsed manga.
        """
        obj = _dict(data)
        return cls(
            id=str(obj.get("id", "")),
            title=str(obj.get("title", "")),
            alt_titles=[str(item) for item in _list(obj.get("altTitles"))],
            url=str(obj.get("url", "")),
            public_url=str(obj.get("publicUrl", "")),
            rating=_float(obj.get("rating"), -1.0),
            is_nsfw=bool(obj.get("isNsfw", False)),
            content_rating=obj.get("contentRating"),
            cover_url=str(obj.get("coverUrl", "")),
            large_cover_url=obj.get("largeCoverUrl"),
            state=obj.get("state"),
            authors=[str(item) for item in _list(obj.get("authors"))],
            source=_dict(obj.get("source")),
            source_id=str(obj.get("sourceId", "")),
            description=str(obj.get("description", "")),
            tags=[_dict(item) for item in _list(obj.get("tags"))],
            chapters=[MangaChapter.from_json(item) for item in _list(obj.get("chapters"))],
            unread=_int(obj.get("unread")),
            progress=_float(obj.get("progress")),
        )


@dataclass(slots=True)
class Source:
    """A content source (site) the SDK can read from.

    Attributes:
        id: Stable source identifier.
        name: Human-readable source name.
        lang: Primary content language/locale code.
        base_url: The source's base site URL.
        engine: Parser engine (e.g. ``"JavaScript"``).
        content_type: Content type (e.g. ``"Manga"``).
        is_installed: Whether the source is installed/available.
        is_pinned: Whether the user pinned the source.
        is_nsfw: Whether the source is flagged adult/NSFW.
        is_obsolete: Whether the source is deprecated.
        icon_url: Source icon URL.
        version: Source/parser version string.
        notes: Free-form notes.
        can_uninstall: Whether the source may be uninstalled.
    """

    id: str
    name: str
    lang: str = ""
    base_url: str = ""
    engine: str = ""
    content_type: str = ""
    is_installed: bool = False
    is_pinned: bool = False
    is_nsfw: bool = False
    is_obsolete: bool = False
    icon_url: str = ""
    version: str = ""
    notes: str = ""
    can_uninstall: bool = True

    @classmethod
    def from_json(cls, data: Any) -> Source:
        """Build a :class:`Source` from a raw payload.

        Accepts both ``name``/``title`` and ``lang``/``locale`` and
        ``baseUrl``/``site`` aliases.

        Args:
            data: A source object from the parser or helper.

        Returns:
            The parsed source.
        """
        obj = _dict(data)
        return cls(
            id=str(obj.get("id", "")),
            name=str(obj.get("name") or obj.get("title") or ""),
            lang=str(obj.get("lang") or obj.get("locale") or ""),
            base_url=str(obj.get("baseUrl") or obj.get("site") or ""),
            engine=str(obj.get("engine", "")),
            content_type=str(obj.get("contentType", "")),
            is_installed=bool(obj.get("isInstalled", False)),
            is_pinned=bool(obj.get("isPinned", False)),
            is_nsfw=bool(obj.get("isNsfw", False)),
            is_obsolete=bool(obj.get("isObsolete", False)),
            icon_url=str(obj.get("iconUrl", "")),
            version=str(obj.get("version", "")),
            notes=str(obj.get("notes", "")),
            can_uninstall=bool(obj.get("canUninstall", True)),
        )


@dataclass(slots=True)
class SourceFilter:
    """A search filter advertised by a source.

    Attributes:
        name: Filter name.
        type_name: Filter widget/type (e.g. select, toggle).
        values: Allowed values for the filter.
    """

    name: str
    type_name: str
    values: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: Any) -> SourceFilter:
        """Build a :class:`SourceFilter` from a raw payload.

        Args:
            data: A filter object from the helper.

        Returns:
            The parsed filter.
        """
        obj = _dict(data)
        return cls(
            name=str(obj.get("name", "")),
            type_name=str(obj.get("typeName", "")),
            values=[str(item) for item in _list(obj.get("values"))],
        )


@dataclass(slots=True)
class SearchPage:
    """One page of manga results from browse or search.

    Attributes:
        entries: The manga on this page.
        has_next_page: Whether a further page is likely available.
    """

    entries: list[Manga]
    has_next_page: bool = False

    @classmethod
    def from_json(cls, data: Any) -> SearchPage:
        """Build a :class:`SearchPage` from a raw payload.

        Args:
            data: A page object with ``entries`` and ``hasNextPage``.

        Returns:
            The parsed page.
        """
        obj = _dict(data)
        return cls(
            entries=[Manga.from_json(item) for item in _list(obj.get("entries"))],
            has_next_page=bool(obj.get("hasNextPage", False)),
        )


@dataclass(slots=True)
class MangaDetails:
    """Full metadata for one manga together with its chapter list.

    Attributes:
        manga: The manga metadata.
        chapters: The manga's chapters.
    """

    manga: Manga
    chapters: list[MangaChapter]

    @classmethod
    def from_json(cls, data: Any) -> MangaDetails:
        """Build a :class:`MangaDetails` from a raw payload.

        Args:
            data: An object with ``manga`` and ``chapters``.

        Returns:
            The parsed details.
        """
        obj = _dict(data)
        return cls(
            manga=Manga.from_json(obj.get("manga")),
            chapters=[MangaChapter.from_json(item) for item in _list(obj.get("chapters"))],
        )


@dataclass(slots=True)
class HistoryEntry:
    """A reading-history record for a manga.

    Attributes:
        manga: The manga that was read.
        chapter_id: The last-read chapter identifier.
        page: The last-read page index.
        percent: Read progress fraction within the chapter.
        updated_at: Last-update timestamp in epoch milliseconds.
    """

    manga: Manga
    chapter_id: str = ""
    page: int = 0
    percent: float = 0.0
    updated_at: int = 0

    @classmethod
    def from_json(cls, data: Any) -> HistoryEntry:
        """Build a :class:`HistoryEntry` from a raw payload.

        Args:
            data: A history object from the helper.

        Returns:
            The parsed entry.
        """
        obj = _dict(data)
        return cls(
            manga=Manga.from_json(obj.get("manga")),
            chapter_id=str(obj.get("chapterId", "")),
            page=_int(obj.get("page")),
            percent=_float(obj.get("percent")),
            updated_at=_int(obj.get("updatedAt")),
        )


@dataclass(slots=True)
class Category:
    """A user-defined library category.

    Attributes:
        id: Category identifier.
        title: Display title.
        manga_count: Number of manga in the category.
    """

    id: int
    title: str
    manga_count: int = 0

    @classmethod
    def from_json(cls, data: Any) -> Category:
        """Build a :class:`Category` from a raw payload.

        Args:
            data: A category object from the helper.

        Returns:
            The parsed category.
        """
        obj = _dict(data)
        return cls(
            id=_int(obj.get("id")),
            title=str(obj.get("title", "")),
            manga_count=_int(obj.get("mangaCount")),
        )


@dataclass(slots=True)
class Download:
    """A chapter download task and its progress.

    Attributes:
        id: Download task identifier.
        source_id: Identifier of the owning source.
        manga_title: Title of the manga being downloaded.
        chapter_title: Title of the chapter being downloaded.
        chapter_url: URL of the chapter being downloaded.
        status: Task status string.
        total_pages: Total number of pages to download.
        completed_pages: Pages downloaded so far.
        failed_pages: Pages that failed to download.
        file_path: Output path once complete, if available.
        error: Error message when the task failed, if any.
    """

    id: str
    source_id: str
    manga_title: str
    chapter_title: str
    chapter_url: str
    status: str
    total_pages: int = 0
    completed_pages: int = 0
    failed_pages: int = 0
    file_path: str | None = None
    error: str | None = None

    @classmethod
    def from_json(cls, data: Any) -> Download:
        """Build a :class:`Download` from a raw payload.

        Args:
            data: A download object from the helper.

        Returns:
            The parsed download.
        """
        obj = _dict(data)
        return cls(
            id=str(obj.get("id", "")),
            source_id=str(obj.get("sourceId", "")),
            manga_title=str(obj.get("mangaTitle", "")),
            chapter_title=str(obj.get("chapterTitle", "")),
            chapter_url=str(obj.get("chapterUrl", "")),
            status=str(obj.get("status", "")),
            total_pages=_int(obj.get("totalPages")),
            completed_pages=_int(obj.get("completedPages")),
            failed_pages=_int(obj.get("failedPages")),
            file_path=obj.get("filePath"),
            error=obj.get("error"),
        )


@dataclass(slots=True)
class DownloadSettings:
    """Download subsystem settings.

    Attributes:
        max_concurrent_downloads: Maximum simultaneous downloads.
        format: Output format (e.g. ``"AUTO"``).
    """

    max_concurrent_downloads: int = 3
    format: str = "AUTO"

    @classmethod
    def from_json(cls, data: Any) -> DownloadSettings:
        """Build :class:`DownloadSettings` from a raw payload.

        Accepts either a bare settings object or one nested under ``settings``.

        Args:
            data: A settings object from the helper.

        Returns:
            The parsed settings.
        """
        obj = _dict(data)
        settings = _dict(obj.get("settings", obj))
        return cls(
            max_concurrent_downloads=_int(settings.get("maxConcurrentDownloads"), 3),
            format=str(settings.get("format", "AUTO")),
        )


@dataclass(slots=True)
class MangaPrefs:
    """Per-manga reader preferences.

    Attributes:
        manga_id: Identifier of the manga these preferences apply to.
        reader_mode: Reader layout/mode.
        brightness: Brightness adjustment.
        contrast: Contrast multiplier.
        saturation: Saturation multiplier.
        hue: Hue rotation.
        palette: Named color palette.
        present: Whether stored preferences exist for this manga.
    """

    manga_id: str
    reader_mode: str = ""
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    hue: float = 0.0
    palette: str = ""
    present: bool = False

    @classmethod
    def from_json(cls, data: Any) -> MangaPrefs:
        """Build :class:`MangaPrefs` from a raw payload.

        Args:
            data: A preferences object from the helper.

        Returns:
            The parsed preferences.
        """
        obj = _dict(data)
        return cls(
            manga_id=str(obj.get("mangaId", "")),
            reader_mode=str(obj.get("readerMode", "")),
            brightness=_float(obj.get("brightness")),
            contrast=_float(obj.get("contrast"), 1.0),
            saturation=_float(obj.get("saturation"), 1.0),
            hue=_float(obj.get("hue")),
            palette=str(obj.get("palette", "")),
            present=bool(obj.get("present", False)),
        )


@dataclass(slots=True)
class GlobalSearchGroup:
    """Results from one source within a cross-source global search.

    Attributes:
        source_id: Identifier of the source that produced these results.
        source_name: Display name of the source.
        entries: Matching manga from this source.
        error: Error message if this source's search failed, else ``None``.
    """

    source_id: str
    source_name: str
    entries: list[Manga]
    error: str | None = None

    @classmethod
    def from_json(cls, data: Any) -> GlobalSearchGroup:
        """Build a :class:`GlobalSearchGroup` from a raw payload.

        Args:
            data: A group object from the helper.

        Returns:
            The parsed group.
        """
        obj = _dict(data)
        return cls(
            source_id=str(obj.get("sourceId", "")),
            source_name=str(obj.get("sourceName", "")),
            entries=[Manga.from_json(item) for item in _list(obj.get("entries"))],
            error=obj.get("error"),
        )


@dataclass(slots=True)
class Stats:
    """Aggregate reading statistics.

    Attributes:
        total_chapters: Total chapters read.
        distinct_manga: Number of distinct manga read.
        favourites_count: Number of favourited manga.
        longest_streak_days: Longest consecutive reading streak in days.
        top_sources: Per-source usage breakdown dicts.
    """

    total_chapters: int = 0
    distinct_manga: int = 0
    favourites_count: int = 0
    longest_streak_days: int = 0
    top_sources: list[JsonDict] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: Any) -> Stats:
        """Build :class:`Stats` from a raw payload.

        Args:
            data: A stats object from the helper.

        Returns:
            The parsed statistics.
        """
        obj = _dict(data)
        return cls(
            total_chapters=_int(obj.get("totalChapters")),
            distinct_manga=_int(obj.get("distinctManga")),
            favourites_count=_int(obj.get("favouritesCount")),
            longest_streak_days=_int(obj.get("longestStreakDays")),
            top_sources=[_dict(item) for item in _list(obj.get("topSources"))],
        )


@dataclass(slots=True)
class BackupImportResult:
    """Outcome of importing a backup archive.

    Attributes:
        ok: Whether the import succeeded.
        imported_favourites: Number of favourites imported.
        imported_history: Number of history records imported.
    """

    ok: bool
    imported_favourites: int = 0
    imported_history: int = 0

    @classmethod
    def from_json(cls, data: Any) -> BackupImportResult:
        """Build a :class:`BackupImportResult` from a raw payload.

        Args:
            data: A result object from the helper.

        Returns:
            The parsed result.
        """
        obj = _dict(data)
        return cls(
            ok=bool(obj.get("ok", False)),
            imported_favourites=_int(obj.get("importedFavourites")),
            imported_history=_int(obj.get("importedHistory")),
        )
