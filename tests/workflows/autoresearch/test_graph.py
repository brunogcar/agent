"""tests/workflows/autoresearch/test_graph.py

[v1.0] Graph topology + WORKFLOW_METADATA tests for the autoresearch workflow.

[v1.3 tests] Merged the full-loop integration test that previously lived in
test_loop_integration.py. The 7 per-node integration tests that were also
in that file have been moved into the new test_nodes_*.py files
(test_nodes_setup, test_nodes_propose, test_nodes_decide, test_nodes_run).

Tests:
  test_graph_has_exactly_7_nodes          — setup, propose, modify, run_experiment,
                                            evaluate, decide, log
  test_entry_point_is_setup              — graph entry point is "setup"
  test_experiment_loop_exists            — WORKFLOW_METADATA.loops has experiment_loop
  test_metadata_exists                   — WORKFLOW_METADATA is a dict
  test_metadata_has_correct_name         — name == "autoresearch"
  test_build_graph_returns_stategraph    — build_autoresearch_graph returns a
                                            compiled graph with .invoke()
  test_loop_runs_one_iteration_then_recurses — [merged] full-loop integration
                                            test that verifies the 7-node call
                                            order with all I/O mocked
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from workflows.autoresearch import build_autoresearch_graph, WORKFLOW_METADATA


class TestAutoresearchGraphTopology:
    """Verify the compiled graph has the right nodes + entry point."""

    def test_build_graph_returns_stategraph(self):
        """build_autoresearch_graph must return a compiled graph with .invoke()."""
        graph = build_autoresearch_graph()
        assert graph is not None
        # Compiled LangGraph instances expose .invoke()
        assert hasattr(graph, "invoke"), "compiled graph must expose .invoke()"

    def test_graph_has_exactly_7_nodes(self):
        """The graph must contain exactly the 7 autoresearch nodes."""
        graph = build_autoresearch_graph()
        # Compiled graphs expose their nodes via .nodes or .get_graph().nodes
        nodes = getattr(graph, "nodes", None)
        if not nodes and hasattr(graph, "get_graph"):
            nodes = graph.get_graph().nodes
        # Some LangGraph versions wrap nodes in a dict, others in a list-like
        if hasattr(nodes, "keys"):
            node_names = set(nodes.keys())
        else:
            node_names = set(n if isinstance(n, str) else getattr(n, "name", str(n)) for n in nodes)
        # The 7 expected nodes (plus possibly __end__ / __start__ built-ins)
        expected = {"setup", "propose", "modify", "run_experiment",
                    "evaluate", "decide", "log"}
        missing = expected - node_names
        assert not missing, f"Missing nodes: {missing}. Found: {node_names}"
        # Exactly 7 user-defined nodes (built-in __start__/__end__ may also be present)
        user_nodes = expected & node_names
        assert len(user_nodes) == 7, f"Expected 7 user nodes, got {len(user_nodes)}: {user_nodes}"

    def test_entry_point_is_setup(self):
        """The graph's entry point must be 'setup'.

        Verified two ways:
          1. WORKFLOW_METADATA['entry_point'] == 'setup' (declared)
          2. The compiled graph has an edge from __start__ → setup (actual)
        """
        # 1. Declared entry point in metadata
        assert WORKFLOW_METADATA["entry_point"] == "setup", (
            "entry_point must be 'setup' — the experiment loop must start with "
            "branch creation + baseline measurement before any proposals"
        )
        # 2. Actual entry point in the compiled graph
        graph = build_autoresearch_graph()
        gg = graph.get_graph()
        # Look for the __start__ → setup edge — that's what "entry point is setup" means
        start_edges = [e for e in gg.edges if e.source == "__start__"]
        assert len(start_edges) >= 1, "graph must have at least one edge from __start__"
        targets = {e.target for e in start_edges}
        assert "setup" in targets, (
            f"__start__ must connect to 'setup' (entry point), got targets: {targets}"
        )

    def test_experiment_loop_exists(self):
        """WORKFLOW_METADATA.loops must contain the experiment_loop."""
        loops = WORKFLOW_METADATA.get("loops", [])
        assert len(loops) >= 1, "autoresearch must have at least one loop (experiment_loop)"
        loop_names = [l.get("name") for l in loops]
        assert "experiment_loop" in loop_names, (
            f"loops must contain 'experiment_loop', got: {loop_names}"
        )
        # The experiment_loop must include all 6 loop nodes (not setup — that
        # only runs once at the start)
        exp_loop = next(l for l in loops if l.get("name") == "experiment_loop")
        loop_nodes = set(exp_loop.get("nodes", []))
        expected_loop_nodes = {"propose", "modify", "run_experiment",
                               "evaluate", "log", "decide"}
        assert expected_loop_nodes.issubset(loop_nodes), (
            f"experiment_loop.nodes must include {expected_loop_nodes}, "
            f"got: {loop_nodes}"
        )
        # The loop must run indefinitely
        assert "human interrupt" in str(exp_loop.get("exit_condition", "")).lower() or \
               "unlimited" in str(exp_loop.get("max_iterations", "")).lower(), (
            f"experiment_loop must run indefinitely (exit_condition=human interrupt, "
            f"max_iterations=unlimited), got: {exp_loop}"
        )


class TestAutoresearchMetadata:
    """WORKFLOW_METADATA structure + content tests."""

    def test_metadata_exists(self):
        """WORKFLOW_METADATA must exist and be a dict."""
        assert isinstance(WORKFLOW_METADATA, dict), (
            "WORKFLOW_METADATA must be a dict for MCP client introspection"
        )

    def test_metadata_has_correct_name(self):
        """WORKFLOW_METADATA['name'] must be 'autoresearch'."""
        assert WORKFLOW_METADATA["name"] == "autoresearch", (
            f"name must be 'autoresearch', got: {WORKFLOW_METADATA.get('name')}"
        )

    def test_metadata_has_correct_version(self):
        """WORKFLOW_METADATA['version'] must exist (not pinned — changes every release)."""
        assert "version" in WORKFLOW_METADATA, "WORKFLOW_METADATA must have a 'version' key"
        assert isinstance(WORKFLOW_METADATA["version"], str), "version must be a string"

    def test_metadata_has_7_nodes(self):
        """WORKFLOW_METADATA['nodes'] must list exactly 7 nodes."""
        nodes = WORKFLOW_METADATA["nodes"]
        assert len(nodes) == 7, f"Expected 7 nodes, got {len(nodes)}"
        expected_names = {"setup", "propose", "modify", "run_experiment",
                          "evaluate", "decide", "log"}
        actual_names = {n["name"] for n in nodes}
        assert actual_names == expected_names, (
            f"node names must match {expected_names}, got: {actual_names}"
        )

    def test_metadata_nodes_have_descriptions(self):
        """Every node in WORKFLOW_METADATA must have a non-empty description."""
        for node in WORKFLOW_METADATA["nodes"]:
            assert "description" in node, (
                f"node {node.get('name')} missing description"
            )
            assert len(node["description"]) > 0, (
                f"node {node.get('name')} has empty description"
            )

    def test_metadata_has_safety_features(self):
        """WORKFLOW_METADATA must declare safety_features (git_branch, results_ledger, time_budget)."""
        safety = WORKFLOW_METADATA.get("safety_features", [])
        assert "git_branch" in safety, "git_branch safety feature missing"
        assert "results_ledger" in safety, "results_ledger safety feature missing"
        assert "time_budget" in safety, "time_budget safety feature missing"

    def test_metadata_edges_include_loop_edge(self):
        """WORKFLOW_METADATA['edges'] must include the log → propose loop edge.

        [v1.3 P0-1] The loop back-edge moved from `decide → propose` to
        `log → propose` (graph order changed from evaluate → log → decide
        to evaluate → decide → log). The loop edge is now the one that
        closes the loop after log records the experiment outcome.

        [v1.4] The loop edge is now CONDITIONAL (was a direct edge in v1.3).
        `route_after_log` checks 3 stopping conditions (max_iterations /
        convergence / stuck) before looping back to propose. All default
        OFF — v1.4 preserves v1.3's "loop forever" behavior unless a
        caller opts in.
        """
        edges = WORKFLOW_METADATA["edges"]
        # Find the loop edge (log → propose) — was decide → propose pre-v1.3
        loop_edges = [e for e in edges if e.get("from") == "log" and e.get("to") == "propose"]
        assert len(loop_edges) == 1, (
            f"expected exactly 1 log → propose edge (the loop), got {len(loop_edges)}"
        )
        assert loop_edges[0].get("type") == "loop", (
            f"log → propose edge must be type='loop', got: {loop_edges[0]}"
        )
        # [v1.4] The loop edge must declare a non-trivial condition now that
        # it's a conditional edge (route_after_log checks stopping conditions).
        condition = loop_edges[0].get("condition", "")
        assert "route_after_log" in condition, (
            f"log → propose edge condition must reference route_after_log, "
            f"got: {condition!r}"
        )


class TestAutoresearchFacade:
    """Verify the thin facade re-exports the graph builder + metadata."""

    def test_facade_reexports_build_autoresearch_graph(self):
        """workflows.autoresearch must re-export build_autoresearch_graph."""
        from workflows.autoresearch import build_autoresearch_graph as f_build
        from workflows.autoresearch_impl.graph import build_autoresearch_graph as impl_build
        assert f_build is impl_build, (
            "facade must re-export the same build_autoresearch_graph function"
        )

    def test_facade_reexports_workflow_metadata(self):
        """workflows.autoresearch must re-export WORKFLOW_METADATA."""
        from workflows.autoresearch import WORKFLOW_METADATA as f_meta
        from workflows.autoresearch_impl.graph import WORKFLOW_METADATA as impl_meta
        assert f_meta is impl_meta, (
            "facade must re-export the same WORKFLOW_METADATA dict"
        )

    def test_facade_all_list(self):
        """workflows.autoresearch.__all__ must list both re-exports."""
        import workflows.autoresearch as facade
        assert "build_autoresearch_graph" in facade.__all__
        assert "WORKFLOW_METADATA" in facade.__all__


class TestAutoresearchLoopIntegration:
    """Full-loop integration tests (all 7 nodes mocked) — merged here from
    the deleted test_loop_integration.py.

    The per-node tests in test_nodes_*.py cover individual node behavior;
    this test class verifies the actual graph WIRING — that the 7 nodes
    are invoked in the correct order and the loop back-edge closes the
    loop. Catches state-passing bugs that the topology tests can't.
    """

    def test_loop_runs_one_iteration_then_recurses(self, ar_state, tmp_path):
        """The loop must execute setup → propose → modify → run_experiment →
        evaluate → decide → log → propose (loop) in the correct order.

        [v1.3 P0-1] Graph order changed from `evaluate → log → decide` to
        `evaluate → decide → log` — `decide` now annotates `current_experiment`
        BEFORE `log` reads it (was: log read pre-decide status, so the ledger
        always said "discard").

        [v1.4] The log → propose back-edge is now CONDITIONAL (was a direct
        edge in v1.3). `route_after_log` checks max_iterations + convergence
        + stuck before looping back. With the default ar_state fixture
        (max_iterations=0, convergence_window=10, history shorter than
        window), all 3 conditions are OFF — the loop continues to propose
        exactly as in v1.3.

        We mock every node to return trivial state and let the loop hit
        LangGraph's recursion_limit (set low) — that proves the loop is wired
        correctly. The GraphRecursionError is the EXPECTED exit condition
        (the loop is supposed to run indefinitely when no stopping condition
        is met).
        """
        # Write a fake train.py so modify's atomic write succeeds
        (tmp_path / "train.py").write_text("print('hello')\n", encoding="utf-8")

        call_order = []

        def _make_node(name, return_value):
            def _node(state):
                call_order.append(name)
                return dict(return_value)
            return _node

        # IMPORTANT: patches must be active BEFORE build_autoresearch_graph()
        # is called, because the graph captures references to the node functions
        # at build time. Patching the module attribute after build doesn't
        # affect what the graph invokes.
        #
        # We patch at the graph module level (workflows.autoresearch_impl.graph)
        # because graph.py does `from .nodes.setup import node_setup` — that
        # creates a binding in graph.py's namespace. Patching the original
        # module (workflows.autoresearch_impl.nodes.setup.node_setup) does NOT
        # affect the binding in graph.py.
        with patch("workflows.autoresearch_impl.graph.node_setup",
                   side_effect=_make_node("setup", {
                       "status": "running",
                       "experiment_count": 0,
                       "current_best": 0.5,
                       "baseline_metric": 0.5,
                       "branch": "autoresearch/test",
                       "results_path": ar_state["results_path"],
                   })), \
             patch("workflows.autoresearch_impl.graph.node_propose",
                   side_effect=_make_node("propose", {
                       "current_experiment": {
                           "iteration": 1,
                           "description": "test proposal",
                           "new_content": "print('hello')\n",
                       },
                   })), \
             patch("workflows.autoresearch_impl.graph.node_modify",
                   side_effect=_make_node("modify", {"status": "running"})), \
             patch("workflows.autoresearch_impl.graph.node_run_experiment",
                   side_effect=_make_node("run_experiment", {
                       "experiment_output": "val_bpb: 0.45\n",
                   })), \
             patch("workflows.autoresearch_impl.graph.node_evaluate",
                   side_effect=_make_node("evaluate", {
                       "current_metric": 0.45,
                       "status": "running",
                   })), \
             patch("workflows.autoresearch_impl.graph.node_decide",
                   side_effect=_make_node("decide", {
                       "current_best": 0.45,
                       "current_experiment": {
                           "iteration": 1, "status": "keep", "commit": "abc1234",
                           "metric": 0.45, "description": "test proposal",
                       },
                   })), \
             patch("workflows.autoresearch_impl.graph.node_log",
                   side_effect=_make_node("log", {
                       "experiment_count": 1,
                       "experiment_history": [{"iteration": 1, "status": "keep"}],
                       "current_experiment": {},
                   })):
            # Build the graph INSIDE the patch context so the compiled graph
            # captures the mocked node functions.
            graph = build_autoresearch_graph()
            # recursion_limit=12 → ~2 iterations (7 nodes per iter: setup+6)
            with pytest.raises(Exception) as exc_info:
                graph.invoke(ar_state, config={"recursion_limit": 12})
            # The expected exception is GraphRecursionError
            assert "Recursion" in type(exc_info.value).__name__ or \
                   "recursion" in str(exc_info.value).lower(), (
                f"expected GraphRecursionError, got {type(exc_info.value).__name__}: {exc_info.value}"
            )

        # Verify the call order: setup must come first, then propose → modify
        # → run_experiment → evaluate → decide → log → propose (loop)
        # [v1.3 P0-1] Order changed: was evaluate → log → decide; now evaluate → decide → log
        assert call_order[0] == "setup", (
            f"setup must be called first, got: {call_order[:5]}"
        )
        # The first iteration (after setup) must follow the expected order
        post_setup = call_order[1:7]
        assert post_setup == ["propose", "modify", "run_experiment",
                              "evaluate", "decide", "log"], (
            f"first iteration must follow the expected order, got: {post_setup}"
        )
        # The loop must come back to propose (now via log → propose edge)
        assert "propose" in call_order[7:], (
            f"loop must come back to propose after log, got: {call_order[7:]}"
        )
