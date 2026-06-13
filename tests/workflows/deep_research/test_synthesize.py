"""tests/workflows/deep_research/test_synthesize.py"""
import pytest
from workflows.deep_research_core.nodes.synthesize import (
    node_synthesize,
    _format_evidence,
    _merge_knowledge,
    _cap_knowledge,
    _parse_score,
)


def test_format_evidence_empty():
    assert _format_evidence([]) == "_(no new evidence this iteration)_"


def test_format_evidence_items():
    ev = [{"title": "T1", "url": "http://x", "summary": "S1"}]
    out = _format_evidence(ev)
    assert "T1" in out and "S1" in out


def test_merge_knowledge_empty_prev():
    assert _merge_knowledge("", "new") == "new"


def test_merge_knowledge_empty_new():
    assert _merge_knowledge("prev", "") == "prev"


def test_merge_knowledge_replaces():
    """Knowledge should be replaced, not concatenated."""
    prev = "old knowledge"
    new = "new synthesis"
    result = _merge_knowledge(prev, new)
    assert result == "new synthesis"
    assert "old knowledge" not in result


def test_cap_knowledge_under_limit():
    kb = "short"
    assert _cap_knowledge(kb, max_chars=100) == "short"


def test_cap_knowledge_over_limit():
    kb = "a" * 10000
    result = _cap_knowledge(kb, max_chars=1000)
    assert "[earlier context truncated]" in result
    assert len(result) <= 1100  # truncated marker + 1000 chars


def test_parse_score_last_number():
    """Should extract the LAST number, not the first."""
    assert _parse_score("Based on 3 sources, score is 72") == 72.0


def test_parse_score_single():
    assert _parse_score("75") == 75.0


def test_parse_score_no_match():
    assert _parse_score("no score here") == 0.0


def test_parse_score_clamp_high():
    assert _parse_score("150") == 100.0


def test_parse_score_clamp_low():
    assert _parse_score("-5") == 0.0


def test_parse_score_100():
    assert _parse_score("100") == 100.0


def test_node_synthesize_mock(mocker):
    state = {
        "extracted_evidence": [],
        "knowledge_base": "",
        "goal": "g",
        "trace_id": "t1",
        "iteration": 1,
    }
    mocker.patch(
        "workflows.deep_research_core.nodes.synthesize.agent",
        side_effect=[
            {"status": "success", "text": "synthesis"},
            {"status": "success", "text": "80"},
        ],
    )
    result = node_synthesize(state)
    assert result["completeness"] == 80.0
    assert result["knowledge_base"] == "synthesis"  # replaced, not appended


def test_node_synthesize_agent_failure(mocker):
    """Research agent failure should preserve old knowledge and score 0."""
    state = {
        "extracted_evidence": [],
        "knowledge_base": "existing",
        "goal": "g",
        "trace_id": "t1",
        "iteration": 1,
    }
    mocker.patch(
        "workflows.deep_research_core.nodes.synthesize.agent",
        return_value={"status": "error", "error": "fail"},
    )
    result = node_synthesize(state)
    assert result["knowledge_base"] == "existing"
    assert result["completeness"] == 0.0
    assert result["converged"] is False
