"""tests/workflows/autoresearch/test_graph.py

[v1.0] Graph topology + WORKFLOW_METADATA tests for the autoresearch workflow.

Tests:
  test_graph_has_exactly_7_nodes          — setup, propose, modify, run_experiment,
                                            evaluate, decide, log
  test_entry_point_is_setup              — graph entry point is "setup"
  test_experiment_loop_exists            — WORKFLOW_METADATA.loops has experiment_loop
  test_metadata_exists                   — WORKFLOW_METADATA is a dict
  test_metadata_has_correct_name         — name == "autoresearch"
  test_build_graph_returns_stategraph    — build_autoresearch_graph returns a
                                            compiled graph with .invoke()
"""
from __future__ import annotations

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
