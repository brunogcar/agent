"""Test read_file action."""

from __future__ import annotations

import pytest
from tools.file import file


class TestReadFile:
    def test_read_file_success(self, sample_txt):
        result = file(action="read_file", path=sample_txt)
        assert result.get("status") == "success"
        assert "Hello World" in result.get("content", "")
        assert result.get("lines") == 5

    def test_read_file_head(self, sample_txt):
        result = file(action="read_file", path=sample_txt, head=2)
        assert result.get("status") == "success"
        lines = result.get("content", "").splitlines()
        assert len(lines) == 2
        assert "Hello World" in lines[0]

    def test_read_file_tail(self, sample_txt):
        result = file(action="read_file", path=sample_txt, tail=2)
        assert result.get("status") == "success"
        lines = result.get("content", "").splitlines()
        assert len(lines) == 2
        assert "Line 5" in lines[-1]

    def test_read_file_not_found(self, mock_cfg):
        result = file(action="read_file", path="nonexistent_12345.txt")
        assert result.get("status") == "error"

    def test_read_file_max_chars(self, mock_cfg):
        path = mock_cfg.workspace_root / "big.txt"
        path.write_text("x" * 10000, encoding="utf-8")
        result = file(action="read_file", path=str(path), max_chars=100)
        assert result.get("status") == "success"
        assert result.get("truncated") is True
        assert len(result.get("content", "")) <= 150  # + truncation message
