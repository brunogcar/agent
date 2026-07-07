"""tests/workflows/deep_research/test_graph.py
Graph topology, WORKFLOW_METADATA, facade, and integration tests.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from workflows.deep_research_impl.graph import build_deep_research_graph, WORKFLOW_METADATA


# ─── Graph topology ─────────────────────────────────────────────────────────

class TestGraphTopology:
    def test_graph_builds(self):
        graph = build_deep_research_graph()
        assert graph is not None
        assert hasattr(graph, "invoke")

    def test_graph_exits_via_hard_cap(self, mocker, base_state):
        """Graph should exit when iteration reaches max_iterations."""
        mocker.patch(
            "workflows.deep_research_impl.nodes.decompose._parse_sub_queries",
            return_value=["What is LangGraph?"],
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.decompose.llm.complete",
            return_value=mocker.MagicMock(ok=True, text='["What is LangGraph?"]'),
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._execute_search_with_fallback",
            return_value=({"status": "success", "data": {"results": []}}, "tavily", {}),
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._extract_evidence",
            return_value=([], {}),
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.synthesize.agent",
            side_effect=[
                {"status": "success", "text": "done"},
                {"status": "success", "text": "20"},
                {"status": "success", "text": "done"},
                {"status": "success", "text": "20"},
            ],
        )
        graph = build_deep_research_graph()
        result = graph.invoke({**base_state, "max_iterations": 2})
        assert result["status"] == "incomplete"
        assert result["iteration"] == 2

    def test_graph_dual_gate_exit(self, mocker, base_state):
        """Graph should exit via dual-gate (completeness + convergence) before hard cap."""
        mocker.patch(
            "workflows.deep_research_impl.nodes.decompose._parse_sub_queries",
            return_value=["What is LangGraph?"],
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.decompose.llm.complete",
            return_value=mocker.MagicMock(ok=True, text='["What is LangGraph?"]'),
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._execute_search_with_fallback",
            return_value=(
                {"status": "success", "data": {"results": [
                    {"url": "https://example.com", "title": "Example", "text": "LangGraph is a framework."}
                ]}},
                "tavily",
                {},
            ),
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._extract_evidence",
            return_value=(
                [{"query": "q1", "url": "https://example.com", "title": "Example",
                  "summary": "LangGraph is a framework.", "source": "web"}],
                {},
            ),
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.synthesize.agent",
            side_effect=[
                {"status": "success", "text": "LangGraph is a framework for building LLM apps."},
                {"status": "success", "text": "95"},
            ],
        )
        mocker.patch("workflows.deep_research_impl.graph.memory.recall", return_value=[])
        mocker.patch("workflows.deep_research_impl.graph.memory.store_semantic", return_value=None)
        mocker.patch("workflows.deep_research_impl.graph.memory.store_episodic", return_value=None)
        mocker.patch("workflows.deep_research_impl.graph.notify", return_value=None)
        mocker.patch("core.citations.citations.get_sources", return_value=[])

        graph = build_deep_research_graph()
        initial_state = {
            **base_state,
            "max_iterations": 10,
            "knowledge_base": "LangGraph is a framework for building LLM apps.",
            "_prev_knowledge": "LangGraph is a framework for building LLM apps.",
            "completeness": 95.0,
        }
        result = graph.invoke(initial_state)
        assert result["status"] == "success"

    def test_graph_loops_then_exits(self, mocker, base_state):
        """Graph should loop via decompose until max_iterations or dual-gate."""
        mocker.patch(
            "workflows.deep_research_impl.nodes.decompose._parse_sub_queries",
            return_value=["What is LangGraph?"],
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.decompose.llm.complete",
            return_value=mocker.MagicMock(ok=True, text='["What is LangGraph?"]'),
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._execute_search_with_fallback",
            return_value=({"status": "success", "data": {"results": []}}, "tavily", {}),
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.search._extract_evidence",
            return_value=([], {}),
        )
        mocker.patch(
            "workflows.deep_research_impl.nodes.synthesize.agent",
            side_effect=[
                {"status": "success", "text": "done"},
                {"status": "success", "text": "20"},
                {"status": "success", "text": "done"},
                {"status": "success", "text": "20"},
            ],
        )
        mocker.patch("workflows.deep_research_impl.graph.memory.recall", return_value=[])
        mocker.patch("workflows.deep_research_impl.graph.memory.store_semantic", return_value=None)
        mocker.patch("workflows.deep_research_impl.graph.memory.store_episodic", return_value=None)
        mocker.patch("workflows.deep_research_impl.graph.notify", return_value=None)
        mocker.patch("core.citations.citations.get_sources", return_value=[])

        graph = build_deep_research_graph()
        result = graph.invoke({**base_state, "max_iterations": 2})
        assert result["status"] == "incomplete"
        assert result["iteration"] == 2


# ─── WORKFLOW_METADATA ──────────────────────────────────────────────────────

class TestWorkflowMetadata:
    """v1.1: WORKFLOW_METADATA must exist and have correct structure."""

    def test_metadata_exists(self):
        assert isinstance(WORKFLOW_METADATA, dict)
        assert WORKFLOW_METADATA["name"] == "deep_research"
        assert WORKFLOW_METADATA["version"] == "1.1"

    def test_metadata_has_all_8_nodes(self):
        nodes = WORKFLOW_METADATA["nodes"]
        assert len(nodes) == 8
        names = [n["name"] for n in nodes]
        for expected in ["recall", "decompose", "search", "synthesize",
                         "report", "notify", "store", "distill"]:
            assert expected in names, f"Missing node: {expected}"

    def test_metadata_has_edges_with_loop(self):
        edges = WORKFLOW_METADATA["edges"]
        pairs = [(e["from"], e["to"]) for e in edges]
        assert ("recall", "decompose") in pairs
        assert ("synthesize", "decompose") in pairs  # the loop back
        assert ("synthesize", "report") in pairs      # the exit
        assert ("store", "distill") in pairs

    def test_metadata_nodes_have_descriptions(self):
        for node in WORKFLOW_METADATA["nodes"]:
            assert "description" in node, f"Node {node['name']} missing description"
            assert len(node["description"]) > 0


# ─── Partial-dict returns (structural invariant) ────────────────────────────

class TestPartialDictReturns:
    """v1.1/P1 #7: _node_* helpers return partial dicts, not {**state, ...}."""

    def test_recall_returns_partial_dict(self, mocker):
        from workflows.deep_research_impl.graph import _node_recall
        mocker.patch(
            "workflows.deep_research_impl.graph.memory.recall",
            return_value=[{"type": "semantic", "score": 0.9, "text": "ctx"}],
        )
        state = {"goal": "g", "trace_id": "t1", "iteration": 0}
        result = _node_recall(state)
        assert "memory_context" in result
        assert "goal" not in result, "Partial dict must not echo unchanged state keys"
        assert "iteration" not in result

    def test_store_returns_empty_dict(self, mocker):
        from workflows.deep_research_impl.graph import _node_store
        mocker.patch("workflows.deep_research_impl.graph.memory.store_semantic")
        mocker.patch("workflows.deep_research_impl.graph.memory.store_episodic")
        state = {"result": "r", "goal": "g", "status": "success", "trace_id": "t1"}
        result = _node_store(state)
        assert result == {}, "_node_store must return {} (side effects only)"

    def test_report_returns_partial_dict(self, mocker):
        from workflows.deep_research_impl.graph import _node_report
        mocker.patch("core.citations.citations.get_sources", return_value=[])
        state = {
            "knowledge_base": "kb", "synthesis": "syn",
            "completeness": 90.0, "completeness_threshold": 85.0,
            "trace_id": "t1",
        }
        result = _node_report(state)
        assert "report" in result and "result" in result and "status" in result
        assert "knowledge_base" not in result, "Partial dict must not echo input"

    def test_notify_returns_partial_dict(self, mocker):
        from workflows.deep_research_impl.graph import _node_notify
        mocker.patch("workflows.deep_research_impl.graph.notify")
        mocker.patch("core.citations.citations.get_sources", return_value=[])
        state = {"result": "r", "trace_id": "t1", "status": "success"}
        result = _node_notify(state)
        assert "artifacts" in result
        assert "result" not in result, "Partial dict must not echo input"

    def test_distill_returns_empty_dict(self):
        from workflows.deep_research_impl.graph import _node_distill
        state = {"trace_id": "t1", "result": "r", "knowledge_base": "kb"}
        assert _node_distill(state) == {}


# ─── Facade ─────────────────────────────────────────────────────────────────

class TestFacade:
    def test_facade_initializes_all_state_fields(self, mocker):
        """run_deep_research_agent must initialize state without AttributeError."""
        mock_run = mocker.patch("workflows.deep_research.run_workflow")
        mock_run.return_value = {"status": "success"}
        from workflows.deep_research import run_deep_research_agent
        result = run_deep_research_agent("What is LangGraph?")
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert "convergence_threshold" in call_kwargs
        assert "budget_browser_actions" in call_kwargs
        assert "budget_api_calls" in call_kwargs
        assert "max_iterations" in call_kwargs
        assert "seen_urls" in call_kwargs
        assert result["status"] == "success"

    def test_facade_rejects_empty_goal(self):
        from workflows.deep_research import run_deep_research_agent
        result = run_deep_research_agent("")
        assert result["status"] == "failed"
        assert "Goal is required" in result["error"]

    def test_facade_rejects_whitespace_goal(self):
        from workflows.deep_research import run_deep_research_agent
        result = run_deep_research_agent(" ")
        assert result["status"] == "failed"
        assert "Goal is required" in result["error"]

    def test_facade_timeout_enforcement(self, mocker):
        """run_deep_research_agent returns timeout when graph exceeds limit."""
        mock_run = mocker.patch("workflows.deep_research.run_workflow")
        mock_run.side_effect = lambda **kwargs: (
            __import__("time").sleep(2),
            {"status": "success"}
        )[1]
        from workflows.deep_research import run_deep_research_agent
        result = run_deep_research_agent("What is LangGraph?", timeout=1)
        assert result["status"] == "timeout"
        assert "exceeded 1s timeout" in result["error"]
