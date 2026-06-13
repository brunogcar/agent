"""Synthesize node: merge evidence into knowledge, evaluate completeness.

Replaces ``knowledge_base`` with the new synthesis (never appends),
clears ``extracted_evidence``, and stores a completeness score from
the critique LLM.  The previous knowledge snapshot is preserved in
``_prev_knowledge`` for convergence detection by the routing layer.
"""
from __future__ import annotations

import difflib
import logging
from typing import Any

from tools.agent_tool import agent
from workflows.deep_research_core.constants import (
    CONVERGENCE_SIMILARITY_THRESHOLD,
    EVALUATE_SYSTEM_PROMPT,
    EVALUATE_USER_TEMPLATE,
    SYNTHESIZE_SYSTEM_PROMPT,
    SYNTHESIZE_USER_TEMPLATE,
)
from workflows.deep_research_core.state import DeepResearchState
from workflows.base import node_step

logger = logging.getLogger(__name__)


def node_synthesize(state: DeepResearchState) -> DeepResearchState:
    """Synthesise new evidence and evaluate loop completeness.

    Steps:
    1. Format the current evidence block.
    2. Call ``agent(role="research")`` to merge it with existing knowledge.
    3. Call ``agent(role="critique")`` for a 0-100 completeness score.
    4. Snapshot old knowledge into ``_prev_knowledge`` for convergence checks.
    5. Clear ``extracted_evidence`` so the next iteration starts clean.

    Args:
        state: Workflow state with ``extracted_evidence``, ``knowledge_base``,
               ``goal``, and ``trace_id``.

    Returns:
        Partial state update with new ``knowledge_base``, ``synthesis``,
        ``completeness``, ``_prev_knowledge``, and cleared evidence.
    """
    goal = state.get("goal", "")
    tid = state.get("trace_id", "")
    evidence = state.get("extracted_evidence", [])
    knowledge_base = state.get("knowledge_base", "")
    failed = state.get("failed_sources", [])

    node_step(state, "synthesize", f"synthesising {len(evidence)} evidence items")

    # -- Format evidence block -------------------------------------
    evidence_text = _format_evidence(evidence)

    # -- Synthesis -------------------------------------------------
    synth_result = agent(
        role="research",
        task=SYNTHESIZE_SYSTEM_PROMPT,
        content=SYNTHESIZE_USER_TEMPLATE.format(
            goal=goal,
            prev_knowledge=knowledge_base or "(none yet)",
            evidence_text=evidence_text,
        ),
        trace_id=tid,
    )

    synthesis = synth_result.get("text", "") if synth_result.get("status") == "success" else ""

    # -- Evaluation / critique ------------------------------------
    failed_text = _format_failed_sources(failed)
    eval_result = agent(
        role="critique",
        task=EVALUATE_SYSTEM_PROMPT,
        content=EVALUATE_USER_TEMPLATE.format(
            goal=goal,
            synthesis=synthesis,
            failed_sources=failed_text,
        ),
        trace_id=tid,
    )

    completeness = _parse_score(eval_result.get("text", "0"))

    # -- Convergence check (store old knowledge before replacing) --
    prev_knowledge = knowledge_base
    new_knowledge = _merge_knowledge(knowledge_base, synthesis)

    node_step(
        state,
        "synthesize",
        f"completeness={completeness:.0f} "
        f"converged={_is_converged(prev_knowledge, new_knowledge)}",
    )

    return {
        "_prev_knowledge": prev_knowledge,
        "knowledge_base": new_knowledge,
        "synthesis": synthesis,
        "completeness": completeness,
        "extracted_evidence": [],  # cleared for next iteration
    }


def _format_evidence(evidence: list[dict[str, Any]]) -> str:
    """Render evidence list as a numbered markdown list."""
    if not evidence:
        return "_(no new evidence this iteration)_"

    lines = []
    for idx, e in enumerate(evidence, start=1):
        title = e.get("title", "Untitled")
        url = e.get("url", "")
        summary = e.get("summary", "")
        tool = e.get("tool_used", "unknown")
        lines.append(
            f"{idx}. **{title}** ({tool})\n"
            f"   URL: {url}\n"
            f"   Summary: {summary}\n"
        )
    return "\n".join(lines)


def _format_failed_sources(failed: list[dict[str, Any]]) -> str:
    """Render failed sources for the critique prompt."""
    if not failed:
        return "_(none)_"
    lines = []
    for f in failed:
        lines.append(f"- {f.get('url', '?')} ({f.get('reason', '?')}, iter {f.get('iteration', '?')})")
    return "\n".join(lines)


def _parse_score(text: str) -> float:
    """Extract the first integer 0-100 from raw LLM critique text.

    Strips markdown, punctuation, and surrounding words.  Falls back
    to ``0.0`` if nothing parseable is found.
    """
    if not text:
        return 0.0

    import re
    # Look for a standalone integer 0-100
    match = re.search(r"\b(\d{1,2}|100)\b", text)
    if match:
        return float(match.group(1))

    return 0.0


def _merge_knowledge(prev: str, new: str) -> str:
    """Merge previous knowledge with the new synthesis.

    If ``prev`` is empty, return ``new`` verbatim.  Otherwise prepend
    a heading so the LLM can distinguish historical context from the
    latest synthesis.
    """
    if not prev:
        return new
    if not new:
        return prev
    return f"{prev}\n\n---\n\n**Iteration Update**\n\n{new}"


def _is_converged(old: str, new: str) -> bool:
    """Return ``True`` if the knowledge base has stabilised.

    Uses ``difflib.SequenceMatcher`` to compute a similarity ratio.
    A ratio above ``CONVERGENCE_SIMILARITY_THRESHOLD`` means the
    synthesis is no longer changing meaningfully between iterations.
    """
    if not old or not new:
        return False
    ratio = difflib.SequenceMatcher(None, old, new).ratio()
    return ratio > CONVERGENCE_SIMILARITY_THRESHOLD
