"""core/router_backend/heuristics.py -- Rule-based fallback routing.

Extracted from core/router.py v1.0 split. All pre-compiled regex patterns are
now MODULE-LEVEL constants (previously they were class attributes on TaskRouter).
The heuristic_route() function is a standalone that takes a goal string and
returns a RoutingDecision.


[DESIGN] KEY DECISIONS -- read before modifying:

  1. HEURISTIC PRIORITY ORDER (after v1.2 false-positive fixes):
     report -> browser -> file -> memory -> git -> notify -> cli -> tavily ->
     consult -> parallel -> deep_research -> understand -> code -> data ->
     research(explicit check, step #17) -> research(default fall-through, step #18).
     The explicit _RE_RESEARCH check (step #17) fires for higher-confidence
     research keywords. Step #18 is the catch-all default with confidence="low".

  2. FALSE-POSITIVE HISTORY -- patterns that were too broad, fixed in v1.2:
     _RE_DIRECT_PARALLEL originally included "simultaneously", "at the same time",
     "concurrently" -- common in code-fix and research requests.
     "Fix the race condition where X happens at the same time as Y" -> parallel (wrong).
     _RE_DIRECT_CONSULT originally included bare "consult" and "second opinion" -- too generic.
     RULE: write adversarial test cases FIRST when adding new patterns.

  3. _RE_RESEARCH IS explicitly checked at step #17 of heuristic_route()
     It returns research with confidence="medium". Step #18 is the pure
     fall-through default with confidence="low". Both exist -- do NOT remove
     the explicit check (step #17) or the default (step #18).

  4. THREE HARDCODED TOOL LISTS drift from each other: ROUTER_TOOLS (constants.py),
     dispatcher.py if-chain, and health.py static /tools fallback.
     The dynamic registry.get_tool_names() path is correct; the static fallbacks lag.
"""
from __future__ import annotations

import re

from core.router_backend.decision import RoutingDecision


# P2 Optimization: Pre-compiled regex patterns for O(1) heuristic matching.
# Replaces fragile O(N*M) string loops with fast, single-pass regex searches.
#
# [HEURISTIC FIX] Removed bare "error" to prevent false positives on research
# questions like "What is the error?". Added compound phrases (error message,
# runtime error, etc.) and "debug"/"audit" which are unambiguously code-related.
_RE_CODE = re.compile(
    r"\b(fix|bug|debug|audit|patch|refactor|improve|add feature|implement|edit|modify|update code|"
    r"error message|runtime error|type error|syntax error|logic error)\b",
    re.IGNORECASE,
)
_RE_DATA = re.compile(
    r"\b(analyse|analyze|calculate|compute|csv|excel|spreadsheet|statistics|pandas|numpy|dataset)\b",
    re.IGNORECASE,
)
_RE_RESEARCH = re.compile(
    r"\b(what is|what are|how does|explain|research|find information|summarise|summarize|look up)\b",
    re.IGNORECASE,
)
_RE_DIRECT_FILE = re.compile(
    r"\b(read file|open file|list files|list directory|write file|show file|read the file|open the file)\b",
    re.IGNORECASE,
)
_RE_DIRECT_MEMORY = re.compile(
    r"\b(recall|remember|what do you know about|store this|save this to memory)\b",
    re.IGNORECASE,
)
_RE_DIRECT_GIT = re.compile(
    r"\b(git status|git log|show commits|git diff|commit this|git commit)\b",
    re.IGNORECASE,
)
_RE_DIRECT_NOTIFY = re.compile(
    r"\b(notify me|send notification|remind me|schedule reminder)\b",
    re.IGNORECASE,
)
# [HEURISTIC FIX] Removed bare "report" to prevent false positives like
# "report a bug in server.py" routing to the report tool instead of autocode.
_RE_REPORT = re.compile(
    r"\b(create a chart|create chart|make a chart|plot a chart|draw a chart|"
    r"visualise|create a graph|make a graph|create a map|make a map|"
    r"create a dashboard|make a dashboard|create a report|make a report|"
    r"bar chart|line chart|pie chart|scatter plot|heatmap)\b",
    re.IGNORECASE,
)

# [ROUTER EXPANSION] New heuristic patterns for tools added after the
# initial router implementation: browser, cli, tavily, consult, parallel.
# Also adds workflow keywords for deep_research and understand.
# All patterns are case-insensitive and pre-compiled at module load time.
_RE_DIRECT_BROWSER = re.compile(
    r"\b(browse|fill form|click button|js-rendered|open page|"
    r"take a screenshot|capture screen|web automation|headless browser)\b",
    re.IGNORECASE,
)
_RE_DIRECT_CLI = re.compile(
    r"\b(run command|execute shell|terminal|bash|powershell|"
    r"pip install|npm install|yarn install|composer install|"
    r"docker build|docker run|kubectl|terraform apply|ansible)\b",
    re.IGNORECASE,
)
_RE_DIRECT_TAVILY = re.compile(
    r"\b(tavily|ai search|deep search|advanced search|"
    r"ai-powered search|intelligent search)\b",
    re.IGNORECASE,
)
# [HEURISTIC FIX] Narrowed consult regex to avoid false positives on
# ordinary English like "consult the documentation" or "get a second opinion
# from my doctor". Kept LLM-specific phrases only.
_RE_DIRECT_CONSULT = re.compile(
    r"\b(consult a different (?:ai|llm|model)|ask another model|"
    r"get another perspective|ask a different llm|"
    r"let's get a second opinion|second opinion from (?:ai|llm|model))\b",
    re.IGNORECASE,
)
# [HEURISTIC FIX] Narrowed parallel regex to avoid false positives on
# ordinary English like "explain how threads run simultaneously" or
# "research these topics in parallel". Requires explicit action intent.
# Uses \b on each alternative so partial words don't match.
_RE_DIRECT_PARALLEL = re.compile(
    r"\b(run\s+.*?\s+in\s+parallel|run\s+.*?\s+at\s+the\s+same\s+time|"
    r"batch process|concurrently|run together|parallel execution)\b",
    re.IGNORECASE,
)
_RE_DEEP_RESEARCH = re.compile(
    r"\b(deep research|thorough investigation|comprehensive report|"
    r"iterative research|multi-faceted research|extensive research|"
    r"in-depth analysis|detailed investigation)\b",
    re.IGNORECASE,
)
_RE_UNDERSTAND = re.compile(
    r"\b(understand codebase|build knowledge graph|analyze project structure|"
    r"index codebase|codebase overview|project analysis|"
    r"map dependencies|explore codebase|scan project)\b",
    re.IGNORECASE,
)
# [HEURISTIC FIX] Added missing heuristic patterns for vision and agent
# tools that were in the prompt but had no fallback coverage.
# Uses flexible matching so "analyze this image" and "ocr this screenshot" work.
# [HEURISTIC FIX v2] Removed bare "ocr" to prevent false positives on
# research questions like "what is OCR?". Requires action verb prefix.
_RE_DIRECT_VISION = re.compile(
    r"\b(ocr\s+(?:this|the|that|these|those|an|a|my)|"
    r"analyze\s+.*?\s+image|describe\s+.*?\s+image|what\s+is\s+in\s+this\s+image|"
    r"read\s+this\s+image|image\s+description|analyze\s+this\s+photo|"
    r"what\s+does\s+this\s+picture\s+show|read\s+text\s+from\s+image|"
    r"screenshot\s+analysis)\b",
    re.IGNORECASE,
)
# [HEURISTIC FIX v2] Removed "agent\s+for" to prevent false positives on
# ordinary English like "find a travel agent for my trip". Kept only
# AI-agent-specific phrases.
_RE_DIRECT_AGENT = re.compile(
    r"\b(delegate\s+.*?\s+agent|spawn\s+an\s+agent|use\s+an\s+agent|sub-agent|"
    r"let\s+an\s+agent|have\s+an\s+agent)\b",
    re.IGNORECASE,
)

# Schedule tool — cron jobs, recurring tasks, calendar sync, reminders with
# rich scheduling (the simple "remind me" path still routes to notify; this
# catches explicit scheduling/calendar intent). Narrowed to avoid false
# positives on ordinary English like "schedule a meeting" (calendar-app
# intent, not tool intent) — requires tool-scheduling phrases.
_RE_DIRECT_SCHEDULE = re.compile(
    r"\b(cron\s+job|recurring\s+(?:job|task|reminder)|every\s+\w+\s+at\s+\d|"
    r"schedule\s+a\s+(?:cron|recurring|daily|weekly|hourly)\s+(?:job|task|reminder)|"
    r"sync\s+(?:my\s+)?calendar|ical\s+sync|caldav|"
    r"run\s+.*?\s+(?:daily|weekly|hourly|every\s+day|every\s+week))\b",
    re.IGNORECASE,
)


def heuristic_route(goal: str) -> RoutingDecision:
    """Rule-based fallback routing when the model is unavailable.

    Standalone function (v1.0 split -- was TaskRouter._heuristic_route).

    Priority order (most specific first):
    1. Report (chart/dashboard creation)
    2. Browser (JS pages, screenshots, forms)
    3. File (read/write/list files)
    4. Memory (recall/store memories)
    5. Git (git operations)
    6. Notify (notifications)
    7. CLI (shell commands)
    8. Tavily (AI-powered search)
    9. Consult (ask another LLM)
    10. Parallel (execute multiple tasks concurrently)
    11. Vision (image analysis)
    12. Agent (delegate to sub-agent)
    13. Deep Research (iterative research)
    14. Understand (knowledge graph)
    15. Code (autocode workflow)
    16. Data (data analysis workflow)
    17. Research (explicit keywords, medium confidence)
    18. Default Research (catch-all, low confidence)
    """
    lower = goal.lower()

    # 1. Report tasks (most specific direct tool)
    if _RE_REPORT.search(goal):
        return RoutingDecision({
            "workflow": "direct",
            "tool": "report",
            "complexity": 3,
            "reason": "Report task -- use report() directly",
            "confidence": "high",
        })

    # 2. Browser tasks (JS-rendered pages, screenshots, forms)
    if _RE_DIRECT_BROWSER.search(goal):
        return RoutingDecision({
            "workflow": "direct",
            "tool": "browser",
            "complexity": 4,
            "reason": "Browser automation task -- use browser() directly",
            "confidence": "high",
        })

    # 3. File operations
    if _RE_DIRECT_FILE.search(goal):
        return RoutingDecision({
            "workflow": "direct",
            "tool": "file",
            "complexity": 2,
            "reason": "Simple file operation -- use file() directly",
            "confidence": "high",
        })

    # 4. Memory operations
    if _RE_DIRECT_MEMORY.search(goal):
        return RoutingDecision({
            "workflow": "direct",
            "tool": "memory",
            "complexity": 1,
            "reason": "Simple memory operation -- use memory() directly",
            "confidence": "high",
        })

    # 5. Git operations
    if _RE_DIRECT_GIT.search(goal):
        return RoutingDecision({
            "workflow": "direct",
            "tool": "git",
            "complexity": 2,
            "reason": "Simple git operation -- use git() directly",
            "confidence": "high",
        })

    # 6. Notification tasks
    if _RE_DIRECT_NOTIFY.search(goal):
        return RoutingDecision({
            "workflow": "direct",
            "tool": "notify",
            "complexity": 1,
            "reason": "Simple notification -- use notify() directly",
            "confidence": "high",
        })

    # 7. CLI / shell command tasks
    if _RE_DIRECT_CLI.search(goal):
        return RoutingDecision({
            "workflow": "direct",
            "tool": "cli",
            "complexity": 3,
            "reason": "Shell command task -- use cli() directly",
            "confidence": "high",
        })

    # 8. Tavily AI search tasks
    if _RE_DIRECT_TAVILY.search(goal):
        return RoutingDecision({
            "workflow": "direct",
            "tool": "tavily",
            "complexity": 4,
            "reason": "AI-powered search task -- use tavily() directly",
            "confidence": "high",
        })

    # 9. Consult / second opinion tasks
    if _RE_DIRECT_CONSULT.search(goal):
        return RoutingDecision({
            "workflow": "direct",
            "tool": "consult",
            "complexity": 2,
            "reason": "Consultation task -- use consult() directly",
            "confidence": "high",
        })

    # 10. Parallel execution (direct tool, not workflow)
    if _RE_DIRECT_PARALLEL.search(goal):
        return RoutingDecision({
            "workflow": "direct",
            "tool": "parallel",
            "complexity": 5,
            "reason": "Multiple independent tasks to run concurrently",
            "confidence": "medium",
        })

    # 11. Vision tasks (image analysis)
    if _RE_DIRECT_VISION.search(goal):
        return RoutingDecision({
            "workflow": "direct",
            "tool": "vision",
            "complexity": 3,
            "reason": "Image analysis task -- use vision() directly",
            "confidence": "high",
        })

    # 12. Agent tasks (delegate to sub-agent)
    if _RE_DIRECT_AGENT.search(goal):
        return RoutingDecision({
            "workflow": "direct",
            "tool": "agent",
            "complexity": 6,
            "reason": "Complex sub-task delegation -- use agent() directly",
            "confidence": "medium",
        })

    # 12b. Schedule tasks (cron / recurring / calendar sync — richer than notify)
    if _RE_DIRECT_SCHEDULE.search(goal):
        return RoutingDecision({
            "workflow": "direct",
            "tool": "schedule",
            "complexity": 3,
            "reason": "Scheduling task (cron/recurring/calendar) -- use schedule() directly",
            "confidence": "high",
        })

    # 13. Deep Research workflow (iterative, multi-faceted research)
    if _RE_DEEP_RESEARCH.search(goal):
        return RoutingDecision({
            "workflow": "deep_research",
            "tool": "workflow",
            "complexity": 8,
            "reason": "Complex research requiring iterative evidence synthesis",
            "confidence": "medium",
        })

    # 14. Understand workflow (codebase knowledge graph)
    if _RE_UNDERSTAND.search(goal):
        return RoutingDecision({
            "workflow": "understand",
            "tool": "workflow",
            "complexity": 6,
            "reason": "Codebase analysis and knowledge graph building",
            "confidence": "medium",
        })

    # 15. Code-related keywords (autocode workflow)
    if _RE_CODE.search(goal):
        # Extra check: does it mention a file?
        has_file = any(
            ext in lower for ext in [".py", ".js", ".ts", ".json", ".yaml", ".md"]
        )
        return RoutingDecision({
            "workflow": "autocode",
            "tool": "workflow",
            "complexity": 7 if has_file else 5,
            "reason": "Contains code modification keywords",
            "confidence": "medium",
        })

    # 16. Data analysis keywords (data workflow)
    if _RE_DATA.search(goal):
        return RoutingDecision({
            "workflow": "data",
            "tool": "python",
            "complexity": 5,
            "reason": "Contains data analysis keywords",
            "confidence": "medium",
        })

    # 17. Explicit research keywords (higher confidence than default)
    if _RE_RESEARCH.search(goal):
        return RoutingDecision({
            "workflow": "research",
            "tool": "web",
            "complexity": 4,
            "reason": "Contains research/question keywords",
            "confidence": "medium",
        })

    # 18. Default to research (catch-all)
    return RoutingDecision({
        "workflow": "research",
        "tool": "web",
        "complexity": 4,
        "reason": "No specific routing keywords matched",
        "confidence": "low",
    })
