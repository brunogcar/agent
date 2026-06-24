"""Test file tool dispatch and unknown actions."""

from __future__ import annotations

import pytest
from tools.file import file


class TestFileDispatch:
    def test_unknown_action(self):
        result = file(action="nonexistent_action")
        assert result.get("status") == "error"
        assert "Unknown action" in result.get("error", "")

    def test_empty_action(self):
        result = file(action="")
        assert result.get("status") == "error"
        assert "action parameter is required" in result.get("error", "")

    def test_list_allowed_directories(self):
        result = file(action="list_allowed_directories")
        assert result.get("status") == "success"
        assert "roots" in result
