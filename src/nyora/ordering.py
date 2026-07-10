"""Order-independent chapter navigation.

Source chapter arrays are **not** in a consistent order: some sources list
chapters oldest-first (ascending, e.g. MangaDex ``0 -> N``) while many
scanlation sites list them newest-first (descending, ``N -> 0``). A fixed
``index + 1`` "next chapter" therefore moves the *wrong* way on half of all
sources.

These helpers detect the reading direction from the chapter numbers so that
"next" is always the later (higher-numbered) chapter, regardless of how the
source ordered the array. This mirrors the fix already shipped in the Nyora
web and Android readers.
"""

from __future__ import annotations

from math import isfinite
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nyora.models import MangaChapter


def chapter_reading_delta(chapters: list[MangaChapter]) -> int:
    """Return the index step that moves to the *next* (later) chapter.

    Compares the first and last chapter numbers: ``+1`` when the array is
    ascending (oldest-first), ``-1`` when descending (newest-first). Falls
    back to ``+1`` (assume oldest-first) when the direction is ambiguous.
    """
    if len(chapters) < 2:
        return 1
    first = chapters[0].number
    last = chapters[-1].number
    if isfinite(first) and isfinite(last) and first != last:
        return 1 if first < last else -1
    return 1


def reading_order(chapters: list[MangaChapter]) -> list[MangaChapter]:
    """Return the chapters in canonical reading order (earliest first)."""
    return list(chapters) if chapter_reading_delta(chapters) == 1 else list(reversed(chapters))


def _index_of(chapters: list[MangaChapter], current: MangaChapter) -> int:
    """Locate ``current`` within ``chapters`` by identity, then id, then url."""
    for i, c in enumerate(chapters):
        if c is current:
            return i
    for i, c in enumerate(chapters):
        if (current.id and c.id == current.id) or (current.url and c.url == current.url):
            return i
    return -1


def adjacent_chapter(
    chapters: list[MangaChapter], current: MangaChapter, reading: int
) -> MangaChapter | None:
    """Return the chapter ``reading`` steps from ``current`` in reading order.

    Args:
        chapters: The manga's chapter list, in whatever order the source gave.
        current: The chapter currently being read.
        reading: ``+1`` for the next (later) chapter, ``-1`` for the previous.

    Returns:
        The neighbouring chapter, or ``None`` at either end / if not found.
    """
    i = _index_of(chapters, current)
    if i < 0:
        return None
    target = i + reading * chapter_reading_delta(chapters)
    return chapters[target] if 0 <= target < len(chapters) else None


def next_chapter(chapters: list[MangaChapter], current: MangaChapter) -> MangaChapter | None:
    """Return the next (later) chapter after ``current``, or ``None``."""
    return adjacent_chapter(chapters, current, 1)


def previous_chapter(chapters: list[MangaChapter], current: MangaChapter) -> MangaChapter | None:
    """Return the previous (earlier) chapter before ``current``, or ``None``."""
    return adjacent_chapter(chapters, current, -1)
