"""Test list_directory action."""

from __future__ import annotations

import pytest
from tools.file import file


class TestListDirectory:
    def test_list_directory(self, sample_dir):
        result = file(action="list_directory", path=sample_dir)
        assert result.get("status") == "success"
        entries = result.get("entries", [])
        names = [e["name"] for e in entries]
        assert "a.txt" in names
        assert "b.txt" in names
        assert "subdir" in names

    def test_list_directory_not_found(self, mock_cfg):
        result = file(action="list_directory", path="nonexistent_dir_12345")
        assert result.get("status") == "error"

    def test_list_directory_file(self, sample_txt):
        result = file(action="list_directory", path=sample_txt)
        assert result.get("status") == "error"
