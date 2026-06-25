"""Test read_multiple_files action."""

from __future__ import annotations

import pytest
from pathlib import Path
from tools.file import file


class TestReadMultipleFiles:
    def test_read_multiple_files(self, mock_cfg):
        p1 = mock_cfg.workspace_root / "file1.txt"
        p2 = mock_cfg.workspace_root / "file2.txt"
        p1.write_text("content 1", encoding="utf-8")
        p2.write_text("content 2", encoding="utf-8")

        result = file(action="read_multiple_files", paths=[str(p1), str(p2)])
        assert result.get("status") == "success"
        assert result.get("count") == 2
        files = result.get("files", [])
        assert len(files) == 2
        assert all("content" in f.get("content", "") for f in files)

    def test_read_multiple_files_with_missing(self, mock_cfg):
        """Facade validates all paths before dispatch; missing path fails early.
        This is the current behavior - the facade filters out unresolved paths."""
        p1 = mock_cfg.workspace_root / "file1.txt"
        p1.write_text("content 1", encoding="utf-8")

        # One missing path — facade filters it, only existing paths reach handler
        result = file(action="read_multiple_files", paths=[str(p1), "nonexistent.txt"])
        # Current behavior: facade drops missing paths, handler gets only existing ones
        assert result.get("status") == "success"
        files = result.get("files", [])
        assert len(files) == 1
        assert "content 1" in files[0].get("content", "")
