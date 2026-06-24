"""Test backup_file action."""

from __future__ import annotations

import pytest
from pathlib import Path
from tools.file import file


class TestBackupFile:
    def test_backup_file(self, sample_txt):
        result = file(action="backup_file", path=sample_txt)
        assert result.get("status") == "success"
        assert "backup" in result
        assert Path(result["backup"]).exists()

    def test_backup_file_not_found(self, mock_cfg):
        result = file(action="backup_file", path="nonexistent_12345.txt")
        assert result.get("status") == "error"
