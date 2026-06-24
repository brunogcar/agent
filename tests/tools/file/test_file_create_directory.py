"""Test create_directory action."""

from __future__ import annotations

import pytest
from pathlib import Path
from tools.file import file


class TestCreateDirectory:
    def test_create_directory(self, mock_cfg):
        path = str(mock_cfg.workspace_root / "new_dir")
        result = file(action="create_directory", path=path)
        assert result.get("status") == "success"
        assert Path(path).is_dir()

    def test_create_nested_directories(self, mock_cfg):
        path = str(mock_cfg.workspace_root / "a" / "b" / "c")
        result = file(action="create_directory", path=path, parents=True)
        assert result.get("status") == "success"
        assert Path(path).is_dir()
