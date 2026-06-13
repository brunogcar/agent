"""tests/workflows/deep_research/test_decompose.py"""
import pytest
from workflows.deep_research_core.nodes.decompose import node_decompose, _parse_sub_queries


def test_parse_sub_queries_json_object():
    raw = '{"steps": [{"description": "q1"}, {"description": "q2"}]}'
    assert _parse_sub_queries(raw, "fallback") == ["q1", "q2"]


def test_parse_sub_queries_json_list():
    raw = '["q1", "q2"]'
    assert _parse_sub_queries(raw, "fallback") == ["q1", "q2"]


def test_parse_sub_queries_bullet_lines():
    raw = "- q1\n- q2\n- q3"
    assert _parse_sub_queries(raw, "fallback") == ["q1", "q2", "q3"]


def test_parse_sub_queries_numbered_lines():
    raw = "1. q1\n2. q2\n6. q6"
    assert _parse_sub_queries(raw, "fallback") == ["q1", "q2", "q6"]


def test_parse_sub_queries_step_pattern():
    raw = "Step 1: q1\nStep 2: q2"
    assert _parse_sub_queries(raw, "fallback") == ["q1", "q2"]


def test_parse_sub_queries_fallback():
    raw = "just some prose"
    assert _parse_sub_queries(raw, "fallback") == []


def test_node_decompose_success(mocker):
    state = {"goal": "test goal", "trace_id": "t1"}
    mocker.patch(
        "workflows.deep_research_core.nodes.decompose.llm.complete",
        return_value=mocker.Mock(ok=True, text='{"steps": [{"description": "q1"}]}'),
    )
    result = node_decompose(state)
    assert result["sub_queries"] == ["q1"]


def test_node_decompose_llm_failure(mocker):
    state = {"goal": "test goal", "trace_id": "t1"}
    mocker.patch(
        "workflows.deep_research_core.nodes.decompose.llm.complete",
        return_value=mocker.Mock(ok=False, error="timeout"),
    )
    result = node_decompose(state)
    assert result["sub_queries"] == ["test goal"]
