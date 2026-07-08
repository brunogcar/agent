"""tests/workflows/research/test_graph.py
Tests for research graph topology, WORKFLOW_METADATA, and subpackage structure.
"""
from __future__ import annotations

import inspect
import ast

from workflows.research import build_research_graph


def _strip_comments_and_docstrings(source: str) -> str:
    """Strip docstrings and comments from source code for pattern matching."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr) and
                isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
    code_only = ast.unparse(tree)
    code_lines = [line for line in code_only.split("\n") if not line.strip().startswith("#")]
    return "\n".join(code_lines)


class TestResearchGraphTopology:
    def test_graph_builds_without_errors(self):
        """The LangGraph must build successfully."""
        graph = build_research_graph()
        assert graph is not None

    def test_graph_contains_parallel_scrape_node(self):
        """Verify the parallel_scrape node is in the graph."""
        graph = build_research_graph()
        nodes = getattr(graph, "nodes", {})
        if not nodes and hasattr(graph, "get_graph"):
            nodes = graph.get_graph().nodes
        assert "parallel_scrape" in nodes, "parallel_scrape node missing from graph!"
        assert "trim" in nodes, "trim node missing from graph (v1.1)!"


class TestWorkflowMetadata:
    """v1.0: WORKFLOW_METADATA must exist and have correct structure."""

    def test_metadata_exists(self):
        from workflows.research_impl.graph import WORKFLOW_METADATA
        assert isinstance(WORKFLOW_METADATA, dict)
        assert WORKFLOW_METADATA["name"] == "research"
        assert WORKFLOW_METADATA["version"] == "1.1"

    def test_metadata_has_nodes(self):
        from workflows.research_impl.graph import WORKFLOW_METADATA
        nodes = WORKFLOW_METADATA["nodes"]
        assert len(nodes) == 9, f"Expected 9 nodes, got {len(nodes)}"
        node_names = [n["name"] for n in nodes]
        assert "recall" in node_names
        assert "search" in node_names
        assert "parallel_scrape" in node_names
        assert "synthesize" in node_names
        assert "trim" in node_names  # v1.1
        assert "report" in node_names
        assert "store" in node_names
        assert "distill" in node_names
        assert "notify" in node_names

    def test_metadata_has_edges(self):
        from workflows.research_impl.graph import WORKFLOW_METADATA
        edges = WORKFLOW_METADATA["edges"]
        assert len(edges) >= 10, f"Expected at least 10 edges, got {len(edges)}"
        edge_pairs = [(e["from"], e["to"]) for e in edges]
        assert ("recall", "search") in edge_pairs
        assert ("search", "parallel_scrape") in edge_pairs
        assert ("synthesize", "trim") in edge_pairs  # v1.1
        assert ("trim", "report") in edge_pairs       # v1.1
        assert ("notify", "END") in edge_pairs

    def test_metadata_nodes_have_descriptions(self):
        from workflows.research_impl.graph import WORKFLOW_METADATA
        for node in WORKFLOW_METADATA["nodes"]:
            assert "description" in node, f"Node {node['name']} missing description"
            assert len(node["description"]) > 0, f"Node {node['name']} has empty description"


class TestSubpackageStructure:
    """[v1.0 refactor] Verify the research_impl subpackage has the correct structure."""

    def test_routes_module_exists(self):
        from workflows.research_impl import routes
        assert hasattr(routes, "route_after_search")
        assert hasattr(routes, "route_after_synthesize")

    def test_helpers_module_exists(self):
        from workflows.research_impl import helpers
        assert hasattr(helpers, "_scrape_and_summarize")
        assert hasattr(helpers, "_browser_fallback_scrape")
        assert hasattr(helpers, "_is_nested_parallel")

    def test_nodes_module_exists(self):
        from workflows.research_impl.nodes.recall import node_recall
        from workflows.research_impl.nodes.search import node_search
        from workflows.research_impl.nodes.parallel_scrape import node_parallel_scrape
        from workflows.research_impl.nodes.synthesize import node_synthesize
        from workflows.research_impl.nodes.report import node_report
        from workflows.research_impl.nodes.store import node_store
        from workflows.research_impl.nodes.distill import node_distill
        from workflows.research_impl.nodes.notify import node_notify
        assert callable(node_recall)
        assert callable(node_search)
        assert callable(node_parallel_scrape)
        assert callable(node_synthesize)
        assert callable(node_report)
        assert callable(node_store)
        assert callable(node_distill)
        assert callable(node_notify)

    def test_facade_reexports(self):
        """Thin facade must re-export build_research_graph and WORKFLOW_METADATA."""
        from workflows.research import build_research_graph
        from workflows.research import WORKFLOW_METADATA
        assert callable(build_research_graph)
        assert isinstance(WORKFLOW_METADATA, dict)

    def test_all_nodes_are_sync(self):
        """[Architecture] All 9 nodes must be sync (def, not async def)."""
        from workflows.research_impl.nodes.recall import node_recall
        from workflows.research_impl.nodes.search import node_search
        from workflows.research_impl.nodes.parallel_scrape import node_parallel_scrape
        from workflows.research_impl.nodes.synthesize import node_synthesize
        from workflows.research_impl.nodes.report import node_report
        from workflows.research_impl.nodes.store import node_store
        from workflows.research_impl.nodes.distill import node_distill
        from workflows.research_impl.nodes.notify import node_notify
        from workflows.base import trim_state_node
        for name, fn in [("recall", node_recall), ("search", node_search),
                         ("parallel_scrape", node_parallel_scrape), ("synthesize", node_synthesize),
                         ("trim", trim_state_node),
                         ("report", node_report), ("store", node_store),
                         ("distill", node_distill), ("notify", node_notify)]:
            assert not inspect.iscoroutinefunction(fn), (
                f"node_{name} must be sync (def, not async def)"
            )

    def test_store_does_not_truncate_to_800(self):
        """[Fix #7] node_store must NOT contain result[:800] in actual code."""
        from workflows.research_impl.nodes.store import node_store
        source = inspect.getsource(node_store)
        code_str = _strip_comments_and_docstrings(source)
        assert "result[:800]" not in code_str, (
            "node_store must not truncate to 800 chars — was fixed in v1.0"
        )

    def test_notify_artifacts_are_strings(self):
        """[Fix #10] node_notify must return artifacts as list of strings, not dicts."""
        from workflows.research_impl.nodes.notify import node_notify
        source = inspect.getsource(node_notify)
        code_str = _strip_comments_and_docstrings(source)
        # Must NOT have the old dict pattern
        assert '[{"sources":' not in code_str, (
            "node_notify must not return artifacts as list of dicts"
        )

    def test_search_deduplicates_urls(self):
        """[Fix #12] node_search must use a set or seen_urls for deduplication."""
        from workflows.research_impl.nodes.search import node_search
        source = inspect.getsource(node_search)
        code_str = _strip_comments_and_docstrings(source)
        assert "seen_urls" in code_str, (
            "node_search must use seen_urls for URL deduplication"
        )

    def test_parallel_scrape_uses_wait_not_as_completed(self):
        """[Fix #4] node_parallel_scrape must use wait(), not as_completed()."""
        from workflows.research_impl.nodes.parallel_scrape import node_parallel_scrape
        source = inspect.getsource(node_parallel_scrape)
        code_str = _strip_comments_and_docstrings(source)
        assert "as_completed" not in code_str, (
            "node_parallel_scrape must use concurrent.futures.wait(), not as_completed()"
        )
        assert "wait(" in code_str, (
            "node_parallel_scrape must use concurrent.futures.wait()"
        )

    def test_parallel_scrape_cancels_futures(self):
        """[Fix #5] node_parallel_scrape must cancel pending futures on timeout."""
        from workflows.research_impl.nodes.parallel_scrape import node_parallel_scrape
        source = inspect.getsource(node_parallel_scrape)
        code_str = _strip_comments_and_docstrings(source)
        assert ".cancel()" in code_str, (
            "node_parallel_scrape must call future.cancel() on timed-out futures"
        )

    def test_distill_no_dead_status_check(self):
        """[Fix #8] node_distill must not have dead status==failed check."""
        from workflows.research_impl.nodes.distill import node_distill
        source = inspect.getsource(node_distill)
        code_str = _strip_comments_and_docstrings(source)
        # The dead code was: if state.get("status") == "failed": return state
        assert 'state.get("status") == "failed"' not in code_str, (
            "node_distill must not have dead status==failed check"
        )

    def test_synthesize_uses_action_dispatch(self):
        """node_synthesize must pass action='dispatch' to agent()."""
        from workflows.research_impl.nodes.synthesize import node_synthesize
        source = inspect.getsource(node_synthesize)
        code_str = _strip_comments_and_docstrings(source)
        assert 'action' in code_str and 'dispatch' in code_str, (
            "node_synthesize must pass action='dispatch' to agent()"
        )
