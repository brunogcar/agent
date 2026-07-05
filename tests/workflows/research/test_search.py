"""tests/workflows/research/test_search.py
Tests for node_search.
"""
from __future__ import annotations

import json
import inspect
from unittest.mock import patch, MagicMock

from workflows.research_impl.nodes.search import node_search


def _base_state():
    return {
        "workflow": "research", "goal": "test", "trace_id": "t1",
        "status": "running", "error": "", "result": "", "artifacts": [],
        "retries": 0, "search_results": ""
    }


class TestNodeSearch:
    def test_node_search_outputs_valid_json(self):
        """node_search MUST output a JSON string of URLs for the parallel scraper."""
        state = _base_state()
        mock_web_result = {
            "status": "success",
            "results": [
                {"url": "http://a.com", "title": "A", "snippet": "snip A"},
                {"url": "http://b.com", "title": "B", "snippet": "snip B"}
            ]
        }
        with patch("tools.web.web", return_value=mock_web_result):
            new_state = node_search(state)
        parsed = json.loads(new_state["search_results"])
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["url"] == "http://a.com"

    def test_node_search_handles_empty_results(self):
        """If web search fails, search_results must be empty string, not invalid JSON."""
        state = _base_state()
        with patch("tools.web.web", return_value={"status": "failed", "error": "timeout"}):
            new_state = node_search(state)
        assert new_state["search_results"] == ""

    def test_node_search_deduplicates_urls(self):
        """[Fix #12] Duplicate URLs from SearXNG should be deduplicated."""
        state = _base_state()
        mock_web_result = {
            "status": "success",
            "results": [
                {"url": "http://same.com", "title": "A", "snippet": "snip A"},
                {"url": "http://same.com", "title": "B", "snippet": "snip B"},
                {"url": "http://unique.com", "title": "C", "snippet": "snip C"}
            ]
        }
        with patch("tools.web.web", return_value=mock_web_result):
            new_state = node_search(state)
        parsed = json.loads(new_state["search_results"])
        assert len(parsed) == 2, "Duplicate URL should be removed"
        urls = [p["url"] for p in parsed]
        assert "http://same.com" in urls
        assert "http://unique.com" in urls


class TestNodeSearchMaxResults:
    """Bug fix: max_results must use cfg.web_max_search_results, not hardcoded 3."""

    def test_node_search_uses_cfg_max_results(self):
        """node_search must pass cfg.web_max_search_results to web(), not hardcoded 3."""
        state = _base_state()
        state["goal"] = "test query"

        fake_cfg = MagicMock()
        fake_cfg.web_max_search_results = 10
        with patch("tools.web.web") as mock_web, \
             patch("core.config.cfg", fake_cfg):
            mock_web.return_value = {"status": "success", "results": []}
            node_search(state)

            call_kwargs = mock_web.call_args.kwargs
            assert call_kwargs.get("max_results") == 10, (
                f"max_results must be cfg.web_max_search_results (10), got "
                f"{call_kwargs.get('max_results')}. Was hardcoded to 3."
            )

    def test_node_search_does_not_hardcode_3(self):
        """The source must not contain hardcoded max_results=3."""
        source = inspect.getsource(node_search)
        assert "max_results=3)" not in source, (
            "node_search must not hardcode max_results=3 — use cfg.web_max_search_results"
        )
