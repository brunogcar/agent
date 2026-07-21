"""core/atomic_write.py — Atomic file writes via tempfile + os.replace.

Single function: `atomic_write(path, content, *, encoding="utf-8") -> None`.

Pattern: `tempfile.mkstemp` in the SAME directory as the target (guarantees
same-filesystem rename — `os.replace` is atomic only within the same
filesystem), `os.fdopen` the file descriptor, write content, `f.flush()`,
`os.fsync(f.fileno())`, then `os.replace(temp, target)`. On failure, the
tempfile is `os.unlink`'d (no `.tmp` leaks) and the original exception
re-raised.

Parent directories are created (with `parents=True, exist_ok=True`) before
the tempfile is created — callers don't need to `mkdir -p` themselves.

WHY THIS EXISTS
---------------
Extracted from 4 duplicated implementations across the autocode + autoresearch
workflows (Phase A of the centralize-workflow-utils refactor — v1.5 of
`core/standalone`):

1. `workflows/autoresearch_impl/nodes/modify.py::_atomic_write` — the
   original implementation (tempfile.mkstemp + os.fdopen + fsync + os.replace
   + os.unlink on failure). Used by `node_modify` for the single + parallel
   experiment write paths AND by `node_decide` (parallel winner copy).
2. `workflows/autocode_impl/patch.py::apply_patch` / `apply_patches` —
   inline `tempfile.NamedTemporaryFile(delete=False) + os.replace` block.
3. `workflows/autocode_impl/nodes/write_new_files.py::node_write_new_files`
   — inline atomic write INSIDE a `filelock.FileLock` block. The FileLock
   stays (cross-process coordination); the inner write now delegates here.
4. `workflows/autocode_impl/nodes/create_skill.py::node_create_skill`
   — inline `tempfile.NamedTemporaryFile + os.replace` block.

All 4 had the same shape (write-to-temp + os.replace) but with subtle
differences (some called `fsync`, some didn't; some created parent dirs,
some didn't; some used `Path.unlink(missing_ok=True)`, some used
`os.unlink` wrapped in try/except OSError). Consolidating into one helper
eliminates the drift.

This module is intentionally minimal — no logging, no tracer integration,
no retry. Callers wrap with their own try/except + tracer calls as needed.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write `content` to `path` atomically.

    Writes to a tempfile in the same directory as `path`, then `os.replace`s
    it into place. `os.replace` is atomic on POSIX and Windows for same-
    filesystem renames, so readers never see a partial file. On failure, the
    tempfile is `os.unlink`'d (no `.tmp` leaks) and the original exception
    is re-raised.

    Parent directories are created (with `parents=True, exist_ok=True`) before
    the tempfile is created — callers don't need to `mkdir -p` themselves.

    Args:
        path: Target file path. Parent dirs are created if missing.
        content: Text content to write.
        encoding: Text encoding (default "utf-8").

    Raises:
        Whatever exception the underlying `os.fdopen` / `write` / `fsync` /
        `os.replace` raises — the tempfile is cleaned up first. Common
        failures: `OSError` (disk full, permission denied), `UnicodeEncodeError`
        (content has chars not representable in `encoding`).
    """
    # Normalize to Path so callers can pass a str OR a Path.
    path = Path(path)
    # Create parent directories (mirrors the modify.py behavior — callers
    # used to do this themselves; consolidating it here eliminates the
    # "did I remember to mkdir?" footgun).
    path.parent.mkdir(parents=True, exist_ok=True)

    # tempfile in the SAME directory as the target guarantees same-filesystem
    # rename (os.replace is atomic only within the same filesystem). The
    # `.{name}.` prefix + `.tmp` suffix makes leaks visible if they ever
    # happen (cleanup failed, process killed twice, etc.).
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        # os.fdopen takes ownership of the file descriptor — closing the
        # Python file also closes the fd. f.flush() pushes Python's buffer
        # to the kernel; os.fsync(fileno) pushes the kernel buffer to disk
        # (so a power loss after fsync doesn't lose the write).
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        # os.replace is atomic on POSIX + Windows for same-filesystem renames.
        # On cross-filesystem, os.replace raises OSError (we'd fall through
        # to the cleanup branch and re-raise). Same-filesystem is guaranteed
        # by tempfile.mkstemp(dir=path.parent).
        os.replace(tmp_path, path)
    except Exception:
        # Clean up the tempfile on failure — don't leak .tmp files in the
        # target directory. try/except OSError so the unlink failure doesn't
        # mask the original exception (the original is re-raised below).
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


__all__ = ["atomic_write"]
