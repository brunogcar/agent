"""Read multiple files action handler."""

from __future__ import annotations

from pathlib import Path

from core.config import cfg
from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action

@register_action(
    "file",
    "read_multiple_files",
    help_text="""Read multiple files concurrently and return combined results.
Required: paths (list of file paths)
Optional: max_chars (default 50000)
Returns: {files: [{path, content, size, lines}], count, errors: []}""",
    examples=[
        'file(action="read_multiple_files", paths=["a.py", "b.py", "c.py"])',
    ],
)
def _handle_read_multiple_files(
    paths: list[str] | None = None,
    max_chars: int = 50_000,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Read multiple files concurrently."""
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
            text = p.read_text(encoding="utf-8", errors="replace")
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n\n[...truncated — {p.stat().st_size} bytes total]"
            results.append({
                "path": str(p),
                "content": text,
                "size": p.stat().st_size,
                "lines": text.count("\n") + 1,
            })
        except Exception as e:
            errors.append({"path": p_str, "error": str(e)})

    return {
        "status": "success",
        "files": results,
        "count": len(results),
        "errors": errors,
    }
