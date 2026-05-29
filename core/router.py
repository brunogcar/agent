"""
core/router.py -- Router-based task router.

Classifies any free-text goal into a structured routing decision
before the workflow layer runs. The Router model is used for speed (15s timeout).

Usage:
    from core.router import router

    decision = router.route("Fix the timeout bug in tools/web.py")
    # Returns:
    # {
    #   "workflow":   "autocode",
    #   "tool":       "workflow",
    #   "complexity": 6,
    #   "reason":     "Involves editing an existing code file to fix a bug",
    #   "confidence": "high"
    # }

    decision = router.classify_complexity("Research ChromaDB")
    # Returns: 4  (int, 1-10)
"""

from __future__ import annotations

import json
import re
from typing import Optional

from core.llm    import llm
from core.tracer import tracer


# -- Routing decision dataclass -----------------------------------------------

class RoutingDecision:
    """Structured routing decision with fallback handling."""
    def __init__(self, raw: dict) -> None:
        self.workflow   = raw.get("workflow",    "research")
        self.tool       = raw.get("tool",        "web")
        self.complexity = int(raw.get("complexity", 5))
        self.reason     = raw.get("reason",      "")
        self.confidence = raw.get("confidence",  "medium")
        self.clarifying_questions = raw.get("clarifying_questions", [])
        self.raw        = raw

    def __repr__(self) -> str:
        return (
            f"RoutingDecision(workflow={self.workflow!r}, "
            f"tool={self.tool!r}, complexity={self.complexity}, "
            f"reason={self.reason!r})"
        )

    def to_dict(self) -> dict:
        return {
            "workflow":   self.workflow,
            "tool":       self.tool,
            "complexity": self.complexity,
            "reason":     self.reason,
            "confidence": self.confidence,
        }


# -- Router -------------------------------------------------------------------

class TaskRouter:
    """
    Routes tasks to the appropriate workflow using the Router model.

    Falls back to heuristic routing if the model is unavailable
    or returns unparseable output.
    """

    # Heuristic keywords for fallback routing
    _CODE_KEYWORDS    = ["fix", "bug", "error", "patch", "refactor", "improve",
                         "add feature", "implement", "edit", "modify", "update code"]
    _DATA_KEYWORDS    = ["analyse", "analyze", "calculate", "compute", "plot",
                         "chart", "csv", "excel", "spreadsheet", "statistics",
                         "pandas", "numpy", "dataset"]
    _RESEARCH_KEYWORDS= ["what is", "what are", "how does", "explain", "research",
                         "find information", "summarise", "summarize", "look up"]
    # Direct tool keywords -- simple single-tool tasks that don't need a workflow
    _DIRECT_FILE      = ["read file", "open file", "list files", "list directory",
                         "write file", "show file", "read the file", "open the file"]
    _DIRECT_MEMORY    = ["recall", "remember", "what do you know about",
                         "store this", "save this to memory"]
    _DIRECT_GIT       = ["git status", "git log", "show commits", "git diff",
                         "commit this", "git commit"]
    _DIRECT_NOTIFY    = ["notify me", "send notification", "remind me",
                         "schedule reminder"]
    # Report keywords -- route to direct report tool
    _REPORT_KEYWORDS = ["create a chart", "create chart", "make a chart",
                           "plot a chart", "draw a chart", "report",
                           "visualise", "create a graph", "make a graph",
                           "create a map", "make a map", "create a dashboard",
                           "make a dashboard", "create a report",
                           "make a report", "bar chart", "line chart",
                           "pie chart", "scatter plot", "heatmap"]

    def _extract_first_json(self, text: str) -> str | None:
        """
        Extract the first valid JSON object from text.
        Handles deep nesting, escaped quotes inside strings, and markdown wrappers.
        Replaces the fragile single-level regex.
        """
        decoder = json.JSONDecoder()
        in_string = False
        escape = False
        depth = 0
        start = None

        for i, ch in enumerate(text):
            if escape:
                escape = False
                continue
            if ch == "\\":
                if in_string:
                    escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue

            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    candidate = text[start:i + 1]
                    try:
                        decoder.decode(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        # Invalid JSON structure, reset and keep looking
                        start = None
        return None

    def route(
        self,
        goal:     str,
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
            role   = "router",
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
        goal:     str,
        trace_id: str,
    ) -> Optional[RoutingDecision]:
        """Try to get a routing decision from the Router."""
        r = llm.complete(
            role   = "router",
            system = (
                "You are a task router. Output ONLY a JSON object wrapped in <tool_call> tags. "
                "No thinking. No explanation.\n"
                "<tool_call>\n"
                '{"workflow": "research or data or autocode",'
                '  "tool": "web or python or file or git or memory or agent or notify or report or workflow",'
                '  "complexity":5,'
                '  "reason": "one sentence",'
                '  "confidence": "high or medium or low",'
                '  "clarifying_questions": ["question1", "question2"]}\n'
                "</tool_call>\n"
                "\n\nRouting rules:"
                "\n- research: finding info, summarising, reading docs, Q&A"
                "\n- data: pandas, analysis, calculations, charts, spreadsheets"
                "\n- autocode: fixing bugs, editing code files, adding features"
                "\n- direct: single-tool task (use tool field, not workflow)"
                "\n\nConfidence rules:"
                "\n- high: Clear task with specific details"
                "\n- medium: Understandable but could be more specific"
                "\n- low: Vague or ambiguous. MUST provide 1-2 clarifying questions to help the user refine their goal."
            ),
            user     = goal,
            trace_id = trace_id,
        )

        if not r.ok:
            return None

        # Parse JSON from response
        text = r.text.strip()
        clean = text

        # 🔴 Consensus Item 4: Tool-Call Envelopes (Prompt Injection Mitigation)
        # Prefer explicit <tool_call> tags if the model followed instructions
        envelope_match = re.search(r'<tool_call>\s*(.*?)\s*</tool_call>', text, re.DOTALL)
        if envelope_match:
            clean = envelope_match.group(1).strip()
        else:
            # Fallback: Strip markdown fences and use deterministic bracket-counting parser
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
        """Rule-based fallback routing when model is unavailable."""
        lower = goal.lower()

        # Check for report tasks before generic routing
        if any(kw in lower for kw in self._REPORT_KEYWORDS):
            return RoutingDecision({
                "workflow":   "direct",
                "tool":       "report",
                "complexity": 3,
                "reason":     "Report task -- use report() directly",
                "confidence": "high",
            })

        # Check for direct single-tool tasks first (most specific)
        if any(kw in lower for kw in self._DIRECT_FILE):
            return RoutingDecision({
                "workflow":   "direct",
                "tool":       "file",
                "complexity": 2,
                "reason":     "Simple file operation -- use file() directly",
                "confidence": "high",
            })

        if any(kw in lower for kw in self._DIRECT_MEMORY):
            return RoutingDecision({
                "workflow":   "direct",
                "tool":       "memory",
                "complexity": 1,
                "reason":     "Simple memory operation -- use memory() directly",
                "confidence": "high",
            })

        if any(kw in lower for kw in self._DIRECT_GIT):
            return RoutingDecision({
                "workflow":   "direct",
                "tool":       "git",
                "complexity": 2,
                "reason":     "Simple git operation -- use git() directly",
                "confidence": "high",
            })

        if any(kw in lower for kw in self._DIRECT_NOTIFY):
            return RoutingDecision({
                "workflow":   "direct",
                "tool":       "notify",
                "complexity": 1,
                "reason":     "Simple notification -- use notify() directly",
                "confidence": "high",
            })

        # Check for code-related keywords
        if any(kw in lower for kw in self._CODE_KEYWORDS):
            # Extra check: does it mention a file?
            has_file = any(
                ext in lower for ext in [".py", ".js", ".ts", ".json", ".yaml", ".md"]
            )
            return RoutingDecision({
                "workflow":   "autocode",
                "tool":       "workflow",
                "complexity": 7 if has_file else 5,
                "reason":     "Contains code modification keywords",
                "confidence": "medium",
            })

        if any(kw in lower for kw in self._DATA_KEYWORDS):
            return RoutingDecision({
                "workflow":   "data",
                "tool":       "python",
                "complexity": 5,
                "reason":     "Contains data analysis keywords",
                "confidence": "medium",
            })

        # Default to research
        return RoutingDecision({
            "workflow":   "research",
            "tool":       "web",
            "complexity": 4,
            "reason":     "No specific routing keywords matched",
            "confidence": "low",
        })


# -- Singleton ----------------------------------------------------------------
router = TaskRouter()

