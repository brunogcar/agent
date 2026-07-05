"""
tools/workflow_tool.py — Launch LangGraph workflows (research, data, autocode).
Registered via @tool so MCP auto-discovers it.

ARCHITECTURE & SAFETY (P0-3 Hardening):
This tool acts as the primary entry point for long-running, multi-step autonomous
tasks. Because workflows like 'autocode' modify the filesystem and take git snapshots,
this module enforces strict validation and observability rules:

1. STRICT TYPE VALIDATION:
   The LLM cannot hallucinate non-existent workflows. Only explicitly allowed
   types (research, data, autocode, report, auto) are accepted. Unknown types
   fail fast with a helpful error message, saving execution tokens.

2. FAIL-FAST PARAMETER GUARDS:
   Autocode requires specific parameters depending on the mode (e.g., 'target_file'
   is always required; 'error_msg' is required for 'fix_error' mode). If these
   are missing, the tool aborts BEFORE taking git snapshots or invoking the Planner.

3. GUARANTEED OBSERVABILITY (trace_id):
   Every single return dictionary (success or error) is guaranteed to contain
   a 'trace_id'. If the MCP host does not provide one, this tool generates a
   new trace immediately. This ensures our JSONL logs can perfectly correlate
   workflow failures back to the original user request.

4. AUTO-ROUTING:
   If type='auto' (or omitted), the tool lazily imports the Router model to
   classify the goal and dynamically select the correct workflow.
"""
from __future__ import annotations

from typing import Literal

from registry import tool
from core.tracer import tracer

# ── Valid workflow types ───────────────────────────────────────────────────
# Strict allowlist prevents the LLM from hallucinating non-existent workflows
# (e.g., "coding" or "analysis") and wasting execution cycles.
VALID_WORKFLOWS: frozenset[str] = frozenset({
    "research",
    "data",
    "autocode",
    "deep_research",
    "understand",  # Codebase Knowledge Graph builder
    "auto",
})

WorkflowType = Literal["research", "data", "autocode", "deep_research", "understand", "auto"]

def _make_error(error: str, trace_id: str, **extra) -> dict:
    """
    Helper to ensure every error response includes trace_id.
    Centralizing error formatting guarantees that our JSONL logs can always
    correlate workflow failures back to the original request.
    """
    result = {"status": "error", "error": error, "trace_id": trace_id}
    result.update(extra)
    return result

@tool
def workflow(
    type: str,
    goal: str,
    # data workflow
    code: str = "",
    # autocode workflow
    target_file: str = "",
    mode: str = "improve",
    error_msg: str = "",
    feature_desc: str = "",
    # understand workflow
    project_root: str = "",
    trace_id: str = "",
    resume: bool = False,
) -> dict:
    """
    Launch a multi-step autonomous workflow.
    
    Workflows:
    - research: Gather info from web, synthesize findings.
    - data: Analyze datasets with pandas/numpy, generate reports.
    - autocode: Fix bugs, add features, refactor code (TDD + safety).
    - deep_research: Iterative multi-faceted research with ReAct loop.
    - understand: Build a Codebase Knowledge Graph via AST parsing.
    - auto: Let the Router classify the task and choose the workflow.
    """
    # === VALIDATION: Ensure trace_id is always present ===
    # If the MCP host doesn't pass a trace_id, we generate one immediately 
    # so that even early validation failures are logged correctly.
    if not trace_id:
        trace_id = tracer.new_trace("workflow", goal=goal)

    # === VALIDATION: type parameter ===
    wf_type = type.strip().lower() if type else ""

    # Special case: empty type defaults to "auto"
    if not wf_type:
        wf_type = "auto"

    if wf_type not in VALID_WORKFLOWS:
        tracer.error(trace_id, "workflow", f"Invalid workflow type: {type}")
        return _make_error(
            f"Invalid workflow type '{type}'. Valid types: {sorted(VALID_WORKFLOWS)}",
            trace_id=trace_id,
            valid_types=list(VALID_WORKFLOWS),
        )

    # === VALIDATION: goal parameter ===
    if not goal or not goal.strip():
        tracer.error(trace_id, "workflow", "Missing goal parameter")
        return _make_error(
            "goal parameter is required",
            trace_id=trace_id,
            workflow_type=wf_type,
        )

    # === VALIDATION: understand-specific parameters ===
    # Understand builds a knowledge graph for a specific project directory.
    # It requires the project_root to know where to scan and where to store artifacts.
    if wf_type == "understand":
        if not project_root or not project_root.strip():
            return _make_error(
                "project_root is required for understand workflow",
                trace_id=trace_id,
                workflow_type=wf_type,
            )

    # === VALIDATION: autocode-specific parameters ===
    # Autocode takes git snapshots and modifies the filesystem. 
    # We must fail fast if the LLM forgot to provide the target file or 
    # the specific error message/feature description required for the mode.
    if wf_type == "autocode":
        if not target_file or not target_file.strip():
            return _make_error(
                "target_file is required for autocode workflow",
                trace_id=trace_id,
                workflow_type=wf_type,
            )

        if mode == "fix_error" and not error_msg:
            return _make_error(
                "error_msg is required for mode='fix_error'",
                trace_id=trace_id,
                workflow_type=wf_type,
                mode=mode,
            )

        if mode == "add_feature" and not feature_desc:
            return _make_error(
                "feature_desc is required for mode='add_feature'",
                trace_id=trace_id,
                workflow_type=wf_type,
                mode=mode,
            )

    # === AUTO-ROUTING ===
    if wf_type == "auto":
        try:
            # Lazy import to prevent circular dependencies at startup
            from core.router import router
            decision = router.route(goal, trace_id=trace_id)
            actual_type = decision.workflow
            
            tracer.step(trace_id, "workflow_route", 
                       f"Auto-routed '{goal[:30]}' to {actual_type} (confidence: {decision.confidence})")

            # If the Router decides this isn't a workflow at all (e.g., "what time is it?"),
            # it returns "direct". We pass this back to the LLM so it can call the correct tool.
            if actual_type == "direct":
                return {
                    "status": "routed",
                    "workflow": "direct",
                    "tool": decision.tool,
                    "reason": decision.reason,
                    "trace_id": trace_id,
                }

            # 🔴 ROUTER CONFIDENCE GUARD: Prevent wasting 15+ minutes on misunderstood tasks
            # If the Router says "low" confidence, it means the goal is too vague or ambiguous.
            # We abort execution and return clarifying questions to the user instead.
            # [Bug #6] Abort on low confidence REGARDLESS of whether clarifying_questions
            # exist. Previously, low confidence with empty questions fell through to
            # execution — defeating the guard's purpose.
            if decision.confidence == "low":
                questions = decision.clarifying_questions or ["Please provide more details about what you want to achieve."]
                questions_text = "\n".join(f"- {q}" for q in questions)
                return {
                    "status": "needs_clarification",
                    "reason": "The task goal is too vague or ambiguous to proceed confidently.",
                    "clarifying_questions": questions,
                    "message": f"To help me understand your request better, please clarify:\n{questions_text}",
                    "trace_id": trace_id,
                }

            wf_type = actual_type

        except Exception as e:
            tracer.error(trace_id, "workflow", f"Router failed: {e}")
            return _make_error(
                f"Failed to route workflow: {e}",
                trace_id=trace_id,
            )

    # === EXECUTION ===
    try:
        from workflows.base import run_workflow

        kwargs = {
            "goal": goal,
            "trace_id": trace_id,
        }

        if wf_type == "data" and code:
            kwargs["code"] = code

        elif wf_type == "autocode":
            kwargs.update({
                "target_file": target_file,
                "mode": mode,
                "error_msg": error_msg,
                "feature_desc": feature_desc,
            })

        # [Bug #3] understand workflow must receive project_root — previously
        # validated above but never forwarded to run_workflow, causing it to
        # default to agent root instead of the specified project directory.
        elif wf_type == "understand":
            kwargs["project_root"] = project_root

        result = run_workflow(
            workflow_type=wf_type,
            resume=resume,
            **kwargs,
        )

        # Ensure trace_id is in result for downstream observability
        if isinstance(result, dict):
            if "trace_id" not in result:
                result["trace_id"] = trace_id
            return result
        
        # Fallback if run_workflow returns a string or non-dict
        return {"status": "success", "result": result, "trace_id": trace_id}

    except Exception as e:
        tracer.error(trace_id, "workflow", f"Workflow execution failed: {e}")
        return _make_error(
            f"Workflow execution failed: {e}",
            trace_id=trace_id,
            workflow_type=wf_type,
        )