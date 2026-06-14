"""tests/workflows/deep_research/test_search.py"""
import pytest
from unittest.mock import patch, MagicMock

from workflows.deep_research_core.nodes.search import (
    _select_tool,
    _is_complex_query,
    _is_js_heavy,
    _is_js_wall,
    _execute_search_with_fallback,
    _extract_evidence,
    node_search,
)
from workflows.deep_research_core.state import DeepResearchState


class TestSelectTool:
    @patch("workflows.deep_research_core.nodes.search.cfg")
    def test_select_tavily_for_complex_query(self, mock_cfg):
        mock_cfg.tavily_api_key = "test-key"
        state = {"budget_api_calls": 5, "budget_browser_actions": 5}
        assert _select_tool(state, "compare Python async frameworks in detail") == "tavily"

    def test_select_web_when_budget_exhausted(self):
        state = {"budget_api_calls": 0, "budget_browser_actions": 5}
        assert _select_tool(state, "compare Python async frameworks") == "web"

    def test_select_web_when_no_tavily_key(self, monkeypatch):
        monkeypatch.setattr("workflows.deep_research_core.nodes.search.cfg", MagicMock(tavily_api_key=None))
        state = {"budget_api_calls": 5, "budget_browser_actions": 5}
        assert _select_tool(state, "simple query") == "web"


class TestIsComplexQuery:
    def test_simple_query(self):
        assert not _is_complex_query("Python async")

    def test_complex_query(self):
        assert _is_complex_query("compare the pros and cons of Python async frameworks")


class TestIsJsHeavy:
    def test_js_heavy_query(self):
        assert _is_js_heavy("React dashboard best practices")

    def test_non_js_query(self):
        assert not _is_js_heavy("Python asyncio tutorial")


class TestIsJsWall:
    def test_empty_text(self):
        assert _is_js_wall("")

    def test_short_text(self):
        assert _is_js_wall("hi")

    def test_js_indicator(self):
        assert _is_js_wall("Please enable JavaScript to view this page")

    def test_normal_text(self):
        assert not _is_js_wall("This is a normal article about Python programming with lots of content.")


class TestExecuteSearchWithFallback:
    @patch("workflows.deep_research_core.nodes.search._execute_search")
    def test_tavily_success_no_fallback(self, mock_execute):
        mock_execute.return_value = {"status": "success", "data": {"results": [{"url": "http://example.com"}]}}
        state = {"budget_api_calls": 5, "trace_id": "test"}
        result = _execute_search_with_fallback("query", state)
        assert result["status"] == "success"
        assert mock_execute.call_count == 1

    @patch("workflows.deep_research_core.nodes.search.cfg")
    @patch("workflows.deep_research_core.nodes.search._execute_search")
    def test_tavily_empty_fallback_to_web(self, mock_execute, mock_cfg):
        mock_cfg.tavily_api_key = "test-key"
        mock_execute.side_effect = [
            {"status": "success", "data": {"results": []}},
            {"status": "success", "data": {"results": [{"url": "http://example.com"}]}},
        ]
        state = {"budget_api_calls": 5, "trace_id": "test"}
        result = _execute_search_with_fallback("query", state)
        assert result["status"] == "success"
        assert mock_execute.call_count == 2


class TestExtractEvidence:
    @patch("workflows.deep_research_core.nodes.search.citations")
    @patch("workflows.deep_research_core.nodes.search.llm")
    def test_extract_evidence_success(self, mock_llm, mock_citations):
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.text.strip.return_value = "Summary of the article"
        mock_llm.complete.return_value = mock_result

        search_result = {
            "status": "success",
            "data": {
                "results": [
                    {"url": "http://example.com", "title": "Example", "text": "This is a long article about Python async frameworks." * 10},
                ]
            }
        }
        state = {"trace_id": "test", "budget_api_calls": 5, "budget_browser_actions": 5}
        evidence = _extract_evidence(search_result, "query", "tavily", "goal", "test", [], state, 1, set())
        assert len(evidence) == 1
        assert evidence[0]["url"] == "http://example.com"
        assert evidence[0]["source"] == "tavily"
        mock_citations.add.assert_called_once()

    @patch("workflows.deep_research_core.nodes.search.citations")
    def test_extract_evidence_skip_failed_url(self, mock_citations):
        search_result = {
            "status": "success",
            "data": {
                "results": [
                    {"url": "http://failed.com", "title": "Failed", "text": ""},
                ]
            }
        }
        failed = [{"url": "http://failed.com", "reason": "timeout"}]
        state = {"trace_id": "test", "budget_api_calls": 5, "budget_browser_actions": 5}
        evidence = _extract_evidence(search_result, "query", "tavily", "goal", "test", failed, state, 1, set())
        assert len(evidence) == 0
        mock_citations.add.assert_not_called()

    @patch("workflows.deep_research_core.nodes.search.citations")
    def test_extract_evidence_too_short(self, mock_citations):
        search_result = {
            "status": "success",
            "data": {
                "results": [
                    {"url": "http://short.com", "title": "Short", "text": "hi"},
                ]
            }
        }
        state = {"trace_id": "test", "budget_api_calls": 5, "budget_browser_actions": 5}
        evidence = _extract_evidence(search_result, "query", "tavily", "goal", "test", [], state, 1, set())
        assert len(evidence) == 0
        mock_citations.add.assert_not_called()

    @patch("workflows.deep_research_core.nodes.search.citations")
    @patch("workflows.deep_research_core.nodes.search.llm")
    def test_extract_evidence_llm_failure_fallback(self, mock_llm, mock_citations):
        mock_result = MagicMock()
        mock_result.ok = False
        mock_llm.complete.return_value = mock_result

        long_text = "a" * 200
        search_result = {
            "status": "success",
            "data": {
                "results": [
                    {"url": "http://example.com", "title": "Example", "text": long_text},
                ]
            }
        }
        state = {"trace_id": "test", "budget_api_calls": 5, "budget_browser_actions": 5}
        evidence = _extract_evidence(search_result, "query", "tavily", "goal", "test", [], state, 1, set())
        assert len(evidence) == 1
        assert evidence[0]["summary"] == long_text[:500]


class TestNodeSearch:
    @patch("workflows.deep_research_core.nodes.search._execute_search_with_fallback")
    @patch("workflows.deep_research_core.nodes.search._extract_evidence")
    def test_node_search_basic(self, mock_extract, mock_fallback):
        mock_fallback.return_value = {"status": "success", "data": {"results": []}}
        mock_extract.return_value = []
        state = {
            "pending_queries": ["query1"],
            "trace_id": "test",
            "goal": "goal",
            "iteration": 0,
            "budget_api_calls": 5,
            "budget_browser_actions": 5,
            "failed_sources": [],
        }
        result = node_search(state)
        assert result["extracted_evidence"] == []
        assert result["pending_queries"] == []

    def test_node_search_empty_queries(self):
        state = {"pending_queries": [], "failed_sources": []}
        result = node_search(state)
        assert result["extracted_evidence"] == []
        assert result["pending_queries"] == []
