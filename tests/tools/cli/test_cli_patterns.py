"""Tests for CLI pattern matching (Layer 1)."""
from __future__ import annotations

import pytest
from tools.cli_ops.patterns import _match_pattern


class TestPatternMatching:
    """Unit tests for _match_pattern."""

    def test_git_status(self):
        """'git status' should match to git:status."""
        result = _match_pattern("git status")
        assert result is not None
        tool, action, params = result
        assert tool == "git"
        assert action == "status"

    def test_git_log_with_number(self):
        """'git log 5' should match to git:log with n=5."""
        result = _match_pattern("git log 5")
        assert result is not None
        tool, action, params = result
        assert tool == "git"
        assert action == "log"
        assert params == {"n": 5}

    def test_read_file(self):
        """'read file.py' should match to file:read_file."""
        result = _match_pattern("read file.py")
        assert result is not None
        tool, action, params = result
        assert tool == "file"
        assert action == "read_file"
        assert params == {"path": "file.py"}

    def test_list_directory(self):
        """'ls tools/' should match to file:list_directory."""
        result = _match_pattern("ls tools/")
        assert result is not None
        tool, action, params = result
        assert tool == "file"
        assert action == "list_directory"
        assert params == {"path": "tools/"}

    def test_search_files(self):
        """'grep import os' should match to file:search_files."""
        result = _match_pattern("grep import os")
        assert result is not None
        tool, action, params = result
        assert tool == "file"
        assert action == "search_files"
        assert params == {"query": "import os"}

    def test_web_search(self):
        """'search python' should match to web:search."""
        result = _match_pattern("search python")
        assert result is not None
        tool, action, params = result
        assert tool == "web"
        assert action == "search"
        assert params == {"query": "python"}

    def test_web_read_url(self):
        """'read https://example.com' should match to web:read."""
        result = _match_pattern("read https://example.com")
        assert result is not None
        tool, action, params = result
        assert tool == "web"
        assert action == "read"
        assert params == {"url": "https://example.com"}

    def test_health(self):
        """'health' should match to system:health."""
        result = _match_pattern("health")
        assert result is not None
        tool, action, params = result
        assert tool == "system"
        assert action == "health"

    def test_help(self):
        """'help' should match to system:help."""
        result = _match_pattern("help")
        assert result is not None
        tool, action, params = result
        assert tool == "system"
        assert action == "help"

    def test_no_match(self):
        """Unknown command should return None."""
        result = _match_pattern("some random gibberish")
        assert result is None
