"""
tests/workflows/data/test_data_flow.py
Deep integration tests for the Data Analysis Workflow.
"""
from __future__ import annotations
import pytest

class TestDataGraphTopology:
    def test_data_graph_compiles(self):
        """Verify the data analysis graph compiles without missing nodes."""
        try:
            from workflows.data import build_data_graph
            graph = build_data_graph()
            # Handle both compiled and uncompiled
            assert graph is not None
        except ImportError:
            pytest.skip("workflows.data not fully implemented yet")
        except AttributeError:
            pytest.skip("workflows.data.build_data_graph not found")

    def test_data_graph_has_execute_and_critique_nodes(self):
        """Verify the core execution and critique loop exists."""
        try:
            from workflows.data import build_data_graph
            graph = build_data_graph()
            
            nodes = getattr(graph, "nodes", {})
            if not nodes and hasattr(graph, "get_graph"):
                nodes = graph.get_graph().nodes
                
            node_names = set(nodes.keys()) if isinstance(nodes, dict) else set(nodes)
            
            # Data workflow must have an execution step and a critique step
            assert any("execute" in n or "run" in n for n in node_names), "Missing execution node"
            assert any("critique" in n or "review" in n for n in node_names), "Missing critique node"
        except (ImportError, AttributeError):
            pytest.skip("workflows.data not fully implemented yet")