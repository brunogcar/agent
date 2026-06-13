"""Tests for search node helpers."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from core.config import cfg
from workflows.deep_research_core.nodes.search import (
    _select_tool,
    _is_complex_query,
    _is_js_heavy,
)


def test_select_tool_tavily_when_complex_and_budget():
    state = {"budget_api_calls": 5}
    with patch.object(cfg, "tavily_api_key", "key"):
        assert _select_tool("compare A and B", state) == "tavily"


def test_select_tool_web_when_no_key():
    state = {"budget_api_calls": 5}
    with patch.object(cfg, "tavily_api_key", None):
        assert _select_tool("compare A and B", state) == "web"


def test_select_tool_web_when_budget_exhausted():
    state = {"budget_api_calls": 0}
    with patch.object(cfg, "tavily_api_key", "key"):
        assert _select_tool("compare A and B", state) == "web"


def test_is_complex_query():
    assert _is_complex_query("compare X and Y") is True
    assert _is_complex_query("simple query") is False


def test_is_js_heavy():
    assert _is_js_heavy("react dashboard") is True
    assert _is_js_heavy("python tutorial") is False
