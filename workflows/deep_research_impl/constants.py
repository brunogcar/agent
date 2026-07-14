"""workflows/deep_research_impl/constants.py
Constants and prompts for the DeepResearch workflow.
"""
from __future__ import annotations
from difflib import SequenceMatcher

# -- Convergence ----------------------------------------------------------------
CONVERGENCE_SIMILARITY_THRESHOLD = 0.85

def _is_converged(old_knowledge: str, new_knowledge: str, threshold: float = CONVERGENCE_SIMILARITY_THRESHOLD) -> bool:
    """Check if two knowledge strings are sufficiently similar to indicate convergence.

    Uses difflib.SequenceMatcher for a conservative similarity estimate.
    With the _merge_knowledge replace semantics, knowledge_base stays bounded
    to ~2-4K chars, making this O(N) in practice.
    """
    if not old_knowledge or not new_knowledge:
        return False
    return SequenceMatcher(None, old_knowledge, new_knowledge).ratio() >= threshold

# -- Decompose prompts ----------------------------------------------------------
DECOMPOSE_SYSTEM_PROMPT = (
    "You are a research planning specialist. "
    "Given a research goal and optionally what we have learned so far, "
    "generate 3-5 specific, searchable sub-queries. "
    "If no findings exist yet, break the goal into initial sub-queries. "
    "If we already have findings, generate follow-up queries that explore "
    "gaps, contradictions, or angles not yet covered. "
    "Each sub-query must be a complete question or search phrase that can be "
    "answered by a web search. "
    "Return ONLY a JSON array of strings. No thinking tags. "
    "No markdown fences. Start with [ and end with ]."
)

DECOMPOSE_USER_TEMPLATE = """Research Goal: {goal}

{findings_section}Generate 3-5 specific, searchable sub-queries.
Return ONLY a JSON array of strings."""

# -- Synthesize prompts ---------------------------------------------------------
SYNTHESIZE_SYSTEM_PROMPT = (
    "You are a research synthesis specialist. "
    "Integrate new evidence with existing knowledge to produce a coherent, "
    "comprehensive answer. Cite sources where possible. "
    "Do not hallucinate facts not present in the provided content. "
    "If sources conflict, note the conflict explicitly. "
    "Format with markdown headings for readability."
)

SYNTHESIZE_USER_TEMPLATE = """Goal: {goal}

Previous Knowledge:
{prev_knowledge}

New Evidence:
{evidence}

Synthesize the above into an updated, comprehensive answer."""

# -- Evaluate prompt ------------------------------------------------------------
EVALUATE_SYSTEM_PROMPT = (
    "You are a strict evaluator. Score the following synthesis on a scale of "
    "0-100 based on how completely it answers the original goal. "
    "0 = completely unaddressed, 50 = partially addressed, "
    "100 = fully and comprehensively answers the goal. "
    "Return ONLY the numeric score (e.g., '85')."
)

EVALUATE_USER_TEMPLATE = """Goal: {goal}

Synthesis:
{synthesis}

Score (0-100):"""
