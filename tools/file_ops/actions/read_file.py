"""Read file action handler."""

from __future__ import annotations

from pathlib import Path

from core.config import cfg
from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action

MAX_READ_SIZE = 10_000_000  # 10MB hard ceiling

@register_action(
    "file",
    "read_file",
    help_text="""Read a single text file. Paths relative to agent and workspace roots.
Supports head/tail line-based reading and max_chars character truncation.
Required: path
Optional: max_chars (default 50000), head (first N lines), tail (last N lines)
Returns: {content, size, lines, truncated}""",
    examples=[
        'file(action="read_file", path="scripts/analysis.py")',
        'file(action="read_file", path="logs/app.log", tail=20)',
        'file(action="read_file", path="README.md", head=50)',
    ],
)
def _read_file(
    path: str = "",
    max_chars: int = 50_000,
    head: int | None = None,
    tail: int | None = None,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Read a file with symlink safety and size limits."""
    resolved = None

    # Use _safe_resolve like every other handler
    resolved = _safe_resolve(path)[0]

    if not resolved:
        return {"status": "error", "error": "File not found or access denied"}

    if not resolved.exists():
        return {"status": "error", "error": f"File not found: {resolved}"}
    if not resolved.is_file():
        return {"status": "error", "error": f"Not a file: {resolved}"}

    stat = resolved.stat()
    if stat.st_size == 0:
        return {
            "status": "success",
            "path": str(resolved),
            "content": "",
            "size": 0,
            "lines": 0,
            "truncated": False,
        }

    # Hard size ceiling before reading into memory
    if stat.st_size > MAX_READ_SIZE:
        return {
            "status": "error",
            "error": f"File too large: {stat.st_size / 1024 / 1024:.1f}MB (max {MAX_READ_SIZE / 1024 / 1024:.0f}MB)",
        }

    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        total_lines = len(lines)

        # Priority: tail > head > max_chars
        if tail is not None and tail > 0:
            lines = lines[-tail:]
            text = "\n".join(lines)
            truncated = total_lines > tail
        elif head is not None and head > 0:
            lines = lines[:head]
            text = "\n".join(lines)
            truncated = total_lines > head
        else:
            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars] + f"\n\n[...truncated — {stat.st_size} bytes total]"

        return {
            "status": "success",
            "path": str(resolved),
            "content": text,
            "size": stat.st_size,
            "lines": text.count("\n") + 1,
            "truncated": truncated,
            "extension": resolved.suffix,
        }
    except Exception as e:
        return {"status": "error", "error": f"Read failed: {e}", "path": str(resolved)}
