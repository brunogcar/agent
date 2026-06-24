"""Test file tool result compression."""

from __future__ import annotations

import pytest
from pathlib import Path
from tools.file import file


class TestFileCompression:
    def test_large_file_read_is_compressed(self, mock_cfg):
        path = mock_cfg.workspace_root / "large.txt"
        path.write_text("x" * 10000, encoding="utf-8")

        result = file(action="read_file", path=str(path))
        assert result.get("status") == "success"
        content = result.get("content", "")
        if len(content) > 4000:
            assert "truncated" in content

    def test_small_file_read_uncompressed(self, mock_cfg):
        path = mock_cfg.workspace_root / "small.txt"
        path.write_text("small content", encoding="utf-8")

        result = file(action="read_file", path=str(path))
        assert result.get("status") == "success"
        assert result.get("content") == "small content"
