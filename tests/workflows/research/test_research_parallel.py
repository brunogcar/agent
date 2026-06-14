"""tests/workflows/research/test_research_parallel.py
Test parallel timeout and nested-parallel guard for research workflow.
"""
import pytest
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from unittest.mock import MagicMock, patch

from workflows.research import node_parallel_scrape, _is_nested_parallel
from workflows.base import WorkflowState
from core.config import cfg

def _base_state(urls: list[dict]) -> WorkflowState:
    return {
        "workflow": "research", "goal": "test", "trace_id": "t1",
        "status": "running", "error": "", "result": "", "artifacts": [],
        "retries": 0, "search_results": json.dumps(urls),
        "memory_context": "",
    }

class TestParallelTimeout:
    """Verify workers exceeding timeout are killed gracefully."""

    def test_worker_timeout_returns_error(self, mocker):
        """Worker whose future.result() times out returns error in dossier."""
        # Mock the future to simulate a timeout on result() call
        mock_future = MagicMock()
        mock_future.result.side_effect = FutureTimeoutError("timed out")

        mock_executor = MagicMock()
        mock_executor.submit.return_value = mock_future
        mock_executor.__enter__ = MagicMock(return_value=mock_executor)
        mock_executor.__exit__ = MagicMock(return_value=False)

        mocker.patch("concurrent.futures.ThreadPoolExecutor", return_value=mock_executor)
        mocker.patch("concurrent.futures.as_completed", return_value=[mock_future])
        mocker.patch.object(cfg, "worker_timeout", 0.1, create=True)
        mocker.patch.object(cfg, "max_concurrent_workers", 2, create=True)
        mocker.patch.object(cfg, "research_browser_fallback_max", 0, create=True)

        state = _base_state([{"url": "http://x", "title": "X"}])
        result = node_parallel_scrape(state)
        # All workers timed out, so search_results should be empty
        assert result["search_results"] == ""

    def test_worker_within_timeout_success(self, mocker):
        """Worker finishing within timeout contributes to dossier."""
        def fast(*a, **k):
            return {"url": "http://x", "title": "F", "status": "success", "summary": "ok"}

        mocker.patch("workflows.research._scrape_and_summarize", side_effect=fast)
        mocker.patch.object(cfg, "worker_timeout", 5, create=True)
        mocker.patch.object(cfg, "max_concurrent_workers", 2, create=True)
        mocker.patch.object(cfg, "research_browser_fallback_max", 0, create=True)
        mocker.patch.object(cfg, "web_max_text_chars", 10000, create=True)

        state = _base_state([{"url": "http://x", "title": "X"}])
        result = node_parallel_scrape(state)
        assert "[Source 1]" in result["search_results"]
        assert "ok" in result["search_results"]

class TestNestedParallelGuard:
    """Verify nested ThreadPoolExecutor calls are rejected to prevent deadlock."""

    def test_nested_rejected(self, mocker):
        """node_parallel_scrape from inside ThreadPoolExecutor must reject."""
        mocker.patch.object(cfg, "max_concurrent_workers", 2, create=True)

        def inner():
            state = _base_state([{"url": "http://x", "title": "X"}])
            return node_parallel_scrape(state)

        with ThreadPoolExecutor(max_workers=1) as outer:
            result = outer.submit(inner).result()

        # Nested guard triggers: returns empty search_results
        assert result["search_results"] == ""

    def test_top_level_allowed(self, mocker):
        """node_parallel_scrape at top-level works normally."""
        def fast(*a, **k):
            return {"url": "http://x", "title": "F", "status": "success", "summary": "ok"}

        mocker.patch("workflows.research._scrape_and_summarize", side_effect=fast)
        mocker.patch.object(cfg, "worker_timeout", 5, create=True)
        mocker.patch.object(cfg, "max_concurrent_workers", 2, create=True)
        mocker.patch.object(cfg, "research_browser_fallback_max", 0, create=True)
        mocker.patch.object(cfg, "web_max_text_chars", 10000, create=True)

        state = _base_state([{"url": "http://x", "title": "X"}])
        result = node_parallel_scrape(state)
        assert "[Source 1]" in result["search_results"]
        assert "ok" in result["search_results"]
