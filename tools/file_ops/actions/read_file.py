"""Read file action handler.

v1.2 changes:
  - Encoding fallback chain: UTF-8 (strict) -> cp1252 (strict) -> latin-1 (last resort,
    never raises). The encoding that succeeded is reported as `encoding` in the result.
  - Chunking via chonkie (soft dependency, lazy import):
      chunk=True, chunk_method="token"|"sentence", chunk_size=N
    When chunk=True, head/tail/max_chars are ignored and the result contains a `chunks`
    list (each chunk is a string) plus `chunk_count`, `chunk_method`, `chunk_size`.
"""

from __future__ import annotations

from pathlib import Path

from core.config import cfg
from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action

MAX_READ_SIZE = 10_000_000  # 10MB hard ceiling

# Encoding fallback chain (v1.2).
# Order matters: try UTF-8 first (the only sane default), then cp1252 (Windows
# ANSI — covers legacy English/European files), then latin-1 (1 byte = 1 char,
# NEVER raises — guaranteed last resort so callers always get content back).
_ENCODING_CHAIN: tuple[str, ...] = ("utf-8", "cp1252", "latin-1")


def _read_with_encoding_fallback(path: Path) -> tuple[str, str]:
    """Try each encoding in _ENCODING_CHAIN strict; return (text, encoding_used).

    latin-1 is the final fallback and is mathematically incapable of raising
    UnicodeDecodeError (every byte 0x00..0xFF maps to a codepoint), so this
    function ALWAYS returns content. The caller gets back which encoding won.
    """
    last_err: Exception | None = None
    for enc in _ENCODING_CHAIN:
        try:
            return path.read_text(encoding=enc), enc
        except UnicodeDecodeError as e:
            last_err = e
            continue
    # Unreachable — latin-1 cannot fail — but keep mypy happy.
    raise last_err  # pragma: no cover


def _chunk_text(text: str, method: str, size: int) -> list[str]:
    """Chunk text via chonkie. Lazy import — soft dependency.

    method:
      "token"     -> TokenChunker (default; chunk_size = tokens per chunk)
      "sentence"  -> SentenceChunker (chunk_size approx tokens per chunk; chonkie
                     groups sentences to roughly hit the target)

    Returns a list of plain-text chunk strings. Any chonkie error is propagated
    as a RuntimeError so the caller can wrap it in a status=error dict.
    """
    if size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    try:
        if method == "token":
            from chonkie import TokenChunker  # type: ignore
            chunker = TokenChunker(chunk_size=size)
        elif method == "sentence":
            from chonkie import SentenceChunker  # type: ignore
            chunker = SentenceChunker(chunk_size=size)
        else:
            raise ValueError(
                f"chunk_method must be 'token' or 'sentence', got: {method!r}"
            )
    except ImportError as e:
        raise RuntimeError(
            "chonkie is not installed. Run `pip install chonkie` to use chunking."
        ) from e

    chunks = chunker.chunk(text)
    # chonkie chunk objects expose .text (str); fall back to str() for safety.
    return [getattr(c, "text", str(c)) for c in chunks]


@register_action(
    "file",
    "read_file",
    help_text="""Read a single text file. Paths relative to agent and workspace roots.
Supports head/tail line-based reading, max_chars character truncation, and
chunking via chonkie (v1.2). Encoding fallback chain UTF-8 -> cp1252 -> latin-1
is applied automatically; the encoding used is reported in the result.

Required: path
Optional:
  max_chars (default 50000)         character truncation (ignored if chunk=True)
  head (first N lines)              line-based (ignored if chunk=True)
  tail (last N lines)               line-based (ignored if chunk=True)
  chunk (bool, default False)       if True, return list of chunks
  chunk_method ('token'|'sentence', default 'token')
  chunk_size (int, default 512)     tokens per chunk (approx for sentence mode)

Returns (no chunking): {content, size, lines, truncated, encoding, extension}
Returns (chunking):    {chunks, chunk_count, chunk_method, chunk_size,
                        size, encoding, extension}""",
    examples=[
        'file(action="read_file", path="scripts/analysis.py")',
        'file(action="read_file", path="logs/app.log", tail=20)',
        'file(action="read_file", path="README.md", head=50)',
        'file(action="read_file", path="big.md", chunk=True, chunk_size=512)',
        'file(action="read_file", path="paper.md", chunk=True, chunk_method="sentence")',
    ],
)
def _read_file(
    path: str = "",
    max_chars: int = 50_000,
    head: int | None = None,
    tail: int | None = None,
    chunk: bool = False,
    chunk_method: str = "token",
    chunk_size: int = 512,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Read a file with symlink safety, size limits, encoding fallback, and chunking."""
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
        # Empty file: still report a sensible result for both modes.
        base = {
            "status": "success",
            "path": str(resolved),
            "size": 0,
            "encoding": "utf-8",
            "extension": resolved.suffix,
        }
        if chunk:
            base.update({
                "chunks": [],
                "chunk_count": 0,
                "chunk_method": chunk_method,
                "chunk_size": chunk_size,
            })
        else:
            base.update({"content": "", "lines": 0, "truncated": False})
        return base

    # Hard size ceiling before reading into memory
    if stat.st_size > MAX_READ_SIZE:
        return {
            "status": "error",
            "error": f"File too large: {stat.st_size / 1024 / 1024:.1f}MB (max {MAX_READ_SIZE / 1024 / 1024:.0f}MB)",
        }

    try:
        # v1.2: encoding fallback chain — guaranteed to succeed (latin-1 last resort).
        text, encoding_used = _read_with_encoding_fallback(resolved)

        # v1.2: chunking branch — mutually exclusive with head/tail/max_chars.
        if chunk:
            try:
                chunks = _chunk_text(text, chunk_method, chunk_size)
            except (RuntimeError, ValueError) as e:
                return {
                    "status": "error",
                    "error": f"Chunking failed: {e}",
                    "path": str(resolved),
                }
            return {
                "status": "success",
                "path": str(resolved),
                "chunks": chunks,
                "chunk_count": len(chunks),
                "chunk_method": chunk_method,
                "chunk_size": chunk_size,
                "size": stat.st_size,
                "encoding": encoding_used,
                "extension": resolved.suffix,
            }

        # Non-chunk branch: head / tail / max_chars (priority: tail > head > max_chars)
        lines = text.splitlines()
        total_lines = len(lines)

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
            "lines": len(text.splitlines()),
            "truncated": truncated,
            "encoding": encoding_used,
            "extension": resolved.suffix,
        }
    except Exception as e:
        return {"status": "error", "error": f"Read failed: {e}", "path": str(resolved)}
