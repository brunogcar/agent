"""Tests for notify facade dispatch and registry.

Mirrors tests/tools/consult/test_dispatch.py. Covers:
  - All 8 actions present in DISPATCH with full metadata
  - Unknown action → error listing valid actions
  - Empty action → error explaining action is required
  - Case insensitivity (SEND / Send / send all dispatch the same handler)
  - duration_ms set by facade (always present on success path)
  - Handler exception caught + wrapped in error response
  - trace_id threaded through dispatch-level errors
  - @meta_tool Literal[...] generation verified
"""
from __future__ import annotations

from typing import get_args, get_type_hints
from unittest.mock import MagicMock, patch

from tools.notify import notify
from tools.notify_ops._registry import DISPATCH


EXPECTED_ACTIONS = {
    "send", "schedule", "cancel", "list",
    "recurring", "modify", "history", "test",
}


class TestDispatch:
    """Dispatcher routes actions and handles unknown/empty actions."""

    def test_unknown_action(self, mock_cfg, mock_notify_send):
        """Unknown action should list valid actions."""
        result = notify(action="nonexistent")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]
        for action in EXPECTED_ACTIONS:
            assert action in result["error"]

    def test_empty_action(self, mock_cfg, mock_notify_send):
        """Empty action should return clear 'action is required' error."""
        result = notify(action="")
        assert result["status"] == "error"
        assert "action is required" in result["error"].lower()

    def test_action_case_insensitive(self, mock_cfg, mock_notify_send):
        """Action should be case-insensitive (uppercase/lowercase both dispatch)."""
        # Uppercase
        result_upper = notify(action="SEND", message="hi")
        assert result_upper["status"] == "success"
        assert result_upper["data"]["action"] == "send"

        # Mixed case
        result_mixed = notify(action="Send", message="hi")
        assert result_mixed["status"] == "success"
        assert result_mixed["data"]["action"] == "send"

    def test_duration_ms_always_present_on_success(self, mock_cfg, mock_notify_send):
        """duration_ms should be present on every handler-returned result."""
        result = notify(action="send", message="hi")
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], (int, float))
        assert result["duration_ms"] >= 0

    def test_duration_ms_present_on_handler_error(self, mock_cfg, mock_notify_send):
        """duration_ms should be present even when the handler returns an error.

        The facade adds duration_ms after the handler returns, so any
        dict-returning handler (success OR error) gets it.
        """
        result = notify(action="send", message="")
        assert result["status"] == "error"
        assert "duration_ms" in result

    def test_handler_exception_caught(self, mock_cfg, mock_notify_send):
        """If the handler raises, the facade should return a graceful error."""
        # Patch helpers._send_notification because action handlers reference
        # it via `helpers._send_notification(...)` (module-level lookup at
        # runtime), not via direct import. Patching the module attribute is
        # the canonical way to intercept helper calls.
        with patch("tools.notify_ops.helpers._send_notification",
                   side_effect=RuntimeError("boom")):
            result = notify(action="send", message="hi")
        assert result["status"] == "error"
        assert "Notify action failed" in result["error"]
        assert "boom" in result["error"]

    def test_trace_id_threaded_through_dispatch_errors(self, mock_cfg, mock_notify_send):
        """trace_id should be present in error responses from dispatch layer."""
        result = notify(action="nonexistent", trace_id="trace-dispatch-1")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-dispatch-1"

        result = notify(action="", trace_id="trace-dispatch-2")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-dispatch-2"


class TestRegistry:
    """Verify all 8 notify actions are registered in DISPATCH."""

    def test_dispatch_has_8_actions(self):
        actions = DISPATCH.get("notify", {})
        assert len(actions) == 8, f"Expected 8 actions, got {len(actions)}: {list(actions.keys())}"
        assert set(actions.keys()) == EXPECTED_ACTIONS

    def test_all_actions_have_metadata(self):
        for name, info in DISPATCH["notify"].items():
            assert "func" in info, f"{name} missing func"
            assert "help" in info, f"{name} missing help"
            assert "examples" in info, f"{name} missing examples"
            assert callable(info["func"]), f"{name} func not callable"
            assert isinstance(info["help"], str) and info["help"], f"{name} help empty"
            assert isinstance(info["examples"], list) and info["examples"], f"{name} examples empty"

    def test_action_names_match_pattern(self):
        """All action names must match ^[a-z][a-z0-9_]*$ (validated by @meta_tool)."""
        import re
        pattern = re.compile(r"^[a-z][a-z0-9_]*$")
        for name in DISPATCH["notify"]:
            assert pattern.match(name), f"{name!r} does not match required pattern"

    def test_facade_action_literal_generated(self):
        """The @meta_tool decorator should have replaced `action: str` with a Literal."""
        hints = get_type_hints(notify)
        action_hint = hints.get("action")
        args = set(get_args(action_hint))
        assert args == EXPECTED_ACTIONS, f"Got: {args}"

    def test_facade_docstring_has_action_list(self):
        """The @meta_tool decorator should have generated a docstring with action list."""
        assert notify.__doc__ is not None
        doc = notify.__doc__
        for action in EXPECTED_ACTIONS:
            assert action in doc, f"{action} not in docstring"
        assert "notify meta-tool" in doc.lower()


class TestFacadeSignature:
    """Verify the facade exposes the expected parameters (for FastMCP schema)."""

    def test_facade_has_required_params(self):
        """Facade should expose action, title, message, timeout, delay_minutes,
        job_id, cron, trace_id."""
        hints = get_type_hints(notify)
        expected_params = {
            "action", "title", "message", "timeout",
            "delay_minutes", "job_id", "cron", "trace_id",
        }
        # Subtract the return type hint if present.
        param_hints = {k for k in hints.keys() if k != "return"}
        for p in expected_params:
            assert p in param_hints, f"facade missing param: {p}"

    def test_facade_cron_param_is_str(self):
        """cron should be typed as str (not Literal — it's free-form)."""
        hints = get_type_hints(notify)
        assert hints.get("cron") is str

    def test_facade_trace_id_param_is_str(self):
        """trace_id should be typed as str."""
        hints = get_type_hints(notify)
        assert hints.get("trace_id") is str
