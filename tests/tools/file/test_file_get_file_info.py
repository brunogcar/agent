"""Test get_file_info action."""

from __future__ import annotations

import pytest
from tools.file import file


class TestGetFileInfo:
    def test_get_file_info_file(self, sample_txt):
        result = file(action="get_file_info", path=sample_txt)
        assert result.get("status") == "success"
        assert result.get("type") == "file"
        assert result.get("size") > 0
        assert "mode" in result
        assert "modified" in result

    def test_get_file_info_directory(self, sample_dir):
        result = file(action="get_file_info", path=sample_dir)
        assert result.get("status") == "success"
        assert result.get("type") == "directory"

    def test_get_file_info_not_found(self, mock_cfg):
        result = file(action="get_file_info", path="nonexistent_12345.txt")
        assert result.get("status") == "error"
