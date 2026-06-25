"""Test exists action."""

from __future__ import annotations

import pytest
from tools.file import file


class TestExists:
    def test_exists_file(self, sample_txt):
        result = file(action="exists", path=sample_txt)
        assert result.get("status") == "success"
        assert result.get("exists") is True
        assert result.get("type") == "file"

    def test_exists_directory(self, sample_dir):
        result = file(action="exists", path=sample_dir)
        assert result.get("status") == "success"
        assert result.get("exists") is True
        assert result.get("type") == "directory"

    def test_exists_not_found(self, mock_cfg):
        result = file(action="exists", path="nonexistent_12345.txt")
        # exists action should return exists=False, not error
        assert result.get("status") == "success"
        assert result.get("exists") is False
