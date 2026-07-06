"""workflows/deep_research_impl/nodes/synthesize.py
Synthesis and evaluation node.

[P0 #2 FIX] Both agent() calls now use the correct parameter mapping:
  - task   = the user instruction (goal + evidence / goal + synthesis)
  - context= the system-style framing prompt (SYNTHESIZE/EVALUATE_SYSTEM_PROMPT)
Previously task= held the system prompt and content= held the user instruction
— backwards. The system prompt text landed in llm.complete(user=...), and the
actual synthesis instruction (goal+evidence) went to content= (tertiary input).

[P1 #6] Removed _agent_ok / _agent_text wrappers. agent() returns a dict with
status/text keys; the wrappers were dead code that handled a legacy
LLMResponse shape that no longer exists.
"""
from __future__ import annotations
import re
from typing import List, Dict, Any
from workflows.deep_research_impl.state import DeepResearchState
from workflows.deep_research_impl.constants import (
    CONVERGENCE_SIMILARITY_THRESHOLD,
    _is_converged,
    SYNTHESIZE_SYSTEM_PROMPT,
    SYNTHESIZE_USER_TEMPLATE,
    EVALUATE_SYSTEM_PROMPT,
    EVALUATE_USER_TEMPLATE,
)
from tools.agent import agent

_MAX_PREV_KNOWLEDGE_CHARS = 6000


def node_synthesize(state: DeepResearchState) -> DeepResearchState:
    """Synthesize evidence into knowledge, evaluate completeness, check convergence."""
    evidence = state.get("extracted_evidence", [])
    goal = state.get("goal", "")
    iteration = state.get("iteration", 0)
    prev_knowledge = state.get("knowledge_base", "")
    max_iter = state.get("max_iterations", 10)
    # NOTE: completeness_threshold is intentionally NOT read here. The
    # threshold comparison lives in routes.py and graph.py (default 85.0
    # on a 0-100 scale, matching _parse_score()'s output). Reading it here
    # would be dead code — the local was previously 0.85 (0-1 scale),
    # which was misleading and never used. Do not re-introduce.
    convergence_threshold = state.get("convergence_threshold", CONVERGENCE_SIMILARITY_THRESHOLD)

    evidence_text = _format_evidence(evidence)
    user_prompt = SYNTHESIZE_USER_TEMPLATE.format(
        goal=goal,
        evidence=evidence_text,
        prev_knowledge=prev_knowledge[:1000],
    )

    # [P0 #2] task= is the user instruction; context= carries the system framing.
    # Previously these were swapped (task=system prompt, content=user instruction).
    try:
        result = agent(
            action   = "dispatch",
            role     = "research",
            task     = user_prompt,
            context  = SYNTHESIZE_SYSTEM_PROMPT,
            trace_id = state.get("trace_id", ""),
        )
        if result.get("status") == "success":
            synthesis = str(result.get("text", "")).strip()
        else:
            synthesis = prev_knowledge
    except Exception:
        synthesis = prev_knowledge

    new_knowledge = _merge_knowledge(prev_knowledge, synthesis)
    new_knowledge = _cap_knowledge(new_knowledge)

    # Evaluate completeness
    evaluate_prompt = EVALUATE_USER_TEMPLATE.format(
        goal=goal,
        synthesis=synthesis,
    )
    # [P0 #2] Same fix for the evaluate call.
    try:
        evaluate_result = agent(
            action   = "dispatch",
            role     = "executor",
            task     = evaluate_prompt,
            context  = EVALUATE_SYSTEM_PROMPT,
            trace_id = state.get("trace_id", ""),
        )
        if evaluate_result.get("status") == "success":
            score = _parse_score(str(evaluate_result.get("text", "")))
        else:
            score = 0.0
    except Exception:
        score = 0.0

    # Converged is False when critique fails (score == 0), otherwise check similarity
    converged = _is_converged(prev_knowledge, new_knowledge, convergence_threshold) if score > 0 else False

    return {
        "knowledge_base": new_knowledge,
        "_prev_knowledge": prev_knowledge,
        "completeness": score,
        "extracted_evidence": [],
        "converged": converged,
        "synthesis": synthesis,
    }

def _format_evidence(evidence: List[Dict[str, Any]]) -> str:
    """Format evidence list into a single string for the synthesis prompt."""
    if not evidence:
        return "_(no new evidence this iteration)_"
    lines = []
    for e in evidence:
        lines.append(f"- [{e.get('source', 'unknown')}] {e.get('title', 'Untitled')}")
        lines.append(f"  URL: {e.get('url', '')}")
        lines.append(f"  Summary: {e.get('summary', '')}")
        lines.append("")
    return "\n".join(lines)

def _merge_knowledge(prev: str, new: str) -> str:
    """Merge previous knowledge with new synthesis.

    Uses REPLACE semantics: the new synthesis always replaces the old knowledge
    if it exists. This prevents infinite context growth.
    """
    if not new:
        return prev
    return new

def _cap_knowledge(knowledge: str, max_chars: int = _MAX_PREV_KNOWLEDGE_CHARS) -> str:
    """Truncate knowledge to fit within the executor's context budget.

    Truncates from the head, keeping the tail, and avoids mid-sentence breaks
    by finding the first sentence or paragraph boundary in the retained portion.
    """
    if len(knowledge) <= max_chars:
        return knowledge
    truncated = knowledge[-max_chars:]
    # Find first sentence boundary to avoid mid-sentence truncation
    first_period = truncated.find(". ")
    if first_period != -1 and first_period < 200:
        truncated = truncated[first_period + 2:]
    first_newline = truncated.find("\n\n")
    if first_newline != -1 and first_newline < 200:
        truncated = truncated[first_newline + 2:]
    return "... [earlier context truncated] ...\n\n" + truncated

def _parse_score(text: str) -> float:
    """Extract the last numeric score from critique text, clamp to 0-100."""
    # Remove negative numbers (e.g. "-5" -> ignore the minus, keep 5)
    cleaned = re.sub(r"-\d+", "", text)
    matches = re.findall(r"\d+", cleaned)
    if matches:
        score = int(matches[-1])  # Last number
        return float(max(0, min(100, score)))
    return 0.0
