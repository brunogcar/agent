"""tests/core/memory_backend/test_pruner.py — additional coverage for missing cases."""
import pytest
from core.memory_backend.pruner import prune_text, prune_tool_dict

class TestPruneTextPythonExec:
    """Pruner handling for python_exec tool string output."""

    def test_python_exec_long_truncated(self):
        """Long python_exec output is silently truncated to max_context_length."""
        long_text = "a" * 5000
        result = prune_text("python_exec", long_text)
        assert len(result) <= 8000

    def test_python_exec_short_preserved(self):
        """Short python_exec output is preserved unchanged."""
        short = "print(1)"
        result = prune_text("python_exec", short)
        assert result == "print(1)"

class TestPruneToolDictLegacy:
    """Pruner handling for flat (legacy) dict structures."""

    def test_flat_dict_preserved(self):
        """Flat dict with short values is preserved."""
        data = {"url": "http://example.com", "title": "Example", "text": "content"}
        result = prune_tool_dict("web", data)
        assert result["url"] == "http://example.com"
        assert result["text"] == "content"

    def test_flat_dict_long_truncated(self):
        """Flat dict with long text is silently truncated."""
        data = {"url": "http://x", "title": "T", "text": "a" * 5000}
        result = prune_tool_dict("web", data)
        assert len(result["text"]) <= 8000

class TestPruneToolDictNested:
    """Pruner handling for nested ok()/fail() schema dicts."""

    def test_ok_schema_preserved(self):
        """Nested ok schema with short values is preserved."""
        data = {"status": "success", "data": {"text": "hello", "url": "http://x"}}
        result = prune_tool_dict("web", data)
        assert result["status"] == "success"
        assert result["data"]["text"] == "hello"

    def test_ok_schema_long_truncated(self):
        """Nested ok schema with long text is silently truncated."""
        data = {"status": "success", "data": {"text": "a" * 5000, "url": "http://x"}}
        result = prune_tool_dict("web", data)
        assert len(result["data"]["text"]) <= 8000

    def test_fail_schema_preserved(self):
        """Nested fail schema with short values is preserved."""
        data = {"status": "error", "error": "not found", "data": {}}
        result = prune_tool_dict("web", data)
        assert result["status"] == "error"
        assert result["error"] == "not found"

    def test_fail_schema_long_truncated(self):
        """Nested fail schema with long error is silently truncated."""
        data = {"status": "error", "error": "a" * 5000, "data": {}}
        result = prune_tool_dict("web", data)
        assert len(result["error"]) <= 8000
