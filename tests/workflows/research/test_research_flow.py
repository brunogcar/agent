"""
tests/workflows/research/test_research_flow.py
Deep integration tests for the Research Workflow graph and node state mutations.
"""
from __future__ import annotations
import json
import pytest
from unittest.mock import patch
from workflows.base import WorkflowState
from workflows.research import (
    build_research_graph, 
    node_search, 
    node_parallel_scrape, 
    route_after_search
)

def _base_state() -> WorkflowState:
    return {
        "workflow": "research", "goal": "test", "trace_id": "t1",
        "status": "running", "error": "", "result": "", "artifacts": [],
        "retries": 0, "search_results": ""
    }

class TestResearchGraphTopology:
    def test_graph_builds_without_errors(self):
        """The LangGraph must build successfully."""
        graph = build_research_graph()
        assert graph is not None

    def test_graph_contains_parallel_scrape_node(self):
        """Verify the Phase 7 parallel_scrape node is actually in the graph."""
        graph = build_research_graph()
        # Handle both compiled and uncompiled graph objects
        nodes = getattr(graph, "nodes", {})
        if not nodes and hasattr(graph, "get_graph"):
            nodes = graph.get_graph().nodes
        assert "parallel_scrape" in nodes, "Phase 7 parallel_scrape node missing from graph!"

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
        
        # Patch where it is actually imported/used
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

class TestNodeParallelScrape:
    def test_dossier_hard_cap_truncation(self):
        """If combined summaries exceed the cap, the dossier MUST be truncated."""
        from core.config import cfg
        original_cap = cfg.web_max_text_chars
        cfg.web_max_text_chars = 50  # Force tiny cap (max dossier = 100 chars)
        
        try:
            state = _base_state()
            state["search_results"] = json.dumps([
                {"url": "http://a.com", "title": "A"},
                {"url": "http://b.com", "title": "B"}
            ])
            
            def mock_worker(url, title, goal, trace_id):
                return {"url": url, "title": title, "status": "success", "summary": "X" * 200}
                
            with patch("workflows.research._scrape_and_summarize", side_effect=mock_worker):
                new_state = node_parallel_scrape(state)
                
            dossier = new_state["search_results"]
            assert "[...TRUNCATED DUE TO LENGTH...]" in dossier
            assert len(dossier) <= (50 * 2) + 50  # Cap * 2 + marker length
        finally:
            cfg.web_max_text_chars = original_cap

    def test_failed_workers_are_excluded_from_dossier(self):
        """
        Based on current research.py implementation: 
        Failed workers do not get a citation slot and are excluded from the dossier.
        Only successful workers increment the citation index.
        """
        state = _base_state()
        state["search_results"] = json.dumps([
            {"url": "http://a.com", "title": "A"},
            {"url": "http://b.com", "title": "B"}
        ])
        
        def mock_worker(url, title, goal, trace_id):
            if "b.com" in url:
                return {"url": url, "title": title, "status": "failed", "error": "timeout"}
            return {"url": url, "title": title, "status": "success", "summary": "Good data"}
            
        with patch("workflows.research._scrape_and_summarize", side_effect=mock_worker):
            new_state = node_parallel_scrape(state)
            
        dossier = new_state["search_results"]
        assert "[Source 1]" in dossier, "Successful worker should be Source 1"
        assert "http://a.com" in dossier
        # Failed worker should NOT be in the dossier based on current implementation
        assert "http://b.com" not in dossier, "Failed worker should be excluded from dossier"

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