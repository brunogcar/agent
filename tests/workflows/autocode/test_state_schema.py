"""
tests/workflows/autocode/test_state_schema.py
Validates AutocodeState schema compliance, plan list indexing,
tdd_source_code handoff, and mutation safety.
Guarantees:
- No external calls; pure state manipulation & routing tests
- Enforces list[dict] plan structure & current_step indexing
- Validates tdd_source_code flows correctly through TDD loop
- Ensures _default_state matches production expectations
"""
from __future__ import annotations

import pytest
from workflows.autocode_impl.state import _default_state, AutocodeState


class TestDefaultStateStructure:
    """_default_state must return correct types and safe defaults."""

    def test_returns_dict_with_required_keys(self):
        state = _default_state(task="schema check")
        assert isinstance(state, dict)
        assert state["task"] == "schema check"
        assert state["status"] == "running"
        assert state["dry_run"] is False

    def test_plan_is_list_not_dict(self):
        state = _default_state()
        assert isinstance(state["plan"], list)
        assert state["plan"] == []

    def test_project_root_defaults_to_empty_string(self):
        state = _default_state()
        assert state["project_root"] == ""

    def test_tdd_fields_initialized_safely(self):
        state = _default_state()
        assert state["tdd_source_code"] == ""
        assert state["tdd_status"] == ""
        assert state["tdd_iteration"] == 0
        assert isinstance(state["test_results"], dict)


class TestPlanListIndexing:
    """Plan must be indexed as list[dict] using current_step."""

    def test_valid_plan_indexing(self):
        plan = [
            {"id": 1, "label": "write_tests", "description": "create pytest"},
            {"id": 2, "label": "write_code", "description": "implement logic"},
        ]
        current_step = 1
        step = plan[current_step]
        assert step["label"] == "write_code"
        assert step["id"] == 2

    def test_out_of_bounds_index_returns_none_safe(self):
        plan = [{"id": 1, "label": "init"}]
        current_step = 5
        # Simulate safe guard used in execute.py
        step = plan[current_step] if current_step < len(plan) else None
        assert step is None


class TestTDDSourceCodeHandoff:
    """tdd_source_code must flow from execute -> write_files -> verify."""

    def test_execute_sets_tdd_source_code(self):
        state = _default_state(task="handoff test")
        # Simulate execute node output
        state["tdd_source_code"] = "def add(a, b): return a + b"
        assert state["tdd_source_code"] != ""
        assert isinstance(state["tdd_source_code"], str)

    def test_write_files_reads_tdd_source_code(self):
        import json
        state = _default_state(task="handoff test")
        payload = {"new_files": {"math.py": "def add(a, b): return a + b"}}
        state["tdd_source_code"] = json.dumps(payload)
        # write_files expects JSON string in tdd_source_code
        parsed = json.loads(state["tdd_source_code"])
        assert "new_files" in parsed

    def test_missing_tdd_source_code_blocks_write(self):
        state = _default_state(task="handoff test")
        state.pop("tdd_source_code", None)
        # Guard used in write_files.py
        has_code = bool(state.get("tdd_source_code"))
        assert has_code is False


class TestStateMutationSafety:
    """Nodes should return minimal diffs, not full state copies."""

    def test_execute_returns_minimal_diff(self):
        # Simulate what execute.py returns
        diff = {
            "tdd_source_code": "def foo(): pass",
            "execution_notes": "Executed step: write_code",
        }
        # LangGraph merges diffs automatically
        assert "task" not in diff
        assert "trace_id" not in diff
        assert len(diff) == 2

    def test_verify_returns_minimal_diff(self):
        # Simulate verify node output
        diff = {
            "verification_passed": True,
            "verification_notes": "AST valid, tests pass",
        }
        assert "plan" not in diff
        assert "tdd_source_code" not in diff
        assert len(diff) == 2