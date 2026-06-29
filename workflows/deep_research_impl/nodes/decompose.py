"""workflows/deep_research_impl/nodes/decompose.py
Decompose a research goal into sub-queries.
"""
from __future__ import annotations
import json
import logging
import re

from core.llm import llm
from workflows.deep_research_impl.state import DeepResearchState
from workflows.deep_research_impl.constants import DECOMPOSE_SYSTEM_PROMPT, DECOMPOSE_USER_TEMPLATE

logger = logging.getLogger(__name__)


def _parse_sub_queries(text: str) -> list[str]:
    """Extract sub-queries from LLM output. Tries JSON, then line heuristic, then fallback to [goal]."""
    if not text:
        return []

    # Try JSON array first
    try:
        parsed = json.loads(text.strip())
        if isinstance(parsed, list) and all(isinstance(q, str) for q in parsed):
            return [q.strip() for q in parsed if q.strip()]
        if isinstance(parsed, dict):
            # Handle {"queries": [...]} or {"steps": [{"description": ...}]}
            queries = parsed.get("queries") or parsed.get("sub_queries")
            if isinstance(queries, list):
                return [q.strip() for q in queries if isinstance(q, str) and q.strip()]
            steps = parsed.get("steps")
            if isinstance(steps, list):
                out = []
                for s in steps:
                    if isinstance(s, dict):
                        desc = s.get("description") or s.get("query") or s.get("action")
                        if isinstance(desc, str) and desc.strip():
                            out.append(desc.strip())
                    elif isinstance(s, str) and s.strip():
                        out.append(s.strip())
                return out
    except json.JSONDecodeError:
        pass

    # Fallback: line-by-line heuristic for bullet/numbered lists
    queries = []
    for line in text.strip().splitlines():
        stripped = line.strip()
        # Match bullets, numbers 1-9, or step prefixes
        if re.match(r'^\s*([\-*•]|\d+[\.)])\s+', stripped):
            stripped = re.sub(r'^\s*([\-*•]|\d+[\.)])\s+', '', stripped).strip()
        # Also match "Step N: query" patterns
        elif re.match(r'^Step\s+\d+[:\.]\s*', stripped, re.IGNORECASE):
            stripped = re.sub(r'^Step\s+\d+[:\.]\s*', '', stripped, flags=re.IGNORECASE).strip()
        else:
            continue
        if stripped:
            queries.append(stripped)

    return queries


def node_decompose_goal(state: DeepResearchState) -> DeepResearchState:
    """Decompose the research goal into sub-queries.

    On the first iteration, generates initial sub-queries from the goal.
    On subsequent iterations, uses the accumulated knowledge_base to
    generate follow-up queries that explore gaps or new angles.
    """
    goal = state.get("goal", "")
    tid = state.get("trace_id", "")
    if not goal:
        return {**state, "sub_queries": [], "pending_queries": []}

    kb = state.get("knowledge_base", "")
    # Cap knowledge base to avoid overflowing the planner context
    findings_section = f"Current Findings:\n{kb[:2000]}\n\n" if kb else ""
    memory_ctx = state.get("memory_context", "")
    if memory_ctx:
        findings_section += f"Relevant Past Research:\n{memory_ctx[:1000]}\n\n"

    user_msg = DECOMPOSE_USER_TEMPLATE.format(goal=goal, findings_section=findings_section)

    try:
        result = llm.complete(
            role="planner",
            system=DECOMPOSE_SYSTEM_PROMPT,
            user=user_msg,
            trace_id=tid,
        )
        if not result.ok:
            logger.warning(f"Decompose LLM failed: {result.error}")
            return {**state, "sub_queries": [goal], "pending_queries": [goal]}

        sub_queries = _parse_sub_queries(result.text)
        if not sub_queries:
            sub_queries = [goal]

        return {**state, "sub_queries": sub_queries, "pending_queries": sub_queries}
    except Exception as e:
        logger.warning(f"Decompose exception: {e}")
        return {**state, "sub_queries": [goal], "pending_queries": [goal]}
