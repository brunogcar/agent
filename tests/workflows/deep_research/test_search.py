"""tests/workflows/deep_research/test_search.py"""
import pytest
from workflows.deep_research_impl.nodes.search import (
    _select_tool,
    _is_complex_query,
    _is_js_wall,
    _execute_search_with_fallback,
    _extract_evidence,
    node_search,
)

class TestSelectTool:
    def test_select_tavily_for_complex_query(self, mocker):
        mocker.patch("workflows.deep_research_impl.nodes.search.cfg.tavily_api_key", "fake-key")
        state = {"budget_api_calls": 5}
        assert _select_tool(state, "compare React vs Angular performance") == "tavily"

    def test_select_web_when_budget_exhausted(self, mocker):
        mocker.patch("workflows.deep_research_impl.nodes.search.cfg.tavily_api_key", "fake-key")
        state = {"budget_api_calls": 0}
        assert _select_tool(state, "simple query") == "web"

    def test_select_web_when_no_tavily_key(self, mocker):
        mocker.patch("workflows.deep_research_impl.nodes.search.cfg.tavily_api_key", None)
        state = {"budget_api_calls": 5}
        assert _select_tool(state, "any query") == "web"

class TestIsComplexQuery:
    def test_simple_query(self):
        assert not _is_complex_query("python")

    def test_complex_query(self):
        assert _is_complex_query("compare the pros and cons of async vs sync Python")

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
        mocker.patch("workflows.deep_research_impl.nodes.search.cfg.tavily_api_key", "fake-key")
        mock_tavily = mocker.patch("workflows.deep_research_impl.nodes.search.tavily")
        mock_tavily.return_value = {"status": "success", "data": {"results": [{"url": "http://example.com"}]}}
        state = {"budget_api_calls": 5, "trace_id": "t1"}
        result, actual_tool, updates = _execute_search_with_fallback("query", state)
        assert result["status"] == "success"
        assert actual_tool == "tavily"
        assert updates == {}
        mock_tavily.assert_called_once()

    def test_tavily_empty_fallback_to_web(self, mocker):
        mocker.patch("workflows.deep_research_impl.nodes.search.cfg.tavily_api_key", "fake-key")
        mocker.patch("workflows.deep_research_impl.nodes.search.tavily", return_value={"status": "success", "data": {"results": []}})
        mock_web = mocker.patch("workflows.deep_research_impl.nodes.search.web")
        mock_web.return_value = {"status": "success", "data": {"results": [{"url": "http://example.com"}]}}
        state = {"budget_api_calls": 5, "trace_id": "t1", "budget_events": []}
        result, actual_tool, updates = _execute_search_with_fallback("query", state)
        assert result["status"] == "success"
        assert actual_tool == "web"
        assert "budget_events" in updates
        mock_web.assert_called_once()

class TestExtractEvidence:
    def test_extract_evidence_success(self, mocker):
        mocker.patch("workflows.deep_research_impl.nodes.search._summarize_evidence", return_value="summary")
        mocker.patch("workflows.deep_research_impl.nodes.search.citations.add")
        # Use text > 300 chars to avoid triggering browser fallback
        long_text = "a" * 400
        result = {"status": "success", "data": {"results": [{"url": "http://example.com", "title": "Example", "text": long_text}]}}
        evidence, updates = _extract_evidence(result, "q", "web", "goal", "tid", [], {"budget_browser_actions": 2}, 1, set())
        assert len(evidence) == 1
        assert evidence[0]["url"] == "http://example.com"
        assert updates == {}  # No browser fallback triggered (text > 300 chars)

    def test_extract_evidence_skip_failed_url(self, mocker):
        failed = [{"url": "http://example.com"}]
        result = {"status": "success", "data": {"results": [{"url": "http://example.com", "title": "Example", "text": "content"}]}}
        evidence, updates = _extract_evidence(result, "q", "web", "goal", "tid", failed, {}, 1, set())
        assert len(evidence) == 0
        assert updates == {}

    def test_extract_evidence_too_short(self, mocker):
        result = {"status": "success", "data": {"results": [{"url": "http://example.com", "title": "Example", "text": "ab"}]}}
        failed = []
        evidence, updates = _extract_evidence(result, "q", "web", "goal", "tid", failed, {}, 1, set())
        assert len(evidence) == 0
        assert len(failed) == 1
        assert updates == {}

    def test_extract_evidence_llm_failure_fallback(self, mocker):
        mocker.patch("workflows.deep_research_impl.nodes.search.llm.complete", return_value=mocker.MagicMock(ok=False))
        mocker.patch("workflows.deep_research_impl.nodes.search.citations.add")
        long_text = "a" * 200
        result = {"status": "success", "data": {"results": [{"url": "http://example.com", "title": "Example", "text": long_text}]}}
        evidence, updates = _extract_evidence(result, "q", "web", "goal", "tid", [], {}, 1, set())
        assert len(evidence) == 1
        assert evidence[0]["summary"] == "a" * 200
        assert updates == {}

class TestNodeSearch:
    def test_node_search_basic(self, mocker):
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._execute_search_with_fallback",
            return_value=({"status": "success", "data": {"results": []}}, "tavily", {}),
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._extract_evidence",
            return_value=([], {}),
        )
        state = {"pending_queries": ["q1"], "trace_id": "t1", "iteration": 0, "budget_api_calls": 5, "budget_browser_actions": 2, "budget_events": [], "failed_sources": [], "goal": "g", "seen_urls": []}
        result = node_search(state)
        assert "extracted_evidence" in result
        assert "seen_urls" in result
        assert "budget_browser_actions" in result
        assert "budget_api_calls" in result

    def test_node_search_empty_queries(self):
        state = {"pending_queries": [], "trace_id": "t1", "iteration": 0, "budget_api_calls": 5, "budget_browser_actions": 2, "budget_events": [], "failed_sources": [], "seen_urls": []}
        result = node_search(state)
        assert result["extracted_evidence"] == []
        assert result["seen_urls"] == []
        assert result["budget_browser_actions"] == 2
        assert result["budget_api_calls"] == 5

    def test_node_search_decrements_budget_per_successful_query(self, mocker):
        """Browser budget must decrement by 2 per URL (navigate + text_content)."""
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.browser",
            side_effect=[
                {"status": "success", "data": {"title": "T1"}},  # navigate
                {"status": "success", "data": {"text": "a" * 200}},  # text_content
            ],
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._is_js_wall",
            return_value=True,  # force browser fallback
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._summarize_evidence",
            return_value="summary",
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.citations.add",
            return_value=1,
        )
        # Use text >= 100 chars so it passes the too_short filter and reaches browser fallback
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._execute_search_with_fallback",
            return_value=({"status": "success", "data": {"results": [{"url": "http://example.com", "title": "T", "text": "a" * 150}]}}, "tavily", {}),
        )

        state = {
            "pending_queries": ["q1"],
            "trace_id": "t1",
            "iteration": 0,
            "budget_api_calls": 5,
            "budget_browser_actions": 3,  # only 3 left!
            "budget_events": [],
            "failed_sources": [],
            "goal": "g",
            "seen_urls": [],
        }
        result = node_search(state)
        # 1 URL triggered browser fallback (2 actions), budget should be 3 - 2 = 1
        assert result["budget_browser_actions"] == 1
        assert "budget_events" in result

    def test_node_search_browser_budget_exhausted_skips_fallback(self, mocker):
        """When browser budget is 0, fallback should be skipped."""
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.browser",
            side_effect=Exception("Should not be called"),
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._is_js_wall",
            return_value=True,  # would trigger fallback, but budget is 0
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._summarize_evidence",
            return_value="summary",
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.citations.add",
            return_value=1,
        )
        # Use text >= 100 chars so it passes the too_short filter
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._execute_search_with_fallback",
            return_value=({"status": "success", "data": {"results": [{"url": "http://example.com", "title": "T", "text": "a" * 150}]}}, "tavily", {}),
        )

        state = {
            "pending_queries": ["q1"],
            "trace_id": "t1",
            "iteration": 0,
            "budget_api_calls": 5,
            "budget_browser_actions": 0,  # exhausted!
            "budget_events": [],
            "failed_sources": [],
            "goal": "g",
            "seen_urls": [],
        }
        result = node_search(state)
        assert result["budget_browser_actions"] == 0
        assert "budget_events" in result

class TestBrowserFallback:
    def test_browser_fallback_playwright_not_installed(self, mocker):
        """Verify _try_browser_fallback gracefully handles missing Playwright."""
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.browser",
            side_effect=Exception("Playwright browser not found"),
        )
        from workflows.deep_research_impl.nodes.search import _try_browser_fallback
        text, updates = _try_browser_fallback("http://example.com", "tid", {"budget_browser_actions": 2})
        assert text == ""
        # Budget is decremented before the browser call attempt
        assert updates == {"budget_browser_actions": 1}

    def test_browser_fallback_navigate_fails(self, mocker):
        """Verify _try_browser_fallback returns empty when navigate fails."""
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.browser",
            return_value={"status": "error", "error": "timeout"},
        )
        from workflows.deep_research_impl.nodes.search import _try_browser_fallback
        text, updates = _try_browser_fallback("http://example.com", "tid", {"budget_browser_actions": 2})
        assert text == ""
        assert updates == {"budget_browser_actions": 1}

    def test_browser_fallback_text_content_fails(self, mocker):
        """Verify _try_browser_fallback returns empty when text_content fails."""
        def mock_browser(action, **kwargs):
            if action == "navigate":
                return {"status": "success", "data": {"title": "Example"}}
            return {"status": "error", "error": "selector not found"}
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.browser",
            mock_browser,
        )
        from workflows.deep_research_impl.nodes.search import _try_browser_fallback
        text, updates = _try_browser_fallback("http://example.com", "tid", {"budget_browser_actions": 2})
        assert text == ""
        assert updates == {"budget_browser_actions": 0}

    def test_browser_fallback_success(self, mocker):
        """Verify _try_browser_fallback returns text on success."""
        def mock_browser(action, **kwargs):
            if action == "navigate":
                return {"status": "success", "data": {"title": "Example"}}
            return {"status": "success", "data": {"text": "Hello world content"}}
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.browser",
            mock_browser,
        )
        from workflows.deep_research_impl.nodes.search import _try_browser_fallback
        text, updates = _try_browser_fallback("http://example.com", "tid", {"budget_browser_actions": 2})
        assert text == "Hello world content"
        assert updates == {"budget_browser_actions": 0}

    def test_browser_fallback_budget_exhausted(self, mocker):
        """Verify _try_browser_fallback returns empty when budget is exhausted."""
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.browser",
            side_effect=Exception("Should not be called"),
        )
        from workflows.deep_research_impl.nodes.search import _try_browser_fallback
        text, updates = _try_browser_fallback("http://example.com", "tid", {"budget_browser_actions": 0})
        assert text == ""
        assert updates == {}
