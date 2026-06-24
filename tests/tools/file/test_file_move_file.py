"""Test move_file action."""

from __future__ import annotations

import pytest
from pathlib import Path
from tools.file import file


class TestMoveFile:
    def test_move_file(self, sample_txt, mock_cfg):
        dest = str(mock_cfg.workspace_root / "moved.txt")
        result = file(action="move_file", source=sample_txt, destination=dest)
        assert result.get("status") == "success"
        assert not Path(sample_txt).exists()
        assert Path(dest).exists()

    def test_move_file_no_force(self, sample_txt, mock_cfg):
        dest = mock_cfg.workspace_root / "existing.txt"
        dest.write_text("x", encoding="utf-8")
        result = file(action="move_file", source=sample_txt, destination=str(dest))
        assert result.get("status") == "error"
        assert "force=True" in result.get("error", "")

    def test_move_file_force(self, sample_txt, mock_cfg):
        dest = mock_cfg.workspace_root / "existing.txt"
        dest.write_text("x", encoding="utf-8")
        result = file(action="move_file", source=sample_txt, destination=str(dest), force=True)
        assert result.get("status") == "success"
