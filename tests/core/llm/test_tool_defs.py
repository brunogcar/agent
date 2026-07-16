"""Tests for core/llm_backend/tools.py — ToolDefinition + provider converters.

Covers:
  1. tool_def_from_meta_tool() — generates correct ToolDefinition from @meta_tool
  2. Action filtering (allowed_actions parameter)
  3. Provider converters (to_openai_tools, to_anthropic_tools, to_gemini_tools)
  4. tool_def_from_registry() — multi-tool generation from registry
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.llm_backend.tools import (
    ToolDefinition,
    tool_def_from_meta_tool,
    tool_def_from_registry,
    to_openai_tools,
    to_anthropic_tools,
    to_gemini_tools,
)


# ── Test fixtures ────────────────────────────────────────────────────────────

def _mock_meta_tool(name="file", actions=None):
    """Build a mock @meta_tool-decorated function with __tool_metadata__."""
    actions = actions or ["read_file", "write_file", "list_directory"]
    fn = MagicMock()
    fn.__tool_metadata__ = {
        "actions": actions,
        "dispatch": {
            a: {"help": f"{a} action help text", "examples": [], "needs_repo": False}
            for a in actions
        },
    }
    return fn


# ── tool_def_from_meta_tool ──────────────────────────────────────────────────

class TestToolDefFromMetaTool:
    def test_generates_definition_with_correct_name(self):
        fn = _mock_meta_tool("web")
        td = tool_def_from_meta_tool("web", fn)
        assert td.name == "web"

    def test_description_includes_action_list(self):
        fn = _mock_meta_tool("file", ["read_file", "write_file"])
        td = tool_def_from_meta_tool("file", fn)
        assert "read_file" in td.description
        assert "write_file" in td.description

    def test_description_includes_help_text(self):
        fn = _mock_meta_tool("file", ["read_file"])
        td = tool_def_from_meta_tool("file", fn)
        assert "read_file action help text" in td.description

    def test_parameters_has_action_enum(self):
        fn = _mock_meta_tool("file", ["read_file", "write_file"])
        td = tool_def_from_meta_tool("file", fn)
        assert td.parameters["type"] == "object"
        action_prop = td.parameters["properties"]["action"]
        assert action_prop["type"] == "string"
        assert action_prop["enum"] == ["read_file", "write_file"]

    def test_parameters_requires_action(self):
        fn = _mock_meta_tool()
        td = tool_def_from_meta_tool("file", fn)
        assert "action" in td.parameters["required"]

    def test_allowed_actions_filters_enum(self):
        fn = _mock_meta_tool("file", ["read_file", "write_file", "delete_file"])
        td = tool_def_from_meta_tool("file", fn, allowed_actions=frozenset({"read_file"}))
        assert td.parameters["properties"]["action"]["enum"] == ["read_file"]
        assert "write_file" not in td.description
        assert "delete_file" not in td.description

    def test_returns_none_for_non_meta_tool(self):
        fn = MagicMock()
        # No __tool_metadata__ attribute
        if hasattr(fn, "__tool_metadata__"):
            del fn.__tool_metadata__
        td = tool_def_from_meta_tool("file", fn)
        assert td is None


# ── Provider converters ──────────────────────────────────────────────────────

class TestProviderConverters:
    def _make_defs(self):
        return [
            ToolDefinition(
                name="file",
                description="File tool",
                parameters={"type": "object", "properties": {"action": {"type": "string"}}},
            ),
            ToolDefinition(
                name="web",
                description="Web tool",
                parameters={"type": "object", "properties": {"action": {"type": "string"}}},
            ),
        ]

    def test_to_openai_tools_format(self):
        defs = self._make_defs()
        result = to_openai_tools(defs)
        assert len(result) == 2
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "file"
        assert result[0]["function"]["description"] == "File tool"
        assert "parameters" in result[0]["function"]

    def test_to_anthropic_tools_format(self):
        defs = self._make_defs()
        result = to_anthropic_tools(defs)
        assert len(result) == 2
        assert result[0]["name"] == "file"
        assert result[0]["description"] == "File tool"
        assert "input_schema" in result[0]
        assert "parameters" not in result[0]  # Anthropic uses input_schema, not parameters

    def test_to_gemini_tools_format(self):
        defs = self._make_defs()
        result = to_gemini_tools(defs)
        # Gemini wraps in functionDeclarations
        assert len(result) == 1
        assert "functionDeclarations" in result[0]
        decls = result[0]["functionDeclarations"]
        assert len(decls) == 2
        assert decls[0]["name"] == "file"
        assert decls[0]["description"] == "File tool"
        assert "parameters" in decls[0]

    def test_empty_defs_produce_empty_lists(self):
        assert to_openai_tools([]) == []
        assert to_anthropic_tools([]) == []
        assert to_gemini_tools([]) == []


# ── tool_def_from_registry ───────────────────────────────────────────────────

class TestToolDefFromRegistry:
    def test_generates_defs_from_registry(self):
        with patch("registry._registered_tool_fns", {
            "file": _mock_meta_tool("file", ["read_file"]),
            "web": _mock_meta_tool("web", ["search"]),
        }):
            defs = tool_def_from_registry(["file", "web"])
        assert len(defs) == 2
        assert defs[0].name == "file"
        assert defs[1].name == "web"

    def test_skips_unknown_tools(self):
        with patch("registry._registered_tool_fns", {
            "file": _mock_meta_tool("file", ["read_file"]),
        }):
            defs = tool_def_from_registry(["file", "nonexistent"])
        assert len(defs) == 1
        assert defs[0].name == "file"

    def test_allowed_actions_map_filters_per_tool(self):
        with patch("registry._registered_tool_fns", {
            "file": _mock_meta_tool("file", ["read_file", "write_file", "delete_file"]),
            "web": _mock_meta_tool("web", ["search", "scrape"]),
        }):
            defs = tool_def_from_registry(
                ["file", "web"],
                allowed_actions_map={
                    "file": frozenset({"read_file"}),
                    "web": frozenset({"search"}),
                },
            )
        assert defs[0].parameters["properties"]["action"]["enum"] == ["read_file"]
        assert defs[1].parameters["properties"]["action"]["enum"] == ["search"]

    def test_empty_tool_names_returns_empty(self):
        with patch("registry._registered_tool_fns", {}):
            defs = tool_def_from_registry([])
        assert defs == []


# Need patch import
from unittest.mock import patch
