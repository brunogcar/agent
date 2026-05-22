"""
Search action handler.
"""

from __future__ import annotations

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops.index import _get_index, _build_index
from core.config import cfg
from tools.file_ops._registry import register_action

@register_action("file", "search")
def _handle_search(query: str = "", max_results: int = 10) -> dict:
    """Full-text search across agent and workspace files."""
    if not query:
        return {"status": "error", "error": "query is required for search"}

    # Build/refresh index
    indexed = _build_index(cfg.workspace_root)

    try:
        db = _get_index()
        rows = db.execute(
            """
            SELECT path, snippet(files_fts, 1, '[', ']', '...', 20) as snippet, rank
            FROM files_fts
            WHERE content MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, max_results),
        ).fetchall()

        results = [
            {"path": row[0], "snippet": row[1], "rank": round(abs(row[2]), 4)}
            for row in rows
        ]

        return {
            "status":        "success",
            "query":         query,
            "results":       results,
            "count":         len(results),
            "indexed_files": indexed,
        }
    except Exception as e:
        return {"status": "error", "error": f"Search failed: {e}"}