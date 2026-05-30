"""
tests/workflows/base/test_base_nodes.py
Deep tests for the foundational workflow state mutation primitives.
"""
from __future__ import annotations
import pytest
from workflows.base import WorkflowState, node_done, node_error, node_step

def _base_state() -> WorkflowState:
    return {
        "workflow": "test", "goal": "test goal", "trace_id": "t1",
        "status": "running", "error": "", "result": "", "artifacts": [],
        "retries": 0
    }

class TestNodeDone:
    def test_sets_success_and_result(self):
        state = _base_state()
        update = node_done(state, result="final output")
        assert update["status"] == "success"
        assert update["result"] == "final output"
        assert update.get("error", "") == ""

    def test_returns_partial_update(self):
        """node_done returns a partial dict for LangGraph to merge."""
        state = _base_state()
        update = node_done(state, result="done")
        assert isinstance(update, dict)
        assert "status" in update
        assert "result" in update

class TestNodeError:
    def test_sets_failed_and_error_message(self):
        state = _base_state()
        update = node_error(state, "test_node", "something broke")
        assert update["status"] == "failed"
        assert update["error"] == "something broke"

    def test_never_empty_error_message(self):
        """node_error must produce a non-empty message even if called with ''."""
        state = _base_state()
        update = node_error(state, "some_node", "")
        assert update["status"] == "failed"
        assert len(update.get("error", "")) > 0, "error message must not be empty"

class TestNodeStep:
    def test_returns_none_and_does_not_corrupt_state(self):
        """node_step is for logging/tracing. It returns None and mutates nothing."""
        state = _base_state()
        state["status"] = "running"
        result = node_step(state, "search", "searching web", query="test")
        assert result is None, "node_step should return None"
        assert state["status"] == "running", "node_step mutated state in place!"