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
        return_value={"status": "success", "data": {"results": []}},
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
    assert "No budget events recorded" in result.get("report", "")


def test_graph_dual_gate_exit(mocker):
    """Graph should exit early when completeness >= threshold AND converged."""
    mocker.patch(
        "workflows.deep_research_core.nodes.decompose.llm.complete",
        return_value=mocker.Mock(ok=True, text='["q1"]'),
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search._execute_search_with_fallback",
        return_value={"status": "success", "data": {"results": []}},
    )
    # Iteration 1: evidence found (mocked), completeness=90
    # Iteration 2: empty queries, same synthesis, converged=True
    mocker.patch(
        "workflows.deep_research_core.nodes.search._extract_evidence",
        return_value=[{"query": "q1", "url": "http://x", "title": "X", "summary": "S", "source": "web"}],
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
        return_value={"status": "success", "data": {"results": []}},
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


def test_node_notify_calls_notify_with_correct_signature(mocker):
    """Verify _node_notify calls notify with the correct action parameter.

    Regression test for the notify() TypeError bug where action was missing
    and trace_id was passed as an invalid kwarg.
    """
    mock_notify = mocker.patch("workflows.deep_research_core.graph.notify")
    state = {
        "result": "Test research result",
        "trace_id": "test-123",
    }
    from workflows.deep_research_core.graph import _node_notify
    result = _node_notify(state)
    mock_notify.assert_called_once_with(
        action="send",
        title="DeepResearch",
        message="Test research result",
    )
    assert result == state


def test_node_distill_is_noop_pass_through():
    """Verify _node_distill is a no-op pass-through node.

    sleep_learn does not export distill_workflow and tracer.get_trace()
    does not exist. The node must not crash and must return state unchanged.
    """
    from workflows.deep_research_core.graph import _node_distill
    state = {
        "trace_id": "test-123",
        "result": "Test result",
        "knowledge_base": "Some knowledge",
    }
    result = _node_distill(state)
    assert result == state


def test_report_status_incomplete_when_below_threshold(mocker):
    """Verify report node returns status='incomplete' when completeness < threshold."""
    from workflows.deep_research_core.graph import _node_report
    state = {
        "knowledge_base": "Partial findings",
        "synthesis": "",
        "completeness": 45.0,
        "completeness_threshold": 85.0,
        "budget_events": [],
    }
    result = _node_report(state)
    assert result["status"] == "incomplete"
    assert "Partial findings" in result["report"]


def test_report_status_success_when_above_threshold(mocker):
    """Verify report node returns status='success' when completeness >= threshold."""
    from workflows.deep_research_core.graph import _node_report
    state = {
        "knowledge_base": "Complete findings",
        "synthesis": "Complete synthesis",
        "completeness": 90.0,
        "completeness_threshold": 85.0,
        "budget_events": [],
    }
    result = _node_report(state)
    assert result["status"] == "success"
    assert "Complete synthesis" in result["report"]


def test_node_recall_returns_memory_context(mocker):
    """Verify _node_recall calls memory.recall with correct signature."""
    mock_recall = mocker.patch("workflows.deep_research_core.graph.memory.recall")
    mock_recall.return_value = [
        {"type": "semantic", "score": 0.85, "text": "Previous research on async"},
    ]
    from workflows.deep_research_core.graph import _node_recall
    state = {
        "goal": "Python async frameworks",
        "trace_id": "test-123",
    }
    result = _node_recall(state)
    mock_recall.assert_called_once_with(
        query="Python async frameworks",
        top_k=5,
        trace_id="test-123",
    )
    assert "Previous research on async" in result.get("memory_context", "")


def test_node_recall_graceful_on_failure(mocker):
    """Verify _node_recall returns empty memory_context on exception."""
    mock_recall = mocker.patch("workflows.deep_research_core.graph.memory.recall")
    mock_recall.side_effect = Exception("DB down")
    from workflows.deep_research_core.graph import _node_recall
    state = {
        "goal": "Python async frameworks",
        "trace_id": "test-123",
    }
    result = _node_recall(state)
    assert result.get("memory_context", "") == ""
