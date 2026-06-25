"""Test append_file action."""

from __future__ import annotations

import pytest
from pathlib import Path
from tools.file import file


class TestAppendFile:
    def test_append_to_existing(self, mock_cfg):
        path = mock_cfg.workspace_root / "append.txt"
        path.write_text("first line\n", encoding="utf-8")

        result = file(action="append_file", path=str(path), content="second line\n")
        assert result.get("status") == "success"
        content = Path(path).read_text(encoding="utf-8")
        assert "first line" in content
        assert "second line" in content

    def test_append_creates_file(self, mock_cfg):
        path = str(mock_cfg.workspace_root / "new_append.txt")

        result = file(action="append_file", path=path, content="new content\n")
        assert result.get("status") == "success"
        assert Path(path).read_text(encoding="utf-8") == "new content\n"

    def test_append_empty_content(self, mock_cfg):
        path = mock_cfg.workspace_root / "append.txt"
        path.write_text("existing", encoding="utf-8")

        result = file(action="append_file", path=str(path), content="")
        assert result.get("status") == "success"
        assert Path(path).read_text(encoding="utf-8") == "existing"
