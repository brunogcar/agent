"""Test copy_file action."""

from __future__ import annotations

import pytest
from pathlib import Path
from tools.file import file


class TestCopyFile:
    def test_copy_file(self, mock_cfg):
        src = mock_cfg.workspace_root / "source.txt"
        src.write_text("source content", encoding="utf-8")
        dst = str(mock_cfg.workspace_root / "copied.txt")

        result = file(action="copy_file", source=str(src), destination=dst)
        assert result.get("status") == "success"
        assert Path(src).exists()
        assert Path(dst).exists()
        assert Path(dst).read_text(encoding="utf-8") == "source content"

    def test_copy_file_no_force(self, mock_cfg):
        src = mock_cfg.workspace_root / "source.txt"
        src.write_text("source", encoding="utf-8")
        dst = mock_cfg.workspace_root / "existing.txt"
        dst.write_text("existing", encoding="utf-8")

        result = file(action="copy_file", source=str(src), destination=str(dst))
        assert result.get("status") == "error"
        assert "force=True" in result.get("error", "")

    def test_copy_file_force(self, mock_cfg):
        src = mock_cfg.workspace_root / "source.txt"
        src.write_text("source", encoding="utf-8")
        dst = mock_cfg.workspace_root / "existing.txt"
        dst.write_text("existing", encoding="utf-8")

        result = file(action="copy_file", source=str(src), destination=str(dst), force=True)
        assert result.get("status") == "success"
        assert Path(dst).read_text(encoding="utf-8") == "source"

    def test_copy_file_not_found(self, mock_cfg):
        result = file(action="copy_file", source="nonexistent.txt", destination="dest.txt")
        assert result.get("status") == "error"
