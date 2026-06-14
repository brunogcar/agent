"""tests/workflows/deep_research/test_search.py"""
import pytest
from workflows.deep_research_core.nodes.search import (
    _select_tool,
    _is_complex_query,
    _is_js_heavy,
    _is_js_wall,
    _execute_search_with_fallback,
    _extract_evidence,
    node_search,
)


class TestSelectTool:
    def test_select_tavily_for_complex_query(self, mocker):
        mocker.patch("workflows.deep_research_core.nodes.search.cfg.tavily_api_key", "fake-key")
        state = {"budget_api_calls": 5}
        assert _select_tool(state, "compare React vs Angular performance") == "tavily"

    def test_select_web_when_budget_exhausted(self, mocker):
        mocker.patch("workflows.deep_research_core.nodes.search.cfg.tavily_api_key", "fake-key")
        state = {"budget_api_calls": 0}
        assert _select_tool(state, "simple query") == "web"

    def test_select_web_when_no_tavily_key(self, mocker):
        mocker.patch("workflows.deep_research_core.nodes.search.cfg.tavily_api_key", None)
        state = {"budget_api_calls": 5}
        assert _select_tool(state, "any query") == "web"


class TestIsComplexQuery:
    def test_simple_query(self):
        assert not _is_complex_query("python")

    def test_complex_query(self):
        assert _is_complex_query("compare the pros and cons of async vs sync Python")


class TestIsJsHeavy:
    def test_js_heavy_query(self):
        assert _is_js_heavy("React dashboard best practices")

    def test_non_js_query(self):
        assert not _is_js_heavy("Python asyncio tutorial")


class TestIsJsWall:
    def test_empty_text(self):
        assert _is_js_wall("")

    def test_short_text(self):
        assert _is_js_wall("short")

    def test_js_indicator(self):
        assert _is_js_wall("Please enable JavaScript to view this page.")

    def test_normal_text(self):
        # Must be >100 chars to pass the length check
        text = "This is a normal article about Python programming with lots of content and detailed explanations that goes well beyond one hundred characters in total length."
        assert not _is_js_wall(text)


class TestExecuteSearchWithFallback:
    def test_tavily_success_no_fallback(self, mocker):
        mocker.patch("workflows.deep_research_core.nodes.search.cfg.tavily_api_key", "fake-key")
        mock_tavily = mocker.patch("workflows.deep_research_core.nodes.search.tavily")
        mock_tavily.return_value = {"status": "success", "data": {"results": [{"url": "http://example.com"}]}}
        state = {"budget_api_calls": 5, "trace_id": "t1"}
        result = _execute_search_with_fallback("query", state)
        assert result["status"] == "success"
        mock_tavily.assert_called_once()

    def test_tavily_empty_fallback_to_web(self, mocker):
        mocker.patch("workflows.deep_research_core.nodes.search.cfg.tavily_api_key", "fake-key")
        mocker.patch("workflows.deep_research_core.nodes.search.tavily", return_value={"status": "success", "data": {"results": []}})
        mock_web = mocker.patch("workflows.deep_research_core.nodes.search.web")
        mock_web.return_value = {"status": "success", "data": {"results": [{"url": "http://example.com"}]}}
        state = {"budget_api_calls": 5, "trace_id": "t1", "budget_events": []}
        result = _execute_search_with_fallback("query", state)
        assert result["status"] == "success"
        mock_web.assert_called_once()


class TestExtractEvidence:
    def test_extract_evidence_success(self, mocker):
        mocker.patch("workflows.deep_research_core.nodes.search._summarize_evidence", return_value="summary")
        mocker.patch("workflows.deep_research_core.nodes.search.citations.add")
        # Text must be >100 chars to not trigger the too_short filter
        long_text = "This is some content that is definitely longer than one hundred characters so it will pass the length check and not be filtered out."
        result = {"status": "success", "data": {"results": [{"url": "http://example.com", "title": "Example", "text": long_text}]}}
        evidence = _extract_evidence(result, "q", "web", "goal", "tid", [], {}, 1, set())
        assert len(evidence) == 1
        assert evidence[0]["url"] == "http://example.com"

    def test_extract_evidence_skip_failed_url(self, mocker):
        failed = [{"url": "http://example.com"}]
        result = {"status": "success", "data": {"results": [{"url": "http://example.com", "title": "Example", "text": "content"}]}}
        evidence = _extract_evidence(result, "q", "web", "goal", "tid", failed, {}, 1, set())
        assert len(evidence) == 0

    def test_extract_evidence_too_short(self, mocker):
        result = {"status": "success", "data": {"results": [{"url": "http://example.com", "title": "Example", "text": "ab"}]}}
        failed = []
        evidence = _extract_evidence(result, "q", "web", "goal", "tid", failed, {}, 1, set())
        assert len(evidence) == 0
        assert len(failed) == 1

    def test_extract_evidence_llm_failure_fallback(self, mocker):
        mocker.patch("workflows.deep_research_core.nodes.search.llm.complete", return_value=mocker.MagicMock(ok=False))
        mocker.patch("workflows.deep_research_core.nodes.search.citations.add")
        long_text = "a" * 200
        result = {"status": "success", "data": {"results": [{"url": "http://example.com", "title": "Example", "text": long_text}]}}
        evidence = _extract_evidence(result, "q", "web", "goal", "tid", [], {}, 1, set())
        assert len(evidence) == 1
        assert evidence[0]["summary"] == "a" * 200


class TestNodeSearch:
    def test_node_search_basic(self, mocker):
        mocker.patch("workflows.deep_research_core.nodes.search._execute_search_with_fallback", return_value={"status": "success", "data": {"results": []}})
        mocker.patch("workflows.deep_research_core.nodes.search._extract_evidence", return_value=[])
        state = {"pending_queries": ["q1"], "trace_id": "t1", "iteration": 0, "budget_api_calls": 5, "budget_browser_actions": 2, "budget_events": [], "failed_sources": [], "goal": "g"}
        result = node_search(state)
        assert "extracted_evidence" in result

    def test_node_search_empty_queries(self):
        state = {"pending_queries": [], "trace_id": "t1", "iteration": 0, "budget_api_calls": 5, "budget_browser_actions": 2, "budget_events": [], "failed_sources": []}
        result = node_search(state)
        assert result["extracted_evidence"] == []
