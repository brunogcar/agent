"""Tests for the @meta_tool decorator.

Covers: empty dispatch, invalid action names, Literal generation,
__tool_metadata__, docstring generation, and FastMCP compatibility.
"""
from __future__ import annotations

import pytest
from typing import get_args

from tools._meta_tool import meta_tool


class TestMetaToolValidation:
    """Input validation: empty dispatch, invalid names, etc."""

    def test_empty_dispatch_raises(self):
        """Empty dispatch should raise ValueError with clear message."""
        with pytest.raises(ValueError, match="empty dispatch"):
            @meta_tool({})
            def dummy_tool(action: str = "") -> dict:
                pass

    def test_invalid_action_name_hyphen(self):
        """Hyphens in action names should raise ValueError."""
        dispatch = {"foo-bar": {"help": "h", "func": lambda: None, "needs_repo": False, "examples": []}}
        with pytest.raises(ValueError, match="Invalid action name"):
            @meta_tool(dispatch)
            def dummy_tool(action: str = "") -> dict:
                pass

    def test_invalid_action_name_uppercase(self):
        """Uppercase in action names should raise ValueError."""
        dispatch = {"FooBar": {"help": "h", "func": lambda: None, "needs_repo": False, "examples": []}}
        with pytest.raises(ValueError, match="Invalid action name"):
            @meta_tool(dispatch)
            def dummy_tool(action: str = "") -> dict:
                pass

    def test_invalid_action_name_dunder(self):
        """Dunder names should raise ValueError."""
        dispatch = {"__import__": {"help": "h", "func": lambda: None, "needs_repo": False, "examples": []}}
        with pytest.raises(ValueError, match="Invalid action name"):
            @meta_tool(dispatch)
            def dummy_tool(action: str = "") -> dict:
                pass

    def test_keyword_action_name_allowed(self):
        """Python keywords are valid Literal values and should be allowed.

        Literal['and'] is valid Python. The regex allows it.
        This is intentional — keywords are not a security risk in Literal types.
        """
        dispatch = {"and": {"help": "h", "func": lambda: None, "needs_repo": False, "examples": []}}
        # Should NOT raise
        @meta_tool(dispatch)
        def dummy_tool(action: str = "") -> dict:
            pass
        assert "and" in dummy_tool.__tool_metadata__["actions"]


class TestMetaToolGeneration:
    """Output generation: Literal, docstring, metadata."""

    def test_literal_annotation_generated(self):
        """@meta_tool should replace action: str with action: Literal[...]."""
        dispatch = {
            "status": {"help": "h1", "func": lambda: None, "needs_repo": False, "examples": []},
            "commit": {"help": "h2", "func": lambda: None, "needs_repo": True, "examples": []},
        }

        @meta_tool(dispatch)
        def dummy_tool(action: str = "") -> dict:
            pass

        literal_type = dummy_tool.__annotations__["action"]
        args = get_args(literal_type)
        assert args == ("commit", "status")  # sorted

    def test_docstring_generated(self):
        """@meta_tool should generate a docstring with action list and help text."""
        dispatch = {
            "status": {"help": "Check status", "func": lambda: None, "needs_repo": False, "examples": ['dummy(action="status")']},
        }

        @meta_tool(dispatch)
        def dummy_tool(action: str = "") -> dict:
            pass

        assert "dummy_tool meta-tool" in dummy_tool.__doc__
        assert "status" in dummy_tool.__doc__
        assert "Check status" in dummy_tool.__doc__
        assert 'dummy(action="status")' in dummy_tool.__doc__

    def test_tool_metadata_generated(self):
        """@meta_tool should populate __tool_metadata__ with actions and dispatch info."""
        dispatch = {
            "status": {"help": "h", "func": lambda: None, "needs_repo": False, "examples": []},
        }

        @meta_tool(dispatch)
        def dummy_tool(action: str = "") -> dict:
            pass

        meta = dummy_tool.__tool_metadata__
        assert meta["actions"] == ["status"]
        assert meta["dispatch"]["status"]["help"] == "h"
        assert meta["dispatch"]["status"]["needs_repo"] is False

    def test_doc_sections_appended(self):
        """doc_sections parameter should append tool-specific text to docstring."""
        dispatch = {
            "status": {"help": "h", "func": lambda: None, "needs_repo": False, "examples": []},
        }

        @meta_tool(dispatch, doc_sections=["Custom note:", "  Do not use in production."])
        def dummy_tool(action: str = "") -> dict:
            pass

        assert "Custom note:" in dummy_tool.__doc__
        assert "Do not use in production." in dummy_tool.__doc__

    def test_signature_cache_cleared(self):
        """del fn.__signature__ should force re-derivation from new annotations."""
        dispatch = {
            "status": {"help": "h", "func": lambda: None, "needs_repo": False, "examples": []},
        }

        def dummy_tool(action: str = "") -> dict:
            pass

        # Pre-inspect to populate cache
        import inspect
        sig_before = inspect.signature(dummy_tool)
        # With from __future__ import annotations, annotation is stored as string
        assert sig_before.parameters["action"].annotation == "str"

        # Apply decorator
        decorated = meta_tool(dispatch)(dummy_tool)

        # Post-inspect should show Literal, not str string
        sig_after = inspect.signature(decorated)
        assert sig_after.parameters["action"].annotation != "str"


class TestMetaToolFastMCP:
    """FastMCP compatibility: verify schema generation works."""

    @pytest.mark.asyncio
    async def test_fastmcp_schema_enum(self):
        """FastMCP should see the Literal enum in JSON schema.

        This is a regression guard: if @meta_tool breaks, FastMCP won't
        generate the enum in the tool schema, and the LLM will see
        action: str instead of action: Literal[...].

        NOTE: FastMCP's Tool object structure varies by version.
        We verify registration succeeded and the tool name is correct.
        Schema introspection is version-dependent and skipped if structure changes.
        """
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        dispatch = {
            "status": {"help": "h", "func": lambda: None, "needs_repo": False, "examples": []},
            "commit": {"help": "h", "func": lambda: None, "needs_repo": True, "examples": []},
        }

        @meta_tool(dispatch)
        def test_tool(action: str = "") -> dict:
            """Test tool."""
            return {}

        mcp.tool()(test_tool)

        # list_tools() is async in FastMCP
        tools = await mcp.list_tools()

        # Find our tool by name
        tool_names = [t.name for t in tools if hasattr(t, "name")]
        assert "test_tool" in tool_names, f"test_tool not registered. Found: {tool_names}"

        # Try to verify enum in schema — FastMCP version-dependent
        tool_entry = None
        for t in tools:
            if getattr(t, "name", None) == "test_tool":
                tool_entry = t
                break

        if tool_entry is None:
            pytest.skip("Could not find test_tool in registry")

        # Schema access varies by FastMCP version — try common paths
        schema = None
        if hasattr(tool_entry, "inputSchema"):
            schema = tool_entry.inputSchema
        elif hasattr(tool_entry, "input_schema"):
            schema = tool_entry.input_schema
        elif hasattr(tool_entry, "model_json_schema"):
            schema = tool_entry.model_json_schema()

        if schema is None:
            pytest.skip("FastMCP Tool schema access changed — manual review needed")

        # Verify enum contains our actions
        action_schema = schema.get("properties", {}).get("action", {})
        enum_values = action_schema.get("enum", [])

        assert "status" in enum_values, f"status not in enum: {enum_values}"
        assert "commit" in enum_values, f"commit not in enum: {enum_values}"
