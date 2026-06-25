"""Test edit_file action."""

from __future__ import annotations

import pytest
from pathlib import Path
from tools.file import file


class TestEditFile:
    def test_edit_file_single(self, sample_txt):
        result = file(
            action="edit_file",
            path=sample_txt,
            edits=[{"oldText": "Hello World", "newText": "Hello Edited"}],
        )
        assert result.get("status") == "success"
        assert result.get("lines_changed") == 1
        content = Path(sample_txt).read_text(encoding="utf-8")
        assert "Hello Edited" in content
        # No .bak should be created
        assert not list(Path(sample_txt).parent.glob("*.bak"))

    def test_edit_file_dry_run(self, sample_txt):
        result = file(
            action="edit_file",
            path=sample_txt,
            edits=[{"oldText": "Hello World", "newText": "Hello Edited"}],
            dry_run=True,
        )
        assert result.get("status") == "success"
        assert result.get("dry_run") is True
        content = Path(sample_txt).read_text(encoding="utf-8")
        assert "Hello World" in content  # Not actually changed

    def test_edit_file_not_found(self, mock_cfg):
        result = file(
            action="edit_file",
            path="nonexistent_12345.txt",
            edits=[{"oldText": "a", "newText": "b"}],
        )
        assert result.get("status") == "error"
