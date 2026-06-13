"""tests/workflows/deep_research/test_graph.py"""
import pytest
from workflows.deep_research_core.graph import build_deep_research_graph


def test_graph_exits_via_hard_cap(mocker):
    """Graph should exit when iteration reaches max_iterations."""
    mocker.patch(
        "workflows.deep_research_core.nodes.decompose.llm.complete",
        return_value=mocker.Mock(ok=True, text='["q1"]'),
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search._execute_search_with_fallback",
        return_value=({"status": "success", "data": {"results": []}}, "web"),
    )
    # 6 items: 2 iterations x 2 agent calls + 2 safety margin
    mocker.patch(
        "workflows.deep_research_core.nodes.synthesize.agent",
        side_effect=[
            {"status": "success", "text": "synth"},
            {"status": "success", "text": "20"},
            {"status": "success", "text": "synth"},
            {"status": "success", "text": "20"},
            {"status": "success", "text": "synth"},
            {"status": "success", "text": "20"},
        ],
    )
    mocker.patch(
        "core.memory.memory.recall",
        return_value=[],
    )
    mocker.patch(
        "core.citations.citations.get_sources",
        return_value=[],
    )
    mocker.patch(
        "core.memory.memory.store_semantic",
        return_value=None,
    )

    graph = build_deep_research_graph()
    result = graph.invoke({
        "goal": "test",
        "trace_id": "t1",
        "budget_api_calls": 2,
        "max_iterations": 2,
        "budget_events": [],
        "extracted_evidence": [],
        "failed_sources": [],
        "knowledge_base": "",
        "_prev_knowledge": "",
        "completeness": 0.0,
        "converged": False,
        "sub_queries": [],
        "pending_queries": [],
        "iteration": 0,
        "consecutive_empty_iterations": 0,
    })
    # Hard cap at iteration 2 (stuck-loop also fires: 2 consecutive empty >= 2)
    assert result["iteration"] == 2
    assert result["status"] in ("success", "incomplete")
    assert "Budget Audit" in result.get("report", "")


def test_graph_dual_gate_exit(mocker):
    """Graph should exit early when completeness >= threshold AND converged."""
    mocker.patch(
        "workflows.deep_research_core.nodes.decompose.llm.complete",
        return_value=mocker.Mock(ok=True, text='["q1"]'),
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search._execute_search_with_fallback",
        return_value=({"status": "success", "data": {"results": []}}, "web"),
    )
    # Iteration 1: evidence found (mocked), completeness=90
    # Iteration 2: empty queries, same synthesis, converged=True
    mocker.patch(
        "workflows.deep_research_core.nodes.search._extract_evidence",
        return_value=[{"query": "q1", "url": "http://x", "title": "X", "summary": "S", "tool": "web"}],
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.synthesize.agent",
        side_effect=[
            {"status": "success", "text": "synthesis v1"},
            {"status": "success", "text": "90"},
            {"status": "success", "text": "synthesis v1"},
            {"status": "success", "text": "90"},
            {"status": "success", "text": "synthesis v1"},
            {"status": "success", "text": "90"},
        ],
    )
    mocker.patch(
        "core.memory.memory.recall",
        return_value=[],
    )
    mocker.patch(
        "core.citations.citations.get_sources",
        return_value=[],
    )
    mocker.patch(
        "core.memory.memory.store_semantic",
        return_value=None,
    )

    graph = build_deep_research_graph()
    result = graph.invoke({
        "goal": "test",
        "trace_id": "t1",
        "budget_api_calls": 10,
        "max_iterations": 10,
        "budget_events": [],
        "extracted_evidence": [],
        "failed_sources": [],
        "knowledge_base": "",
        "_prev_knowledge": "",
        "completeness": 0.0,
        "converged": False,
        "sub_queries": [],
        "pending_queries": [],
        "iteration": 0,
        "consecutive_empty_iterations": 0,
    })
    # Should exit at iteration 2 via dual-gate (completeness + convergence)
    assert result["iteration"] == 2
    assert result["status"] == "success"


def test_graph_stuck_loop_exit(mocker):
    """Graph should exit when 2+ consecutive iterations produce no evidence."""
    mocker.patch(
        "workflows.deep_research_core.nodes.decompose.llm.complete",
        return_value=mocker.Mock(ok=True, text='["q1"]'),
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search._execute_search_with_fallback",
        return_value=({"status": "success", "data": {"results": []}}, "web"),
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.synthesize.agent",
        side_effect=[
            {"status": "success", "text": "synth"},
            {"status": "success", "text": "20"},
            {"status": "success", "text": "synth"},
            {"status": "success", "text": "20"},
            {"status": "success", "text": "synth"},
            {"status": "success", "text": "20"},
        ],
    )
    mocker.patch(
        "core.memory.memory.recall",
        return_value=[],
    )
    mocker.patch(
        "core.citations.citations.get_sources",
        return_value=[],
    )
    mocker.patch(
        "core.memory.memory.store_semantic",
        return_value=None,
    )

    graph = build_deep_research_graph()
    result = graph.invoke({
        "goal": "test",
        "trace_id": "t1",
        "budget_api_calls": 10,
        "max_iterations": 10,
        "budget_events": [],
        "extracted_evidence": [],
        "failed_sources": [],
        "knowledge_base": "",
        "_prev_knowledge": "",
        "completeness": 0.0,
        "converged": False,
        "sub_queries": [],
        "pending_queries": [],
        "iteration": 0,
        "consecutive_empty_iterations": 0,
    })
    # Should exit at iteration 2 due to stuck-loop detection
    assert result["iteration"] == 2
    assert result["consecutive_empty_iterations"] == 2
