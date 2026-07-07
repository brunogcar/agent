"""count_lines action handler.

v1.2 — NEW action.

`wc -l` equivalent: counts newlines in a file without reading the whole thing
into memory. Uses 64KB binary chunk reads (bytes mode), so it works on files
of any encoding including binary files (where it just counts 0x0A bytes).

Why this exists:
  read_file has a 10MB hard ceiling and loads the full file into memory to
  splitlines(). For a 5GB log, that's a non-starter. count_lines streams the
  file in 64KB blocks and counts 0x0A bytes — O(1) memory, O(n) time.

Returns wc -l semantics: `lines` is the number of newline bytes in the file.
A file with no trailing newline still gets counted correctly (a file ending
in \n has N newlines = N "lines" in wc -l; a file not ending in \n has
N-1 newlines but N logical lines — wc -l reports N-1, we match that).
"""

from __future__ import annotations

from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action

# 64KB read block — matches GNU coreutils wc default.
_CHUNK_BYTES = 64 * 1024


@register_action(
    "file",
    "count_lines",
    help_text="""Count newlines in a file (wc -l equivalent). Streams in 64KB binary
chunks — O(1) memory, works on files of any size and any encoding (including
binary). Use this instead of read_file when you only need a line count.

Required: path
Returns: {path, lines, bytes, truncated}""",
    examples=[
        'file(action="count_lines", path="logs/app.log")',
        'file(action="count_lines", path="data/huge.csv")',
    ],
)
def _handle_count_lines(
    path: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Stream-count newlines in a file. O(1) memory, O(n) time."""
    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}
    if not p or not p.exists():
        return {"status": "error", "error": f"File not found: {path}"}
    if not p.is_file():
        return {"status": "error", "error": f"Not a file: {path}"}

    try:
        size = p.stat().st_size
        line_count = 0
        # Binary mode — we're counting 0x0A bytes, not decoding text.
        # This is exactly what `wc -l` does and works on any encoding.
        with open(p, "rb") as f:
            while True:
                block = f.read(_CHUNK_BYTES)
                if not block:
                    break
                line_count += block.count(b"\n")

        return {
            "status": "success",
            "path": str(p),
            "lines": line_count,
            "bytes": size,
            # Always False — we never load the file into memory, so there's
            # no truncation. The field exists for parity with read_file's
            # result shape so callers can write uniform code.
            "truncated": False,
        }
    except Exception as e:
        return {"status": "error", "error": f"count_lines failed: {e}", "path": str(p)}
