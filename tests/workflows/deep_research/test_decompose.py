"""tests/workflows/deep_research/test_decompose.py
Tests for node_decompose_goal — goal decomposition into sub-queries.
"""
from __future__ import annotations

from workflows.deep_research_impl.nodes.decompose import node_decompose_goal, _parse_sub_queries


class TestParseSubQueries:
    def test_json_list(self):
        assert _parse_sub_queries('["q1", "q2", "q3"]') == ["q1", "q2", "q3"]

    def test_json_object(self):
        assert _parse_sub_queries('{"queries": ["a", "b"]}') == ["a", "b"]

    def test_fallback_to_empty_on_non_json(self):
        assert _parse_sub_queries("not json at all") == []


class TestNodeDecomposeGoal:
    def test_empty_goal_returns_empty_queries(self):
        state = {"goal": "", "trace_id": "t1"}
        result = node_decompose_goal(state)
        assert result["sub_queries"] == []
        assert result["pending_queries"] == []

    def test_returns_queries_from_llm(self, mocker):
        mocker.patch(
            "workflows.deep_research_impl.nodes.decompose.llm.complete",
            return_value=mocker.MagicMock(ok=True, text='["q1", "q2"]'),
        )
        state = {"goal": "What is X?", "trace_id": "t1"}
        result = node_decompose_goal(state)
        assert result["sub_queries"] == ["q1", "q2"]
        assert result["pending_queries"] == ["q1", "q2"]
