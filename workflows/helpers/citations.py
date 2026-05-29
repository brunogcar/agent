"""
core/citations.py -- Citation tracker for research workflows.

Tracks which facts came from which sources during a research session.
Keyed by trace_id so citations are scoped to a single workflow run.

Usage:
    from workflows.helpers.citations import citations

    # During scraping
    citations.add(trace_id, url="https://example.com", title="Example",
                  snippet="ChromaDB supports persistent storage")

    # When building report
    sources = citations.get_sources(trace_id)
    numbered = citations.get_numbered(trace_id)
    # -> [{"n": 1, "url": "...", "title": "...", "snippets": [...]}]

    # Inline citation marker for text
    marker = citations.cite(trace_id, url="https://example.com")
    # -> "[1]"
"""

from __future__ import annotations

import threading
import time
from typing import Optional


class CitationTracker:
    """
    Per-trace citation store. Thread-safe.

    Each source gets a number [1], [2], [3]... in order of first appearance.
    Multiple facts from the same URL share the same citation number.
    """

    MAX_TRACES = 100  # evict oldest when over limit

    def __init__(self) -> None:
        self._lock   = threading.Lock()
        # trace_id -> {"url": {"title", "snippets": [], "number": int, "added_at": float}}
        self._store: dict[str, dict[str, dict]] = {}
        self._order: list[str] = []

    def _ensure_trace(self, trace_id: str) -> None:
        """Create trace entry if missing. Must be called under lock."""
        if trace_id not in self._store:
            self._store[trace_id] = {}
            self._order.append(trace_id)
            # Evict oldest if over limit
            while len(self._order) > self.MAX_TRACES:
                old = self._order.pop(0)
                self._store.pop(old, None)

    def add(
        self,
        trace_id: str,
        url:      str,
        title:    str    = "",
        snippet:  str    = "",
    ) -> int:
        """
        Register a source URL for this trace.
        Returns the citation number (1-based, stable across multiple calls).
        """
        if not url or not trace_id:
            return 0

        with self._lock:
            self._ensure_trace(trace_id)
            sources = self._store[trace_id]

            if url not in sources:
                number = len(sources) + 1
                sources[url] = {
                    "url":      url,
                    "title":    title or url,
                    "snippets": [],
                    "number":   number,
                    "added_at": time.time(),
                }

            if snippet and snippet not in sources[url]["snippets"]:
                sources[url]["snippets"].append(snippet[:300])

            # Update title if we now have a better one
            if title and sources[url]["title"] == url:
                sources[url]["title"] = title

            return sources[url]["number"]

    def cite(self, trace_id: str, url: str) -> str:
        """
        Return inline citation marker like "[1]" for a URL.
        Registers the URL if not already seen.
        """
        if not url or not trace_id:
            return ""
        with self._lock:
            self._ensure_trace(trace_id)
            sources = self._store[trace_id]
            if url not in sources:
                number = len(sources) + 1
                sources[url] = {
                    "url": url, "title": url,
                    "snippets": [], "number": number,
                    "added_at": time.time(),
                }
            return f"[{sources[url]['number']}]"

    def get_sources(self, trace_id: str) -> list[dict]:
        """
        Return all sources for a trace, sorted by citation number.
        Each entry: {number, url, title, snippets, added_at}
        """
        with self._lock:
            sources = self._store.get(trace_id, {})
            return sorted(sources.values(), key=lambda s: s["number"])

    def get_numbered(self, trace_id: str) -> list[dict]:
        """
        Alias for get_sources -- more explicit name for template rendering.
        """
        return self.get_sources(trace_id)

    def has_sources(self, trace_id: str) -> bool:
        with self._lock:
            return bool(self._store.get(trace_id))

    def clear(self, trace_id: str) -> None:
        with self._lock:
            self._store.pop(trace_id, None)
            if trace_id in self._order:
                self._order.remove(trace_id)

    def count(self, trace_id: str) -> int:
        with self._lock:
            return len(self._store.get(trace_id, {}))


# -- Singleton ----------------------------------------------------------------
citations = CitationTracker()
