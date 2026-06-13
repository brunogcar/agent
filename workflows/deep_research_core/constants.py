"""System prompts and static configuration for DeepResearch nodes.

All multi-line prompts live here so that node files remain focused
on state manipulation and routing.  Prompts are tuned for the
local executor/planner/critique roles defined in the per-role model
registry.
"""
from __future__ import annotations

# -- Decompose -------------------------------------------------------
DECOMPOSE_SYSTEM_PROMPT: str = (
    "You are a research planner.  Break the user's research goal into "
    "3-5 concrete, specific sub-queries that can be searched independently.\n\n"
    "Return ONLY a JSON object in this exact format:\n"
    '{\n'
    '  "steps": [\n'
    '    {"description": "First sub-query"},\n'
    '    {"description": "Second sub-query"},\n'
    '    {"description": "Third sub-query"}\n'
    '  ]\n'
    '}\n\n'
    "Each sub-query must be self-contained and searchable.  "
    "Do not include explanations outside the JSON."
)

DECOMPOSE_USER_TEMPLATE: str = "Research goal: {goal}"

# -- Synthesize ------------------------------------------------------
SYNTHESIZE_SYSTEM_PROMPT: str = (
    "You are a research synthesizer.  Integrate new evidence with "
    "existing knowledge to produce a coherent, comprehensive answer "
    "to the research goal.\n\n"
    "Rules:\n"
    "1. Synthesize all evidence into a unified narrative.\n"
    "2. Cite sources using [index] format.\n"
    "3. Highlight contradictions or gaps.\n"
    "4. Keep the response focused on the goal.\n\n"
    "Return the synthesis as plain text."
)

SYNTHESIZE_USER_TEMPLATE: str = (
    "Goal: {goal}\n\n"
    "Previous knowledge:\n{prev_knowledge}\n\n"
    "New evidence:\n{evidence_text}"
)

# -- Evaluate / Critique ---------------------------------------------
EVALUATE_SYSTEM_PROMPT: str = (
    "You are a research evaluator.  Rate how completely the following "
    "synthesis answers the original research goal.\n\n"
    "Respond with ONLY a single integer between 0 and 100, where:\n"
    "  0   = completely irrelevant or empty\n"
    "  50  = partially answers the goal\n"
    "  100 = fully and comprehensively answers the goal\n\n"
    "Do not include any explanation, reasoning, or formatting.  "
    "Only the number."
)

EVALUATE_USER_TEMPLATE: str = (
    "Goal: {goal}\n\n"
    "Synthesis:\n{synthesis}\n\n"
    "Failed sources (do not re-attempt):\n{failed_sources}"
)

# -- Report ----------------------------------------------------------
REPORT_SYSTEM_PROMPT: str = (
    "You are a research reporter.  Produce a final markdown report "
    "from the accumulated synthesis and telemetry.\n\n"
    "Include a 'Budget Audit' appendix that lists every tool "
    "selection and fallback event."
)

# -- Heuristic keywords ----------------------------------------------
JS_HEAVY_HINTS: list[str] = [
    "react", "angular", "vue", "spa", "dashboard",
    "interactive", "dynamic", "single-page", "app",
]

COMPLEX_QUERY_HINTS: list[str] = [
    " and ", " vs ", " compare ", " contrast ",
    " difference between", " pros and cons", " overview of",
]

# -- Convergence -----------------------------------------------------
CONVERGENCE_SIMILARITY_THRESHOLD: float = 0.90
"""SequenceMatcher ratio above which knowledge_base is considered stable."""
