"""tests/workflows/deep_research/test_graph.py
Integration tests for the DeepResearch LangGraph.
"""
import pytest
from langgraph.graph import END
from workflows.deep_research_impl.graph import build_deep_research_graph
from workflows.deep_research_impl.state import DeepResearchState

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
    # 2 iterations * 2 agent calls (research + critique) = 4 total
    mocker.patch(
        "workflows.deep_research_impl.nodes.synthesize.agent",
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
        "workflows.deep_research_impl.nodes.decompose._parse_sub_queries",
        return_value=["What is LangGraph?"],
    )
    mocker.patch(
        "workflows.deep_research_impl.nodes.decompose.llm.complete",
        return_value=mocker.MagicMock(ok=True, text='["What is LangGraph?"]'),
    )
    # Consistent mocks: search returns results, extract returns evidence
    mocker.patch(
        "workflows.deep_research_impl.nodes.search._execute_search_with_fallback",
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
        "workflows.deep_research_impl.nodes.search._extract_evidence",
        return_value=(
            [{"query": "q1", "url": "https://example.com", "title": "Example", "summary": "LangGraph is a framework.", "source": "web"}],
            {},
        ),
    )
    mocker.patch(
        "workflows.deep_research_impl.nodes.synthesize.agent",
        side_effect=[
            {"status": "success", "text": "LangGraph is a framework for building LLM apps."},  # research
            {"status": "success", "text": "95"},  # critique (high score)
        ],
    )
    mocker.patch(
        "workflows.deep_research_impl.graph.memory.recall",
        return_value=[],
    )
    mocker.patch(
        "workflows.deep_research_impl.graph.memory.store_semantic",
        return_value=None,
    )
    mocker.patch(
        "workflows.deep_research_impl.graph.memory.store_episodic",
        return_value=None,
    )
    mocker.patch(
        "workflows.deep_research_impl.graph.notify",
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
    # 2 iterations * 2 agent calls = 4 total
    mocker.patch(
        "workflows.deep_research_impl.nodes.synthesize.agent",
        side_effect=[
            {"status": "success", "text": "done"},  # iter 1 research
            {"status": "success", "text": "20"},   # iter 1 critique
            {"status": "success", "text": "done"},  # iter 2 research
            {"status": "success", "text": "20"},   # iter 2 critique
        ],
    )
    mocker.patch(
        "workflows.deep_research_impl.graph.memory.recall",
        return_value=[],
    )
    mocker.patch(
        "workflows.deep_research_impl.graph.memory.store_semantic",
        return_value=None,
    )
    mocker.patch(
        "workflows.deep_research_impl.graph.memory.store_episodic",
        return_value=None,
    )
    mocker.patch(
        "workflows.deep_research_impl.graph.notify",
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

    [v1.1] Now also returns artifacts (source URLs) as a partial dict,
    not `return state`.
    """
    mock_notify = mocker.patch("workflows.deep_research_impl.graph.notify")
    mocker.patch("core.citations.citations.get_sources", return_value=[])
    state = {
        "result": "Test research result",
        "trace_id": "test-123",
    }
    from workflows.deep_research_impl.graph import _node_notify
    result = _node_notify(state)
    mock_notify.assert_called_once_with(
        action="send",
        title="DeepResearch",
        message="Test research result",
    )
    # [v1.1] Partial dict — returns artifacts, not the whole state.
    assert "artifacts" in result
    assert result["artifacts"] == []

def test_node_distill_is_noop_pass_through():
    """Verify _node_distill is a no-op that returns an empty partial dict.

    [v1.1] Returns {} (partial dict), not `return state`. No behavior change
    — LangGraph merges {} into state with no effect.
    """
    from workflows.deep_research_impl.graph import _node_distill
    state = {
        "trace_id": "test-123",
        "result": "Test result",
        "knowledge_base": "Some knowledge",
    }
    result = _node_distill(state)
    assert result == {}

def test_report_status_incomplete_when_below_threshold(mocker):
    """Verify report node returns status='incomplete' when completeness < threshold."""
    from workflows.deep_research_impl.graph import _node_report
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
    from workflows.deep_research_impl.graph import _node_report
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
    mock_recall = mocker.patch("workflows.deep_research_impl.graph.memory.recall")
    mock_recall.return_value = [
        {"type": "semantic", "score": 0.85, "text": "Previous research on async"},
    ]
    from workflows.deep_research_impl.graph import _node_recall
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
    mock_recall = mocker.patch("workflows.deep_research_impl.graph.memory.recall")
    mock_recall.side_effect = Exception("DB down")
    from workflows.deep_research_impl.graph import _node_recall
    state = {
        "goal": "Python async frameworks",
        "trace_id": "test-123",
    }
    result = _node_recall(state)
    assert result.get("memory_context", "") == ""

def test_node_store_calls_both_memory_types(mocker):
    """Verify _node_store calls store_semantic and store_episodic.

    [v1.1/P1 #10] store_semantic now receives the FULL result (was result[:800]).
    Semantic memory is for content retrieval; truncation defeated the purpose.
    Same fix as research workflow #7.
    [v1.1/P1 #7] Returns {} (partial dict), not `return state`.
    """
    mock_store_semantic = mocker.patch("workflows.deep_research_impl.graph.memory.store_semantic")
    mock_store_episodic = mocker.patch("workflows.deep_research_impl.graph.memory.store_episodic")
    from workflows.deep_research_impl.graph import _node_store
    state = {
        "result": "Test research result",
        "goal": "What is LangGraph?",
        "status": "success",
        "trace_id": "test-123",
    }
    result = _node_store(state)
    # [P1 #10] Full result, no [:800] truncation.
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
    # [P1 #7] Partial dict (side effects only).
    assert result == {}

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
    from workflows.deep_research_impl.routes import route_after_synthesize
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


# ─── v1.1: WORKFLOW_METADATA + citations + partial dicts ────────────────────

class TestWorkflowMetadata:
    """v1.1: WORKFLOW_METADATA must exist and have correct structure."""

    def test_metadata_exists(self):
        from workflows.deep_research_impl.graph import WORKFLOW_METADATA
        assert isinstance(WORKFLOW_METADATA, dict)
        assert WORKFLOW_METADATA["name"] == "deep_research"
        assert WORKFLOW_METADATA["version"] == "1.1"

    def test_metadata_has_all_8_nodes(self):
        from workflows.deep_research_impl.graph import WORKFLOW_METADATA
        nodes = WORKFLOW_METADATA["nodes"]
        assert len(nodes) == 8
        names = [n["name"] for n in nodes]
        for expected in ["recall", "decompose", "search", "synthesize",
                         "report", "notify", "store", "distill"]:
            assert expected in names, f"Missing node: {expected}"

    def test_metadata_has_edges_with_loop(self):
        from workflows.deep_research_impl.graph import WORKFLOW_METADATA
        edges = WORKFLOW_METADATA["edges"]
        pairs = [(e["from"], e["to"]) for e in edges]
        assert ("recall", "decompose") in pairs
        assert ("synthesize", "decompose") in pairs  # the loop back
        assert ("synthesize", "report") in pairs      # the exit
        assert ("store", "distill") in pairs

    def test_metadata_nodes_have_descriptions(self):
        from workflows.deep_research_impl.graph import WORKFLOW_METADATA
        for node in WORKFLOW_METADATA["nodes"]:
            assert "description" in node, f"Node {node['name']} missing description"
            assert len(node["description"]) > 0


class TestCitationsWired:
    """v1.1: citations collected by node_search must surface in report + notify."""

    def test_report_appends_sources_section(self, mocker):
        """_node_report must append a ## Sources section from the citation tracker."""
        from workflows.deep_research_impl.graph import _node_report
        mocker.patch(
            "core.citations.citations.get_sources",
            return_value=[
                {"number": 1, "url": "https://a.example", "title": "Source A"},
                {"number": 2, "url": "https://b.example", "title": "Source B"},
            ],
        )
        state = {
            "knowledge_base": "Findings here",
            "synthesis": "Synthesis here",
            "completeness": 90.0,
            "completeness_threshold": 85.0,
            "trace_id": "t1",
        }
        result = _node_report(state)
        assert "## Sources" in result["report"]
        assert "https://a.example" in result["report"]
        assert "https://b.example" in result["report"]
        assert "Source A" in result["report"]

    def test_report_no_sources_no_section(self, mocker):
        """No sources -> no Sources section (but report still built)."""
        from workflows.deep_research_impl.graph import _node_report
        mocker.patch("core.citations.citations.get_sources", return_value=[])
        state = {
            "knowledge_base": "Findings",
            "synthesis": "",
            "completeness": 40.0,
            "completeness_threshold": 85.0,
            "trace_id": "t1",
        }
        result = _node_report(state)
        assert "## Sources" not in result["report"]
        assert "Findings" in result["report"]

    def test_notify_returns_source_urls_as_artifacts(self, mocker):
        """_node_notify must return source URLs as artifacts (list[str])."""
        from workflows.deep_research_impl.graph import _node_notify
        mocker.patch("workflows.deep_research_impl.graph.notify")
        mocker.patch(
            "core.citations.citations.get_sources",
            return_value=[
                {"url": "https://a.example"},
                {"url": "https://b.example"},
            ],
        )
        state = {"result": "r", "trace_id": "t1", "status": "success"}
        result = _node_notify(state)
        assert result["artifacts"] == ["https://a.example", "https://b.example"]


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


class TestRecallLogsFailure:
    """v1.1/P1 #8: _node_recall must log memory failures via tracer.error."""

    def test_recall_logs_error_on_memory_failure(self, mocker):
        from workflows.deep_research_impl.graph import _node_recall
        mocker.patch(
            "workflows.deep_research_impl.graph.memory.recall",
            side_effect=RuntimeError("chromadb down"),
        )
        mock_error = mocker.patch("core.tracer.tracer.error")
        state = {"goal": "g", "trace_id": "t1"}
        result = _node_recall(state)
        assert result == {"memory_context": ""}, "Failure must still return empty context"
        assert mock_error.called, "Memory failure must be logged via tracer.error"


class TestStoreFullText:
    """v1.1/P1 #10: _node_store must store the FULL result, not result[:800]."""

    def test_store_does_not_truncate_to_800(self, mocker):
        from workflows.deep_research_impl.graph import _node_store
        mock_semantic = mocker.patch("workflows.deep_research_impl.graph.memory.store_semantic")
        mocker.patch("workflows.deep_research_impl.graph.memory.store_episodic")
        long_result = "X" * 2000  # > 800 chars
        state = {
            "result": long_result, "goal": "g", "status": "success", "trace_id": "t1",
        }
        _node_store(state)
        stored_text = mock_semantic.call_args.kwargs["text"]
        assert len(stored_text) > 800, "store_semantic must not truncate to 800 chars"
        assert long_result in stored_text
