"""tests/workflows/autocode/test_debug.py
Tests for node_systematic_debug — debug loop routing, JSON parsing,
and max-retries enforcement.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch


class TestDebugLoopRouting:
    def test_debug_edge_routes_to_summarize_context(self):
        """The graph must have edges debug → summarize_context → apply_patches.

        [v2.0] Phase 4: debug → summarize_context → apply_patches (was: debug → apply_patches).
        The summarize node compresses debug_history before re-entering the loop.
        """
        from workflows.autocode_impl.graph import build_graph
        g = build_graph()
        assert ("node_systematic_debug", "node_summarize_context") in g.edges
        assert ("node_summarize_context", "node_apply_patches") in g.edges


class TestDebugJsonParsing:
    def test_debug_node_uses_parse_json_fallback(self, mocker, base_state):
        """node_systematic_debug must handle nested JSON from the LLM."""
        from workflows.autocode_impl.nodes.debug import node_systematic_debug
        # [v3.0] tdd fields live ONLY in the tdd sub-state.
        base_state["tdd"]["iteration"] = 1
        base_state["tdd"]["max_retries"] = 3
        base_state["tdd"]["error"] = "AssertionError"
        base_state["test_results"] = {"stderr": "AssertionError", "stdout": ""}
        mocker.patch(
            "workflows.autocode_impl.nodes.debug._call",
            return_value='{"root_cause": "off by one", "fix": "change < to <=", "defense_notes": "add bounds check"}',
        )
        result = node_systematic_debug(base_state)
        # Must return a dict (partial update) — not crash
        assert isinstance(result, dict)

    def test_json_loads_parses_nested_structure(self):
        """Sanity: json.loads handles nested structures the LLM might emit."""
        import json
        raw = '{"root_cause": "x", "fix": {"file": "a.py", "old": "x", "new": "y"}}'
        parsed = json.loads(raw)
        assert parsed["fix"]["file"] == "a.py"


class TestMaxRetriesEnforcement:
    def test_max_retries_in_state(self, base_state):
        from workflows.autocode_impl.state import MAX_RETRIES
        # [v3.0] max_retries lives ONLY in the tdd sub-state.
        assert base_state["tdd"]["max_retries"] == 3
        assert MAX_RETRIES == 3

    def test_debug_sets_max_retries_exceeded(self, mocker, base_state):
        """When tdd_iteration > max_retries, debug must set tdd_status='max_retries_exceeded'."""
        from workflows.autocode_impl.nodes.debug import node_systematic_debug
        # [v3.0] tdd fields live ONLY in the tdd sub-state.
        base_state["tdd"]["iteration"] = 4  # > max_retries (3)
        base_state["tdd"]["max_retries"] = 3
        base_state["tdd"]["error"] = "AssertionError"
        base_state["test_results"] = {"stderr": "error", "stdout": ""}
        mocker.patch("core.memory_engine.memory.store")
        result = node_systematic_debug(base_state)
        # [v3.0] tdd_status lives ONLY in the tdd sub-state now.
        assert result["tdd"]["status"] == "max_retries_exceeded"
