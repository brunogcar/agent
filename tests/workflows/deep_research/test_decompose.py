"""tests/workflows/deep_research/test_decompose.py"""
import pytest
from workflows.deep_research_impl.nodes.decompose import node_decompose_goal, _parse_sub_queries


def test_parse_sub_queries_json_list():
    raw = '["q1", "q2", "q3"]'
    assert _parse_sub_queries(raw) == ["q1", "q2", "q3"]


def test_parse_sub_queries_json_object():
    raw = '{"queries": ["a", "b"]}'
    assert _parse_sub_queries(raw) == ["a", "b"]


def test_parse_sub_queries_fallback_to_goal():
    raw = "not json at all"
    assert _parse_sub_queries(raw) == []


def test_node_decompose_empty_goal():
    state = {"goal": "", "trace_id": "t1"}
    result = node_decompose_goal(state)
    assert result["sub_queries"] == []
    assert result["pending_queries"] == []


def test_node_decompose_returns_queries(mocker):
    mocker.patch(
        "workflows.deep_research_impl.nodes.decompose.llm.complete",
        return_value=mocker.MagicMock(ok=True, text='["q1", "q2"]'),
    )
    state = {"goal": "What is X?", "trace_id": "t1"}
    result = node_decompose_goal(state)
    assert result["sub_queries"] == ["q1", "q2"]
    assert result["pending_queries"] == ["q1", "q2"]
