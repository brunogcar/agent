"""tests/workflows/autocode/test_graph.py
Graph topology, WORKFLOW_METADATA, singleton, and state schema tests.
"""
from __future__ import annotations

import pytest
from langgraph.graph import StateGraph

from workflows.autocode_impl.graph import build_graph, get_graph, WORKFLOW_METADATA


# ─── Graph topology ─────────────────────────────────────────────────────────

class TestGraphTopology:
    def test_graph_has_exactly_17_nodes(self):
        g = build_graph()
        expected = {
            "node_classify_task", "node_validate_input", "node_brainstorm",
            "node_write_plan", "node_git_branch", "node_write_tests",
            "node_execute_step", "node_run_tests", "node_systematic_debug",
            "node_write_files", "node_write_files_with_flag_reset",
            "node_verify", "node_commit", "node_distill_memory", "node_create_skill",
            "node_analyze_impact", "node_report",
        }
        assert set(g.nodes.keys()) == expected, \
            f"Node mismatch. Missing: {expected - set(g.nodes.keys())}"

    def test_entry_point_is_classify(self):
        g = build_graph()
        assert "node_classify_task" in g.nodes

    def test_build_graph_returns_stategraph(self):
        g = build_graph()
        assert isinstance(g, StateGraph)

    def test_tdd_loop_edge_exists(self):
        """Debug loop: node_systematic_debug → node_write_files."""
        g = build_graph()
        assert ("node_systematic_debug", "node_write_files") in g.edges

    def test_terminal_nodes_exist(self):
        g = build_graph()
        assert "node_create_skill" in g.nodes
        assert "node_distill_memory" in g.nodes


# ─── Singleton ──────────────────────────────────────────────────────────────

class TestGraphSingleton:
    def test_get_graph_returns_same_instance(self):
        g1 = get_graph()
        g2 = get_graph()
        assert g1 is g2

    def test_compiled_graph_has_invoke(self):
        compiled = get_graph()
        assert hasattr(compiled, "invoke")
        assert hasattr(compiled, "stream")

    def test_get_graph_returns_compiled_not_stategraph(self):
        """get_graph() must return a compiled graph (has invoke, not add_node)."""
        compiled = get_graph()
        assert hasattr(compiled, "invoke")
        assert not hasattr(compiled, "add_node"), \
            "get_graph must return compiled graph, not StateGraph"


# ─── WORKFLOW_METADATA ──────────────────────────────────────────────────────

class TestWorkflowMetadata:
    def test_metadata_exists(self):
        assert isinstance(WORKFLOW_METADATA, dict)
        assert WORKFLOW_METADATA["name"] == "autocode"
        assert WORKFLOW_METADATA["version"] == "1.1"

    def test_metadata_has_17_nodes(self):
        nodes = WORKFLOW_METADATA["nodes"]
        assert len(nodes) == 17

    def test_metadata_nodes_have_types(self):
        for node in WORKFLOW_METADATA["nodes"]:
            assert "type" in node
            assert node["type"] in ("llm", "tool", "logic", "composite")

    def test_metadata_has_loops(self):
        loops = WORKFLOW_METADATA["loops"]
        assert len(loops) >= 1
        assert loops[0]["name"] == "debug_loop"

    def test_metadata_has_branches(self):
        branches = WORKFLOW_METADATA["branches"]
        assert len(branches) >= 1
        assert branches[0]["name"] == "create_skill"

    def test_metadata_has_safety_features(self):
        safety = WORKFLOW_METADATA["safety_features"]
        assert "git_branch" in safety
        assert "atomic_writes" in safety


# ─── State schema ───────────────────────────────────────────────────────────

class TestStateSchema:
    def test_state_has_all_required_tdd_fields(self):
        from workflows.autocode_impl.state import AutocodeState
        import typing
        hints = typing.get_type_hints(AutocodeState)
        for field in ["tdd_source_code", "tdd_status", "tdd_iteration",
                       "test_results", "plan", "current_step"]:
            assert field in hints, f"AutocodeState missing required TDD field: {field}"

    def test_state_has_git_scoping_field(self):
        from workflows.autocode_impl.state import AutocodeState
        import typing
        hints = typing.get_type_hints(AutocodeState)
        assert "project_root" in hints
        assert "spec" in hints

    def test_default_state_structure(self):
        from workflows.autocode_impl.state import _default_state
        state = _default_state(task="schema check")
        assert state["task"] == "schema check"
        assert state["status"] == "running"
        assert state["dry_run"] is False
        assert isinstance(state["plan"], list)
        assert state["plan"] == []
        assert state["project_root"] == ""
        assert state["tdd_iteration"] == 0


# ─── Partial-dict returns (structural invariant) ────────────────────────────

class TestPartialDictReturns:
    """[#33] All autocode nodes must return partial update dicts."""

    _NODE_MODULES = [
        "classify", "validate", "brainstorm", "plan", "branch", "tests",
        "execute", "write_files", "analyze_impact", "run_tests", "debug",
        "verify", "report", "commit", "memory", "create_skill",
    ]

    def _get_node_functions(self):
        import ast, importlib, inspect
        for mod_name in self._NODE_MODULES:
            mod = importlib.import_module(f"workflows.autocode_impl.nodes.{mod_name}")
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if callable(obj) and attr.startswith("node_") and not inspect.iscoroutinefunction(obj):
                    try:
                        yield mod_name, attr, inspect.getsource(obj)
                    except (OSError, TypeError):
                        pass

    def test_no_node_returns_star_state_spread(self):
        import ast
        violations = []
        for mod_name, func_name, source in self._get_node_functions():
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Return) and node.value and isinstance(node.value, ast.Dict):
                    for k, v in zip(node.value.keys, node.value.values):
                        if k is None and isinstance(v, ast.Name) and v.id == "state":
                            violations.append(f"{mod_name}.{func_name}")
        assert not violations, f"Nodes return {{**state, ...}}: {violations}"

    def test_no_node_returns_bare_state(self):
        import ast
        violations = []
        for mod_name, func_name, source in self._get_node_functions():
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Return) and node.value and isinstance(node.value, ast.Name) and node.value.id == "state":
                    violations.append(f"{mod_name}.{func_name}")
        assert not violations, f"Nodes do bare `return state`: {violations}"

    def test_all_nodes_are_sync(self):
        import inspect, importlib
        violations = []
        for mod_name in self._NODE_MODULES:
            mod = importlib.import_module(f"workflows.autocode_impl.nodes.{mod_name}")
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if callable(obj) and attr.startswith("node_"):
                    if inspect.iscoroutinefunction(obj):
                        violations.append(f"{mod_name}.{attr}")
        assert not violations, f"Async nodes (must be sync): {violations}"
