"""Decompose node: break a research goal into sub-queries.

If the planner LLM returns malformed JSON, the node falls back to a
single sub-query equal to the original goal so the graph never crashes.
"""
from __future__ import annotations

import json
import logging

from tools.agent_tool import agent
from workflows.deep_research_core.constants import (
    DECOMPOSE_SYSTEM_PROMPT,
    DECOMPOSE_USER_TEMPLATE,
)
from workflows.deep_research_core.state import DeepResearchState
from workflows.base import node_step

logger = logging.getLogger(__name__)


def node_decompose(state: DeepResearchState) -> DeepResearchState:
    """Break the research goal into 3–5 independent sub-queries.

    Uses ``agent(role="plan")`` to generate the sub-queries.  If the
    planner returns prose, malformed JSON, or fails outright, the node
    gracefully falls back to a single sub-query equal to the original
    goal so the loop can continue.

    Args:
        state: Workflow state containing at least ``goal`` and ``trace_id``.

    Returns:
        Partial state update with ``pending_queries`` populated.
    """
    goal = state.get("goal", "")
    tid = state.get("trace_id", "")
    node_step(state, "decompose", "breaking goal into sub-queries", goal=goal[:60])

    result = agent(
        role="plan",
        task=DECOMPOSE_SYSTEM_PROMPT,
        content=DECOMPOSE_USER_TEMPLATE.format(goal=goal),
        trace_id=tid,
    )

    # ── Fallback path: planner failed ──────────────────────────────
    if result.get("status") != "success":
        node_step(state, "decompose", "plan agent failed, using single query fallback")
        return {"pending_queries": [goal]}

    text = result.get("text", "")
    queries = _parse_sub_queries(text)

    if not queries:
        node_step(state, "decompose", "JSON parse failed, using single query fallback")
        queries = [goal]

    node_step(state, "decompose", f"generated {len(queries)} sub-queries")
    return {"pending_queries": queries}


def _parse_sub_queries(text: str) -> list[str]:
    """Extract sub-queries from planner LLM output.

    Tries, in order:
    1. JSON object with ``steps`` list.
    2. JSON list of strings.
    3. Line-by-line heuristic (only lines starting with ``-`` or numbers).

    Args:
        text: Raw LLM output.

    Returns:
        List of non-empty query strings.  Empty list if nothing usable found.
    """
    # 1. JSON object with "steps"
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "steps" in data:
            return [
                str(s.get("description", "")).strip()
                for s in data["steps"]
                if str(s.get("description", "")).strip()
            ]
        if isinstance(data, list):
            return [str(q).strip() for q in data if str(q).strip()]
    except json.JSONDecodeError:
        pass

    # 2. Line-by-line extraction — ONLY lines that look like list items
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        # Only accept lines that start with markdown bullets or numbering
        if stripped.startswith(("- ", "* ", "1. ", "2. ", "3. ", "4. ", "5. ")):
            stripped = stripped[2:].strip()
            if stripped:
                lines.append(stripped)

    return lines
