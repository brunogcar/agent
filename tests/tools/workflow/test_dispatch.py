"""Tests for the workflow facade dispatch and registries.

Mirrors the structure of tests/tools/vision/test_dispatch.py. Covers:
  - Unknown action → error listing valid actions
  - Empty action → error explaining action is required
  - Case insensitivity (RUN / Run / run all dispatch the same handler)
  - All 5 actions present in DISPATCH with full metadata
  - All 8 types present in TYPE_DISPATCH with full metadata
  - Literal[...] generation for the `action` parameter
  - Docstring generation with action list + doc_sections
  - duration_ms always present
  - Handler exceptions caught
"""
from __future__ import annotations

from tools.workflow import workflow


class TestDispatch:
    """Facade-level dispatch routes actions and handles unknown/empty actions."""

    def test_unknown_action(self, mock_tracer):
        """Unknown action should list valid actions."""
        result = workflow(action="nonexistent", trace_id="t1")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]
        assert "run" in result["error"]
        assert "list" in result["error"]
        assert "status" in result["error"]
        assert "cancel" in result["error"]
        assert "history" in result["error"]

    def test_empty_action(self):
        """Empty action should return clear 'action is required' error."""
        result = workflow(action="")
        assert result["status"] == "error"
        assert "action is required" in result["error"].lower()

    def test_action_case_insensitive(self, mock_tracer, mock_run_workflow):
        """Action should be case-insensitive (uppercase/lowercase both dispatch)."""
        # Uppercase
        result_upper = workflow(action="RUN", type="research", goal="test", trace_id="t1")
        assert result_upper["status"] == "success", f"RUN failed: {result_upper}"

        # Mixed case
        result_mixed = workflow(action="Run", type="research", goal="test", trace_id="t2")
        assert result_mixed["status"] == "success", f"Run failed: {result_mixed}"

    def test_duration_ms_always_present(self, mock_tracer, mock_run_workflow):
        """duration_ms should be present on every handler-returned result."""
        result = workflow(action="run", type="research", goal="test", trace_id="t1")
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], (int, float))
        assert result["duration_ms"] >= 0

    def test_handler_exception_caught(self, mock_tracer, mock_run_workflow):
        """If run_workflow raises inside the type handler, the result should
        propagate as a clean error from _execute_workflow.

        The type handler calls _execute_workflow which doesn't catch exceptions
        itself — they bubble up to the facade's outer try/except.
        """
        mock_run_workflow.side_effect = RuntimeError("LangGraph crashed")
        result = workflow(action="run", type="research", goal="test", trace_id="t1")
        assert result["status"] == "error"
        assert "Workflow action failed" in result["error"]

    def test_trace_id_threaded_through_dispatch(self):
        """trace_id should be present in error responses from dispatch layer."""
        result = workflow(action="nonexistent", trace_id="trace-dispatch-1")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-dispatch-1"

        result = workflow(action="", trace_id="trace-dispatch-2")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-dispatch-2"


class TestRegistry:
    """Verify all 9 workflow actions are registered in DISPATCH.

    v1.0: 5 actions (run | list | status | cancel | history).
    v1.2: +4 actions (resume | logs | templates | kill) → 9 total.
    """

    def test_dispatch_has_9_actions(self):
        from tools.workflow_ops._registry import DISPATCH
        actions = DISPATCH.get("workflow", {})
        assert len(actions) == 9
        expected = {"run", "list", "status", "cancel", "history",
                    "resume", "logs", "templates", "kill"}
        assert set(actions.keys()) == expected

    def test_all_actions_have_metadata(self):
        from tools.workflow_ops._registry import DISPATCH
        for name, info in DISPATCH["workflow"].items():
            assert "func" in info, f"{name} missing func"
            assert "help" in info, f"{name} missing help"
            assert "examples" in info, f"{name} missing examples"
            assert callable(info["func"]), f"{name} func not callable"
            assert isinstance(info["help"], str) and info["help"], f"{name} help empty"
            assert isinstance(info["examples"], list) and info["examples"], f"{name} examples empty"

    def test_action_names_match_pattern(self):
        """All action names must match ^[a-z][a-z0-9_]*$ (validated by @meta_tool)."""
        import re
        from tools.workflow_ops._registry import DISPATCH
        pattern = re.compile(r"^[a-z][a-z0-9_]*$")
        for name in DISPATCH["workflow"]:
            assert pattern.match(name), f"{name!r} does not match required pattern"

    def test_facade_action_literal_generated(self):
        """The @meta_tool decorator should have replaced `action: str` with a Literal."""
        from typing import get_args, get_type_hints
        from tools.workflow import workflow as workflow_fn
        hints = get_type_hints(workflow_fn)
        action_hint = hints.get("action")
        # Literal[...] args should be exactly the 9 registered actions (v1.2).
        args = set(get_args(action_hint))
        assert args == {"run", "list", "status", "cancel", "history",
                        "resume", "logs", "templates", "kill"}, f"Got: {args}"

    def test_facade_docstring_has_action_list(self):
        """The @meta_tool decorator should have generated a docstring with action list."""
        from tools.workflow import workflow as workflow_fn
        assert workflow_fn.__doc__ is not None
        doc = workflow_fn.__doc__
        assert "run" in doc
        assert "list" in doc
        assert "status" in doc
        assert "cancel" in doc
        assert "history" in doc
        assert "workflow meta-tool" in doc.lower()

    def test_facade_docstring_has_doc_sections(self):
        """The doc_sections passed to @meta_tool should be present in the docstring."""
        from tools.workflow import workflow as workflow_fn
        doc = workflow_fn.__doc__
        # Spot-check a few doc_sections strings
        assert "WORKFLOW TOOL" in doc
        assert "Launch and manage LangGraph workflows" in doc
        assert "NOT parallel-safe" in doc


class TestTypeRegistry:
    """Verify all 8 workflow types are registered in TYPE_DISPATCH.

    v1.1-p1: Added 'compose' type (chain multiple workflows sequentially).
    """

    def test_type_dispatch_has_8_types(self):
        from tools.workflow_ops._type_registry import TYPE_DISPATCH
        assert len(TYPE_DISPATCH) == 8
        expected = {"research", "data", "autocode", "deep_research",
                    "understand", "autoresearch", "auto", "compose"}
        assert set(TYPE_DISPATCH.keys()) == expected

    def test_all_types_have_metadata(self):
        from tools.workflow_ops._type_registry import TYPE_DISPATCH
        for name, info in TYPE_DISPATCH.items():
            assert "func" in info, f"{name} missing func"
            assert "help" in info, f"{name} missing help"
            assert callable(info["func"]), f"{name} func not callable"
            assert isinstance(info["help"], str) and info["help"], f"{name} help empty"

    def test_type_names_match_pattern(self):
        """All type names must match ^[a-z][a-z0-9_]*$."""
        import re
        from tools.workflow_ops._type_registry import TYPE_DISPATCH
        pattern = re.compile(r"^[a-z][a-z0-9_]*$")
        for name in TYPE_DISPATCH:
            assert pattern.match(name), f"{name!r} does not match required pattern"

    def test_type_dispatch_excludes_report(self):
        """TYPE_DISPATCH must NOT include 'report' — it's a tool, not a workflow."""
        from tools.workflow_ops._type_registry import TYPE_DISPATCH
        assert "report" not in TYPE_DISPATCH, (
            "TYPE_DISPATCH must not include 'report' — it's a tool, not a workflow."
        )
