"""
core/router.py -- Router-based task router.
Classifies any free-text goal into a structured routing decision
before the workflow layer runs. The Router model is used for speed (15s timeout).

Usage:
    from core.router import router
    decision = router.route("Fix the timeout bug in tools/web.py")
    # Returns:
    # {
    #    "workflow":    "autocode",
    #    "tool":        "workflow",
    #    "complexity": 6,
    #    "reason":      "Involves editing an existing code file to fix a bug",
    #    "confidence":  "high"
    # }

    decision = router.classify_complexity("Research ChromaDB")
    # Returns: 4  (int, 1-10)
"""
from __future__ import annotations
import json
import re
from typing import Optional
from core.llm    import llm
from core.tracer   import tracer

# -- Routing decision dataclass -----------------------------------------------
class RoutingDecision:
    """Structured routing decision with fallback handling."""
    def __init__(self, raw: dict) -> None:
        self.workflow   = raw.get("workflow",     "research")
        self.tool       = raw.get("tool",         "web")
        self.complexity = int(raw.get("complexity", 5))
        self.reason     = raw.get("reason",       "")
        self.confidence = raw.get("confidence",   "medium")
        self.clarifying_questions = raw.get("clarifying_questions", [])
        self.raw        = raw

    def __repr__(self) -> str:
        return (
            f"RoutingDecision(workflow={self.workflow!r},  "
            f"tool={self.tool!r}, complexity={self.complexity},  "
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

    # P2 Optimization: Pre-compiled regex patterns for O(1) heuristic matching
    # Replaces fragile O(N*M) string loops with fast, single-pass regex searches.
    _RE_CODE = re.compile(r"\b(fix|bug|error|patch|refactor|improve|add feature|implement|edit|modify|update code)\b", re.IGNORECASE)
    _RE_DATA = re.compile(r"\b(analyse|analyze|calculate|compute|plot|chart|csv|excel|spreadsheet|statistics|pandas|numpy|dataset)\b", re.IGNORECASE)
    _RE_RESEARCH = re.compile(r"\b(what is|what are|how does|explain|research|find information|summarise|summarize|look up)\b", re.IGNORECASE)
    _RE_DIRECT_FILE = re.compile(r"\b(read file|open file|list files|list directory|write file|show file|read the file|open the file)\b", re.IGNORECASE)
    _RE_DIRECT_MEMORY = re.compile(r"\b(recall|remember|what do you know about|store this|save this to memory)\b", re.IGNORECASE)
    _RE_DIRECT_GIT = re.compile(r"\b(git status|git log|show commits|git diff|commit this|git commit)\b", re.IGNORECASE)
    _RE_DIRECT_NOTIFY = re.compile(r"\b(notify me|send notification|remind me|schedule reminder)\b", re.IGNORECASE)
    _RE_REPORT = re.compile(r"\b(create a chart|create chart|make a chart|plot a chart|draw a chart|report|visualise|create a graph|make a graph|create a map|make a map|create a dashboard|make a dashboard|create a report|make a report|bar chart|line chart|pie chart|scatter plot|heatmap)\b", re.IGNORECASE)

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
                "Rate the complexity of this task on a scale of 1-10.  "
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
                "You are a task router. Output ONLY a JSON object wrapped in <tool_call> tags.  "
                "No thinking. No explanation.\n"
                "<tool_call>\n"
                '{"workflow": "research or data or autocode",'
                '   "tool": "web or python or file or git or memory or agent or notify or report or workflow",'
                '   "complexity":5,'
                '   "reason": "one sentence",'
                '   "confidence": "high or medium or low",'
                '   "clarifying_questions": ["question1", "question2"]}\n'
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
        envelope_match = re.search(r'<tool_call>(.*?)</tool_call>', text, re.DOTALL | re.IGNORECASE)
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
        if self._RE_REPORT.search(goal):
            return RoutingDecision({
                "workflow":    "direct",
                "tool":        "report",
                "complexity": 3,
                "reason":      "Report task -- use report() directly",
                "confidence":  "high",
            })

        # Check for direct single-tool tasks first (most specific)
        if self._RE_DIRECT_FILE.search(goal):
            return RoutingDecision({
                "workflow":    "direct",
                "tool":        "file",
                "complexity": 2,
                "reason":      "Simple file operation -- use file() directly",
                "confidence":  "high",
            })

        if self._RE_DIRECT_MEMORY.search(goal):
            return RoutingDecision({
                "workflow":    "direct",
                "tool":        "memory",
                "complexity": 1,
                "reason":      "Simple memory operation -- use memory() directly",
                "confidence":  "high",
            })

        if self._RE_DIRECT_GIT.search(goal):
            return RoutingDecision({
                "workflow":    "direct",
                "tool":        "git",
                "complexity": 2,
                "reason":      "Simple git operation -- use git() directly",
                "confidence":  "high",
            })

        if self._RE_DIRECT_NOTIFY.search(goal):
            return RoutingDecision({
                "workflow":    "direct",
                "tool":        "notify",
                "complexity": 1,
                "reason":      "Simple notification -- use notify() directly",
                "confidence":  "high",
            })

        # Check for code-related keywords
        if self._RE_CODE.search(goal):
            # Extra check: does it mention a file?
            has_file = any(
                ext in lower for ext in [".py", ".js", ".ts", ".json", ".yaml", ".md"]
            )
            return RoutingDecision({
                "workflow":    "autocode",
                "tool":        "workflow",
                "complexity": 7 if has_file else 5,
                "reason":      "Contains code modification keywords",
                "confidence":  "medium",
            })

        if self._RE_DATA.search(goal):
            return RoutingDecision({
                "workflow":    "data",
                "tool":        "python",
                "complexity": 5,
                "reason":      "Contains data analysis keywords",
                "confidence":  "medium",
            })

        # Default to research
        return RoutingDecision({
            "workflow":    "research",
            "tool":        "web",
            "complexity": 4,
            "reason":      "No specific routing keywords matched",
            "confidence":  "low",
        })

# -- Singleton ----------------------------------------------------------------
router = TaskRouter()