"""Legacy parser-only Node bridge.

The main SDK talks to Nyora's shared helper REST API. This class preserves the
old direct JS parser execution path for scripts that already used NyoraPythonEngine.
"""

from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Any


class NyoraPythonEngine:
    """Legacy Node-based parser bridge.

    Executes parser methods by shelling out to ``node bridge.js`` from a bridge
    directory. Preserved for scripts that predate the embedded
    :class:`nyora.runtime.ParserRuntime`; new code should prefer
    :class:`nyora.direct.Nyora`.

    Attributes:
        bridge_dir: Directory containing ``bridge.js`` and the sources cache.
        bridge_path: Path to ``bridge.js``.
        sources_cache_path: Path to the cached ``sources.json``.
        sources: The most recently loaded source catalog.
    """

    def __init__(self, bridge_dir: str | None = None) -> None:
        """Configure the bridge.

        Args:
            bridge_dir: Directory holding ``bridge.js``. Defaults to the package
                repository root.
        """
        if bridge_dir is None:
            self.bridge_dir = Path(__file__).resolve().parents[2]
        else:
            self.bridge_dir = Path(bridge_dir).expanduser().resolve()

        self.bridge_path = self.bridge_dir / "bridge.js"
        self.sources_cache_path = self.bridge_dir / "sources.json"
        self.sources: list[dict[str, Any]] = []

    def load_sources(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Load the source catalog from cache or the public feed.

        Args:
            force_refresh: When ``True``, ignore the local cache and re-download.

        Returns:
            The source catalog as a list of dicts.
        """
        if not force_refresh and self.sources_cache_path.exists():
            self.sources = json.loads(self.sources_cache_path.read_text(encoding="utf-8"))
            return self.sources

        url = "https://Hasan72341.github.io/nyora-ota-parsers/sources.json"
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request) as response:
            self.sources = json.loads(response.read().decode("utf-8"))

        self.sources_cache_path.write_text(json.dumps(self.sources, indent=2), encoding="utf-8")
        return self.sources

    def execute(self, source_id: str, method: str, args: dict[str, Any]) -> Any:
        """Run a parser method via the Node bridge subprocess.

        Args:
            source_id: Source identifier.
            method: Parser method name (e.g. ``"list"``, ``"details"``).
            args: Method arguments.

        Returns:
            The parsed JSON result emitted by the bridge.

        Raises:
            subprocess.CalledProcessError: If the bridge exits non-zero.
        """
        payload = {"sourceId": source_id, "method": method, "args": args}
        result = subprocess.run(
            ["node", str(self.bridge_path)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=self.bridge_dir,
            check=True,
        )
        return json.loads(result.stdout)

    def search(self, source_id: str, query: str, page: int = 1) -> Any:
        """Search a source for manga matching a query.

        Args:
            source_id: Source identifier.
            query: Free-text search query.
            page: One-based page number.

        Returns:
            The raw bridge result for the search.
        """
        return self.execute(
            source_id,
            "list",
            {"page": page, "order": "RELEVANCE", "filter": {"query": query}},
        )

    def get_popular(self, source_id: str, page: int = 1) -> Any:
        """Fetch a page of popular manga from a source.

        Args:
            source_id: Source identifier.
            page: One-based page number.

        Returns:
            The raw bridge result for the listing.
        """
        return self.execute(source_id, "list", {"page": page, "order": "POPULARITY"})

    def get_details(self, source_id: str, manga_url: str) -> Any:
        """Fetch full metadata for one manga.

        Args:
            source_id: Source identifier.
            manga_url: The manga's URL.

        Returns:
            The raw bridge result for the details.
        """
        return self.execute(source_id, "details", {"url": manga_url})

    def get_pages(self, source_id: str, chapter_url: str) -> Any:
        """Resolve the readable pages of a chapter.

        Args:
            source_id: Source identifier.
            chapter_url: The chapter's URL.

        Returns:
            The raw bridge result for the pages.
        """
        return self.execute(source_id, "pages", {"url": chapter_url})
