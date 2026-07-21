"""tests/workflows/understand/test_graph.py
Tests for understand graph topology and WORKFLOW_METADATA.
"""
from __future__ import annotations

from workflows.understand_impl.graph import build_understand_graph, WORKFLOW_METADATA


def test_build_understand_graph_compiles():
    """Ensure the LangGraph state machine compiles without errors."""
    graph = build_understand_graph()
    assert graph is not None
    assert hasattr(graph, "invoke")


class TestWorkflowMetadata:
    """v1.0: WORKFLOW_METADATA must exist and have correct structure."""

    def test_metadata_exists(self):
        assert isinstance(WORKFLOW_METADATA, dict)
        assert WORKFLOW_METADATA["name"] == "understand"
        # Version is not asserted — it changes every release and updating
        # the test each time is unproductive. Just verify it exists.
        assert "version" in WORKFLOW_METADATA

    def test_metadata_has_nodes(self):
        nodes = WORKFLOW_METADATA["nodes"]
        assert len(nodes) == 4
        node_names = [n["name"] for n in nodes]
        assert "node_init_project" in node_names
        assert "node_discover_files" in node_names
        assert "node_parse_and_store" in node_names
        assert "node_report" in node_names

    def test_metadata_has_edges(self):
        edges = WORKFLOW_METADATA["edges"]
        assert len(edges) >= 4
        edge_pairs = [(e["from"], e["to"]) for e in edges]
        assert ("node_init_project", "node_discover_files") in edge_pairs
        assert ("node_report", "END") in edge_pairs

    def test_metadata_nodes_have_descriptions(self):
        for node in WORKFLOW_METADATA["nodes"]:
            assert "description" in node
            assert len(node["description"]) > 0

    def test_init_edge_is_conditional(self):
        """[v1.4.1 P0-1] The init→discover edge must be marked conditional."""
        edges = WORKFLOW_METADATA["edges"]
        init_edge = next(
            (e for e in edges if e["from"] == "node_init_project"),
            None,
        )
        assert init_edge is not None, "init → discover edge must exist"
        assert init_edge.get("conditional") is True, (
            "init → discover edge must be conditional (route_after_init short-circuits to END on failure)"
        )
        assert "condition" in init_edge, (
            "conditional edge must document its condition string"
        )

    def test_metadata_has_safety_features(self):
        """[v1.4.1 P2-11] WORKFLOW_METADATA must include a safety_features list."""
        assert "safety_features" in WORKFLOW_METADATA, (
            "WORKFLOW_METADATA must declare safety_features for MCP client introspection"
        )
        features = WORKFLOW_METADATA["safety_features"]
        assert isinstance(features, list)
        assert len(features) > 0
        # Spot-check a few of the v1.4.1 hardening features.
        for required in (
            "route_after_init",          # P0-1
            "cancellation_checks",       # P1-6
            "project_scoped_vectors",    # P1-3
            "embedding_batch_errors",    # P1-5
            "errors_capped_at_100",      # P2-10
        ):
            assert required in features, (
                f"safety_features missing required entry: {required}"
            )
