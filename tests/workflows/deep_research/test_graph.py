"""tests/workflows/deep_research/test_graph.py
Integration tests for the DeepResearch LangGraph.
"""
import pytest
from langgraph.graph import END
from workflows.deep_research_core.graph import build_deep_research_graph
from workflows.deep_research_core.state import DeepResearchState

BASE_STATE = {
    "goal": "What is LangGraph?",
    "trace_id": "test-graph-001",
    "iteration": 0,
    "consecutive_empty_iterations": 0,
    "budget_api_calls": 5,
    "budget_browser_actions": 2,
    "budget_events": [],
    "max_iterations": 10,
    "completeness_threshold": 85.0,
    "convergence_threshold": 0.85,
    "knowledge_base": "",
    "_prev_knowledge": "",
    "completeness": 0.0,
    "converged": False,
    "sub_queries": [],
    "pending_queries": [],
    "extracted_evidence": [],
    "failed_sources": [],
    "seen_urls": [],
}

def test_graph_exits_via_hard_cap(mocker):
    """Graph should exit when iteration reaches max_iterations."""
    mocker.patch(
        "workflows.deep_research_core.nodes.decompose._parse_sub_queries",
        return_value=["What is LangGraph?"],
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.decompose.llm.complete",
        return_value=mocker.MagicMock(ok=True, text='["What is LangGraph?"]'),
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search._execute_search_with_fallback",
        return_value=({"status": "success", "data": {"results": []}}, "tavily", {}),
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search._extract_evidence",
        return_value=([], {}),
    )
    # 2 iterations * 2 agent calls (research + critique) = 4 total
    mocker.patch(
        "workflows.deep_research_core.nodes.synthesize.agent",
        side_effect=[
            {"status": "success", "text": "done"},  # iter 1 research
            {"status": "success", "text": "20"},   # iter 1 critique (low score)
            {"status": "success", "text": "done"},  # iter 2 research
            {"status": "success", "text": "20"},   # iter 2 critique (low score)
        ],
    )

    graph = build_deep_research_graph()
    initial_state = {**BASE_STATE, "max_iterations": 2}
    result = graph.invoke(initial_state)
    # Hard cap reached with low completeness -> status is incomplete
    assert result["status"] == "incomplete"
    assert result["iteration"] == 2

def test_graph_dual_gate_exit(mocker):
    """Graph should exit via dual-gate (completeness + convergence) before hard cap."""
    mocker.patch(
        "workflows.deep_research_core.nodes.decompose._parse_sub_queries",
        return_value=["What is LangGraph?"],
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.decompose.llm.complete",
        return_value=mocker.MagicMock(ok=True, text='["What is LangGraph?"]'),
    )
    # Consistent mocks: search returns results, extract returns evidence
    mocker.patch(
        "workflows.deep_research_core.nodes.search._execute_search_with_fallback",
        return_value=(
            {
                "status": "success",
                "data": {
                    "results": [
                        {"url": "https://example.com", "title": "Example", "text": "LangGraph is a framework."}
                    ]
                }
            },
            "tavily",
            {},
        ),
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search._extract_evidence",
        return_value=(
            [{"query": "q1", "url": "https://example.com", "title": "Example", "summary": "LangGraph is a framework.", "source": "web"}],
            {},
        ),
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.synthesize.agent",
        side_effect=[
            {"status": "success", "text": "LangGraph is a framework for building LLM apps."},  # research
            {"status": "success", "text": "95"},  # critique (high score)
        ],
    )
    mocker.patch(
        "workflows.deep_research_core.graph.memory.recall",
        return_value=[],
    )
    mocker.patch(
        "workflows.deep_research_core.graph.memory.store_semantic",
        return_value=None,
    )
    mocker.patch(
        "workflows.deep_research_core.graph.memory.store_episodic",
        return_value=None,
    )
    mocker.patch(
        "workflows.deep_research_core.graph.notify",
        return_value=None,
    )
    mocker.patch(
        "core.citations.citations.get_sources",
        return_value=[],
    )

    graph = build_deep_research_graph()
    initial_state = {
        **BASE_STATE,
        "max_iterations": 10,
        "knowledge_base": "LangGraph is a framework for building LLM apps.",
        "_prev_knowledge": "LangGraph is a framework for building LLM apps.",
        "completeness": 95.0,
    }
    result = graph.invoke(initial_state)
    # Dual-gate should fire: completeness >= threshold AND converged
    assert result["status"] == "success"

def test_graph_loops_then_exits(mocker):
    """Graph should loop via decompose until max_iterations or dual-gate."""
    mocker.patch(
        "workflows.deep_research_core.nodes.decompose._parse_sub_queries",
        return_value=["What is LangGraph?"],
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.decompose.llm.complete",
        return_value=mocker.MagicMock(ok=True, text='["What is LangGraph?"]'),
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search._execute_search_with_fallback",
        return_value=({"status": "success", "data": {"results": []}}, "tavily", {}),
    )
    mocker.patch(
        "workflows.deep_research_core.nodes.search._extract_evidence",
        return_value=([], {}),
    )
    # 2 iterations * 2 agent calls = 4 total
    mocker.patch(
        "workflows.deep_research_core.nodes.synthesize.agent",
        side_effect=[
            {"status": "success", "text": "done"},  # iter 1 research
            {"status": "success", "text": "20"},   # iter 1 critique
            {"status": "success", "text": "done"},  # iter 2 research
            {"status": "success", "text": "20"},   # iter 2 critique
        ],
    )
    mocker.patch(
        "workflows.deep_research_core.graph.memory.recall",
        return_value=[],
    )
    mocker.patch(
        "workflows.deep_research_core.graph.memory.store_semantic",
        return_value=None,
    )
    mocker.patch(
        "workflows.deep_research_core.graph.memory.store_episodic",
        return_value=None,
    )
    mocker.patch(
        "workflows.deep_research_core.graph.notify",
        return_value=None,
    )
    mocker.patch(
        "core.citations.citations.get_sources",
        return_value=[],
    )

    graph = build_deep_research_graph()
    initial_state = {**BASE_STATE, "max_iterations": 2}
    result = graph.invoke(initial_state)
    # Hard cap reached with low completeness -> incomplete
    assert result["status"] == "incomplete"
    assert result["iteration"] == 2

# -- Regression tests for previous bug fixes -----------------------------------

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

def test_node_store_calls_both_memory_types(mocker):
    """Verify _node_store calls store_semantic and store_episodic."""
    mock_store_semantic = mocker.patch("workflows.deep_research_core.graph.memory.store_semantic")
    mock_store_episodic = mocker.patch("workflows.deep_research_core.graph.memory.store_episodic")
    from workflows.deep_research_core.graph import _node_store
    state = {
        "result": "Test research result",
        "goal": "What is LangGraph?",
        "status": "success",
        "trace_id": "test-123",
    }
    result = _node_store(state)
    mock_store_semantic.assert_called_once_with(
        text="Deep Research: Test research result",
        importance=6,
        tags="deep_research",
        trace_id="test-123",
    )
    mock_store_episodic.assert_called_once_with(
        text="Completed deep research workflow: 'What is LangGraph?'",
        importance=5,
        goal="What is LangGraph?",
        outcome="success",
        tools_used="tavily,web,browser,llm",
        trace_id="test-123",
    )
    assert result == state

def test_facade_initializes_all_state_fields(mocker):
    """Verify run_deep_research_agent initializes state without AttributeError.

    Regression test for the cfg.deep_research_convergence_threshold
    AttributeError that fired when the facade was called directly.
    """
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

def test_route_returns_decompose_not_search(mocker):
    """Verify route_after_synthesize returns 'decompose' (not 'search') for continuation.

    Regression test: earlier versions routed to 'search', which caused the loop
    to skip decompose and burn iterations with empty pending_queries.
    """
    from workflows.deep_research_core.routes import route_after_synthesize
    state = {
        "iteration": 1,
        "max_iterations": 10,
        "completeness": 50.0,
        "completeness_threshold": 85.0,
        "knowledge_base": "Some findings",
        "_prev_knowledge": "",
        "consecutive_empty_iterations": 0,
    }
    result = route_after_synthesize(state)
    assert result == "decompose"

def test_facade_rejects_empty_goal(mocker):
    """Verify run_deep_research_agent rejects empty goals without crashing."""
    from workflows.deep_research import run_deep_research_agent
    result = run_deep_research_agent("")
    assert result["status"] == "failed"
    assert "Goal is required" in result["error"]

def test_facade_rejects_whitespace_goal(mocker):
    """Verify run_deep_research_agent rejects whitespace-only goals."""
    from workflows.deep_research import run_deep_research_agent
    result = run_deep_research_agent(" ")
    assert result["status"] == "failed"
    assert "Goal is required" in result["error"]

def test_facade_timeout_enforcement(mocker):
    """Verify run_deep_research_agent returns timeout when graph exceeds limit."""
    mock_run = mocker.patch("workflows.deep_research.run_workflow")
    mock_run.side_effect = lambda **kwargs: (
        __import__("time").sleep(2),
        {"status": "success"}
    )[1]
    from workflows.deep_research import run_deep_research_agent
    result = run_deep_research_agent("What is LangGraph?", timeout=1)
    assert result["status"] == "timeout"
    assert "exceeded 1s timeout" in result["error"]
