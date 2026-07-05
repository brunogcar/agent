"""tests/workflows/research/test_synthesize.py
Tests for node_synthesize — agent dispatch, error handling, style fix.
"""
from __future__ import annotations

import inspect
import ast
from unittest.mock import patch

from workflows.research_impl.nodes.synthesize import node_synthesize


def _base_state():
    return {
        "workflow": "research", "goal": "test", "trace_id": "t1",
        "status": "running", "error": "", "result": "", "artifacts": [],
        "retries": 0, "search_results": ""
    }


class TestNodeSynthesizeActionDispatch:
    """Regression tests for agent() action='dispatch' fix."""

    def test_node_synthesize_calls_agent_with_action_dispatch(self):
        """agent() must be invoked with action='dispatch'."""
        state = _base_state()
        state["search_results"] = "### [Source 1] Title\nURL: http://a.com\nGood data"

        with patch("tools.agent.agent") as mock_agent:
            mock_agent.return_value = {
                "status": "success",
                "text": "synthesized answer",
                "elapsed": 0.1,
            }
            node_synthesize(state)

        assert mock_agent.called, "agent() must be called from node_synthesize"
        _, kwargs = mock_agent.call_args
        assert kwargs.get("action") == "dispatch", (
            f"agent() must be called with action='dispatch'; got action={kwargs.get('action')!r}."
        )

    def test_node_synthesize_propagates_success_when_action_dispatch_present(self):
        """With action='dispatch', a successful agent() response must propagate to state['result']."""
        state = _base_state()
        state["search_results"] = "### [Source 1] Title\nURL: http://a.com\nGood data"

        with patch("tools.agent.agent") as mock_agent:
            mock_agent.return_value = {
                "status": "success",
                "text": "real synthesized answer",
                "elapsed": 0.1,
            }
            result = node_synthesize(state)

        assert result.get("result") == "real synthesized answer", (
            "node_synthesize must populate state['result'] from agent response."
        )


class TestNodeSynthesizeErrorCheck:
    """Style fix: not r.get('status') == 'success' → r.get('status') != 'success'."""

    def test_synthesize_uses_explicit_not_equal(self):
        """node_synthesize must use != 'success' in actual code, not 'not ... == "success"'."""
        source = inspect.getsource(node_synthesize)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                    node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
        code_only = ast.unparse(tree)
        code_lines = [line for line in code_only.split("\n") if not line.strip().startswith("#")]
        code_str = "\n".join(code_lines)
        assert "not r.get" not in code_str or "!=" in code_str, (
            "node_synthesize should use r.get('status') != 'success' in actual code."
        )
