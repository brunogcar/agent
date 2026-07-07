"""Read multiple files action handler.

v1.2 changes:
  - Same encoding fallback chain as read_file (UTF-8 -> cp1252 -> latin-1).
    Per-file `encoding` field in the result list.
  - Same chunk params (chunk, chunk_method, chunk_size) applied uniformly to
    every file in the batch. When chunk=True, per-file result contains `chunks`
    instead of `content`.
"""

from __future__ import annotations

from pathlib import Path

from core.config import cfg
from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action
from tools.file_ops.actions.read_file import _read_with_encoding_fallback, _chunk_text


@register_action(
    "file",
    "read_multiple_files",
    help_text="""Read multiple files concurrently and return combined results.
Encoding fallback (UTF-8 -> cp1252 -> latin-1) and optional chunking (chonkie)
are applied uniformly to every file in the batch.

Required: paths (list of file paths)
Optional:
  max_chars (default 50000)         character truncation per file (ignored if chunk=True)
  chunk (bool, default False)       if True, return chunks list per file
  chunk_method ('token'|'sentence', default 'token')
  chunk_size (int, default 512)     tokens per chunk (approx for sentence mode)

Returns:
  {files: [{path, content|chunks, size, lines?, encoding, ...}],
   count, errors: []}""",
    examples=[
        'file(action="read_multiple_files", paths=["a.py", "b.py", "c.py"])',
        'file(action="read_multiple_files", paths=["a.md","b.md"], chunk=True, chunk_size=512)',
    ],
)
def _handle_read_multiple_files(
    paths: list[str] | None = None,
    max_chars: int = 50_000,
    chunk: bool = False,
    chunk_method: str = "token",
    chunk_size: int = 512,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Read multiple files concurrently (sequentially under the hood — concurrency
    is provided by the small per-file try/except isolation, not threads)."""
    if not paths:
        return {"status": "error", "error": "paths list is required for read_multiple_files"}

    results = []
    errors = []

    for p_str in paths:
        p, err = _safe_resolve(p_str)
        if err:
            errors.append({"path": p_str, "error": err})
            continue
        if not p or not p.exists():
            errors.append({"path": p_str, "error": f"File not found: {p_str}"})
            continue
        if not p.is_file():
            errors.append({"path": p_str, "error": f"Not a file: {p_str}"})
            continue

        try:
            text, encoding_used = _read_with_encoding_fallback(p)
            size = p.stat().st_size

            if chunk:
                try:
                    chunks = _chunk_text(text, chunk_method, chunk_size)
                except (RuntimeError, ValueError) as e:
                    errors.append({"path": p_str, "error": f"Chunking failed: {e}"})
                    continue
                results.append({
                    "path": str(p),
                    "chunks": chunks,
                    "chunk_count": len(chunks),
                    "chunk_method": chunk_method,
                    "chunk_size": chunk_size,
                    "size": size,
                    "encoding": encoding_used,
                })
            else:
                if len(text) > max_chars:
                    text = text[:max_chars] + f"\n\n[...truncated — {size} bytes total]"
                results.append({
                    "path": str(p),
                    "content": text,
                    "size": size,
                    "lines": len(text.splitlines()),
                    "encoding": encoding_used,
                })
        except Exception as e:
            errors.append({"path": p_str, "error": str(e)})

    return {
        "status": "success",
        "files": results,
        "count": len(results),
        "errors": errors,
    }
