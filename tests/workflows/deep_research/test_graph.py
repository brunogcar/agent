"""Integration tests for the compiled DeepResearch graph."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from workflows.deep_research_core.graph import build_deep_research_graph


def test_graph_exits_via_hard_cap():
    """Graph runs and exits via max_iterations hard cap."""
    graph = build_deep_research_graph()

    def mock_agent(*, role, task, content, trace_id):
        if role == "plan":
            return {"status": "success", "text": '{"steps": [{"description": "q1"}]}', "role": "plan", "model": "m", "elapsed": 1}
        elif role == "research":
            return {"status": "success", "text": "done", "role": "research", "model": "m", "elapsed": 1}
        elif role == "critique":
            return {"status": "success", "text": "95", "role": "critique", "model": "m", "elapsed": 1}
        return {"status": "error", "error": "unknown"}

    mock_web = {"status": "success", "data": {"results": [{"url": "http://a", "title": "A", "content": "text"}]}}
    mock_llm = MagicMock()
    mock_llm.ok = True
    mock_llm.text = "summary"

    # Patch LOCAL names inside each node module
    with patch("workflows.deep_research_core.nodes.decompose.agent", side_effect=mock_agent):
        with patch("workflows.deep_research_core.nodes.search.web", return_value=mock_web):
            with patch("workflows.deep_research_core.nodes.search.tavily", return_value=mock_web):
                with patch("workflows.deep_research_core.nodes.search.llm") as mock_llm_cls:
                    mock_llm_cls.complete.return_value = mock_llm
                    with patch("workflows.deep_research_core.nodes.synthesize.agent", side_effect=mock_agent):
                        result = graph.invoke(
                            {
                                "goal": "test",
                                "trace_id": "t1",
                                "iteration": 0,
                                "max_iterations": 1,
                                "completeness_threshold": 85.0,
                                "knowledge_base": "",
                                "_prev_knowledge": "",
                                "pending_queries": [],
                                "extracted_evidence": [],
                                "failed_sources": [],
                                "budget_api_calls": 10,
                                "budget_browser_actions": 5,
                                "budget_events": [],
                                "synthesis": "",
                                "report": "",
                            }
                        )
                        assert result["status"] == "success"
                        assert "done" in result["report"]


def test_graph_loops_then_exits():
    """Graph loops once then exits via hard cap."""
    graph = build_deep_research_graph()

    def mock_agent(*, role, task, content, trace_id):
        if role == "plan":
            return {"status": "success", "text": '{"steps": [{"description": "q1"}]}', "role": "plan", "model": "m", "elapsed": 1}
        elif role == "research":
            return {"status": "success", "text": "done", "role": "research", "model": "m", "elapsed": 1}
        elif role == "critique":
            return {"status": "success", "text": "95", "role": "critique", "model": "m", "elapsed": 1}
        return {"status": "error", "error": "unknown"}

    mock_web = {"status": "success", "data": {"results": [{"url": "http://a", "title": "A", "content": "text"}]}}
    mock_llm = MagicMock()
    mock_llm.ok = True
    mock_llm.text = "summary"

    with patch("workflows.deep_research_core.nodes.decompose.agent", side_effect=mock_agent):
        with patch("workflows.deep_research_core.nodes.search.web", return_value=mock_web):
            with patch("workflows.deep_research_core.nodes.search.tavily", return_value=mock_web):
                with patch("workflows.deep_research_core.nodes.search.llm") as mock_llm_cls:
                    mock_llm_cls.complete.return_value = mock_llm
                    with patch("workflows.deep_research_core.nodes.synthesize.agent", side_effect=mock_agent):
                        result = graph.invoke(
                            {
                                "goal": "test",
                                "trace_id": "t1",
                                "iteration": 0,
                                "max_iterations": 2,
                                "completeness_threshold": 85.0,
                                "knowledge_base": "",
                                "_prev_knowledge": "",
                                "pending_queries": [],
                                "extracted_evidence": [],
                                "failed_sources": [],
                                "budget_api_calls": 10,
                                "budget_browser_actions": 5,
                                "budget_events": [],
                                "synthesis": "",
                                "report": "",
                            }
                        )
                        assert result["status"] == "success"
                        assert result["iteration"] == 2
