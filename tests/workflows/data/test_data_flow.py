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


class TestActionDispatchRegression:
    """Regression tests for v1.5 fix: agent() must be called with action='dispatch'.

    Previously node_execute (code-gen path) and node_critique called agent()
    without action='dispatch'. The agent() facade requires action='dispatch'
    for LLM calls — without it, both calls return 'Unknown action' error.

    Impact before fix:
      - node_execute code-gen path ALWAYS failed (couldn't generate code from goal)
      - node_critique silently fell through (critique was dead code)
    """

    def test_node_execute_calls_agent_with_action_dispatch(self):
        """When code generation is needed, agent() must be called with action='dispatch'."""
        from unittest.mock import patch, MagicMock
        from workflows.data import node_execute

        # Empty code triggers the code-generation path
        state = {
            "goal": "Compute sum of list",
            "trace_id": "t1",
            "code": "",
            "memory_context": "",
        }

        # NOTE: agent and python are imported INSIDE node_execute
        # (`from tools.agent import agent`, `from tools.python import python`),
        # so we patch at the source modules, not at workflows.data.<name>.
        with patch("tools.agent.agent") as mock_agent, \
             patch("tools.python.python") as mock_python:
            mock_agent.return_value = {
                "status": "success",
                "text": "```python\nprint(sum([1,2,3]))\n```",
                "parsed": {"patch": "print(sum([1,2,3]))"},
                "elapsed": 0.1,
            }
            mock_python.return_value = {"status": "success", "output": "6"}
            node_execute(state)

        assert mock_agent.called, "agent() must be called from node_execute code-gen path"
        _, kwargs = mock_agent.call_args
        assert kwargs.get("action") == "dispatch", (
            f"agent() must be called with action='dispatch'; got action={kwargs.get('action')!r}. "
            f"This regresses the v1.5 fix — without action='dispatch', code generation always fails."
        )

    def test_node_critique_calls_agent_with_action_dispatch(self):
        """node_critique must call agent() with action='dispatch'."""
        from unittest.mock import patch
        from workflows.data import node_critique

        state = {
            "goal": "Compute sum of list",
            "trace_id": "t1",
            "output": "6",
        }

        # NOTE: agent is imported INSIDE node_critique — patch at source.
        with patch("tools.agent.agent") as mock_agent:
            mock_agent.return_value = {
                "status": "success",
                "text": "Output looks correct.",
                "elapsed": 0.1,
            }
            node_critique(state)

        assert mock_agent.called, "agent() must be called from node_critique"
        _, kwargs = mock_agent.call_args
        assert kwargs.get("action") == "dispatch", (
            f"agent() must be called with action='dispatch'; got action={kwargs.get('action')!r}. "
            f"This regresses the v1.5 fix — without action='dispatch', critique is dead code."
        )