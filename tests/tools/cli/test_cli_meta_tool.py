"""Tests for @meta_tool integration on cli() facade.

Verifies docstring generation, __tool_metadata__, and the full 4-layer
dispatch flow (pattern match → shell → router → executor).
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

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


class TestCliIntegration:
    """Integration tests for the full 4-layer cli() dispatch flow (P1 #4).

    Each test mocks one layer's downstream call to verify that layer fires
    and downstream layers are NOT invoked.
    """

    def test_cli_integration_pattern_match(self, mock_cfg):
        """Pattern match layer should fire and dispatch to git:status."""
        # 'git status' matches the ^git\s+status$ pattern → git:status
        with patch("tools.cli._safe_dispatch", return_value="clean tree") as mock_dispatch, \
             patch("tools.cli._shell_exec") as mock_shell, \
             patch("tools.cli._call_router") as mock_router:
            result = cli("git status", trace_id="t1")

            # Pattern layer fired: _safe_dispatch was called with git:status
            mock_dispatch.assert_called_once()
            args, _ = mock_dispatch.call_args
            assert args[0] == "git"
            assert args[1] == "status"
            # trace_id should be propagated into params
            assert args[2].get("trace_id") == "t1"

            # Downstream layers should NOT have been called
            mock_shell.assert_not_called()
            mock_router.assert_not_called()

            # Result should wrap the dispatched output
            assert result["status"] == "success"
            assert result["output"] == "clean tree"
            assert result["trace_id"] == "t1"

    def test_cli_integration_shell_fallback(self, mock_cfg):
        """Shell layer should fire when no pattern matches but command is whitelisted.

        'whoami' is in ALLOWED_COMMANDS and matches no pattern, so it falls
        through to the shell layer.
        """
        with patch("tools.cli._shell_exec", return_value="agent-user") as mock_shell, \
             patch("tools.cli._safe_dispatch") as mock_dispatch, \
             patch("tools.cli._call_router") as mock_router:
            result = cli("whoami", trace_id="t2")

            # Shell layer fired: _shell_exec called with the command
            mock_shell.assert_called_once_with("whoami")

            # Downstream layers should NOT have been called (shell succeeded)
            mock_dispatch.assert_not_called()
            mock_router.assert_not_called()

            assert result["status"] == "success"
            assert result["output"] == "agent-user"

    def test_cli_integration_router_fallback(self, mock_cfg):
        """Router layer should fire when shell fails and router returns dispatch.

        'do something weird' matches no pattern. The shell layer rejects it
        (because 'do' is not in the allowlist), so the router layer fires.
        The router returns a dispatch route, which _safe_dispatch executes.
        """
        router_response = {
            "route": "dispatch",
            "tool_name": "system",
            "action": "health",
            "params": {},
        }
        with patch("tools.cli._shell_exec", return_value="Shell error: Command 'do' is not in the allowlist.") as mock_shell, \
             patch("tools.cli._call_router", return_value=router_response) as mock_router, \
             patch("tools.cli._safe_dispatch", return_value="all systems operational") as mock_dispatch:
            result = cli("do something weird", trace_id="t3")

            # Shell layer fired but failed (returned Shell error)
            mock_shell.assert_called_once_with("do something weird")

            # Router layer fired and returned a dispatch route
            mock_router.assert_called_once_with("do something weird")

            # _safe_dispatch was called with the router's tool/action
            mock_dispatch.assert_called_once()
            args, _ = mock_dispatch.call_args
            assert args[0] == "system"
            assert args[1] == "health"
            assert args[2].get("trace_id") == "t3"

            assert result["status"] == "success"
            assert result["output"] == "all systems operational"

    def test_cli_integration_router_escalate(self, mock_cfg):
        """When router returns 'escalate', cli should hand off to Executor."""
        router_response = {
            "route": "escalate",
            "reason": "complex multi-step task",
        }
        with patch("tools.cli._shell_exec", return_value="Shell error: not allowed"), \
             patch("tools.cli._call_router", return_value=router_response) as mock_router, \
             patch("tools.cli._safe_dispatch") as mock_dispatch:
            result = cli("do something weird", trace_id="t4")

            # Router fired but escalated; _safe_dispatch should NOT have been called
            mock_router.assert_called_once()
            mock_dispatch.assert_not_called()

            # Output should mention escalation
            assert result["status"] == "success"
            assert "Escalated to Executor" in result["output"]
            assert "complex multi-step task" in result["output"]
