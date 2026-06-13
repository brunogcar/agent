"""workflows/deep_research_core/nodes/synthesize.py
Synthesis and evaluation node.
"""
from __future__ import annotations
import re
from typing import List, Dict, Any
from workflows.deep_research_core.state import DeepResearchState
from workflows.deep_research_core.budget import log_event
from workflows.deep_research_core.constants import (
    CONVERGENCE_SIMILARITY_THRESHOLD,
    _is_converged,
    SYNTHESIZE_SYSTEM_PROMPT,
    SYNTHESIZE_USER_TEMPLATE,
    EVALUATE_SYSTEM_PROMPT,
    EVALUATE_USER_TEMPLATE,
)
from tools.agent_tool import agent

# Max chars of previous knowledge to send to synthesis LLM
_MAX_PREV_KNOWLEDGE_CHARS = 6000


def node_synthesize(state: DeepResearchState) -> DeepResearchState:
    """Synthesize evidence and evaluate completeness."""
    evidence = state.get("extracted_evidence", [])
    knowledge_base = state.get("knowledge_base", "")
    goal = state.get("goal", "")
    tid = state.get("trace_id", "")
    iteration = state.get("iteration", 0)

    formatted = _format_evidence(evidence)
    prev_knowledge = knowledge_base

    # Cap previous knowledge to prevent context overflow in the executor
    kb_for_prompt = _cap_knowledge(knowledge_base)

    prompt = SYNTHESIZE_USER_TEMPLATE.format(
        goal=goal,
        evidence=formatted,
        prev_knowledge=kb_for_prompt,
    )
    result = agent(
        role="research",
        task=SYNTHESIZE_SYSTEM_PROMPT,
        content=prompt,
        trace_id=tid,
    )
    if result.get("status") != "success":
        return {
            "knowledge_base": knowledge_base,
            "_prev_knowledge": prev_knowledge,
            "completeness": 0.0,
            "converged": False,
        }

    synthesis = result.get("text", "")
    new_knowledge = _merge_knowledge(knowledge_base, synthesis)

    # Evaluate
    eval_prompt = EVALUATE_USER_TEMPLATE.format(goal=goal, synthesis=synthesis)
    eval_result = agent(
        role="critique",
        task=EVALUATE_SYSTEM_PROMPT,
        content=eval_prompt,
        trace_id=tid,
    )
    score = 0.0
    if eval_result.get("status") == "success":
        score = _parse_score(eval_result.get("text", ""))

    log_event(state, "synthesize", f"iteration={iteration}, completeness={score}")

    converged = _is_converged(prev_knowledge, new_knowledge)
    return {
        "knowledge_base": new_knowledge,
        "_prev_knowledge": prev_knowledge,
        "completeness": score,
        "extracted_evidence": [],
        "converged": converged,
    }


def _format_evidence(evidence: List[Dict[str, Any]]) -> str:
    if not evidence:
        return "_(no new evidence this iteration)_"
    lines = []
    for i, ev in enumerate(evidence, 1):
        lines.append(
            f"{i}. **{ev.get('title', 'Untitled')}** ({ev.get('url', '')})\n"
            f"   {ev.get('summary', '')}"
        )
    return "\n\n".join(lines)


def _merge_knowledge(prev: str, new: str) -> str:
    """Replace knowledge_base with new synthesis.

    The LLM already integrates old + new into a coherent whole.
    prev is already snapshotted in _prev_knowledge by the caller for
    convergence detection — do not re-embed it here.
    """
    return new if new else prev


def _cap_knowledge(knowledge: str, max_chars: int = _MAX_PREV_KNOWLEDGE_CHARS) -> str:
    """Truncate knowledge to fit within the executor's context budget."""
    if len(knowledge) <= max_chars:
        return knowledge
    return "... [earlier context truncated] ...\n\n" + knowledge[-max_chars:]


def _parse_score(text: str) -> float:
    """Extract the last integer 0-100 from critique text.

    LLMs typically put the final score at the end. Taking the last
    number avoids matching example numbers from the prompt itself
    (e.g. "0 = no coverage, 50 = partial, 100 = fully comprehensive").

    Negative numbers are ignored (e.g. -5 returns 0.0).
    Values > 100 are clamped to 100.
    """
    if not text:
        return 0.0
    # Strip negative numbers so we don't extract digits from them
    cleaned = re.sub(r"-\d+", "", text)
    matches = re.findall(r"\d+", cleaned)
    if matches:
        score = int(matches[-1])
        return float(max(0, min(100, score)))
    return 0.0
