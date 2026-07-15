"""tools/workflow_ops/types/auto.py — The `auto` type handler.

Router dispatch + confidence guard. Calls core.router.router.route() to
classify the goal and dynamically select the correct workflow.

Three outcomes:
  1. Router returns workflow="direct" — the goal isn't a workflow task at
     all (e.g. "what time is it?"). Return routing info to the LLM so it
     can call the correct tool.
  2. Router returns confidence="low" — the goal is too vague. Return
     clarifying questions to the user instead of wasting 15+ minutes on a
     misunderstood task. [Bug #6] This guard fires EVEN IF clarifying_questions
     is empty — previously, low confidence with empty questions fell through
     to execution.
  3. Router returns a specific workflow type (research, data, autocode, ...)
     with non-low confidence — delegate to that type's handler via
     TYPE_DISPATCH.

[DESIGN] Why delegate to TYPE_DISPATCH[routed_type] rather than calling
_execute_workflow directly? Two reasons:
  1. The routed type's handler performs its own validation (e.g. autocode
     requires target_file). If the auto-routed call is missing required
     params, the user gets a clean validation error instead of a confusing
     crash inside run_workflow.
  2. It avoids duplicating the kwargs-assembly logic for each type. The
     routed type handler already calls _execute_workflow with the right
     kwargs.

If the routed type isn't in TYPE_DISPATCH (e.g. router returns a workflow
name we don't have a handler for), we fall back to calling _execute_workflow
directly with just goal + trace_id + resume — matching the legacy behavior
where unknown routed types were passed through to run_workflow.
"""
from __future__ import annotations

from core.tracer import tracer

from tools.workflow_ops._type_registry import register_type, TYPE_DISPATCH
from tools.workflow_ops.helpers import (
    _ensure_trace_id,
    _execute_workflow,
    _make_error,
    _validate_goal,
)


@register_type(
    "auto",
    help_text="Let the Router classify the goal and choose the workflow.",
)
def _type_auto(
    goal: str = "",
    trace_id: str = "",
    resume: bool = False,
    **kwargs,
) -> dict:
    trace_id = _ensure_trace_id(trace_id, goal)

    if not _validate_goal(goal, trace_id):
        return _make_error("goal is required", trace_id, workflow_type="auto")

    try:
        # Lazy import to prevent circular dependencies at startup
        from core.router import router
        decision = router.route(goal, trace_id=trace_id)
        actual_type = decision.workflow

        tracer.step(
            trace_id, "workflow_route",
            f"Auto-routed '{goal[:30]}' to {actual_type} (confidence: {decision.confidence})",
        )

        # Case 1: Router says this isn't a workflow at all — return routing
        # info to the LLM so it can call the correct tool.
        if actual_type == "direct":
            return {
                "status": "routed",
                "workflow": "direct",
                "tool": decision.tool,
                "reason": decision.reason,
                "trace_id": trace_id,
            }

        # Case 2: 🔴 ROUTER CONFIDENCE GUARD
        # [Bug #6] Abort on low confidence REGARDLESS of whether clarifying_questions
        # exist. Previously, low confidence with empty questions fell through to
        # execution — defeating the guard's purpose.
        if decision.confidence == "low":
            questions = decision.clarifying_questions or [
                "Please provide more details about what you want to achieve."
            ]
            questions_text = "\n".join(f"- {q}" for q in questions)
            return {
                "status": "needs_clarification",
                "reason": "The task goal is too vague or ambiguous to proceed confidently.",
                "clarifying_questions": questions,
                "message": f"To help me understand your request better, please clarify:\n{questions_text}",
                "trace_id": trace_id,
            }

        # Case 3: Routed to a specific workflow type with non-low confidence.
        # Delegate to the type handler if we have one — it'll re-validate
        # type-specific params (e.g. autocode requires target_file) and call
        # _execute_workflow with the right kwargs.
        if actual_type in TYPE_DISPATCH:
            type_handler = TYPE_DISPATCH[actual_type]["func"]
            return type_handler(
                goal=goal,
                trace_id=trace_id,
                resume=resume,
                **kwargs,
            )

        # Fallback: routed type has no dedicated handler — call
        # _execute_workflow directly with goal + trace_id + resume. Matches
        # the legacy behavior where unknown routed types were passed
        # through to run_workflow.
        return _execute_workflow(actual_type, goal, trace_id, resume)

    except Exception as e:
        tracer.error(trace_id, "workflow", f"Router failed: {e}")
        return _make_error(
            f"Failed to route workflow: {e}",
            trace_id=trace_id,
        )
