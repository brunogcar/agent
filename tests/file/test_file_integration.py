"""Integration tests for file tool dispatch."""

from unittest.mock import patch
from tools.file import file

class TestFileDispatch:
    def test_read_dispatch(self):
        # Test that dispatch correctly routes to read action
        result = file(action="read", path="tools/file.py")
        assert result.get("status") == "success"
        assert "content" in result

    def test_unknown_action(self):
        result = file(action="nonexistent_action")
        assert result.get("status") == "error"
        assert "Unknown file action" in result.get("error", "")