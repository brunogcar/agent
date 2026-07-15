"""Tests for consult facade dispatch and registry.

Mirrors the structure of tests/tools/swarm/test_dispatch.py. Covers:
  - Unknown action → error listing valid actions
  - Empty action → error explaining action is required
  - Case insensitivity (ADVISE / Advise / advise all dispatch the same handler)
  - All 3 actions present in DISPATCH with full metadata
"""
from __future__ import annotations

from tools.consult import consult


class TestDispatch:
    """Dispatcher routes actions and handles unknown/empty actions."""

    def test_unknown_action(self):
        """Unknown action should list valid actions."""
        result = consult(action="nonexistent")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]
        assert "advise" in result["error"]
        assert "review" in result["error"]
        assert "explain" in result["error"]

    def test_empty_action(self):
        """Empty action should return clear 'action is required' error."""
        result = consult(action="")
        assert result["status"] == "error"
        assert "action is required" in result["error"].lower()

    def test_action_case_insensitive(self, mock_cfg, mock_llm, mock_budget):
        """Action should be case-insensitive (uppercase/lowercase both dispatch)."""
        # Set up a successful response so we can verify the action actually runs.
        from tests.tools.consult.conftest import make_mock_response
        mock_llm.complete.return_value = make_mock_response(text="OK")

        # Uppercase
        result_upper = consult(action="ADVISE", question="Test?")
        assert result_upper["status"] == "success"
        assert result_upper["action"] == "advise"

        # Mixed case
        result_mixed = consult(action="Advise", question="Test?")
        assert result_mixed["status"] == "success"
        assert result_mixed["action"] == "advise"

    def test_duration_ms_always_present(self, mock_cfg, mock_llm, mock_budget):
        """duration_ms should be present on every handler-returned result."""
        from tests.tools.consult.conftest import make_mock_response
        mock_llm.complete.return_value = make_mock_response(text="OK")
        result = consult(action="advise", question="Test?")
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], (int, float))
        assert result["duration_ms"] >= 0

    def test_handler_exception_caught(self, mock_cfg, mock_llm, mock_budget):
        """If the handler raises, the facade should return a graceful error."""
        mock_llm.complete.side_effect = RuntimeError("boom")
        result = consult(action="advise", question="Test?")
        assert result["status"] == "error"
        assert "Consult action failed" in result["error"]
        assert "boom" in result["error"]

    def test_trace_id_threaded_through_dispatch(self):
        """trace_id should be present in error responses from dispatch layer."""
        result = consult(action="nonexistent", trace_id="trace-dispatch-1")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-dispatch-1"

        result = consult(action="", trace_id="trace-dispatch-2")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-dispatch-2"


class TestRegistry:
    """Verify all 3 consult actions are registered in DISPATCH."""

    def test_dispatch_has_3_actions(self):
        from tools.consult_ops._registry import DISPATCH
        actions = DISPATCH.get("consult", {})
        assert len(actions) == 3
        expected = {"advise", "review", "explain"}
        assert set(actions.keys()) == expected

    def test_all_actions_have_metadata(self):
        from tools.consult_ops._registry import DISPATCH
        for name, info in DISPATCH["consult"].items():
            assert "func" in info, f"{name} missing func"
            assert "help" in info, f"{name} missing help"
            assert "examples" in info, f"{name} missing examples"
            assert callable(info["func"]), f"{name} func not callable"
            assert isinstance(info["help"], str) and info["help"], f"{name} help empty"
            assert isinstance(info["examples"], list) and info["examples"], f"{name} examples empty"

    def test_action_names_match_pattern(self):
        """All action names must match ^[a-z][a-z0-9_]*$ (validated by @meta_tool)."""
        import re
        from tools.consult_ops._registry import DISPATCH
        pattern = re.compile(r"^[a-z][a-z0-9_]*$")
        for name in DISPATCH["consult"]:
            assert pattern.match(name), f"{name!r} does not match required pattern"

    def test_facade_action_literal_generated(self):
        """The @meta_tool decorator should have replaced `action: str` with a Literal."""
        from typing import get_args, get_type_hints
        from tools.consult import consult as consult_fn
        hints = get_type_hints(consult_fn)
        action_hint = hints.get("action")
        # Literal[...] args should be exactly {"advise", "review", "explain"} (sorted).
        args = set(get_args(action_hint))
        assert args == {"advise", "review", "explain"}, f"Got: {args}"

    def test_facade_docstring_has_action_list(self):
        """The @meta_tool decorator should have generated a docstring with action list."""
        from tools.consult import consult as consult_fn
        assert consult_fn.__doc__ is not None
        doc = consult_fn.__doc__
        assert "advise" in doc
        assert "review" in doc
        assert "explain" in doc
        assert "consult meta-tool" in doc.lower()
