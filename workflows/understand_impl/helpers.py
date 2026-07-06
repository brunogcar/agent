"""Helpers for understand workflow."""
from __future__ import annotations

import hashlib
from pathlib import Path


def _chunked_md5(file_path: Path, chunk_size: int = 8192) -> str:
    """[Bug #6] Compute MD5 hash using chunked reading instead of read_bytes().

    Prevents loading entire large files into memory.
    """
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()
