"""Test result compression for large file outputs."""

from __future__ import annotations

import pytest
from pathlib import Path
from tools.file import file


class TestFileCompression:
    def test_large_file_read_is_compressed(self, mock_cfg):
        # Create a file > 4000 chars in the mock workspace
        path = mock_cfg.workspace_root / "big.txt"
        content = "x" * 5000
        path.write_text(content, encoding="utf-8")

        result = file(action="read_file", path=str(path))
        assert result.get("status") == "success"
        text = result.get("content", "")
        # compress_result truncates at 4000 chars
        if len(content) > 4000:
            assert "truncated" in text

    def test_small_file_read_uncompressed(self, mock_cfg):
        path = mock_cfg.workspace_root / "small.txt"
        content = "small content"
        path.write_text(content, encoding="utf-8")

        result = file(action="read_file", path=str(path))
        assert result.get("status") == "success"
        text = result.get("content", "")
        assert "truncated" not in text
