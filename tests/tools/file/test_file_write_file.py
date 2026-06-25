"""Test write_file action."""

from __future__ import annotations

import pytest
from pathlib import Path
from tools.file import file


class TestWriteFile:
    def test_write_file_new(self, mock_cfg):
        path = str(mock_cfg.workspace_root / "new.txt")
        result = file(action="write_file", path=path, content="new content")
        assert result.get("status") == "success"
        assert Path(path).read_text(encoding="utf-8") == "new content"

    def test_write_file_overwrite(self, mock_cfg):
        path = mock_cfg.workspace_root / "existing.txt"
        path.write_text("old", encoding="utf-8")
        result = file(action="write_file", path=str(path), content="new")
        assert result.get("status") == "success"
        assert Path(path).read_text(encoding="utf-8") == "new"
        # No .bak should be created
        assert not list(path.parent.glob("*.bak"))

    def test_write_file_empty_content(self, mock_cfg):
        """Empty content is valid - writes an empty file."""
        path = str(mock_cfg.workspace_root / "empty.txt")
        result = file(action="write_file", path=path, content="")
        assert result.get("status") == "success"
        assert Path(path).read_text(encoding="utf-8") == ""
