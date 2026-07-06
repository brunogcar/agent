"""tests/workflows/data/test_critique.py
Tests for node_critique — context= usage, empty-output skip, failure logging.

NOTE: agent is imported INSIDE node_critique, so we patch at the SOURCE module
(tools.agent.agent).
"""
from __future__ import annotations

from unittest.mock import patch

from workflows.data_impl.nodes.critique import node_critique


class TestNodeCritique:
    def test_calls_agent_with_action_dispatch(self, base_state):
        """[Regression] node_critique must call agent(action='dispatch')."""
        base_state["output"] = "6"
        with patch("tools.agent.agent") as mock_agent:
            mock_agent.return_value = {"status": "success", "text": "Output is correct."}
            node_critique(base_state)

        assert mock_agent.called, "agent() must be called from node_critique"
        _, kwargs = mock_agent.call_args
        assert kwargs.get("action") == "dispatch", (
            "agent() must be called with action='dispatch' (regresses the v1.5 fix)"
        )
        assert kwargs.get("role") == "critique"

    def test_uses_context_not_content(self, base_state):
        """[Fix #4] Must pass the code output via context= (text), not content= (image)."""
        base_state["output"] = "6"
        with patch("tools.agent.agent") as mock_agent:
            mock_agent.return_value = {"status": "success", "text": "ok"}
            node_critique(base_state)
            _, kwargs = mock_agent.call_args
            assert "context" in kwargs, "node_critique must pass context= for text"
            assert "content" not in kwargs, (
                "node_critique must not pass content= (content is for base64 images)"
            )
            assert "6" in kwargs["context"]

    def test_success_returns_result_with_analysis(self, base_state):
        base_state["output"] = "6"
        with patch("tools.agent.agent") as mock_agent:
            mock_agent.return_value = {"status": "success", "text": "Looks good."}
            out = node_critique(base_state)
        assert "OUTPUT:\n6" in out["result"]
        assert "ANALYSIS:\nLooks good." in out["result"]
        # [Fix #1] Partial dict.
        assert "goal" not in out

    def test_empty_output_skips_critique(self, base_state):
        """[Fix #6] Empty output skips critique (and is now logged, not silent)."""
        base_state["output"] = ""
        with patch("tools.agent.agent") as mock_agent:
            out = node_critique(base_state)
        assert mock_agent.called is False, "agent() must not run when output is empty"
        assert out == {}, "Empty-output skip must return an empty partial dict"

    def test_critique_failure_logs_and_uses_output(self, base_state):
        """[Fix #7] Critique failure must log via tracer.error and fall back to raw output."""
        base_state["output"] = "6"
        with patch("tools.agent.agent") as mock_agent, \
             patch("core.tracer.tracer.error") as mock_error:
            mock_agent.return_value = {"status": "error", "error": "model timeout"}
            out = node_critique(base_state)
        assert out == {"result": "6"}, "Failed critique must fall back to raw output"
        assert mock_error.called, "Critique failure must be logged via tracer.error"

    def test_agent_exception_is_graceful(self, base_state):
        """[Fix #8] An unexpected agent() exception must not crash the workflow."""
        base_state["output"] = "6"
        with patch("tools.agent.agent") as mock_agent, \
             patch("core.tracer.tracer.error") as mock_error:
            mock_agent.side_effect = RuntimeError("agent exploded")
            out = node_critique(base_state)
        assert out == {"result": "6"}
        assert mock_error.called, "agent() exception must be logged via tracer.error"
