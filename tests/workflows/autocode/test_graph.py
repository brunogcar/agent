"""tests/workflows/autocode/test_graph.py
Graph topology, WORKFLOW_METADATA, singleton, and state schema tests.
"""
from __future__ import annotations

import pytest
from langgraph.graph import StateGraph

from workflows.autocode_impl.graph import build_graph, get_graph, WORKFLOW_METADATA


# ─── Graph topology ─────────────────────────────────────────────────────────

class TestGraphTopology:
    def test_graph_has_exactly_29_nodes(self):
        g = build_graph()
        expected = {
            "node_classify_task", "node_validate_input", "node_brainstorm",
            "node_write_plan", "node_git_branch", "node_write_tests",
            "node_execute_step", "node_run_tests", "node_systematic_debug",
            # [v3.1] #48: swarm fallback node (when debug retries exhausted)
            "node_swarm_fallback",
            # [v2.0] Phase 3.1: node_write_files split into 3 + wrapper
            "node_apply_patches", "node_write_new_files", "node_persist_artifacts",
            "node_write_files",  # backward-compat wrapper (registered, not wired)
            # [v2.0] Phase 3.2: node_verify split into 4 + wrapper
            "node_run_pytest", "node_run_lint", "node_llm_review", "node_verify_decision",
            "node_verify",  # backward-compat wrapper (registered, not wired)
            # [v2.0] Phase 3.3: node_publish split into 3 + wrapper
            "node_push", "node_create_pr", "node_merge_pr",
            "node_publish",  # backward-compat wrapper (registered, not wired)
            # [v2.0] Phase 4: debug loop refactor
            "node_summarize_context",
            "node_commit",
            "node_distill_memory", "node_create_skill",
            "node_analyze_impact", "node_report",
        }
        # [v3.1] Was 28 (v2.0 Phase 4). v3.1 added node_swarm_fallback = 29 nodes.
        assert set(g.nodes.keys()) == expected, \
            f"Node mismatch. Missing: {expected - set(g.nodes.keys())}"

    def test_entry_point_is_classify(self):
        g = build_graph()
        assert "node_classify_task" in g.nodes

    def test_build_graph_returns_stategraph(self):
        g = build_graph()
        assert isinstance(g, StateGraph)

    def test_tdd_loop_edge_exists(self):
        """Debug loop: node_systematic_debug → node_summarize_context → node_apply_patches.
        [v2.0] Phase 4: summarize_context added between debug and apply_patches."""
        g = build_graph()
        assert ("node_systematic_debug", "node_summarize_context") in g.edges
        assert ("node_summarize_context", "node_apply_patches") in g.edges

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
        assert "version" in WORKFLOW_METADATA  # [v2.0.4] don't hard-code version (bumps on every release)

    def test_metadata_has_28_nodes(self):
        nodes = WORKFLOW_METADATA["nodes"]
        assert len(nodes) == 28  # [v3.1] was 27 (v2.0 Phase 4), +1 node_swarm_fallback (v3.1 #48)

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
        """[v3.0] TDD fields moved to TDDState sub-state; test_results stays flat (ephemeral)."""
        from workflows.autocode_impl.state import AutocodeState, TDDState, PlanState
        import typing
        # TDD fields are now in TDDState sub-state
        tdd_hints = typing.get_type_hints(TDDState)
        for field in ["source_code", "status", "iteration"]:
            assert field in tdd_hints, f"TDDState missing required field: {field}"
        # test_results stays flat (ephemeral, not in any sub-state)
        state_hints = typing.get_type_hints(AutocodeState)
        assert "test_results" in state_hints, "AutocodeState missing ephemeral test_results field"
        # plan + current_step are in PlanState sub-state
        plan_hints = typing.get_type_hints(PlanState)
        for field in ["plan", "current_step"]:
            assert field in plan_hints, f"PlanState missing required field: {field}"

    def test_state_has_git_scoping_field(self):
        """[v3.0] spec moved to PlanState sub-state; project_root stays flat (core)."""
        from workflows.autocode_impl.state import AutocodeState, PlanState
        import typing
        state_hints = typing.get_type_hints(AutocodeState)
        assert "project_root" in state_hints  # core flat field
        # spec is now in PlanState sub-state
        plan_hints = typing.get_type_hints(PlanState)
        assert "spec" in plan_hints

    def test_default_state_structure(self):
        """[v3.0] plan is in plan_state sub-state; tdd_iteration is in tdd sub-state."""
        from workflows.autocode_impl.state import _default_state
        state = _default_state(task="schema check")
        assert state["task"] == "schema check"
        assert state["status"] == "running"
        assert state["dry_run"] is False
        # plan is now in plan_state sub-state
        assert isinstance(state["plan_state"]["plan"], list)
        assert state["plan_state"]["plan"] == []
        assert state["project_root"] == ""
        # tdd_iteration is now in tdd sub-state
        assert state["tdd"]["iteration"] == 0


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
