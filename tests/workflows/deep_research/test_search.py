"""tests/workflows/deep_research/test_search.py
Tests for node_search — tool selection, fallback, evidence extraction,
budget tracking, and seen_urls dedup.
"""
from __future__ import annotations

from workflows.deep_research_impl.nodes.search import (
    _select_tool,
    _is_complex_query,
    _is_js_wall,
    _execute_search_with_fallback,
    _extract_evidence,
    node_search,
)


# ─── Tool selection ─────────────────────────────────────────────────────────

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


# ─── Query classification ───────────────────────────────────────────────────

class TestIsComplexQuery:
    def test_simple_query(self):
        assert not _is_complex_query("python")

    def test_complex_query(self):
        assert _is_complex_query("compare the pros and cons of async vs sync Python")


# ─── JS wall detection ──────────────────────────────────────────────────────

class TestIsJsWall:
    def test_empty_text(self):
        assert _is_js_wall("")

    def test_short_text(self):
        assert _is_js_wall("short")

    def test_js_indicator(self):
        assert _is_js_wall("Please enable JavaScript to view this page.")

    def test_normal_text(self):
        text = ("This is a normal article about Python programming with lots of content "
                "and detailed explanations that goes well beyond one hundred characters.")
        assert not _is_js_wall(text)


# ─── Search with fallback ───────────────────────────────────────────────────

class TestExecuteSearchWithFallback:
    def test_tavily_success_no_fallback(self, mocker):
        """[P0 #4] Tavily attempt decrements API budget (paid API charges per call)."""
        mocker.patch("workflows.deep_research_impl.nodes.search.cfg.tavily_api_key", "fake-key")
        mock_tavily = mocker.patch("workflows.deep_research_impl.nodes.search.tavily")
        mock_tavily.return_value = {"status": "success", "data": {"results": [{"url": "http://example.com"}]}}
        state = {"budget_api_calls": 5, "trace_id": "t1"}
        result, actual_tool, updates = _execute_search_with_fallback("query", state)
        assert result["status"] == "success"
        assert actual_tool == "tavily"
        assert updates == {"budget_api_calls": 4}
        mock_tavily.assert_called_once()

    def test_tavily_empty_fallback_to_web(self, mocker):
        mocker.patch("workflows.deep_research_impl.nodes.search.cfg.tavily_api_key", "fake-key")
        mocker.patch("workflows.deep_research_impl.nodes.search.tavily",
                     return_value={"status": "success", "data": {"results": []}})
        mock_web = mocker.patch("workflows.deep_research_impl.nodes.search.web")
        mock_web.return_value = {"status": "success", "data": {"results": [{"url": "http://example.com"}]}}
        state = {"budget_api_calls": 5, "trace_id": "t1", "budget_events": []}
        result, actual_tool, updates = _execute_search_with_fallback("query", state)
        assert result["status"] == "success"
        assert actual_tool == "web"
        assert "budget_events" in updates
        mock_web.assert_called_once()


# ─── Evidence extraction ────────────────────────────────────────────────────

class TestExtractEvidence:
    def test_extract_evidence_success(self, mocker):
        mocker.patch("workflows.deep_research_impl.nodes.search._summarize_evidence", return_value="summary")
        mocker.patch("workflows.deep_research_impl.nodes.search.citations.add")
        long_text = "a" * 400
        result = {"status": "success", "data": {"results": [{"url": "http://example.com", "title": "Example", "text": long_text}]}}
        evidence, updates = _extract_evidence(result, "q", "web", "goal", "tid", [], {"budget_browser_actions": 2}, 1, set())
        assert len(evidence) == 1
        assert evidence[0]["url"] == "http://example.com"
        assert updates == {}

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


# ─── node_search integration ────────────────────────────────────────────────

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
        state = {"pending_queries": ["q1"], "trace_id": "t1", "iteration": 0,
                 "budget_api_calls": 5, "budget_browser_actions": 2, "budget_events": [],
                 "failed_sources": [], "goal": "g", "seen_urls": []}
        result = node_search(state)
        assert "extracted_evidence" in result
        assert "seen_urls" in result
        assert "budget_browser_actions" in result
        assert "budget_api_calls" in result

    def test_node_search_empty_queries(self):
        state = {"pending_queries": [], "trace_id": "t1", "iteration": 0,
                 "budget_api_calls": 5, "budget_browser_actions": 2, "budget_events": [],
                 "failed_sources": [], "seen_urls": []}
        result = node_search(state)
        assert result["extracted_evidence"] == []
        assert result["seen_urls"] == []
        assert result["budget_browser_actions"] == 2
        assert result["budget_api_calls"] == 5

    def test_browser_budget_decrements_per_url(self, mocker):
        """Browser budget must decrement by 2 per URL (navigate + text_content)."""
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.browser",
            side_effect=[
                {"status": "success", "data": {"title": "T1"}},
                {"status": "success", "data": {"text": "a" * 200}},
            ],
        )
        mocker.patch("workflows.deep_research_impl.nodes.search._is_js_wall", return_value=True)
        mocker.patch("workflows.deep_research_impl.nodes.search._summarize_evidence", return_value="summary")
        mocker.patch("workflows.deep_research_impl.nodes.search.citations.add", return_value=1)
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._execute_search_with_fallback",
            return_value=({"status": "success", "data": {"results": [{"url": "http://example.com", "title": "T", "text": "a" * 150}]}}, "tavily", {}),
        )
        state = {
            "pending_queries": ["q1"], "trace_id": "t1", "iteration": 0,
            "budget_api_calls": 5, "budget_browser_actions": 3,
            "budget_events": [], "failed_sources": [], "goal": "g", "seen_urls": [],
        }
        result = node_search(state)
        assert result["budget_browser_actions"] == 1
        assert "budget_events" in result

    def test_browser_budget_exhausted_skips_fallback(self, mocker):
        """When browser budget is 0, fallback should be skipped."""
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.browser",
            side_effect=Exception("Should not be called"),
        )
        mocker.patch("workflows.deep_research_impl.nodes.search._is_js_wall", return_value=True)
        mocker.patch("workflows.deep_research_impl.nodes.search._summarize_evidence", return_value="summary")
        mocker.patch("workflows.deep_research_impl.nodes.search.citations.add", return_value=1)
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._execute_search_with_fallback",
            return_value=({"status": "success", "data": {"results": [{"url": "http://example.com", "title": "T", "text": "a" * 150}]}}, "tavily", {}),
        )
        state = {
            "pending_queries": ["q1"], "trace_id": "t1", "iteration": 0,
            "budget_api_calls": 5, "budget_browser_actions": 0,
            "budget_events": [], "failed_sources": [], "goal": "g", "seen_urls": [],
        }
        result = node_search(state)
        assert result["budget_browser_actions"] == 0
        assert "budget_events" in result


# ─── Browser fallback ───────────────────────────────────────────────────────

class TestBrowserFallback:
    def test_playwright_not_installed(self, mocker):
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.browser",
            side_effect=Exception("Playwright browser not found"),
        )
        from workflows.deep_research_impl.nodes.search import _try_browser_fallback
        text, updates = _try_browser_fallback("http://example.com", "tid", {"budget_browser_actions": 2})
        assert text == ""
        assert updates == {"budget_browser_actions": 1}

    def test_navigate_fails(self, mocker):
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.browser",
            return_value={"status": "error", "error": "timeout"},
        )
        from workflows.deep_research_impl.nodes.search import _try_browser_fallback
        text, updates = _try_browser_fallback("http://example.com", "tid", {"budget_browser_actions": 2})
        assert text == ""
        assert updates == {"budget_browser_actions": 1}

    def test_text_content_fails(self, mocker):
        def mock_browser(action, **kwargs):
            if action == "navigate":
                return {"status": "success", "data": {"title": "Example"}}
            return {"status": "error", "error": "selector not found"}
        mocker.patch("workflows.deep_research_impl.nodes.search.browser", mock_browser)
        from workflows.deep_research_impl.nodes.search import _try_browser_fallback
        text, updates = _try_browser_fallback("http://example.com", "tid", {"budget_browser_actions": 2})
        assert text == ""
        assert updates == {"budget_browser_actions": 0}

    def test_success(self, mocker):
        def mock_browser(action, **kwargs):
            if action == "navigate":
                return {"status": "success", "data": {"title": "Example"}}
            return {"status": "success", "data": {"text": "Hello world content"}}
        mocker.patch("workflows.deep_research_impl.nodes.search.browser", mock_browser)
        from workflows.deep_research_impl.nodes.search import _try_browser_fallback
        text, updates = _try_browser_fallback("http://example.com", "tid", {"budget_browser_actions": 2})
        assert text == "Hello world content"
        assert updates == {"budget_browser_actions": 0}

    def test_budget_exhausted(self, mocker):
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.browser",
            side_effect=Exception("Should not be called"),
        )
        from workflows.deep_research_impl.nodes.search import _try_browser_fallback
        text, updates = _try_browser_fallback("http://example.com", "tid", {"budget_browser_actions": 0})
        assert text == ""
        assert updates == {}


# ─── API budget: only Tavily decrements ─────────────────────────────────────

class TestApiBudgetOnlyForTavily:
    """[v1.0.2 + P0 #4] API budget only decrements for Tavily (paid), not web (free)."""

    def test_web_search_does_not_decrement_api_budget(self, mocker):
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.web",
            return_value={"status": "success", "data": {"results": []}},
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.tavily",
            side_effect=Exception("Should not be called"),
        )
        mocker.patch("workflows.deep_research_impl.nodes.search._select_tool", return_value="web")
        mock_decrement = mocker.patch(
            "workflows.deep_research_impl.nodes.search.decrement_api_calls",
            return_value={"budget_api_calls": 10},
        )
        state = {
            "pending_queries": ["test query"], "budget_api_calls": 10,
            "budget_browser_actions": 5, "seen_urls": [], "failed_sources": [],
            "budget_events": [], "trace_id": "test", "goal": "test", "iteration": 0,
        }
        node_search(state)
        assert not mock_decrement.called, "decrement_api_calls must NOT be called for web searches"

    def test_tavily_search_decrements_api_budget(self, mocker):
        mocker.patch(
            "workflows.deep_research_impl.nodes.search.tavily",
            return_value={"status": "success", "data": {"results": [{"url": "http://example.com", "title": "Test", "text": "A" * 200}]}},
        )
        mocker.patch("workflows.deep_research_impl.nodes.search._select_tool", return_value="tavily")
        mocker.patch("workflows.deep_research_impl.nodes.search._extract_evidence", return_value=([], {}))
        mocker.patch("workflows.deep_research_impl.nodes.search._summarize_evidence", return_value="summary")
        mock_decrement = mocker.patch(
            "workflows.deep_research_impl.nodes.search.decrement_api_calls",
            return_value={"budget_api_calls": 9},
        )
        state = {
            "pending_queries": ["test query"], "budget_api_calls": 10,
            "budget_browser_actions": 5, "seen_urls": [], "failed_sources": [],
            "budget_events": [], "trace_id": "test", "goal": "test", "iteration": 0,
        }
        node_search(state)
        assert mock_decrement.called, "decrement_api_calls MUST be called for Tavily searches"


# ─── seen_urls dedup (merged from test_seen_urls.py) ────────────────────────

class TestSeenUrls:
    """seen_urls persistence across iterations — prevents redundant API calls."""

    def test_seen_urls_passed_to_workflow(self):
        """run_deep_research_agent must include seen_urls in initial state."""
        from unittest.mock import patch
        from workflows.deep_research import run_deep_research_agent
        with patch("workflows.deep_research.run_workflow") as mock_run:
            mock_run.return_value = {"status": "success", "result": "test", "report": "",
                                     "seen_urls": ["https://example.com/page1"]}
            result = run_deep_research_agent(
                goal="test goal",
                seen_urls=["https://example.com/page1"],
                trace_id="test-trace",
            )
            call_kwargs = mock_run.call_args[1]
            assert "seen_urls" in call_kwargs
            assert call_kwargs["seen_urls"] == ["https://example.com/page1"]
            assert call_kwargs.get("trace_id") == "test-trace"

    def test_seen_urls_empty_by_default(self):
        from unittest.mock import patch
        from workflows.deep_research import run_deep_research_agent
        with patch("workflows.deep_research.run_workflow") as mock_run:
            mock_run.return_value = {"status": "success", "result": "", "report": ""}
            run_deep_research_agent(goal="test goal")
            call_kwargs = mock_run.call_args[1]
            assert "seen_urls" in call_kwargs
            assert call_kwargs["seen_urls"] == []
            assert call_kwargs.get("trace_id") == ""

    def test_seen_urls_persists_across_calls(self):
        from unittest.mock import patch
        from workflows.deep_research import run_deep_research_agent
        initial_seen = ["https://example.com/page1"]
        with patch("workflows.deep_research.run_workflow") as mock_run:
            mock_run.return_value = {"status": "success", "result": "test", "report": "",
                                     "seen_urls": initial_seen + ["https://example.com/page2"]}
            result1 = run_deep_research_agent(goal="test goal", seen_urls=initial_seen)
            result2 = run_deep_research_agent(goal="test goal",
                                              seen_urls=result1.get("seen_urls", []))
            call_kwargs = mock_run.call_args[1]
            assert "https://example.com/page2" in call_kwargs["seen_urls"]

    def test_seen_urls_deduplicates_in_state(self):
        from unittest.mock import patch
        from workflows.deep_research import run_deep_research_agent
        with patch("workflows.deep_research.run_workflow") as mock_run:
            def capture_state(**kwargs):
                seen = kwargs.get("seen_urls", [])
                seen.append("https://example.com/dup")
                seen.append("https://example.com/dup")
                return {"status": "success", "result": "", "report": "", "seen_urls": list(set(seen))}
            mock_run.side_effect = capture_state
            result = run_deep_research_agent(goal="test", seen_urls=["https://example.com/dup"])
            assert result["seen_urls"].count("https://example.com/dup") == 1
