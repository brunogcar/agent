"""tests/workflows/autocode/test_call_trace_id.py — Assert _call() callers pass trace_id.

[v1.2 P1] All 8 _call() callers must pass trace_id=tid so retry-exhaustion
errors are attributed to the workflow's trace. Before v1.2, the trace_id
param existed on _call() but no caller passed it — errors used trace_id="".
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


def _base_state():
    from workflows.autocode_impl.state import _default_state
    state = _default_state(task="test task")
    state["trace_id"] = "test-trace-001"
    state["task_type"] = "feature"
    state["project_root"] = "/tmp"
    state["plan_state"]["plan"] = [{"id": 1, "label": "write_code", "description": "implement"}]
    state["plan_state"]["current_step"] = 0
    state["tdd"]["max_retries"] = 3
    return state


class TestCallTraceIdPropagation:
    """Each _call() caller must pass trace_id=tid."""

    @pytest.mark.parametrize("node_module,node_func,state_overrides", [
        ("workflows.autocode_impl.nodes.classify", "node_classify_task", {}),
        ("workflows.autocode_impl.nodes.brainstorm", "node_brainstorm", {"task_type": "feature"}),
        ("workflows.autocode_impl.nodes.plan", "node_write_plan", {}),
        # [v1.2 fix] node_write_tests requires the current plan step's label to
        # be "write_tests" (else it early-returns and never calls _call). The
        # default base_state's plan has label "write_code", so override.
        ("workflows.autocode_impl.nodes.tests", "node_write_tests", {
            "plan_state": {
                "plan": [{"id": 1, "label": "write_tests", "description": "write tests",
                          "acceptance": "tests exist", "files": []}],
                "current_step": 0,
                "spec": "test spec",
                "brainstorm_notes": "",
                "plan_accepted": False,
            },
        }),
        ("workflows.autocode_impl.nodes.execute", "node_execute_step", {}),
        ("workflows.autocode_impl.nodes.llm_review", "node_llm_review", {}),
    ])
    def test_call_passes_trace_id(self, node_module, node_func, state_overrides, tmp_path):
        """Mock _call() and assert it receives trace_id matching state's trace_id."""
        state = _base_state()
        state["project_root"] = str(tmp_path)
        state.update(state_overrides)

        import importlib
        mod = importlib.import_module(node_module)
        func = getattr(mod, node_func)

        with patch(f"{node_module}._call") as mock_call:
            mock_call.return_value = '{"task_type": "feature", "questions": [], "steps": [], "test_code": "", "code": "", "verdict": "pass", "issues": []}'
            try:
                func(state)
            except Exception:
                pass  # We only care about the _call() kwargs
            assert mock_call.called, f"{node_func} did not call _call()"
            _, kwargs = mock_call.call_args
            assert kwargs.get("trace_id") == state["trace_id"], \
                f"{node_func} did not pass trace_id=tid to _call() (got trace_id={kwargs.get('trace_id')!r})"
