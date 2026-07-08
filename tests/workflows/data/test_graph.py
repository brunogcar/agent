"""tests/workflows/data/test_graph.py
Tests for data graph topology, WORKFLOW_METADATA, and subpackage structure.
"""
from __future__ import annotations

import inspect
import ast

from workflows.data import build_data_graph
from workflows.data_impl.graph import WORKFLOW_METADATA


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


class TestDataGraphTopology:
    def test_data_graph_compiles(self):
        """Verify the data analysis graph compiles without missing nodes."""
        graph = build_data_graph()
        assert graph is not None
        assert hasattr(graph, "invoke")

    def test_data_graph_has_execute_and_critique_nodes(self):
        """Verify the core execution and critique loop exists."""
        graph = build_data_graph()
        nodes = getattr(graph, "nodes", {})
        if not nodes and hasattr(graph, "get_graph"):
            nodes = graph.get_graph().nodes
        node_names = set(nodes.keys()) if isinstance(nodes, dict) else set(nodes)
        assert any("execute" in n or "run" in n for n in node_names), "Missing execution node"
        assert any("critique" in n or "review" in n for n in node_names), "Missing critique node"
        assert any("trim" in n for n in node_names), "Missing trim node (v1.1)"


class TestWorkflowMetadata:
    """v1.0: WORKFLOW_METADATA must exist and have correct structure."""

    def test_metadata_exists(self):
        assert isinstance(WORKFLOW_METADATA, dict)
        assert WORKFLOW_METADATA["name"] == "data"
        assert WORKFLOW_METADATA["version"] == "1.1"

    def test_metadata_has_nodes(self):
        nodes = WORKFLOW_METADATA["nodes"]
        assert len(nodes) == 6, f"Expected 6 nodes, got {len(nodes)}"
        node_names = [n["name"] for n in nodes]
        assert "recall" in node_names
        assert "execute" in node_names
        assert "critique" in node_names
        assert "trim" in node_names  # v1.1: trim node between critique and store
        assert "store" in node_names
        assert "notify" in node_names

    def test_metadata_has_edges(self):
        edges = WORKFLOW_METADATA["edges"]
        assert len(edges) >= 6, f"Expected at least 6 edges, got {len(edges)}"
        edge_pairs = [(e["from"], e["to"]) for e in edges]
        assert ("recall", "execute") in edge_pairs
        assert ("execute", "critique") in edge_pairs
        assert ("execute", "END") in edge_pairs
        assert ("critique", "trim") in edge_pairs  # v1.1
        assert ("trim", "store") in edge_pairs      # v1.1
        assert ("notify", "END") in edge_pairs

    def test_metadata_nodes_have_descriptions(self):
        for node in WORKFLOW_METADATA["nodes"]:
            assert "description" in node, f"Node {node['name']} missing description"
            assert len(node["description"]) > 0, f"Node {node['name']} has empty description"


class TestSubpackageStructure:
    """[v1.0 refactor] Verify the data_impl subpackage has the correct structure
    and that the audit fixes are present in source."""

    def test_routes_module_exists(self):
        from workflows.data_impl import routes
        assert hasattr(routes, "route_after_execute")
        # [Fix #10] route_after_critique was dead code (always returned "store")
        # and must be removed.
        assert not hasattr(routes, "route_after_critique"), (
            "route_after_critique was dead code and must be removed"
        )

    def test_helpers_module_exists(self):
        from workflows.data_impl import helpers
        assert hasattr(helpers, "_extract_code_from_response")

    def test_nodes_module_exists(self):
        from workflows.data_impl.nodes.recall import node_recall
        from workflows.data_impl.nodes.execute import node_execute
        from workflows.data_impl.nodes.critique import node_critique
        from workflows.data_impl.nodes.store import node_store
        from workflows.data_impl.nodes.notify import node_notify
        assert callable(node_recall)
        assert callable(node_execute)
        assert callable(node_critique)
        assert callable(node_store)
        assert callable(node_notify)

    def test_facade_reexports(self):
        """Thin facade must re-export build_data_graph and WORKFLOW_METADATA."""
        from workflows.data import build_data_graph as bg
        from workflows.data import WORKFLOW_METADATA as wm
        assert callable(bg)
        assert isinstance(wm, dict)

    def test_all_nodes_are_sync(self):
        """[Architecture] All 5 nodes must be sync (def, not async def)."""
        from workflows.data_impl.nodes.recall import node_recall
        from workflows.data_impl.nodes.execute import node_execute
        from workflows.data_impl.nodes.critique import node_critique
        from workflows.data_impl.nodes.store import node_store
        from workflows.data_impl.nodes.notify import node_notify
        for name, fn in [("recall", node_recall), ("execute", node_execute),
                         ("critique", node_critique), ("store", node_store),
                         ("notify", node_notify)]:
            assert not inspect.iscoroutinefunction(fn), (
                f"node_{name} must be sync (def, not async def)"
            )

    def test_critique_uses_context_not_content(self):
        """[Fix #4] node_critique must pass context= (text), not content= (image)."""
        from workflows.data_impl.nodes.critique import node_critique
        source = inspect.getsource(node_critique)
        code_str = _strip_comments_and_docstrings(source)
        assert "context=" in code_str, (
            "node_critique must pass context= to agent() for text"
        )
        assert "content=" not in code_str, (
            "node_critique must not pass content= (content is for base64 images)"
        )

    def test_critique_logs_failure_via_tracer_error(self):
        """[Fix #7] node_critique must log critique failure via tracer.error (was silent)."""
        from workflows.data_impl.nodes.critique import node_critique
        source = inspect.getsource(node_critique)
        code_str = _strip_comments_and_docstrings(source)
        assert "tracer.error" in code_str, (
            "node_critique must use tracer.error() on critique failure (was silent fallback)"
        )

    def test_store_checks_code_generated(self):
        """[Fix #5] node_store must check code_generated before procedural storage."""
        from workflows.data_impl.nodes.store import node_store
        source = inspect.getsource(node_store)
        code_str = _strip_comments_and_docstrings(source)
        assert "code_generated" in code_str, (
            "node_store must check code_generated so user-provided code is not "
            "stored as procedural memory"
        )

    def test_notify_wraps_notify_call(self):
        """[Fix #10] node_notify must log notify() failure via tracer.error."""
        from workflows.data_impl.nodes.notify import node_notify
        source = inspect.getsource(node_notify)
        code_str = _strip_comments_and_docstrings(source)
        assert "tracer.error" in code_str, (
            "node_notify must use tracer.error() on notify() failure"
        )

    def test_execute_no_inline_import_re(self):
        """[Fix #9] node_execute must not have an inline `import re` (moved to helper)."""
        from workflows.data_impl.nodes.execute import node_execute
        source = inspect.getsource(node_execute)
        code_str = _strip_comments_and_docstrings(source)
        assert "import re" not in code_str, (
            "node_execute must not inline `import re` — code extraction lives in helpers"
        )

    def test_execute_sets_exec_error_on_failure(self):
        """[Fix #2] node_execute source must set exec_error on failure paths."""
        from workflows.data_impl.nodes.execute import node_execute
        source = inspect.getsource(node_execute)
        code_str = _strip_comments_and_docstrings(source)
        assert "exec_error" in code_str, (
            "node_execute must set exec_error so route_after_execute routes failures to END"
        )
