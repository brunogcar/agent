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
            assert "[... dossier truncated:" in dossier
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


class TestNodeSynthesizeActionDispatch:
    """Regression tests for v1.5 fix: agent() must be called with action='dispatch'.

    Previously node_synthesize called agent(role='research', ...) without
    action='dispatch'. The agent() facade requires action='dispatch' for
    LLM calls — without it, the call returns 'Unknown action' error and
    node_synthesize ALWAYS falls into the error branch, making the research
    workflow unable to produce any result.
    """

    def test_node_synthesize_calls_agent_with_action_dispatch(self):
        """agent() must be invoked with action='dispatch'."""
        from workflows.research import node_synthesize

        state = _base_state()
        state["search_results"] = "### [Source 1] Title\nURL: http://a.com\nGood data"

        # NOTE: agent is imported INSIDE node_synthesize (`from tools.agent import agent`),
        # so we patch at the source module, not at workflows.research.agent.
        with patch("tools.agent.agent") as mock_agent:
            mock_agent.return_value = {
                "status": "success",
                "text": "synthesized answer",
                "elapsed": 0.1,
            }
            node_synthesize(state)

        assert mock_agent.called, "agent() must be called from node_synthesize"
        _, kwargs = mock_agent.call_args
        assert kwargs.get("action") == "dispatch", (
            f"agent() must be called with action='dispatch'; got action={kwargs.get('action')!r}. "
            f"This regresses the v1.5 fix — without action='dispatch', the agent facade "
            f"returns 'Unknown action' and node_synthesize always fails."
        )

    def test_node_synthesize_propagates_success_when_action_dispatch_present(self):
        """With action='dispatch', a successful agent() response must propagate
        to state['result'] instead of always falling into the error branch."""
        from workflows.research import node_synthesize

        state = _base_state()
        state["search_results"] = "### [Source 1] Title\nURL: http://a.com\nGood data"

        # NOTE: agent is imported INSIDE node_synthesize — patch at source.
        with patch("tools.agent.agent") as mock_agent:
            mock_agent.return_value = {
                "status": "success",
                "text": "real synthesized answer",
                "elapsed": 0.1,
            }
            result = node_synthesize(state)

        assert result.get("result") == "real synthesized answer", (
            "node_synthesize must populate state['result'] from agent response when "
            "action='dispatch' is correctly passed. Before the v1.5 fix, this always "
            "returned node_error() because agent() returned 'Unknown action' error."
        )


class TestNodeSearchMaxResults:
    """Bug fix: max_results must use cfg.web_max_search_results, not hardcoded 3."""

    def test_node_search_uses_cfg_max_results(self):
        """node_search must pass cfg.web_max_search_results to web(), not hardcoded 3."""
        from workflows.research import node_search
        from unittest.mock import patch, MagicMock

        state = _base_state()
        state["goal"] = "test query"

        # NOTE: web AND cfg are imported INSIDE node_search, so we patch at source.
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
        import inspect
        from workflows.research import node_search
        source = inspect.getsource(node_search)
        # Must not have max_results=3 as a literal (3 as part of cfg is fine)
        assert "max_results=3)" not in source, (
            "node_search must not hardcode max_results=3 — use cfg.web_max_search_results"
        )


class TestNodeSynthesizeErrorCheck:
    """Style fix: not r.get('status') == 'success' → r.get('status') != 'success'."""

    def test_synthesize_uses_explicit_not_equal(self):
        """node_synthesize must use != 'success' in actual code, not 'not ... == "success"'."""
        import inspect
        import ast
        from workflows.research import node_synthesize
        source = inspect.getsource(node_synthesize)
        # Strip comments and docstrings to check actual code only
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                    node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
        code_only = ast.unparse(tree)
        code_lines = [line for line in code_only.split("\n") if not line.strip().startswith("#")]
        code_str = "\n".join(code_lines)
        assert "not r.get" not in code_str or "!=" in code_str, (
            "node_synthesize should use r.get('status') != 'success' in actual code, "
            "not the confusing 'not r.get(status) == success' pattern"
        )

