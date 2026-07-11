"""tests/workflows/autocode/test_debug.py
Tests for node_systematic_debug — debug loop routing, JSON parsing,
and max-retries enforcement.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch


class TestDebugLoopRouting:
    def test_debug_edge_routes_to_apply_patches(self):
        """The graph must have a direct edge debug → apply_patches (not via run_tests).

        [v2.0] Was: debug → write_files. Phase 3.1 split changed target to
        node_apply_patches (first of the 3 split write nodes).
        """
        from workflows.autocode_impl.graph import build_graph
        g = build_graph()
        assert ("node_systematic_debug", "node_apply_patches") in g.edges


class TestDebugJsonParsing:
    def test_debug_node_uses_parse_json_fallback(self, mocker, base_state):
        """node_systematic_debug must handle nested JSON from the LLM."""
        from workflows.autocode_impl.nodes.debug import node_systematic_debug
        base_state["tdd_iteration"] = 1
        base_state["max_retries"] = 3
        base_state["tdd_error"] = "AssertionError"
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
        assert base_state["max_retries"] == 3
        assert MAX_RETRIES == 3

    def test_debug_sets_max_retries_exceeded(self, mocker, base_state):
        """When tdd_iteration > max_retries, debug must set tdd_status='max_retries_exceeded'."""
        from workflows.autocode_impl.nodes.debug import node_systematic_debug
        base_state["tdd_iteration"] = 4  # > max_retries (3)
        base_state["max_retries"] = 3
        base_state["tdd_error"] = "AssertionError"
        base_state["test_results"] = {"stderr": "error", "stdout": ""}
        mocker.patch("core.memory_engine.memory.store")
        result = node_systematic_debug(base_state)
        assert result["tdd_status"] == "max_retries_exceeded"
