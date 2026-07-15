"""Tests for the auto-paging iterators."""

from __future__ import annotations

import asyncio

from nyora import AsyncMangaPager, MangaPager
from nyora.models import Manga, SearchPage


def _page(ids, has_next):
    entries = [Manga(id=str(i), title=f"m{i}") for i in ids]
    return SearchPage(entries=entries, has_next_page=has_next)


def _fetch(page):
    # 3 pages: [1,2], [3,4], [5] (last)
    return {1: _page([1, 2], True), 2: _page([3, 4], True), 3: _page([5], False)}[page]


def test_pager_walks_all_pages():
    titles = [m.title for m in MangaPager(_fetch)]
    assert titles == ["m1", "m2", "m3", "m4", "m5"]


def test_pager_respects_limit():
    got = list(MangaPager(_fetch, limit=3))
    assert [m.id for m in got] == ["1", "2", "3"]


def test_pager_respects_max_pages():
    got = list(MangaPager(_fetch, max_pages=2))
    assert [m.id for m in got] == ["1", "2", "3", "4"]


def test_pager_pages_iterator():
    pages = list(MangaPager(_fetch).pages())
    assert len(pages) == 3
    assert pages[-1].has_next_page is False


def test_async_pager():
    async def afetch(page):
        return _fetch(page)

    async def run():
        out = []
        async for m in AsyncMangaPager(afetch, limit=4):
            out.append(m.id)
        return out

    assert asyncio.run(run()) == ["1", "2", "3", "4"]
