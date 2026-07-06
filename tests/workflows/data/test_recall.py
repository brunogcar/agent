"""tests/workflows/data/test_recall.py
Tests for node_recall — memory recall with graceful failure.
"""
from __future__ import annotations

from unittest.mock import patch

from workflows.data_impl.nodes.recall import node_recall


class TestNodeRecall:
    def test_returns_memory_context_from_results(self, base_state):
        results = [{"type": "episodic", "text": "prev sales analysis"}]
        with patch("core.memory_engine.memory") as mock_memory:
            mock_memory.recall.return_value = results
            out = node_recall(base_state)

        assert out == {"memory_context": "[episodic] prev sales analysis"}
        # [Fix #1] Partial dict — must NOT echo back unchanged state keys.
        assert "goal" not in out
        assert "trace_id" not in out

    def test_no_results_returns_empty_context(self, base_state):
        with patch("core.memory_engine.memory") as mock_memory:
            mock_memory.recall.return_value = []
            out = node_recall(base_state)
        assert out == {"memory_context": ""}

    def test_memory_failure_is_graceful(self, base_state):
        """[Fix #8] A memory backend failure must not crash the workflow."""
        with patch("core.memory_engine.memory") as mock_memory:
            mock_memory.recall.side_effect = RuntimeError("chromadb down")
            out = node_recall(base_state)
        assert out == {"memory_context": ""}

    def test_recall_passes_goal_as_query(self, base_state):
        with patch("core.memory_engine.memory") as mock_memory:
            mock_memory.recall.return_value = []
            node_recall(base_state)
            _, kwargs = mock_memory.recall.call_args
            assert kwargs["query"] == "Compute sum of list"
            assert kwargs["trace_id"] == "t1"
