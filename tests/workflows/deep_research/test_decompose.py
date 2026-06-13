"""Tests for the decompose node."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from workflows.deep_research_core.nodes.decompose import node_decompose, _parse_sub_queries


def test_parse_sub_queries_json_steps():
    text = json.dumps({"steps": [{"description": "q1"}, {"description": "q2"}]})
    assert _parse_sub_queries(text) == ["q1", "q2"]


def test_parse_sub_queries_json_list():
    text = json.dumps(["q1", "q2", "q3"])
    assert _parse_sub_queries(text) == ["q1", "q2", "q3"]


def test_parse_sub_queries_line_heuristic():
    text = "- q1\n- q2\n- q3\n"
    assert _parse_sub_queries(text) == ["q1", "q2", "q3"]


def test_parse_sub_queries_empty():
    assert _parse_sub_queries("") == []


def test_node_decompose_success():
    state = {"goal": "test goal", "trace_id": "t1"}
    mock_result = {"status": "success", "text": json.dumps({"steps": [{"description": "q1"}]}), "role": "plan", "model": "m", "elapsed": 1}

    with patch("workflows.deep_research_core.nodes.decompose.agent", return_value=mock_result):
        result = node_decompose(state)
        assert result["pending_queries"] == ["q1"]


def test_node_decompose_fallback_on_failure():
    state = {"goal": "test goal", "trace_id": "t1"}
    mock_result = {"status": "error", "error": "llm failed"}

    with patch("workflows.deep_research_core.nodes.decompose.agent", return_value=mock_result):
        result = node_decompose(state)
        assert result["pending_queries"] == ["test goal"]


def test_node_decompose_fallback_on_bad_json():
    state = {"goal": "test goal", "trace_id": "t1"}
    mock_result = {"status": "success", "text": "not json at all", "role": "plan", "model": "m", "elapsed": 1}

    with patch("workflows.deep_research_core.nodes.decompose.agent", return_value=mock_result):
        result = node_decompose(state)
        assert result["pending_queries"] == ["test goal"]
