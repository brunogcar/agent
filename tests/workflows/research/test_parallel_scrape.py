"""tests/workflows/research/test_parallel_scrape.py
Tests for node_parallel_scrape — dossier building, truncation, failed workers,
timeout handling, and nested parallel guard.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from workflows.research_impl.nodes.parallel_scrape import node_parallel_scrape
from workflows.research_impl.helpers import _is_nested_parallel


def _base_state():
    return {
        "workflow": "research", "goal": "test", "trace_id": "t1",
        "status": "running", "error": "", "result": "", "artifacts": [],
        "retries": 0, "search_results": ""
    }


class TestNodeParallelScrape:
    def test_dossier_hard_cap_truncation(self):
        """If combined summaries exceed the cap, the dossier MUST be truncated."""
        from core.config import cfg
        original_cap = cfg.web_max_text_chars
        cfg.web_max_text_chars = 50

        try:
            state = _base_state()
            state["search_results"] = json.dumps([
                {"url": "http://a.com", "title": "A"},
                {"url": "http://b.com", "title": "B"}
            ])

            def mock_worker(url, title, goal, trace_id):
                return {"url": url, "title": title, "status": "success", "summary": "X" * 200}

            with patch("workflows.research_impl.nodes.parallel_scrape._scrape_and_summarize", side_effect=mock_worker):
                new_state = node_parallel_scrape(state)

            dossier = new_state["search_results"]
            assert "[... dossier truncated:" in dossier
            assert len(dossier) <= (50 * 2) + 50
        finally:
            cfg.web_max_text_chars = original_cap

    def test_failed_workers_are_excluded_from_dossier(self):
        """Failed workers do not get a citation slot and are excluded from the dossier."""
        state = _base_state()
        state["search_results"] = json.dumps([
            {"url": "http://a.com", "title": "A"},
            {"url": "http://b.com", "title": "B"}
        ])

        def mock_worker(url, title, goal, trace_id):
            if "b.com" in url:
                return {"url": url, "title": title, "status": "failed", "error": "timeout"}
            return {"url": url, "title": title, "status": "success", "summary": "Good data"}

        with patch("workflows.research_impl.nodes.parallel_scrape._scrape_and_summarize", side_effect=mock_worker):
            new_state = node_parallel_scrape(state)

        dossier = new_state["search_results"]
        assert "[Source 1]" in dossier, "Successful worker should be Source 1"
        assert "http://a.com" in dossier
        assert "http://b.com" not in dossier, "Failed worker should be excluded from dossier"


class TestNestedParallelGuard:
    """Tests for the nested parallel scrape guard."""

    def test_nested_parallel_rejected(self):
        """When parallel_scrape is already active, nested calls must be rejected."""
        from workflows.research_impl.helpers import _set_parallel_active
        _set_parallel_active(True)
        try:
            assert _is_nested_parallel() is True
        finally:
            _set_parallel_active(False)

    def test_not_nested_proceeds(self):
        """When parallel_scrape is NOT active, nested guard returns False."""
        from workflows.research_impl.helpers import _set_parallel_active
        _set_parallel_active(False)
        assert _is_nested_parallel() is False


class TestWorkerTimeout:
    """Tests for worker timeout handling."""

    def test_worker_exceeds_timeout(self):
        """Workers that exceed the timeout should return a failed status."""
        # This is tested via the mock — real timeout testing requires
        # actual ThreadPoolExecutor which is covered by integration tests.
        state = _base_state()
        state["search_results"] = json.dumps([
            {"url": "http://slow.com", "title": "Slow"}
        ])

        def slow_worker(url, title, goal, trace_id):
            return {"url": url, "title": title, "status": "failed", "error": "timeout"}

        with patch("workflows.research_impl.nodes.parallel_scrape._scrape_and_summarize", side_effect=slow_worker):
            new_state = node_parallel_scrape(state)

        assert new_state["search_results"] == "", "Failed worker should produce empty dossier"
