"""tests/workflows/deep_research/test_recall.py
Tests for _node_recall — memory recall with graceful failure.
"""
from __future__ import annotations


class TestNodeRecall:
    def test_returns_memory_context_from_results(self, mocker):
        from workflows.deep_research_impl.graph import _node_recall
        mocker.patch(
            "workflows.deep_research_impl.graph.memory.recall",
            return_value=[{"type": "semantic", "score": 0.85, "text": "Previous research on async"}],
        )
        state = {"goal": "Python async frameworks", "trace_id": "test-123"}
        result = _node_recall(state)
        mock_recall = mocker.patch  # just for assertion formatting
        assert "Previous research on async" in result.get("memory_context", "")

    def test_recall_passes_correct_args(self, mocker):
        from workflows.deep_research_impl.graph import _node_recall
        mock_recall = mocker.patch("workflows.deep_research_impl.graph.memory.recall")
        mock_recall.return_value = [
            {"type": "semantic", "score": 0.85, "text": "ctx"},
        ]
        state = {"goal": "Python async frameworks", "trace_id": "test-123"}
        _node_recall(state)
        mock_recall.assert_called_once_with(
            query="Python async frameworks",
            top_k=5,
            trace_id="test-123",
        )

    def test_no_results_returns_empty_context(self, mocker):
        from workflows.deep_research_impl.graph import _node_recall
        mocker.patch("workflows.deep_research_impl.graph.memory.recall", return_value=[])
        state = {"goal": "g", "trace_id": "t1"}
        result = _node_recall(state)
        assert result == {"memory_context": ""}

    def test_graceful_on_failure(self, mocker):
        """Memory failure must return empty context (non-fatal)."""
        from workflows.deep_research_impl.graph import _node_recall
        mocker.patch(
            "workflows.deep_research_impl.graph.memory.recall",
            side_effect=Exception("DB down"),
        )
        state = {"goal": "Python async frameworks", "trace_id": "test-123"}
        result = _node_recall(state)
        assert result.get("memory_context", "") == ""


class TestRecallLogsFailure:
    """v1.1/P1 #8: _node_recall must log memory failures via tracer.error."""

    def test_recall_logs_error_on_memory_failure(self, mocker):
        from workflows.deep_research_impl.graph import _node_recall
        mocker.patch(
            "workflows.deep_research_impl.graph.memory.recall",
            side_effect=RuntimeError("chromadb down"),
        )
        mock_error = mocker.patch("core.tracer.tracer.error")
        state = {"goal": "g", "trace_id": "t1"}
        result = _node_recall(state)
        assert result == {"memory_context": ""}, "Failure must still return empty context"
        assert mock_error.called, "Memory failure must be logged via tracer.error"
