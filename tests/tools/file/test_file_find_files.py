"""Test find_files action."""

from __future__ import annotations

import pytest
from pathlib import Path
from tools.file import file


class TestFindFiles:
    def test_find_files_glob(self, mock_cfg):
        # Create files
        (mock_cfg.workspace_root / "a.py").write_text("a", encoding="utf-8")
        (mock_cfg.workspace_root / "b.py").write_text("b", encoding="utf-8")
        (mock_cfg.workspace_root / "c.txt").write_text("c", encoding="utf-8")
        sub = mock_cfg.workspace_root / "subdir"
        sub.mkdir()
        (sub / "d.py").write_text("d", encoding="utf-8")

        result = file(action="find_files", pattern="**/*.py", path=str(mock_cfg.workspace_root))
        assert result.get("status") == "success"
        files = result.get("files", [])
        names = [f["name"] for f in files]
        assert "a.py" in names
        assert "b.py" in names
        assert "d.py" in names
        assert "c.txt" not in names

    def test_find_files_no_pattern(self, mock_cfg):
        result = file(action="find_files", path=str(mock_cfg.workspace_root))
        assert result.get("status") == "error"
        assert "pattern" in result.get("error", "").lower()

    def test_find_files_not_found(self, mock_cfg):
        result = file(action="find_files", pattern="*.py", path="nonexistent_dir_12345")
        assert result.get("status") == "error"
