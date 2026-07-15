"""Tests for python facade dispatch and registry.

Mirrors the structure of tests/tools/consult/test_dispatch.py. Covers:
  - Unknown action → error listing valid actions
  - Empty action → error explaining action is required
  - Case insensitivity (RUN / Run / run all dispatch the same handler)
  - All 5 actions present in DISPATCH with full metadata
  - Literal annotation auto-generated via @meta_tool
  - trace_id threading at the dispatch layer
  - Empty code rejection at the facade (before dispatch)
"""
from __future__ import annotations

import re

from tools.python import python


class TestDispatch:
    """Dispatcher routes actions and handles unknown/empty actions."""

    def test_unknown_action(self, mock_cfg, mock_pruner):
        """Unknown action should list valid actions."""
        result = python(action="nonexistent", code="print('x')")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]
        for expected in ("run", "run_data", "eval", "profile", "lint"):
            assert expected in result["error"]

    def test_empty_action(self, mock_cfg, mock_pruner):
        """Empty action should return clear 'action is required' error."""
        result = python(action="", code="print('x')")
        assert result["status"] == "error"
        assert "action is required" in result["error"].lower()

    def test_action_case_insensitive(self, mock_cfg, mock_pruner):
        """Action should be case-insensitive (RUN / Run / run all dispatch)."""
        # All three should dispatch the same handler — success means dispatch worked.
        r1 = python(action="RUN", code="print('hi')")
        r2 = python(action="Run", code="print('hi')")
        r3 = python(action="run", code="print('hi')")
        assert r1["status"] == "success"
        assert r2["status"] == "success"
        assert r3["status"] == "success"
        # All three should produce the same output
        assert r1["data"] == r2["data"] == r3["data"]

    def test_action_whitespace_stripped(self, mock_cfg, mock_pruner):
        """Leading/trailing whitespace in action should be stripped."""
        result = python(action="  run  ", code="print('hi')")
        assert result["status"] == "success"

    def test_facade_rejects_empty_code_before_dispatch(self, mock_cfg, mock_pruner):
        """Empty code should fail at the facade, not reach the handler."""
        result = python(action="run", code="")
        assert result["status"] == "error"
        assert "No code provided" in result["error"]

    def test_handler_exception_caught(self, mock_cfg, mock_pruner):
        """If the handler raises, the facade should return a graceful error."""
        from tools.python_ops._registry import DISPATCH
        original = DISPATCH["python"]["run"]["func"]
        # Replace the handler with one that always raises.
        DISPATCH["python"]["run"]["func"] = lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            result = python(action="run", code="print('x')")
            assert result["status"] == "error"
            assert "Python action failed" in result["error"]
            assert "boom" in result["error"]
        finally:
            DISPATCH["python"]["run"]["func"] = original

    def test_trace_id_threaded_through_dispatch(self, mock_cfg, mock_pruner):
        """trace_id should be present in error responses from dispatch layer."""
        result = python(action="nonexistent", code="print('x')", trace_id="trace-dispatch-1")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-dispatch-1"

        result = python(action="", code="print('x')", trace_id="trace-dispatch-2")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-dispatch-2"

    def test_duration_ms_always_present(self, mock_cfg, mock_pruner):
        """duration_ms should be present on every result."""
        result = python(action="run", code="print('hi')")
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], (int, float))
        assert result["duration_ms"] >= 0


class TestRegistry:
    """Verify all 5 python actions are registered in DISPATCH."""

    def test_dispatch_has_5_actions(self):
        from tools.python_ops._registry import DISPATCH
        actions = DISPATCH.get("python", {})
        assert len(actions) == 5
        expected = {"run", "run_data", "eval", "profile", "lint"}
        assert set(actions.keys()) == expected

    def test_all_actions_have_metadata(self):
        from tools.python_ops._registry import DISPATCH
        for name, info in DISPATCH["python"].items():
            assert "func" in info, f"{name} missing func"
            assert "help" in info, f"{name} missing help"
            assert "examples" in info, f"{name} missing examples"
            assert callable(info["func"]), f"{name} func not callable"
            assert isinstance(info["help"], str) and info["help"], f"{name} help empty"
            assert isinstance(info["examples"], list) and info["examples"], f"{name} examples empty"

    def test_action_names_match_pattern(self):
        """All action names must match ^[a-z][a-z0-9_]*$ (validated by @meta_tool)."""
        from tools.python_ops._registry import DISPATCH
        pattern = re.compile(r"^[a-z][a-z0-9_]*$")
        for name in DISPATCH["python"]:
            assert pattern.match(name), f"{name!r} does not match required pattern"

    def test_facade_action_literal_generated(self):
        """The @meta_tool decorator should have replaced `action: str` with a Literal."""
        from typing import get_args, get_type_hints
        from tools.python import python as python_fn
        hints = get_type_hints(python_fn)
        action_hint = hints.get("action")
        args = set(get_args(action_hint))
        assert args == {"run", "run_data", "eval", "profile", "lint"}, f"Got: {args}"

    def test_facade_docstring_has_action_list(self):
        """The @meta_tool decorator should have generated a docstring with action list."""
        from tools.python import python as python_fn
        assert python_fn.__doc__ is not None
        doc = python_fn.__doc__
        for action in ("run", "run_data", "eval", "profile", "lint"):
            assert action in doc, f"{action} not in docstring"
        assert "python meta-tool" in doc.lower()


class TestFacadeSignature:
    """Verify the facade signature includes all v1.0 params."""

    def test_facade_has_5_params(self):
        """The facade should accept: action, code, trace_id, timeout, json_schema."""
        import inspect
        from tools.python import python as python_fn
        sig = inspect.signature(python_fn)
        params = set(sig.parameters.keys())
        assert params == {"action", "code", "trace_id", "timeout", "json_schema"}

    def test_facade_param_defaults(self):
        """Verify default values for the new v1.0 params."""
        import inspect
        from tools.python import python as python_fn
        sig = inspect.signature(python_fn)
        assert sig.parameters["action"].default == ""
        assert sig.parameters["code"].default == ""
        assert sig.parameters["trace_id"].default == ""
        assert sig.parameters["timeout"].default == -1
        assert sig.parameters["json_schema"].default == ""
