"""workflows/deep_research_core/nodes/decompose.py
Goal-decomposition node.
"""
from __future__ import annotations
import json
import re
from typing import List
from workflows.deep_research_core.state import DeepResearchState
from workflows.deep_research_core.constants import (
    DECOMPOSE_SYSTEM_PROMPT,
    DECOMPOSE_USER_TEMPLATE,
)
from core.llm import llm
from core.config import cfg


def node_decompose(state: DeepResearchState) -> DeepResearchState:
    """Break the research goal into sub-queries."""
    goal = state.get("goal", "")
    tid = state.get("trace_id", "")
    if not goal:
        return {"status": "error", "error": "No goal provided"}

    # Cap goal length to prevent context overflow / DoS
    max_goal = getattr(cfg, "deep_research_goal_max_chars", 2000)
    goal = goal[:max_goal]

    # Call llm.complete directly so the system prompt is actually
    # DECOMPOSE_SYSTEM_PROMPT, not the autocode plan prompt from
    # agent_tool.py (see Bug 4 in review).
    result = llm.complete(
        role="planner",
        system=DECOMPOSE_SYSTEM_PROMPT,
        user=DECOMPOSE_USER_TEMPLATE.format(goal=goal),
        trace_id=tid,
    )
    if not result.ok:
        return {"sub_queries": [goal], "pending_queries": [goal], "extracted_evidence": []}

    raw = result.text
    queries = _parse_sub_queries(raw, goal)
    if not queries:
        queries = [goal]
    return {"sub_queries": queries, "pending_queries": queries, "extracted_evidence": []}


def _parse_sub_queries(text: str, fallback: str) -> List[str]:
    """Extract sub-queries from planner output.

    Tries three strategies:
      1. JSON object with {"steps": [{"description": "..."}]}
      2. JSON list of strings
      3. Line-by-line heuristic (bullets, numbers, or "Step N:" patterns)
    """
    # Strategy 1 & 2: JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "steps" in data:
            return [s["description"] for s in data["steps"] if s.get("description")]
        if isinstance(data, list):
            return [q for q in data if isinstance(q, str) and q.strip()]
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    # Strategy 3: line-by-line heuristic
    lines = text.strip().splitlines()
    queries = []
    for line in lines:
        stripped = line.strip()
        # Match bullets, numbers 1-9, or "Step N:" patterns
        if re.match(r'^\s*([\-*•]|\d+[\.)])\s+', stripped):
            # Strip the prefix
            cleaned = re.sub(r'^\s*([\-*•]|\d+[\.)])\s+', '', stripped).strip()
            if cleaned:
                queries.append(cleaned)
        elif re.match(r'^Step\s+\d+[\.:]?\s*', stripped, re.IGNORECASE):
            cleaned = re.sub(r'^Step\s+\d+[\.:]?\s*', '', stripped, flags=re.IGNORECASE).strip()
            if cleaned:
                queries.append(cleaned)
    return queries if queries else []
