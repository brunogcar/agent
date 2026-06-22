"""core/router.py -- Router-based task router.
Classifies any free-text goal into a structured routing decision
before the workflow layer runs. The Router model is used for speed (15s timeout).

Usage:
    from core.router import router
    decision = router.route("Fix the timeout bug in tools/web.py")
    # Returns:
    # {
    #   "workflow": "autocode",
    #   "tool": "workflow",
    #   "complexity": 6,
    #   "reason": "Involves editing an existing code file to fix a bug",
    #   "confidence": "high"
    # }

    decision = router.classify_complexity("Research ChromaDB")
    # Returns: 4 (int, 1-10)
"""
from __future__ import annotations
import json
import re
from typing import Optional
from core.llm import llm
from core.tracer import tracer

# -- Routing decision dataclass -----------------------------------------------
class RoutingDecision:
    """Structured routing decision with fallback handling.

    Consumed by the workflow tool, the dispatcher, and the gateway.
    All fields have sensible defaults so heuristics never crash.
    """
    def __init__(self, raw: dict) -> None:
        self.workflow = raw.get("workflow", "research")
        self.tool = raw.get("tool", "web")
        self.complexity = int(raw.get("complexity", 5))
        self.reason = raw.get("reason", "")
        self.confidence = raw.get("confidence", "medium")
        self.clarifying_questions = raw.get("clarifying_questions", [])
        self.raw = raw

    def __repr__(self) -> str:
        return (
            f"RoutingDecision(workflow={self.workflow!r}, "
            f"tool={self.tool!r}, complexity={self.complexity}, "
            f"reason={self.reason!r})"
        )

    def to_dict(self) -> dict:
        return {
            "workflow": self.workflow,
            "tool": self.tool,
            "complexity": self.complexity,
            "reason": self.reason,
            "confidence": self.confidence,
        }

# -- Router -------------------------------------------------------------------
class TaskRouter:
    """
    Routes tasks to the appropriate workflow using the Router model.
    Falls back to heuristic routing if the model is unavailable
    or returns unparseable output.

    Heuristic priority (most specific first):
      1. report   -> direct (chart/dashboard creation)
      2. browser  -> direct (JS pages, screenshots, forms)
      3. file     -> direct (read/write/list files)
      4. memory   -> direct (recall/store memories)
      5. git      -> direct (git operations)
      6. notify   -> direct (notifications)
      7. cli      -> direct (shell commands)
      8. tavily   -> direct (AI-powered search)
      9. consult  -> direct (ask another LLM)
     10. parallel  -> direct (execute multiple tasks concurrently)
     11. deep_research -> workflow (iterative research)
     12. understand    -> workflow (knowledge graph)
     13. autocode     -> workflow (code edits)
     14. data         -> workflow (analysis)
     15. research     -> workflow (default catch-all)

    Rationale: Direct-tool keywords are more specific than workflow
    keywords. A user saying "read file X" must never be misrouted to
    the autocode workflow just because "fix" also appears in the goal.
    """

    # P2 Optimization: Pre-compiled regex patterns for O(1) heuristic matching
    # Replaces fragile O(N*M) string loops with fast, single-pass regex searches.
    _RE_CODE = re.compile(r"\b(fix|bug|error|patch|refactor|improve|add feature|implement|edit|modify|update code)\b", re.IGNORECASE)
    _RE_DATA = re.compile(r"\b(analyse|analyze|calculate|compute|csv|excel|spreadsheet|statistics|pandas|numpy|dataset)\b", re.IGNORECASE)
    _RE_RESEARCH = re.compile(r"\b(what is|what are|how does|explain|research|find information|summarise|summarize|look up)\b", re.IGNORECASE)
    _RE_DIRECT_FILE = re.compile(r"\b(read file|open file|list files|list directory|write file|show file|read the file|open the file)\b", re.IGNORECASE)
    _RE_DIRECT_MEMORY = re.compile(r"\b(recall|remember|what do you know about|store this|save this to memory)\b", re.IGNORECASE)
    _RE_DIRECT_GIT = re.compile(r"\b(git status|git log|show commits|git diff|commit this|git commit)\b", re.IGNORECASE)
    _RE_DIRECT_NOTIFY = re.compile(r"\b(notify me|send notification|remind me|schedule reminder)\b", re.IGNORECASE)
    _RE_REPORT = re.compile(r"\b(create a chart|create chart|make a chart|plot a chart|draw a chart|report|visualise|create a graph|make a graph|create a map|make a map|create a dashboard|make a dashboard|create a report|make a report|bar chart|line chart|pie chart|scatter plot|heatmap)\b", re.IGNORECASE)

    # [ROUTER EXPANSION] New heuristic patterns for tools added after the
    # initial router implementation: browser, cli, tavily, consult, parallel.
    # Also adds workflow keywords for deep_research and understand.
    # All patterns are case-insensitive and pre-compiled at class load time.
    _RE_DIRECT_BROWSER = re.compile(
        r"\b(browse|screenshot|fill form|click button|js-rendered|open page|"
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
    _RE_DIRECT_CONSULT = re.compile(
        r"\b(consult|ask another model|second opinion|"
        r"get another perspective|ask a different llm)\b",
        re.IGNORECASE,
    )
    _RE_DIRECT_PARALLEL = re.compile(
        r"\b(run in parallel|in parallel|batch process|concurrently|at the same time|"
        r"simultaneously|process all|run together|parallel execution)\b",
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

    def _extract_first_json(self, text: str) -> str | None:
        """
        Extract the first valid JSON object from text.
        Handles deep nesting, escaped quotes inside strings, and markdown wrappers.
        Uses Python's native C-optimized json.JSONDecoder().raw_decode() for safety.
        """
        # 1. Strip markdown fences immediately (immune to LLM formatting)
        clean = text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

        # 2. Try direct parse first (fastest)
        try:
            json.loads(clean)
            return clean
        except json.JSONDecodeError:
            pass

        # 3. Fallback: Use Python's native C-optimized raw_decode
        # This safely handles all escape sequences, nested strings, and edge cases.
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(clean):
            if clean[idx] in '{[':
                try:
                    obj, end = decoder.raw_decode(clean, idx)
                    return clean[idx:end]
                except json.JSONDecodeError:
                    pass
            idx += 1
        return None

    def route(
        self,
        goal: str,
        trace_id: str = "",
    ) -> RoutingDecision:
        """
        Route a goal to the best workflow.
        Tries the Router first, falls back to heuristics on failure.
        """
        if not goal.strip():
            return RoutingDecision({
                "workflow": "research", "tool": "web",
                "complexity": 1, "reason": "Empty goal",
                "confidence": "low",
                "clarifying_questions": ["What would you like me to help you with?"]
            })

        if trace_id:
            tracer.step(trace_id, "router", "routing task", goal=goal[:60])

        # Try model-based routing
        decision = self._model_route(goal, trace_id)
        if decision:
            if trace_id:
                tracer.step(trace_id, "router",
                    f"routed to {decision.workflow} (model)",
                    complexity=decision.complexity)
            return decision

        # Fall back to heuristics
        decision = self._heuristic_route(goal)
        if trace_id:
            tracer.step(trace_id, "router",
                f"routed to {decision.workflow} (heuristic)",
                complexity=decision.complexity)
        return decision

    def classify_complexity(self, goal: str) -> int:
        """
        Quick complexity score (1-10) for a goal.
        Uses the Router classify role.
        """
        r = llm.complete(
            role = "router",
            system = (
                "Rate the complexity of this task on a scale of 1-10. "
                "Output only a single integer. Nothing else."
                "\n1-3: single tool, clear input/output"
                "\n4-6: multi-step, predictable"
                "\n7-9: complex, multiple tools, uncertainty"
                "\n10: requires human judgment"
            ),
            user = goal,
        )
        if r.ok:
            try:
                return max(1, min(10, int(r.text.strip())))
            except (ValueError, TypeError):
                pass
        return 5  # default

    def _model_route(
        self,
        goal: str,
        trace_id: str,
    ) -> Optional[RoutingDecision]:
        """Try to get a routing decision from the Router."""
        r = llm.complete(
            role = "router",
            system = (
                "No thinking. No explanation.\n"
                '{"workflow": "research or data or autocode or deep_research or understand",'
                # [ROUTER EXPANSION] Tool list expanded from 10 to 15 tools.
                # Added: cli, browser, tavily, consult, parallel.
                # The router prompt must stay in sync with registered tools.
                ' "tool": "web or python or file or git or memory or agent or notify or report or vision or workflow or cli or browser or tavily or consult or parallel",'
                ' "complexity":5,'
                ' "reason": "one sentence",'
                ' "confidence": "high or medium or low",'
                ' "clarifying_questions": ["question1", "question2"]}\n'
                "\n\nWorkflow routing rules:\n"
                "- research: finding info, summarising, reading docs, Q&A\n"
                "- data: pandas, analysis, calculations, charts, spreadsheets\n"
                "- autocode: fixing bugs, editing code files, adding features\n"
                "- deep_research: complex multi-faceted research, iterative evidence synthesis\n"
                "- understand: build or query codebase knowledge graph, analyze project structure\n"
                "\nTool routing rules (for direct workflow):\n"
                "- web: general web search and page reading\n"
                "- python: data analysis, calculations, plotting\n"
                "- file: read, write, list files and directories\n"
                "- git: git operations, commits, diffs, status\n"
                "- memory: recall, store, search memories\n"
                "- agent: delegate to sub-agent for complex sub-tasks\n"
                "- notify: send notifications and reminders\n"
                "- report: create charts, dashboards, visual reports\n"
                "- vision: image analysis and description\n"
                "- workflow: multi-step task execution via workflow engine\n"
                "- cli: shell commands, system administration, package management\n"
                "- browser: JavaScript-rendered pages, screenshots, form interaction\n"
                "- tavily: AI-powered deep web search\n"
                "- consult: ask another LLM for a second opinion\n"
                "- parallel: execute multiple independent tasks concurrently\n"
                "\nConfidence rules:\n"
                "- high: Clear task with specific details\n"
                "- medium: Understandable but could be more specific\n"
                "- low: Vague or ambiguous. MUST provide 1-2 clarifying questions to help the user refine their goal."
            ),
            user = goal,
            trace_id = trace_id,
        )

        if not r.ok:
            return None

        # Parse JSON from response
        text = r.text.strip()
        clean = text

        # Strip markdown fences and use deterministic JSON extractor
        for fence in ("```json", "```"):
            if clean.startswith(fence):
                clean = clean[len(fence):]
                clean = clean.strip().rstrip("`").strip()

        extracted = self._extract_first_json(clean)
        if extracted:
            clean = extracted

        try:
            data = json.loads(clean)
            # Validate required fields
            if "workflow" in data:
                return RoutingDecision(data)
        except (json.JSONDecodeError, ValueError):
            pass

        return None

    def _heuristic_route(self, goal: str) -> RoutingDecision:
        """Rule-based fallback routing when model is unavailable.

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
         11. Deep Research (iterative research)
         12. Understand (knowledge graph)
         13. Code (autocode workflow)
         14. Data (data analysis workflow)
         15. Default Research (catch-all)
        """
        lower = goal.lower()

        # 1. Report tasks (most specific direct tool)
        if self._RE_REPORT.search(goal):
            return RoutingDecision({
                "workflow": "direct",
                "tool": "report",
                "complexity": 3,
                "reason": "Report task -- use report() directly",
                "confidence": "high",
            })

        # 2. Browser tasks (JS-rendered pages, screenshots, forms)
        if self._RE_DIRECT_BROWSER.search(goal):
            return RoutingDecision({
                "workflow": "direct",
                "tool": "browser",
                "complexity": 4,
                "reason": "Browser automation task -- use browser() directly",
                "confidence": "high",
            })

        # 3. File operations
        if self._RE_DIRECT_FILE.search(goal):
            return RoutingDecision({
                "workflow": "direct",
                "tool": "file",
                "complexity": 2,
                "reason": "Simple file operation -- use file() directly",
                "confidence": "high",
            })

        # 4. Memory operations
        if self._RE_DIRECT_MEMORY.search(goal):
            return RoutingDecision({
                "workflow": "direct",
                "tool": "memory",
                "complexity": 1,
                "reason": "Simple memory operation -- use memory() directly",
                "confidence": "high",
            })

        # 5. Git operations
        if self._RE_DIRECT_GIT.search(goal):
            return RoutingDecision({
                "workflow": "direct",
                "tool": "git",
                "complexity": 2,
                "reason": "Simple git operation -- use git() directly",
                "confidence": "high",
            })

        # 6. Notification tasks
        if self._RE_DIRECT_NOTIFY.search(goal):
            return RoutingDecision({
                "workflow": "direct",
                "tool": "notify",
                "complexity": 1,
                "reason": "Simple notification -- use notify() directly",
                "confidence": "high",
            })

        # 7. CLI / shell command tasks
        if self._RE_DIRECT_CLI.search(goal):
            return RoutingDecision({
                "workflow": "direct",
                "tool": "cli",
                "complexity": 3,
                "reason": "Shell command task -- use cli() directly",
                "confidence": "high",
            })

        # 8. Tavily AI search tasks
        if self._RE_DIRECT_TAVILY.search(goal):
            return RoutingDecision({
                "workflow": "direct",
                "tool": "tavily",
                "complexity": 4,
                "reason": "AI-powered search task -- use tavily() directly",
                "confidence": "high",
            })

        # 9. Consult / second opinion tasks
        if self._RE_DIRECT_CONSULT.search(goal):
            return RoutingDecision({
                "workflow": "direct",
                "tool": "consult",
                "complexity": 2,
                "reason": "Consultation task -- use consult() directly",
                "confidence": "high",
            })

        # 10. Parallel execution (direct tool, not workflow)
        if self._RE_DIRECT_PARALLEL.search(goal):
            return RoutingDecision({
                "workflow": "direct",
                "tool": "parallel",
                "complexity": 5,
                "reason": "Multiple independent tasks to run concurrently",
                "confidence": "medium",
            })

        # 11. Deep Research workflow (iterative, multi-faceted research)
        if self._RE_DEEP_RESEARCH.search(goal):
            return RoutingDecision({
                "workflow": "deep_research",
                "tool": "workflow",
                "complexity": 8,
                "reason": "Complex research requiring iterative evidence synthesis",
                "confidence": "medium",
            })

        # 12. Understand workflow (codebase knowledge graph)
        if self._RE_UNDERSTAND.search(goal):
            return RoutingDecision({
                "workflow": "understand",
                "tool": "workflow",
                "complexity": 6,
                "reason": "Codebase analysis and knowledge graph building",
                "confidence": "medium",
            })

        # 13. Code-related keywords (autocode workflow)
        if self._RE_CODE.search(goal):
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

        # 14. Data analysis keywords (data workflow)
        if self._RE_DATA.search(goal):
            return RoutingDecision({
                "workflow": "data",
                "tool": "python",
                "complexity": 5,
                "reason": "Contains data analysis keywords",
                "confidence": "medium",
            })

        # 15. Default to research (catch-all)
        return RoutingDecision({
            "workflow": "research",
            "tool": "web",
            "complexity": 4,
            "reason": "No specific routing keywords matched",
            "confidence": "low",
        })

# -- Singleton ----------------------------------------------------------------
router = TaskRouter()
