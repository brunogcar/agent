"""tests/workflows/deep_research/test_store.py
Tests for _node_store — memory storage (full text, non-fatal).
"""
from __future__ import annotations


class TestNodeStore:
    def test_calls_both_memory_types(self, mocker):
        """_node_store must call store_semantic and store_episodic.

        [v1.1/P1 #10] store_semantic receives the FULL result (was result[:800]).
        [v1.1/P1 #7] Returns {} (partial dict, side effects only).
        """
        from workflows.deep_research_impl.graph import _node_store
        mock_semantic = mocker.patch("workflows.deep_research_impl.graph.memory.store_semantic")
        mock_episodic = mocker.patch("workflows.deep_research_impl.graph.memory.store_episodic")
        state = {
            "result": "Test research result",
            "goal": "What is LangGraph?",
            "status": "success",
            "trace_id": "test-123",
        }
        result = _node_store(state)
        mock_semantic.assert_called_once_with(
            text="Deep Research: Test research result",
            importance=6,
            tags="deep_research",
            trace_id="test-123",
        )
        mock_episodic.assert_called_once_with(
            text="Completed deep research workflow: 'What is LangGraph?'",
            importance=5,
            goal="What is LangGraph?",
            outcome="success",
            tools_used="tavily,web,browser,llm",
            trace_id="test-123",
        )
        assert result == {}


class TestStoreFullText:
    """v1.1/P1 #10: _node_store must store the FULL result, not result[:800]."""

    def test_store_does_not_truncate_to_800(self, mocker):
        from workflows.deep_research_impl.graph import _node_store
        mock_semantic = mocker.patch("workflows.deep_research_impl.graph.memory.store_semantic")
        mocker.patch("workflows.deep_research_impl.graph.memory.store_episodic")
        long_result = "X" * 2000  # > 800 chars
        state = {
            "result": long_result, "goal": "g", "status": "success", "trace_id": "t1",
        }
        _node_store(state)
        stored_text = mock_semantic.call_args.kwargs["text"]
        assert len(stored_text) > 800, "store_semantic must not truncate to 800 chars"
        assert long_result in stored_text
