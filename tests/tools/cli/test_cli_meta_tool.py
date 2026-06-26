"""Tests for @meta_tool integration on cli() facade.

Verifies docstring generation and __tool_metadata__.
"""
from __future__ import annotations

from tools.cli import cli


class TestMetaTool:
    """Verify @meta_tool decorator applied correctly."""

    def test_cli_has_tool_metadata(self):
        """cli() should have __tool_metadata__ from @meta_tool."""
        assert hasattr(cli, "__tool_metadata__")

    def test_cli_docstring_contains_actions(self):
        """Auto-generated docstring should list available actions."""
        assert cli.__doc__ is not None
        assert "health" in cli.__doc__.lower()
        assert "help" in cli.__doc__.lower()

    def test_cli_docstring_contains_architecture(self):
        """Docstring should mention 4-layer architecture."""
        assert "4-Layer" in cli.__doc__ or "layer" in cli.__doc__.lower()

    def test_cli_docstring_contains_security(self):
        """Docstring should mention security controls."""
        assert "Security" in cli.__doc__

    def test_cli_no_action_literal_annotation(self):
        """cli() should NOT have action: Literal[...] — it takes command: str."""
        annotations = cli.__annotations__
        assert "action" not in annotations
        assert "command" in annotations
        assert annotations["command"] == "str"
