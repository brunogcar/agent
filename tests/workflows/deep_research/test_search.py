"""tests/workflows/deep_research/test_search.py"""
import pytest
from workflows.deep_research_core.nodes.search import (
    node_search,
    _select_tool,
    _is_complex_query,
    _is_js_heavy,
    _is_js_wall,
    _extract_evidence,
    _execute_search_with_fallback,
)


def test_select_tool_tavily_when_budget_available():
    state = {"budget_api_calls": 5}
    assert _select_tool("complex query here", state) == "tavily"


def test_select_tool_web_when_budget_exhausted():
    state = {"budget_api_calls": 0}
    assert _select_tool("any query", state) == "web"


def test_is_complex_query_long():
    assert _is_complex_query("a" * 81) is True


def test_is_complex_query_short():
    assert _is_complex_query("short") is False


def test_is_js_heavy_react():
    assert _is_js_heavy("react dashboard") is True


def test_is_js_wall_empty():
    assert _is_js_wall("") is True


def test_is_js_wall_indicators():
    assert _is_js_wall("Please enable JavaScript to view this page.") is True


def test_is_js_wall_clean():
    assert _is_js_wall("This is a normal article about Python.") is False


def test_extract_evidence_skips_failed_url(mocker):
    """URL already in failed list should be skipped."""
    seen = set()
    failed = [{"url": "http://example.com", "reason": "read_failed", "iteration": 1}]
    result = {
        "status": "success",
        "data": {"results": [{"url": "http://example.com", "title": "Ex", "text": "content"}]},
    }
    out = _extract_evidence(result, "q", "web", "goal", "tid", failed, seen, 1)
    assert out == []
    assert len(failed) == 1  # not re-added


def test_extract_evidence_too_short(mocker):
    """Text < 100 chars should be added to failed_sources."""
    mocker.patch(
        "workflows.deep_research_core.nodes.search.web",
        return_value={"status": "success", "data": {"text": "hi"}},
    )
    seen = set()
    failed = []
    result = {
        "status": "success",
        "data": {"results": [{"url": "http://x.com", "title": "X"}]},
    }
    out = _extract_evidence(result, "q", "web", "goal", "tid", failed, seen, 1)
    assert out == []
    assert len(failed) == 1
    assert failed[0]["reason"] == "too_short"
    assert failed[0]["iteration"] == 1


def test_extract_evidence_llm_success(mocker):
    """Successful LLM summarization returns evidence with citation."""
    mocker.patch(
        "workflows.deep_research_core.nodes.search.web",
        return_value={"status": "success", "data": {"text": "a" * 200}},
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search.llm.complete",
        return_value=mocker.Mock(ok=True, text="Summary bullet."),
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search.citations.add",
        return_value=1,
    )
    seen = set()
    failed = []
    result = {
        "status": "success",
        "data": {"results": [{"url": "http://x.com", "title": "X"}]},
    }
    out = _extract_evidence(result, "q", "web", "goal", "tid", failed, seen, 1)
    assert len(out) == 1
    assert out[0]["summary"] == "Summary bullet."
    assert out[0]["tool"] == "web"


def test_extract_evidence_llm_failure_fallback(mocker):
    """LLM failure falls back to raw text[:500]."""
    mocker.patch(
        "workflows.deep_research_core.nodes.search.web",
        return_value={"status": "success", "data": {"text": "a" * 200}},
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search.llm.complete",
        return_value=mocker.Mock(ok=False, error="timeout"),
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search.citations.add",
        return_value=1,
    )
    seen = set()
    failed = []
    result = {
        "status": "success",
        "data": {"results": [{"url": "http://x.com", "title": "X"}]},
    }
    out = _extract_evidence(result, "q", "web", "goal", "tid", failed, seen, 1)
    assert len(out) == 1
    assert out[0]["summary"] == "a" * 200  # text[:500] since text is 200 chars


def test_extract_evidence_deduplication(mocker):
    """Same URL across multiple results should only be processed once."""
    mocker.patch(
        "workflows.deep_research_core.nodes.search.web",
        return_value={"status": "success", "data": {"text": "a" * 200}},
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search.llm.complete",
        return_value=mocker.Mock(ok=True, text="Summary."),
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search.citations.add",
        return_value=1,
    )
    seen = set()
    failed = []
    result = {
        "status": "success",
        "data": {
            "results": [
                {"url": "http://x.com", "title": "X"},
                {"url": "http://x.com", "title": "X dup"},  # duplicate
            ]
        },
    }
    out = _extract_evidence(result, "q", "web", "goal", "tid", failed, seen, 1)
    assert len(out) == 1  # only one processed


def test_execute_search_with_fallback_tavily_to_web(mocker):
    """Tavily empty results should fallback to web."""
    mocker.patch(
        "workflows.deep_research_core.nodes.search.tavily",
        return_value={"status": "success", "data": {"results": []}},
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search.web",
        return_value={"status": "success", "data": {"results": [{"url": "http://x.com"}]}},
    )
    state = {"budget_events": []}
    result, tool = _execute_search_with_fallback("q", "tavily", "tid", state)
    assert tool == "web"
    assert result["status"] == "success"


def test_node_search_tracks_consecutive_empty(mocker):
    """Two empty iterations should set consecutive_empty_iterations=2."""
    mocker.patch(
        "workflows.deep_research_core.nodes.search._execute_search_with_fallback",
        return_value=({"status": "success", "data": {"results": []}}, "web"),
    )
    state = {
        "pending_queries": ["q1"],
        "goal": "g",
        "trace_id": "tid",
        "iteration": 0,
        "consecutive_empty_iterations": 0,
        "budget_events": [],
        "failed_sources": [],
        "extracted_evidence": [],
    }
    result = node_search(state)
    assert result["consecutive_empty_iterations"] == 1
