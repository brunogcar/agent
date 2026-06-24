"""Test delete_file action."""

from __future__ import annotations

import pytest
from pathlib import Path
from tools.file import file


class TestDeleteFile:
    def test_delete_file_no_force(self, sample_txt):
        result = file(action="delete_file", path=sample_txt)
        assert result.get("status") == "error"
        assert "force=True" in result.get("error", "")

    def test_delete_file_with_force(self, sample_txt):
        result = file(action="delete_file", path=sample_txt, force=True)
        assert result.get("status") == "success"
        assert not Path(sample_txt).exists()

    def test_delete_directory_recursive(self, mock_cfg):
        d = mock_cfg.workspace_root / "deldir"
        d.mkdir()
        (d / "file.txt").write_text("x", encoding="utf-8")
        result = file(action="delete_file", path=str(d), force=True, recursive=True)
        assert result.get("status") == "success"
        assert not d.exists()
