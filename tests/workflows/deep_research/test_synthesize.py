"""tests/workflows/deep_research/test_synthesize.py"""
import pytest
from workflows.deep_research_impl.nodes.synthesize import (
    node_synthesize,
    _format_evidence,
    _merge_knowledge,
    _cap_knowledge,
    _parse_score,
)


def test_format_evidence_empty():
    assert _format_evidence([]) == "_(no new evidence this iteration)_"


def test_format_evidence_items():
    ev = [{"title": "T1", "url": "http://x", "summary": "S1"}]
    out = _format_evidence(ev)
    assert "T1" in out and "S1" in out


def test_merge_knowledge_empty_prev():
    assert _merge_knowledge("", "new") == "new"


def test_merge_knowledge_empty_new():
    assert _merge_knowledge("prev", "") == "prev"


def test_merge_knowledge_replaces():
    """Knowledge should be replaced, not concatenated."""
    prev = "old knowledge"
    new = "new synthesis"
    result = _merge_knowledge(prev, new)
    assert result == "new synthesis"
    assert "old knowledge" not in result


def test_cap_knowledge_under_limit():
    kb = "short"
    assert _cap_knowledge(kb, max_chars=100) == "short"


def test_cap_knowledge_over_limit():
    kb = "a" * 10000
    result = _cap_knowledge(kb, max_chars=1000)
    assert "[earlier context truncated]" in result
    assert len(result) <= 1100  # truncated marker + 1000 chars


def test_parse_score_last_number():
    """Should extract the LAST number, not the first."""
    assert _parse_score("Based on 3 sources, score is 72") == 72.0


def test_parse_score_single():
    assert _parse_score("75") == 75.0


def test_parse_score_no_match():
    assert _parse_score("no score here") == 0.0


def test_parse_score_clamp_high():
    assert _parse_score("150") == 100.0


def test_parse_score_clamp_low():
    assert _parse_score("-5") == 0.0


def test_parse_score_100():
    assert _parse_score("100") == 100.0


def test_node_synthesize_mock(mocker):
    state = {
        "extracted_evidence": [],
        "knowledge_base": "",
        "goal": "g",
        "trace_id": "t1",
        "iteration": 1,
    }
    mocker.patch(
        "workflows.deep_research_impl.nodes.synthesize.agent",
        side_effect=[
            {"status": "success", "text": "synthesis"},
            {"status": "success", "text": "80"},
        ],
    )
    result = node_synthesize(state)
    assert result["completeness"] == 80.0
    assert result["knowledge_base"] == "synthesis"  # replaced, not appended


def test_node_synthesize_agent_failure(mocker):
    """Research agent failure should preserve old knowledge and score 0."""
    state = {
        "extracted_evidence": [],
        "knowledge_base": "existing",
        "goal": "g",
        "trace_id": "t1",
        "iteration": 1,
    }
    mocker.patch(
        "workflows.deep_research_impl.nodes.synthesize.agent",
        return_value={"status": "error", "error": "fail"},
    )
    result = node_synthesize(state)
    assert result["knowledge_base"] == "existing"
    assert result["completeness"] == 0.0
    assert result["converged"] is False


# ─── v1.5 regression: agent() must be called with action='dispatch' ────────
# Previously both agent() calls in node_synthesize (synthesize + evaluate)
# were missing action='dispatch'. The agent() facade requires it for LLM
# calls — without it, both calls returned 'Unknown action' error, so:
#   - synthesis always fell back to prev_knowledge (always "" on first iter)
#   - evaluate always returned score=0.0 (completeness permanently 0)
# Net effect: deep_research could never advance its knowledge base.


def test_node_synthesize_calls_research_agent_with_action_dispatch(mocker):
    """The synthesis agent() call must pass action='dispatch'."""
    state = {
        "extracted_evidence": [
            {"title": "T1", "url": "http://x", "summary": "S1", "source": "tavily"}
        ],
        "knowledge_base": "",
        "goal": "g",
        "trace_id": "t1",
        "iteration": 0,
    }

    mock_agent = mocker.patch(
        "workflows.deep_research_impl.nodes.synthesize.agent",
        return_value={"status": "success", "text": "new synthesis"},
    )
    node_synthesize(state)

    assert mock_agent.call_count == 2, "Expected 2 agent() calls (synthesize + evaluate)"
    # First call: synthesize with role='research'
    first_call_kwargs = mock_agent.call_args_list[0].kwargs
    assert first_call_kwargs.get("action") == "dispatch", (
        f"synthesize agent() call must pass action='dispatch'; "
        f"got action={first_call_kwargs.get('action')!r}. Without it, synthesis always "
        f"falls back to prev_knowledge (deep_research never advances)."
    )
    assert first_call_kwargs.get("role") == "research"


def test_node_synthesize_calls_evaluate_agent_with_action_dispatch(mocker):
    """The evaluate agent() call must pass action='dispatch'."""
    state = {
        "extracted_evidence": [
            {"title": "T1", "url": "http://x", "summary": "S1", "source": "tavily"}
        ],
        "knowledge_base": "",
        "goal": "g",
        "trace_id": "t1",
        "iteration": 0,
    }

    mock_agent = mocker.patch(
        "workflows.deep_research_impl.nodes.synthesize.agent",
        return_value={"status": "success", "text": "Score: 90"},
    )
    node_synthesize(state)

    assert mock_agent.call_count == 2
    # Second call: evaluate with role='executor'
    second_call_kwargs = mock_agent.call_args_list[1].kwargs
    assert second_call_kwargs.get("action") == "dispatch", (
        f"evaluate agent() call must pass action='dispatch'; "
        f"got action={second_call_kwargs.get('action')!r}. Without it, completeness "
        f"score is permanently 0.0 (deep_research never converges on completeness)."
    )
    assert second_call_kwargs.get("role") == "executor"


def test_node_synthesize_completeness_advances_with_action_dispatch(mocker):
    """End-to-end: with action='dispatch', evaluate's score propagates to state['completeness'].

    Before the v1.5 fix, the evaluate call returned 'Unknown action' error,
    so score was always 0.0 and completeness never advanced.
    """
    state = {
        "extracted_evidence": [
            {"title": "T1", "url": "http://x", "summary": "S1", "source": "tavily"}
        ],
        "knowledge_base": "",
        "goal": "g",
        "trace_id": "t1",
        "iteration": 0,
    }

    mocker.patch(
        "workflows.deep_research_impl.nodes.synthesize.agent",
        return_value={"status": "success", "text": "Score: 92"},
    )
    result = node_synthesize(state)

    assert result["completeness"] == 92.0, (
        "completeness must reflect the evaluate agent's score when action='dispatch' "
        "is correctly passed. Before v1.5 fix, this was always 0.0."
    )
    assert result["knowledge_base"] == "Score: 92", (
        "knowledge_base must be populated from synthesis when action='dispatch' is passed."
    )


# ─── v1.1 regression: P0 #2 — task/context must not be swapped ─────────────
# Previously task= held the SYSTEM prompt and content= held the USER instruction.
# That's backwards: task -> llm.complete(user=task), so the system prompt text
# landed in the user slot, and the actual synthesis instruction (goal+evidence)
# went to content= (tertiary input). The agent(role="research") system prompt
# then overrode the intended framing entirely.

def test_synthesize_uses_task_for_user_instruction(mocker):
    """[P0 #2] task= must hold the user instruction (goal + evidence), not the system prompt."""
    state = {
        "extracted_evidence": [
            {"title": "T1", "url": "http://x", "summary": "S1", "source": "tavily"}
        ],
        "knowledge_base": "",
        "goal": "What is LangGraph?",
        "trace_id": "t1",
        "iteration": 0,
    }
    mock_agent = mocker.patch(
        "workflows.deep_research_impl.nodes.synthesize.agent",
        return_value={"status": "success", "text": "synthesis"},
    )
    node_synthesize(state)

    # First call = synthesize. task= must be the user instruction (contains goal + evidence).
    synthesize_kwargs = mock_agent.call_args_list[0].kwargs
    assert synthesize_kwargs.get("action") == "dispatch"
    assert "What is LangGraph?" in synthesize_kwargs.get("task", ""), (
        "task= must carry the user instruction (goal + evidence). "
        "Previously task= held the system prompt — backwards."
    )
    assert "S1" in synthesize_kwargs.get("task", ""), (
        "task= must carry the formatted evidence. Previously this went to content=."
    )


def test_synthesize_uses_context_for_system_prompt(mocker):
    """[P0 #2] context= must hold the system framing prompt, not the user instruction."""
    from workflows.deep_research_impl.constants import SYNTHESIZE_SYSTEM_PROMPT
    state = {
        "extracted_evidence": [],
        "knowledge_base": "",
        "goal": "g",
        "trace_id": "t1",
        "iteration": 0,
    }
    mock_agent = mocker.patch(
        "workflows.deep_research_impl.nodes.synthesize.agent",
        return_value={"status": "success", "text": "synthesis"},
    )
    node_synthesize(state)

    synthesize_kwargs = mock_agent.call_args_list[0].kwargs
    # context= must be the system prompt string, NOT the user instruction.
    assert synthesize_kwargs.get("context") == SYNTHESIZE_SYSTEM_PROMPT, (
        "context= must carry the system framing prompt. "
        "Previously context= was empty and content= held the user instruction."
    )
    # And content= must NOT carry the user instruction (that's now in task=).
    assert "content" not in synthesize_kwargs or synthesize_kwargs.get("content") == "", (
        "content= must not be used for the user instruction (it's for base64 images)."
    )


def test_evaluate_uses_task_for_user_instruction(mocker):
    """[P0 #2] evaluate call must also use task= for the user instruction."""
    state = {
        "extracted_evidence": [],
        "knowledge_base": "",
        "goal": "What is LangGraph?",
        "trace_id": "t1",
        "iteration": 0,
    }
    mock_agent = mocker.patch(
        "workflows.deep_research_impl.nodes.synthesize.agent",
        return_value={"status": "success", "text": "90"},
    )
    node_synthesize(state)

    # Second call = evaluate. task= must contain the goal + synthesis.
    evaluate_kwargs = mock_agent.call_args_list[1].kwargs
    assert evaluate_kwargs.get("action") == "dispatch"
    assert "What is LangGraph?" in evaluate_kwargs.get("task", ""), (
        "evaluate task= must carry the user instruction (goal + synthesis)."
    )
