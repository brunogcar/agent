"""tests/workflows/deep_research/test_synthesize.py
Tests for node_synthesize — synthesis, evaluation, convergence, and the
P0 #2 task/context parameter mapping fix.
"""
from __future__ import annotations

from workflows.deep_research_impl.nodes.synthesize import (
    node_synthesize,
    _format_evidence,
    _merge_knowledge,
    _cap_knowledge,
    _parse_score,
)


# ─── Helper functions ───────────────────────────────────────────────────────

class TestFormatEvidence:
    def test_empty(self):
        assert _format_evidence([]) == "_(no new evidence this iteration)_"

    def test_items(self):
        ev = [{"title": "T1", "url": "http://x", "summary": "S1"}]
        out = _format_evidence(ev)
        assert "T1" in out and "S1" in out


class TestMergeKnowledge:
    def test_empty_prev(self):
        assert _merge_knowledge("", "new") == "new"

    def test_empty_new(self):
        assert _merge_knowledge("prev", "") == "prev"

    def test_replaces_not_concatenates(self):
        assert _merge_knowledge("old knowledge", "new synthesis") == "new synthesis"
        assert "old knowledge" not in _merge_knowledge("old knowledge", "new synthesis")


class TestCapKnowledge:
    def test_under_limit(self):
        assert _cap_knowledge("short", max_chars=100) == "short"

    def test_over_limit(self):
        kb = "a" * 10000
        result = _cap_knowledge(kb, max_chars=1000)
        assert "[earlier context truncated]" in result
        assert len(result) <= 1100


class TestParseScore:
    def test_last_number(self):
        assert _parse_score("Based on 3 sources, score is 72") == 72.0

    def test_single(self):
        assert _parse_score("75") == 75.0

    def test_no_match(self):
        assert _parse_score("no score here") == 0.0

    def test_clamp_high(self):
        assert _parse_score("150") == 100.0

    def test_clamp_low(self):
        assert _parse_score("-5") == 0.0

    def test_100(self):
        assert _parse_score("100") == 100.0


# ─── node_synthesize ────────────────────────────────────────────────────────

class TestNodeSynthesize:
    def test_mock_synthesis_and_score(self, mocker):
        state = {"extracted_evidence": [], "knowledge_base": "", "goal": "g", "trace_id": "t1", "iteration": 1}
        mocker.patch(
            "workflows.deep_research_impl.nodes.synthesize.agent",
            side_effect=[
                {"status": "success", "text": "synthesis"},
                {"status": "success", "text": "80"},
            ],
        )
        result = node_synthesize(state)
        assert result["completeness"] == 80.0
        assert result["knowledge_base"] == "synthesis"

    def test_agent_failure_preserves_old_knowledge(self, mocker):
        state = {"extracted_evidence": [], "knowledge_base": "existing", "goal": "g", "trace_id": "t1", "iteration": 1}
        mocker.patch(
            "workflows.deep_research_impl.nodes.synthesize.agent",
            return_value={"status": "error", "error": "fail"},
        )
        result = node_synthesize(state)
        assert result["knowledge_base"] == "existing"
        assert result["completeness"] == 0.0
        assert result["converged"] is False


# ─── v1.0.1 regression: action='dispatch' ─────────────────────────────────

class TestActionDispatch:
    """Both agent() calls must pass action='dispatch' (was missing, caused
    synthesis to fall back to prev_knowledge and completeness to stay 0)."""

    def test_synthesize_call_passes_action_dispatch(self, mocker):
        state = {"extracted_evidence": [{"title": "T1", "url": "http://x", "summary": "S1", "source": "tavily"}],
                 "knowledge_base": "", "goal": "g", "trace_id": "t1", "iteration": 0}
        mock_agent = mocker.patch(
            "workflows.deep_research_impl.nodes.synthesize.agent",
            return_value={"status": "success", "text": "new synthesis"},
        )
        node_synthesize(state)
        assert mock_agent.call_count == 2
        first_kwargs = mock_agent.call_args_list[0].kwargs
        assert first_kwargs.get("action") == "dispatch"
        assert first_kwargs.get("role") == "research"

    def test_evaluate_call_passes_action_dispatch(self, mocker):
        state = {"extracted_evidence": [{"title": "T1", "url": "http://x", "summary": "S1", "source": "tavily"}],
                 "knowledge_base": "", "goal": "g", "trace_id": "t1", "iteration": 0}
        mock_agent = mocker.patch(
            "workflows.deep_research_impl.nodes.synthesize.agent",
            return_value={"status": "success", "text": "Score: 90"},
        )
        node_synthesize(state)
        assert mock_agent.call_count == 2
        second_kwargs = mock_agent.call_args_list[1].kwargs
        assert second_kwargs.get("action") == "dispatch"
        assert second_kwargs.get("role") == "executor"

    def test_completeness_advances_with_action_dispatch(self, mocker):
        state = {"extracted_evidence": [{"title": "T1", "url": "http://x", "summary": "S1", "source": "tavily"}],
                 "knowledge_base": "", "goal": "g", "trace_id": "t1", "iteration": 0}
        mocker.patch(
            "workflows.deep_research_impl.nodes.synthesize.agent",
            return_value={"status": "success", "text": "Score: 92"},
        )
        result = node_synthesize(state)
        assert result["completeness"] == 92.0
        assert result["knowledge_base"] == "Score: 92"


# ─── v1.1 regression: P0 #2 — task/context must not be swapped ─────────────

class TestTaskContextMapping:
    """[P0 #2] task= must hold the user instruction; context= must hold the
    system prompt. Previously these were swapped (task=system prompt,
    content=user instruction) — backwards."""

    def test_synthesize_uses_task_for_user_instruction(self, mocker):
        state = {"extracted_evidence": [{"title": "T1", "url": "http://x", "summary": "S1", "source": "tavily"}],
                 "knowledge_base": "", "goal": "What is LangGraph?", "trace_id": "t1", "iteration": 0}
        mock_agent = mocker.patch(
            "workflows.deep_research_impl.nodes.synthesize.agent",
            return_value={"status": "success", "text": "synthesis"},
        )
        node_synthesize(state)
        synthesize_kwargs = mock_agent.call_args_list[0].kwargs
        assert synthesize_kwargs.get("action") == "dispatch"
        assert "What is LangGraph?" in synthesize_kwargs.get("task", "")
        assert "S1" in synthesize_kwargs.get("task", "")

    def test_synthesize_uses_context_for_system_prompt(self, mocker):
        from workflows.deep_research_impl.constants import SYNTHESIZE_SYSTEM_PROMPT
        state = {"extracted_evidence": [], "knowledge_base": "", "goal": "g", "trace_id": "t1", "iteration": 0}
        mock_agent = mocker.patch(
            "workflows.deep_research_impl.nodes.synthesize.agent",
            return_value={"status": "success", "text": "synthesis"},
        )
        node_synthesize(state)
        synthesize_kwargs = mock_agent.call_args_list[0].kwargs
        assert synthesize_kwargs.get("context") == SYNTHESIZE_SYSTEM_PROMPT
        assert "content" not in synthesize_kwargs or synthesize_kwargs.get("content") == ""

    def test_evaluate_uses_task_for_user_instruction(self, mocker):
        state = {"extracted_evidence": [], "knowledge_base": "", "goal": "What is LangGraph?",
                 "trace_id": "t1", "iteration": 0}
        mock_agent = mocker.patch(
            "workflows.deep_research_impl.nodes.synthesize.agent",
            return_value={"status": "success", "text": "90"},
        )
        node_synthesize(state)
        evaluate_kwargs = mock_agent.call_args_list[1].kwargs
        assert evaluate_kwargs.get("action") == "dispatch"
        assert "What is LangGraph?" in evaluate_kwargs.get("task", "")
