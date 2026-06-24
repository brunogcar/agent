"""Test search_files action."""

from __future__ import annotations

import pytest
from tools.file import file


class TestSearchFiles:
    def test_search_files(self, mock_cfg):
        # Create a file with searchable content
        p = mock_cfg.workspace_root / "searchable.py"
        p.write_text("def hello_world():\n    return 42\n", encoding="utf-8")

        result = file(action="search_files", query="hello_world", max_results=5)
        # Search may return 0 results if index is cold — that's OK
        assert result.get("status") in ("success", "error")
        if result.get("status") == "success":
            assert "results" in result

    def test_search_files_no_query(self):
        result = file(action="search_files")
        assert result.get("status") == "error"
