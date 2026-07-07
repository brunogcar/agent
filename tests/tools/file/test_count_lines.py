"""Test count_lines action (v1.2 — NEW).

count_lines is a wc -l equivalent that streams the file in 64KB binary chunks.
It does NOT load the file into memory, so it works on files of any size and
any encoding (including binary).

One concern per test class — no generic names.
"""

from __future__ import annotations

import os
import pytest
from tools.file import file


# ─────────────────────────────────────────────────────────────────────────────
# Basic line counting (wc -l semantics)
# ─────────────────────────────────────────────────────────────────────────────

class TestCountLinesBasic:
    """count_lines must match wc -l semantics: count of 0x0A bytes."""

    def test_single_line_no_trailing_newline(self, mock_cfg):
        """File with one line and NO trailing newline.
        wc -l reports 0 (counts newline bytes, not logical lines)."""
        path = mock_cfg.workspace_root / "no_trailing.txt"
        path.write_bytes(b"single line without newline")
        result = file(action="count_lines", path=str(path))
        assert result["status"] == "success"
        assert result["lines"] == 0
        assert result["bytes"] == len(b"single line without newline")
        assert result["truncated"] is False

    def test_single_line_with_trailing_newline(self, mock_cfg):
        """One trailing newline => 1 line per wc -l."""
        path = mock_cfg.workspace_root / "trailing.txt"
        path.write_bytes(b"line\n")
        result = file(action="count_lines", path=str(path))
        assert result["status"] == "success"
        assert result["lines"] == 1
        assert result["bytes"] == 5

    def test_multiple_lines(self, mock_cfg):
        path = mock_cfg.workspace_root / "multi.txt"
        path.write_bytes(b"a\nb\nc\nd\ne\n")
        result = file(action="count_lines", path=str(path))
        assert result["status"] == "success"
        assert result["lines"] == 5
        assert result["bytes"] == 10

    def test_empty_file(self, mock_cfg):
        """Empty file: 0 lines, 0 bytes."""
        path = mock_cfg.workspace_root / "empty.txt"
        path.write_bytes(b"")
        result = file(action="count_lines", path=str(path))
        assert result["status"] == "success"
        assert result["lines"] == 0
        assert result["bytes"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Encoding independence (binary mode)
# ─────────────────────────────────────────────────────────────────────────────

class TestCountLinesEncodingIndependence:
    """count_lines reads in binary mode — works on any encoding without
    triggering the UTF-8 fallback chain. It just counts 0x0A bytes."""

    def test_utf8_multibyte_chars(self, mock_cfg):
        """Multi-byte UTF-8 chars (e.g. é = 2 bytes) must not affect line count."""
        path = mock_cfg.workspace_root / "utf8.txt"
        path.write_bytes("café\nrésumé\n".encode("utf-8"))
        result = file(action="count_lines", path=str(path))
        assert result["status"] == "success"
        assert result["lines"] == 2

    def test_cp1252_file(self, mock_cfg):
        """cp1252-encoded file with high bytes — count_lines doesn't decode,
        just counts newlines."""
        path = mock_cfg.workspace_root / "cp1252.txt"
        path.write_bytes(b"line1 \x93\x94\nline2\n")
        result = file(action="count_lines", path=str(path))
        assert result["status"] == "success"
        assert result["lines"] == 2

    def test_binary_file(self, mock_cfg):
        """Binary file with embedded 0x0A bytes — count_lines counts them too,
        just like wc -l on a binary."""
        path = mock_cfg.workspace_root / "bin.dat"
        # Random-ish binary with 3 newlines embedded
        path.write_bytes(bytes([0, 10, 255, 10, 128, 10, 64]))
        result = file(action="count_lines", path=str(path))
        assert result["status"] == "success"
        assert result["lines"] == 3
        assert result["bytes"] == 7


# ─────────────────────────────────────────────────────────────────────────────
# Large file streaming (memory efficiency)
# ─────────────────────────────────────────────────────────────────────────────

class TestCountLinesStreaming:
    """count_lines must handle large files without loading them into memory.
    64KB chunk reads => O(1) memory regardless of file size."""

    def test_large_file(self, mock_cfg):
        """1MB file with 100k lines — verify count and that bytes matches size."""
        path = mock_cfg.workspace_root / "big.log"
        # Each line is "L\n" = 2 bytes; 500,000 lines = 1,000,000 bytes
        line = b"L\n"
        n = 500_000
        with open(path, "wb") as f:
            for _ in range(n):
                f.write(line)
        result = file(action="count_lines", path=str(path))
        assert result["status"] == "success"
        assert result["lines"] == n
        assert result["bytes"] == n * len(line)
        assert result["truncated"] is False

    def test_64kb_boundary(self, mock_cfg):
        """Verify chunk boundary doesn't drop newlines — file that's exactly
        64KB plus one byte (so the last byte is in a tiny tail chunk)."""
        path = mock_cfg.workspace_root / "boundary.log"
        # 64KB of 'a' with newlines every 64 bytes, then 1 trailing newline
        chunk_size = 64 * 1024
        line = b"a" * 63 + b"\n"  # 64 bytes per line
        n_lines_in_block = chunk_size // 64  # 1024 lines per 64KB block
        with open(path, "wb") as f:
            for _ in range(n_lines_in_block):
                f.write(line)
            f.write(b"\n")  # one extra newline straddling the boundary
        result = file(action="count_lines", path=str(path))
        assert result["status"] == "success"
        assert result["lines"] == n_lines_in_block + 1
        assert result["bytes"] == chunk_size + 1


# ─────────────────────────────────────────────────────────────────────────────
# Error paths
# ─────────────────────────────────────────────────────────────────────────────

class TestCountLinesErrors:
    def test_file_not_found(self, mock_cfg):
        result = file(action="count_lines", path="does_not_exist_xyz.txt")
        assert result["status"] == "error"

    def test_path_is_directory(self, mock_cfg):
        d = mock_cfg.workspace_root / "subdir"
        d.mkdir(parents=True, exist_ok=True)
        result = file(action="count_lines", path=str(d))
        assert result["status"] == "error"
