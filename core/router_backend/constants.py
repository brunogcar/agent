"""core/router_backend/constants.py -- Router prompt + expected tool/workflow sets.

Extracted from core/router.py v1.0 split. Module-level constants so tests
can import them directly instead of parsing source code with
inspect.getsource() + ast.literal_eval.
"""
from __future__ import annotations

# -- Module-level constants for prompt and expected sets ----------------------
ROUTER_WORKFLOWS = ["research", "data", "autocode", "deep_research", "understand"]
ROUTER_TOOLS = [
    "web", "python", "file", "git", "memory", "agent", "notify", "report",
    "vision", "workflow", "cli", "browser", "tavily", "consult", "parallel", "swarm", "github",
    "schedule",
]

# Pre-built prompt fragments for model_route(). Kept as constants so tests
# and docs can reference the canonical strings without source parsing.
_ROUTER_PROMPT_WORKFLOW_LIST = " or ".join(ROUTER_WORKFLOWS)
_ROUTER_PROMPT_TOOL_LIST = " or ".join(ROUTER_TOOLS)

# Few-shot examples for the router prompt. Each tuple is (goal, decision_json).
# These help the LLM learn the routing pattern by imitation.
# NOTE: goals must be consistent with heuristic routing (verified by tests).
ROUTER_FEW_SHOT_EXAMPLES = [
    (
        '"Fix the bug in server.py"',
        '{"workflow": "autocode", "tool": "workflow", "complexity": 7, "reason": "Code fix with specific file", "confidence": "high", "clarifying_questions": []}',
    ),
    (
        '"What is ChromaDB?"',
        '{"workflow": "research", "tool": "web", "complexity": 4, "reason": "Information lookup", "confidence": "high", "clarifying_questions": []}',
    ),
    (
        '"Create a bar chart of sales data"',
        '{"workflow": "direct", "tool": "report", "complexity": 3, "reason": "Chart creation request", "confidence": "high", "clarifying_questions": []}',
    ),
]

ROUTER_SYSTEM_PROMPT = (
    "No thinking. No explanation.\n"
    + '{"workflow": "' + _ROUTER_PROMPT_WORKFLOW_LIST + '",'
    + ' "tool": "' + _ROUTER_PROMPT_TOOL_LIST + '",'
    + ' "complexity":5,'
    + ' "reason": "one sentence",'
    + ' "confidence": "high or medium or low",'
    + ' "clarifying_questions": ["question1", "question2"]}\n'
    + "\n\nWorkflow routing rules:\n"
    + "- research: finding info, summarising, reading docs, Q&A\n"
    + "- data: pandas, analysis, calculations, charts, spreadsheets\n"
    + "- autocode: fixing bugs, editing code files, adding features\n"
    + "- deep_research: complex multi-faceted research, iterative evidence synthesis\n"
    + "- understand: build or query codebase knowledge graph, analyze project structure\n"
    + "\nTool routing rules (for direct workflow):\n"
    + "- web: general web search and page reading\n"
    + "- python: data analysis, calculations, plotting\n"
    + "- file: read, write, list files and directories\n"
    + "- git: git operations, commits, diffs, status\n"
    + "- memory: recall, store, search memories\n"
    + "- agent: delegate to sub-agent for complex sub-tasks\n"
    + "- notify: send notifications and reminders\n"
    + "- report: create charts, dashboards, visual reports\n"
    + "- vision: image analysis and description\n"
    + "- workflow: multi-step task execution via workflow engine\n"
    + "- cli: shell commands, system administration, package management\n"
    + "- browser: JavaScript-rendered pages, screenshots, form interaction\n"
    + "- tavily: AI-powered deep web search\n"
    + "- consult: ask another LLM for a second opinion\n"
    + "- parallel: execute multiple independent tasks concurrently\n"
    + "- swarm: multi-model consultation (ask all cloud providers at once)\n"
    + "- github: GitHub PR operations (create, list, review, merge, push)\n"
    + "- schedule: cron/interval/one-shot jobs + iCal calendar sync (delivered via notify)\n"
    + "\nConfidence rules:\n"
    + "- high: Clear task with specific details\n"
    + "- medium: Understandable but could be more specific\n"
    + "- low: Vague or ambiguous. MUST provide 1-2 clarifying questions to help the user refine their goal."
    + "\n\nExamples:\n"
    + "\n".join(f"- {goal} -> {decision}" for goal, decision in ROUTER_FEW_SHOT_EXAMPLES)
)
