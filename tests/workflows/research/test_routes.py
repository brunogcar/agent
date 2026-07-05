"""tests/workflows/research/test_routes.py
Tests for routing functions.
"""
from __future__ import annotations

from workflows.research_impl.routes import route_after_search, route_after_synthesize


def _base_state():
    return {
        "workflow": "research", "goal": "test", "trace_id": "t1",
        "status": "running", "error": "", "result": "", "artifacts": [],
        "retries": 0, "search_results": ""
    }


class TestRouting:
    def test_route_after_search_routes_to_synthesize_on_success(self):
        """Valid dossier must route to synthesize."""
        state = _base_state()
        state["search_results"] = "### [Source 1] Title\nURL: http://a.com\nGood data"
        assert route_after_search(state) == "synthesize"

    def test_route_after_search_routes_to_end_on_empty(self):
        """Empty dossier must route to END (or failed)."""
        state = _base_state()
        state["search_results"] = ""
        next_node = route_after_search(state)
        assert next_node in ("END", "failed", "__end__", "notify")

    def test_route_after_synthesize_routes_to_report_on_success(self):
        """Successful synthesis must route to report."""
        state = _base_state()
        state["status"] = "running"
        assert route_after_synthesize(state) == "report"

    def test_route_after_synthesize_routes_to_end_on_failed(self):
        """Failed synthesis must route to END."""
        state = _base_state()
        state["status"] = "failed"
        assert route_after_synthesize(state) == "failed"
