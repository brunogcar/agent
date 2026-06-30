"""Tavily tests — DISPATCH registry."""
from __future__ import annotations

import pytest

from tools.tavily_ops._registry import register_action, DISPATCH


class TestRegistry:
    """Test action registration and auto-discovery."""

    def test_duplicate_action_raises(self):
        @register_action("__test_tool__", "dup_action", help_text="first")
        def first(): pass

        with pytest.raises(ValueError, match="Duplicate action"):
            @register_action("__test_tool__", "dup_action", help_text="second")
            def second(): pass

        # Cleanup
        del DISPATCH["__test_tool__"]

    def test_research_not_in_dispatch(self):
        """Regression guard: research must NOT be auto-registered."""
        assert "research" not in DISPATCH.get("tavily", {})

    def test_search_in_dispatch(self):
        assert "search" in DISPATCH.get("tavily", {})

    def test_extract_in_dispatch(self):
        assert "extract" in DISPATCH.get("tavily", {})

    def test_crawl_in_dispatch(self):
        assert "crawl" in DISPATCH.get("tavily", {})

    def test_map_in_dispatch(self):
        assert "map" in DISPATCH.get("tavily", {})
