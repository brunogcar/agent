"""
Read multiple files action handler.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops.actions.read import _read_file
from tools.file_ops._registry import register_action

@register_action("file", "read_many")
def _handle_read_many(paths: list = None, mode: str = "full", max_chars: int = 50_000) -> dict:
    """Read multiple files concurrently."""
    if not paths:
        return {"status": "error", "error": "paths list is required for read_many"}

    summary_chars = 500 if mode == "summary" else max_chars

    def _read_one(path_str: str) -> dict:
        p, err = _safe_resolve(path_str)   # p is already resolved & contained
        if err:
            return {"path": path_str, "error": err, "content": "", "size": 0}
        result = _read_file(p, summary_chars)
        return {
            "path":    path_str,
            "content": result.get("content", ""),
            "size":    result.get("size", 0),
            "lines":   result.get("lines", 0),
            "error":   result.get("error", ""),
        }

    results = []
    # ThreadPoolExecutor for concurrent reads
    with ThreadPoolExecutor(max_workers=min(len(paths), 8)) as executor:
        futures = {executor.submit(_read_one, p): p for p in paths}
        for future in as_completed(futures):
            results.append(future.result())

    # Restore original order
    order  = {p: i for i, p in enumerate(paths)}
    results.sort(key=lambda r: order.get(r["path"], 999))

    total_size = sum(r["size"] for r in results)
    errors     = [r["path"] for r in results if r["error"]]

    return {
        "status":     "success",
        "files":      results,
        "count":      len(results),
        "total_size": total_size,
        "errors":     errors,
        "mode":       mode,
    }