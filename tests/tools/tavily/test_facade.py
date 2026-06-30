"""Tavily tests — @meta_tool facade."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tools.tavily import tavily
from tools.tavily_ops._registry import DISPATCH


class TestFacade:
    """Test the tavily facade dispatch and metadata."""

    def test_unknown_action(self, mock_tavily_client):
        result = tavily(action="nonexistent")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]
        assert "search" in result["error"]

    def test_action_trimmed_and_lowered(self, mock_tavily_client):
        result = tavily(action="  SEARCH  ", query="test")
        assert result["status"] == "success"

    def test_trace_id_passed_to_fail(self, mock_tavily_client):
        result = tavily(action="search", trace_id="tid-abc")
        assert result.get("trace_id") == "tid-abc"

    def test_facade_has_tool_metadata(self):
        from tools.tavily import tavily as tavily_fn
        assert hasattr(tavily_fn, "__tool_metadata__")
        assert "actions" in tavily_fn.__tool_metadata__
        assert "search" in tavily_fn.__tool_metadata__["actions"]

    def test_facade_action_literal(self):
        from tools.tavily import tavily as tavily_fn
        from typing import get_type_hints
        hints = get_type_hints(tavily_fn)
        action_hint = hints.get("action")
        assert action_hint is not None
        # Should be a Literal, not plain str
        assert hasattr(action_hint, "__args__")
        assert "search" in action_hint.__args__
