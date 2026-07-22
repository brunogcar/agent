"""tools/workflow_ops/types/compose.py — The `compose` type handler.

Chain multiple workflows sequentially — pass outputs of one as inputs to the next.

Example:
    workflow(action="run", type="compose", steps=[
        {"type": "research", "goal": "Survey LLM agent frameworks"},
        {"type": "data", "goal": "Analyze findings", "code": "print(data)"},
    ])

Each step runs via _execute_workflow(). The result of step N is merged into
the kwargs of step N+1 as `prev_result` (the full result dict). Steps can
also explicitly reference previous step outputs via `step_results` (a list
of all prior results).

[v1.2.1] Step goals + string kwargs support `{stepN.field}` and `{prev.field}`
placeholders that resolve to fields from prior step results. See
`_resolve_step_refs` below.

If any step fails, the chain stops and returns the failure. Successful
steps' results are preserved in the `steps` field of the final result.
"""
from __future__ import annotations
import re
from typing import Any, Dict, List

from tools.workflow_ops._type_registry import register_type
from tools.workflow_ops.helpers import _ensure_trace_id, _make_error


# [v1.2.1] Regex for {stepN.field} and {prev.field} placeholders. Captures
# the prefix ("step1", "step42", or "prev") + the field name. Unresolved
# placeholders (e.g. {step5.field} when only 2 steps have run) are left
# untouched so callers see a clear signal in the goal text.
_STEP_REF_RE = re.compile(r"\{(step\d+|prev)\.(\w+)\}")


def _resolve_step_refs(text: str, step_results: List[Dict[str, Any]]) -> str:
    """Resolve `{stepN.field}` and `{prev.field}` placeholders in text.

    - `{step1.target_file}` -> `step_results[0].get("target_file", "")`
    - `{prev.result}`        -> `step_results[-1].get("result", "")`

    Unresolved placeholders (e.g. {step5.field} when only 2 steps have run,
    or a missing field) are left as-is — the original placeholder survives
    so the caller sees a clear signal in the goal text. Non-string values
    are `str()`-d. Non-string `text` inputs are returned unchanged.
    """
    if not isinstance(text, str) or not text:
        return text
    if not step_results:
        return text

    def _replace(match: "re.Match[str]") -> str:
        prefix, field = match.group(1), match.group(2)
        try:
            if prefix == "prev":
                val = step_results[-1].get(field, "")
            else:
                # "step<N>" -> 1-indexed N -> 0-indexed step_results[N-1]
                step_num = int(prefix[4:])
                if not (1 <= step_num <= len(step_results)):
                    return match.group(0)  # step doesn't exist -- leave placeholder
                val = step_results[step_num - 1].get(field, "")
        except (ValueError, IndexError, KeyError, AttributeError):
            return match.group(0)  # resolution failed -- leave placeholder

        # Empty values are left as the placeholder so callers see the
        # missing reference rather than a silent blank.
        return str(val) if val not in ("", None) else match.group(0)

    return _STEP_REF_RE.sub(_replace, text)


@register_type(
    "compose",
    help_text="Chain multiple workflows sequentially (research -> data -> report).",
)
def _type_compose(
    goal: str = "",
    trace_id: str = "",
    steps: List[Dict[str, Any]] = None,
    **kwargs,
) -> dict:
    """Run multiple workflows in sequence, passing results forward.

    Args:
        goal: Overall goal for the composed workflow (used for tracing).
        trace_id: Trace ID.
        steps: List of step dicts, each with at minimum:
            - type: workflow type ("research", "data", "autocode", etc.)
            - goal: step-specific goal
            - (optional) type-specific kwargs (code, target_file, etc.)
    """
    trace_id = _ensure_trace_id(trace_id, goal)

    if not steps:
        return _make_error(
            "steps is required for type='compose' (list of step dicts)",
            trace_id,
            workflow_type="compose",
        )

    if not isinstance(steps, list) or len(steps) == 0:
        return _make_error(
            "steps must be a non-empty list of step dicts",
            trace_id,
            workflow_type="compose",
        )

    from tools.workflow_ops.helpers import _execute_workflow
    from core.tracer import tracer

    step_results: List[Dict[str, Any]] = []

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            return _make_error(
                f"Step {i} must be a dict, got {type(step).__name__}",
                trace_id,
                workflow_type="compose",
            )

        step_type = step.get("type", "")
        step_goal = step.get("goal", "")

        if not step_type:
            return _make_error(
                f"Step {i} missing 'type'",
                trace_id,
                workflow_type="compose",
            )
        if not step_goal:
            return _make_error(
                f"Step {i} missing 'goal'",
                trace_id,
                workflow_type="compose",
            )

        # [v1.2.1] Resolve {stepN.field} + {prev.field} placeholders in the
        # step goal + all string-valued kwargs against step_results so far.
        # Step 1 (index 0) has no prior results, so resolution is a no-op for it
        # (kept for symmetry / safety). Unresolved placeholders are left as-is.
        step_goal = _resolve_step_refs(step_goal, step_results)

        # Build kwargs for this step — merge step-specific kwargs + prev_result.
        # IMPORTANT: pass a SNAPSHOT of step_results (list(...)) — not the live
        # reference. The live list is mutated by step_results.append() below,
        # which would otherwise retroactively change what step N sees as its
        # `step_results` input. The snapshot freezes the list at the moment
        # step N is invoked (i.e. results of steps 0..N-1, not including N).
        step_kwargs = {k: v for k, v in step.items() if k not in ("type", "goal")}
        # Resolve placeholders in every string-valued kwarg too (e.g. target_file,
        # error_msg, code). Non-string values (lists, ints, bools) are skipped.
        step_kwargs = {
            k: (_resolve_step_refs(v, step_results) if isinstance(v, str) else v)
            for k, v in step_kwargs.items()
        }
        if step_results:
            step_kwargs["prev_result"] = step_results[-1]
            step_kwargs["step_results"] = list(step_results)

        tracer.step(
            trace_id, "compose",
            f"Step {i+1}/{len(steps)}: {step_type} - {step_goal[:60]}",
        )

        result = _execute_workflow(step_type, step_goal, trace_id, **step_kwargs)

        step_results.append(result)

        if result.get("status") not in ("success", "completed"):
            # Step failed — stop the chain
            tracer.error(
                trace_id, "compose",
                f"Step {i+1} ({step_type}) failed: {result.get('error', 'unknown')}",
            )
            return {
                "status": "failed",
                "error": f"Step {i+1} ({step_type}) failed: {result.get('error', 'unknown')}",
                "failed_step": i + 1,
                "failed_step_type": step_type,
                "steps": step_results,
                "trace_id": trace_id,
            }

    # All steps succeeded
    tracer.step(trace_id, "compose", f"All {len(steps)} steps completed")
    return {
        "status": "success",
        "result": f"Composed workflow ({len(steps)} steps) completed successfully",
        "steps": step_results,
        "final_result": step_results[-1] if step_results else {},
        "trace_id": trace_id,
    }
