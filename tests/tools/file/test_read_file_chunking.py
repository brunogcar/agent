"""Test read_file chunking (v1.2) and encoding fallback (v1.2).

One concern per test class — no generic names.

Concerns covered:
  - Encoding fallback chain (UTF-8 -> cp1252 -> latin-1)
  - Token chunking via chonkie
  - Sentence chunking via chonkie
  - Chunking interplay: chunk=True ignores head/tail/max_chars
  - Empty file + chunk=True
  - read_multiple_files with chunk=True
"""

from __future__ import annotations

import pytest
from tools.file import file


# ─────────────────────────────────────────────────────────────────────────────
# Encoding fallback chain (UTF-8 -> cp1252 -> latin-1)
# ─────────────────────────────────────────────────────────────────────────────

class TestEncodingFallback:
    """v1.2: read_file must succeed on any byte sequence via fallback chain."""

    def test_utf8_file_reports_utf8(self, mock_cfg):
        """Plain ASCII/UTF-8 file should report encoding='utf-8'."""
        path = mock_cfg.workspace_root / "utf8.txt"
        path.write_text("Hello, world!\nLine 2\n", encoding="utf-8")
        result = file(action="read_file", path=str(path))
        assert result["status"] == "success"
        assert result["encoding"] == "utf-8"
        assert "Hello, world!" in result["content"]

    def test_cp1252_only_file_falls_back(self, mock_cfg):
        """File with cp1252-only bytes (e.g. 0x93/0x94 smart quotes) that are
        INVALID in UTF-8 must fall back to cp1252 and report that encoding."""
        # 0x93 = left double quote in cp1252, INVALID as UTF-8 start byte
        path = mock_cfg.workspace_root / "cp1252.txt"
        path.write_bytes(b"Hello \x93world\x94\n")
        result = file(action="read_file", path=str(path))
        assert result["status"] == "success"
        assert result["encoding"] == "cp1252"
        # cp1252 0x93 = U+201C, 0x94 = U+201D
        assert "\u201c" in result["content"]
        assert "\u201d" in result["content"]

    def test_latin1_last_resort(self, mock_cfg):
        """Bytes that are invalid in BOTH utf-8 and cp1252 (e.g. 0x81 — undefined
        in cp1252) must fall back to latin-1 which never fails."""
        # 0x81 is undefined in cp1252 (Microsoft maps it to U+0081 only with
        # Best-Fit mapping, but Python's cp1252 codec raises on it).
        path = mock_cfg.workspace_root / "latin1.txt"
        path.write_bytes(b"Binary \x81 \x8d \x8f data\n")
        result = file(action="read_file", path=str(path))
        assert result["status"] == "success"
        assert result["encoding"] == "latin-1"
        # latin-1 maps 0x81 -> U+0081 verbatim
        assert "\x81" in result["content"]

    def test_pure_ascii_works_as_utf8(self, mock_cfg):
        """Pure ASCII must report utf-8 (a strict subset, no fallback needed)."""
        path = mock_cfg.workspace_root / "ascii.txt"
        path.write_text("Just ASCII\n", encoding="ascii")
        result = file(action="read_file", path=str(path))
        assert result["status"] == "success"
        assert result["encoding"] == "utf-8"


# ─────────────────────────────────────────────────────────────────────────────
# Token chunking
# ─────────────────────────────────────────────────────────────────────────────

class TestTokenChunking:
    """v1.2: chunk=True with chunk_method='token' returns list of chunks."""

    def test_token_chunks_returned_as_list(self, mock_cfg):
        path = mock_cfg.workspace_root / "long.md"
        # ~600 tokens of repetitive text — should produce multiple chunks at size=128
        path.write_text("The quick brown fox. " * 200, encoding="utf-8")
        result = file(
            action="read_file",
            path=str(path),
            chunk=True,
            chunk_method="token",
            chunk_size=128,
        )
        assert result["status"] == "success"
        assert "chunks" in result
        assert "content" not in result  # chunking mode returns chunks, not content
        assert isinstance(result["chunks"], list)
        assert result["chunk_count"] == len(result["chunks"])
        assert result["chunk_count"] >= 2
        assert result["chunk_method"] == "token"
        assert result["chunk_size"] == 128
        # Each chunk should be a non-empty string
        for c in result["chunks"]:
            assert isinstance(c, str)
            assert len(c) > 0

    def test_token_chunk_size_affects_count(self, mock_cfg):
        """Smaller chunk_size => more chunks for the same content."""
        path = mock_cfg.workspace_root / "same.md"
        path.write_text("The quick brown fox jumps over the lazy dog. " * 100, encoding="utf-8")
        big = file(action="read_file", path=str(path), chunk=True, chunk_size=256)
        small = file(action="read_file", path=str(path), chunk=True, chunk_size=64)
        assert big["status"] == "success"
        assert small["status"] == "success"
        assert small["chunk_count"] > big["chunk_count"]


# ─────────────────────────────────────────────────────────────────────────────
# Sentence chunking
# ─────────────────────────────────────────────────────────────────────────────

class TestSentenceChunking:
    """v1.2: chunk_method='sentence' groups whole sentences."""

    def test_sentence_chunks_returned(self, mock_cfg):
        path = mock_cfg.workspace_root / "paragraphs.md"
        # Many short sentences — sentence chunker should group them
        path.write_text(
            "This is sentence one. This is sentence two. "
            "This is sentence three. This is sentence four. "
            "This is sentence five. This is sentence six.\n",
            encoding="utf-8",
        )
        result = file(
            action="read_file",
            path=str(path),
            chunk=True,
            chunk_method="sentence",
            chunk_size=32,
        )
        assert result["status"] == "success"
        assert isinstance(result["chunks"], list)
        assert result["chunk_count"] >= 1
        assert result["chunk_method"] == "sentence"


# ─────────────────────────────────────────────────────────────────────────────
# Chunking interplay with head/tail/max_chars
# ─────────────────────────────────────────────────────────────────────────────

class TestChunkInterplay:
    """v1.2: chunk=True is mutually exclusive with head/tail/max_chars."""

    def test_chunk_ignores_head_and_tail(self, mock_cfg):
        """When chunk=True, head and tail are ignored — we get chunks, not lines."""
        path = mock_cfg.workspace_root / "interplay.md"
        path.write_text("Sentence one. " * 100, encoding="utf-8")
        result = file(
            action="read_file",
            path=str(path),
            chunk=True,
            chunk_size=64,
            head=5,  # should be ignored
            tail=10,  # should be ignored
            max_chars=100,  # should be ignored
        )
        assert result["status"] == "success"
        assert "chunks" in result
        assert "content" not in result
        assert "truncated" not in result  # truncation is a non-chunk concept

    def test_chunk_false_uses_max_chars(self, mock_cfg):
        """When chunk=False (default), max_chars applies normally."""
        path = mock_cfg.workspace_root / "interplay2.md"
        path.write_text("x" * 5000, encoding="utf-8")
        result = file(
            action="read_file",
            path=str(path),
            chunk=False,
            max_chars=100,
        )
        assert result["status"] == "success"
        assert "content" in result
        assert "chunks" not in result
        assert result["truncated"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestChunkEdgeCases:
    """Empty files and error paths with chunking."""

    def test_empty_file_with_chunk_true(self, mock_cfg):
        """Empty file + chunk=True returns empty chunk list, not an error."""
        path = mock_cfg.workspace_root / "empty.md"
        path.write_text("", encoding="utf-8")
        result = file(
            action="read_file",
            path=str(path),
            chunk=True,
            chunk_method="token",
            chunk_size=128,
        )
        assert result["status"] == "success"
        assert result["chunks"] == []
        assert result["chunk_count"] == 0

    def test_invalid_chunk_method_errors(self, mock_cfg):
        """Unknown chunk_method should return a clean error, not a crash."""
        path = mock_cfg.workspace_root / "ok.md"
        path.write_text("Some text here. ", encoding="utf-8")
        result = file(
            action="read_file",
            path=str(path),
            chunk=True,
            chunk_method="paragraph",  # not supported
        )
        assert result["status"] == "error"
        assert "chunk_method" in result["error"].lower() or "paragraph" in result["error"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# read_multiple_files with chunking
# ─────────────────────────────────────────────────────────────────────────────

class TestReadMultipleFilesChunking:
    """v1.2: chunking applies uniformly to every file in the batch."""

    def test_read_multiple_files_with_chunk(self, mock_cfg):
        p1 = mock_cfg.workspace_root / "a.md"
        p2 = mock_cfg.workspace_root / "b.md"
        p1.write_text("Alpha content. " * 100, encoding="utf-8")
        p2.write_text("Beta content. " * 100, encoding="utf-8")
        result = file(
            action="read_multiple_files",
            paths=[str(p1), str(p2)],
            chunk=True,
            chunk_method="token",
            chunk_size=64,
        )
        assert result["status"] == "success"
        assert result["count"] == 2
        for entry in result["files"]:
            assert "chunks" in entry
            assert "content" not in entry
            assert entry["chunk_count"] >= 1
            assert entry["chunk_method"] == "token"
            assert entry["chunk_size"] == 64

    def test_read_multiple_files_encoding_reported(self, mock_cfg):
        """Each file reports its own encoding."""
        p1 = mock_cfg.workspace_root / "ascii.txt"
        p2 = mock_cfg.workspace_root / "cp1252.txt"
        p1.write_bytes(b"Plain ASCII\n")
        p2.write_bytes(b"Hello \x93world\x94\n")
        result = file(
            action="read_multiple_files",
            paths=[str(p1), str(p2)],
        )
        assert result["status"] == "success"
        encodings = [f["encoding"] for f in result["files"]]
        assert "utf-8" in encodings
        assert "cp1252" in encodings
